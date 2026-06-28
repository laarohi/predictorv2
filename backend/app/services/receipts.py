"""Build the Phase 1 prediction receipt email for one user.

The receipt is the user's inbox-archived snapshot of what they
submitted before the tournament started — sent at the moment
`phase1_deadline` passes. Its purpose is dispute prevention:

  "I never predicted that" → "open the email I sent at lock-time,
  here's what you submitted, here's the timestamp Gmail recorded."

Renders two bodies (HTML for clients that show it, plain text for
clients that don't / for users who don't trust HTML email). Both
cover the same three sections: group-stage scores grouped by group,
Phase 1 bracket organised by round, and bonus picks.

Email HTML rules of the road (followed throughout):
- Inline styles only; <style> blocks get stripped by Outlook.
- Tables for layout; flexbox/grid are unsupported.
- Hard-coded hex colors; CSS variables don't work.
- Max width 600px; mobile clients render that natively.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.bonus import BonusPrediction
from app.models.competition import Competition
from app.models.email_send import EmailSend
from app.models.fixture import Fixture
from app.models.prediction import MatchPrediction, PredictionPhase, TeamPrediction
from app.models.user import User
from app.config import get_settings
from app.services.bonus import get_questions as get_bonus_questions
from app.services.email import EMAIL_SKIPPED, EmailSendError, send_email

logger = logging.getLogger(__name__)

DEADLINE_KIND_PHASE_1 = "phase1"


def _parse_allowlist(raw: str) -> set[str] | None:
    """Parse EMAIL_TO_ALLOWLIST into a normalised set of addresses.

    Returns None when the allowlist is blank (production "send to
    everyone" mode). Returns an empty set if the value is set but
    contains no usable entries — which means "send to nobody",
    intentionally distinguished so we can log that case loudly.
    """
    if not raw.strip():
        return None
    return {e.strip().lower() for e in raw.split(",") if e.strip()}

# Panini colours, baked in (CSS variables don't work in email).
PAPER = "#f1ebde"
PAPER_2 = "#e9e1cf"
INK = "#0e1d40"
INK_2 = "#514a3d"
INK_3 = "#8a826f"
RED = "#c8281f"
GOLD = "#d49a2e"
GREEN = "#1b6c3e"

STAGE_LABELS: dict[str, str] = {
    "round_of_32": "Round of 32",
    "round_of_16": "Round of 16",
    "quarter_final": "Quarter-finals",
    "semi_final": "Semi-finals",
    "final": "Final",
    "winner": "Winner",
}

# Ordered for the bracket section (group/winner are special-cased).
BRACKET_STAGES_IN_ORDER = ["round_of_32", "round_of_16", "quarter_final", "semi_final", "final"]


@dataclass(frozen=True, slots=True)
class Receipt:
    """Renderable email body. The endpoint hands these straight to the
    email service; nothing else interprets them."""

    subject: str
    html: str
    text: str


# ── data loaders ────────────────────────────────────────────────────────────


async def _load_group_predictions(
    session: AsyncSession, user_id: uuid.UUID
) -> list[tuple[MatchPrediction, Fixture]]:
    """Match predictions for group-stage fixtures, ordered by group.

    Filters by `fixture.stage == 'group'` rather than `phase == PHASE_1`.
    Phase classification on MatchPrediction can drift (historical bug:
    predictions made while Phase 2 was active globally got stamped
    PHASE_2 even for group fixtures). The fixture's stage is the
    structural source of truth — a group-stage match is Phase 1 by
    definition.
    """
    result = await session.execute(
        select(MatchPrediction, Fixture)
        .join(Fixture, MatchPrediction.fixture_id == Fixture.id)
        .where(MatchPrediction.user_id == user_id)
        .where(Fixture.stage == "group")
        .order_by(Fixture.group, Fixture.kickoff, Fixture.match_number)
    )
    return list(result.all())


async def _load_bracket_predictions(
    session: AsyncSession, user_id: uuid.UUID
) -> list[TeamPrediction]:
    """Phase 1 bracket picks (group winners + each knockout round)."""
    result = await session.execute(
        select(TeamPrediction)
        .where(TeamPrediction.user_id == user_id)
        .where(TeamPrediction.phase == PredictionPhase.PHASE_1)
    )
    return list(result.scalars().all())


async def _load_bonus_predictions(
    session: AsyncSession, user_id: uuid.UUID
) -> list[BonusPrediction]:
    result = await session.execute(
        select(BonusPrediction).where(BonusPrediction.user_id == user_id)
    )
    return list(result.scalars().all())


# ── public entry point ──────────────────────────────────────────────────────


async def build_phase1_receipt(session: AsyncSession, user: User) -> Receipt:
    """Build the user's Phase 1 receipt — subject + HTML + plain text.

    Safe to call for users with zero predictions; the rendered body
    just shows empty sections. The scheduler's idempotency layer
    handles "did we send this user a receipt yet?" — this builder
    doesn't dedupe.
    """
    group_rows = await _load_group_predictions(session, user.id)
    bracket_rows = await _load_bracket_predictions(session, user.id)
    bonus_rows = await _load_bonus_predictions(session, user.id)

    # Bonus question id → label, with {n}-substituted labels already
    # rendered by the bonus service.
    question_labels = {q.id: q.label for q in get_bonus_questions()}

    rendered_at = datetime.now(timezone.utc)

    subject = "Your World Cup 2026 predictions — locked in"
    html = _render_html(user, group_rows, bracket_rows, bonus_rows, question_labels, rendered_at)
    text = _render_text(user, group_rows, bracket_rows, bonus_rows, question_labels, rendered_at)

    return Receipt(subject=subject, html=html, text=text)


# ── HTML renderer ───────────────────────────────────────────────────────────


def _render_html(
    user: User,
    group_rows: list[tuple[MatchPrediction, Fixture]],
    bracket_rows: list[TeamPrediction],
    bonus_rows: list[BonusPrediction],
    question_labels: dict[str, str],
    rendered_at: datetime,
) -> str:
    groups_html = _html_group_section(group_rows)
    bracket_html = _html_bracket_section(bracket_rows)
    bonus_html = _html_bonus_section(bonus_rows, question_labels)
    summary_counts = _summary_counts(group_rows, bracket_rows, bonus_rows)
    rendered_at_str = rendered_at.strftime("%Y-%m-%d %H:%M UTC")

    return f"""\
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Your World Cup 2026 predictions — locked in</title>
</head>
<body style="margin:0; padding:0; background:{PAPER}; font-family:'Helvetica Neue',Helvetica,Arial,sans-serif; color:{INK};">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAPER};">
    <tr>
      <td align="center" style="padding:24px 12px;">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px; background:{PAPER}; border:2px solid {INK};">
          <tr>
            <td style="padding:18px 22px 14px; border-bottom:2px solid {INK}; background:{PAPER_2};">
              <div style="font-size:11px; letter-spacing:0.1em; text-transform:uppercase; color:{INK_3};">CxF Predict<span style="color:#d49a2e;">aa</span> · World Cup 2026</div>
              <div style="font-family:'Archivo Black','Helvetica Neue',Helvetica,Arial,sans-serif; font-size:24px; line-height:1.2; margin-top:4px; letter-spacing:0.01em;">Your predictions are locked in</div>
              <div style="font-size:13px; color:{INK_2}; margin-top:6px;">Hi {_esc(user.name)}, here's a record of everything you submitted before the tournament began.</div>
            </td>
          </tr>
          <tr>
            <td style="padding:16px 22px;">
              <p style="margin:0 0 14px; font-size:14px; line-height:1.5; color:{INK_2};">
                These predictions are now locked. <strong>The first match kicks off in about an hour</strong> — reply to this email immediately if anything looks wrong. Once kickoff happens, predictions are final.
              </p>
              <div style="font-size:12px; font-family:'IBM Plex Mono',Menlo,Consolas,monospace; color:{INK_3}; margin-bottom:8px;">
                {summary_counts} · sent {rendered_at_str}
              </div>
            </td>
          </tr>
          {groups_html}
          {bracket_html}
          {bonus_html}
          <tr>
            <td style="padding:14px 22px 22px; border-top:2px solid {INK}; background:{PAPER_2}; font-size:11px; color:{INK_3}; letter-spacing:0.03em;">
              You're receiving this because you registered for CxF Predictaa.
              <div style="margin-top:6px;"><a href="https://predictor.laarohi.xyz" style="color:{INK_2};">predictor.laarohi.xyz</a></div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _html_group_section(group_rows: list[tuple[MatchPrediction, Fixture]]) -> str:
    if not group_rows:
        return _html_empty_section(
            "Group-stage scores",
            "You didn't submit any group-stage score predictions.",
        )

    # Cluster by group letter.
    by_group: dict[str, list[tuple[MatchPrediction, Fixture]]] = {}
    for pred, fixture in group_rows:
        by_group.setdefault(fixture.group or "?", []).append((pred, fixture))

    cards = []
    for group, rows in sorted(by_group.items()):
        row_html = "".join(
            f"<tr>"
            f'<td style="padding:4px 0; font-size:13px; color:{INK};">{_esc(f.home_team)}</td>'
            f'<td align="center" style="padding:4px 8px; font-family:\'IBM Plex Mono\',Menlo,Consolas,monospace; font-size:13px; font-weight:600;">{p.home_score}–{p.away_score}</td>'
            f'<td align="right" style="padding:4px 0; font-size:13px; color:{INK};">{_esc(f.away_team)}</td>'
            f"</tr>"
            for p, f in rows
        )
        cards.append(
            f'<div style="border:1.5px solid {INK}; background:{PAPER}; margin-bottom:10px;">'
            f'  <div style="padding:6px 12px; background:{INK}; color:{PAPER}; font-family:\'Archivo Black\',\'Helvetica Neue\',Helvetica,Arial,sans-serif; font-size:13px; letter-spacing:0.08em;">GROUP {_esc(group)}</div>'
            f'  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:8px 14px;">{row_html}</table>'
            f'</div>'
        )

    return (
        '<tr><td style="padding:0 22px 4px;">'
        f'<div style="font-family:\'Archivo Black\',\'Helvetica Neue\',Helvetica,Arial,sans-serif; font-size:15px; letter-spacing:0.02em; margin:10px 0 10px;">GROUP-STAGE SCORES</div>'
        f'{"".join(cards)}'
        '</td></tr>'
    )


def _html_bracket_section(bracket_rows: list[TeamPrediction]) -> str:
    if not bracket_rows:
        return _html_empty_section(
            "Bracket",
            "You didn't submit any bracket predictions.",
        )

    by_stage: dict[str, list[str]] = {}
    winner: str | None = None
    for pred in bracket_rows:
        if pred.stage == "winner":
            winner = pred.team
        else:
            by_stage.setdefault(pred.stage, []).append(pred.team)

    rows_html = []
    for stage_key in BRACKET_STAGES_IN_ORDER:
        teams = by_stage.get(stage_key, [])
        if not teams:
            continue
        teams_str = ", ".join(sorted(_esc(t) for t in teams))
        rows_html.append(
            f'<tr>'
            f'<td style="padding:5px 0; width:140px; font-size:11px; font-family:\'IBM Plex Mono\',Menlo,Consolas,monospace; color:{INK_3}; letter-spacing:0.06em; text-transform:uppercase; vertical-align:top;">{STAGE_LABELS[stage_key]}</td>'
            f'<td style="padding:5px 0; font-size:13px; color:{INK}; line-height:1.5;">{teams_str}</td>'
            f'</tr>'
        )

    if winner:
        rows_html.append(
            f'<tr>'
            f'<td style="padding:8px 0 5px; width:140px; font-size:11px; font-family:\'IBM Plex Mono\',Menlo,Consolas,monospace; color:{GOLD}; letter-spacing:0.06em; text-transform:uppercase; vertical-align:top; border-top:1.5px solid {INK}; font-weight:700;">Winner</td>'
            f'<td style="padding:8px 0 5px; font-size:15px; color:{INK}; line-height:1.4; border-top:1.5px solid {INK}; font-weight:700;">{_esc(winner)}</td>'
            f'</tr>'
        )

    return (
        '<tr><td style="padding:0 22px 4px;">'
        f'<div style="font-family:\'Archivo Black\',\'Helvetica Neue\',Helvetica,Arial,sans-serif; font-size:15px; letter-spacing:0.02em; margin:14px 0 10px;">BRACKET</div>'
        f'<div style="border:1.5px solid {INK}; background:{PAPER}; padding:10px 14px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{"".join(rows_html)}</table>'
        f'</div>'
        '</td></tr>'
    )


def _html_bonus_section(
    bonus_rows: list[BonusPrediction], question_labels: dict[str, str]
) -> str:
    if not bonus_rows:
        return _html_empty_section(
            "Bonus picks",
            "You didn't submit any bonus picks.",
        )

    row_html = "".join(
        f'<tr>'
        f'<td style="padding:5px 0; font-size:12px; color:{INK_2}; vertical-align:top; line-height:1.4;">{_esc(question_labels.get(p.question_id, p.question_id))}</td>'
        f'<td style="padding:5px 0 5px 12px; font-size:13px; color:{INK}; font-weight:600; vertical-align:top; text-align:right;">{_esc(p.answer)}</td>'
        f'</tr>'
        for p in sorted(bonus_rows, key=lambda b: b.question_id)
    )

    return (
        '<tr><td style="padding:0 22px 4px;">'
        f'<div style="font-family:\'Archivo Black\',\'Helvetica Neue\',Helvetica,Arial,sans-serif; font-size:15px; letter-spacing:0.02em; margin:14px 0 10px;">BONUS PICKS</div>'
        f'<div style="border:1.5px solid {INK}; background:{PAPER}; padding:10px 14px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{row_html}</table>'
        f'</div>'
        '</td></tr>'
    )


def _html_empty_section(title: str, message: str) -> str:
    return (
        '<tr><td style="padding:0 22px 4px;">'
        f'<div style="font-family:\'Archivo Black\',\'Helvetica Neue\',Helvetica,Arial,sans-serif; font-size:15px; letter-spacing:0.02em; margin:14px 0 6px;">{_esc(title.upper())}</div>'
        f'<div style="border:1.5px dashed {INK_3}; padding:10px 14px; font-size:12px; color:{INK_3};">{_esc(message)}</div>'
        '</td></tr>'
    )


# ── plain-text renderer ─────────────────────────────────────────────────────


def _render_text(
    user: User,
    group_rows: list[tuple[MatchPrediction, Fixture]],
    bracket_rows: list[TeamPrediction],
    bonus_rows: list[BonusPrediction],
    question_labels: dict[str, str],
    rendered_at: datetime,
) -> str:
    lines: list[str] = []
    lines.append("CXF PREDICTAA · WORLD CUP 2026")
    lines.append("=" * 40)
    lines.append("")
    lines.append(f"Hi {user.name},")
    lines.append("")
    lines.append("These predictions are now locked. Here's a record of everything")
    lines.append("you submitted before the tournament.")
    lines.append("")
    lines.append("The first match kicks off in about an hour. REPLY to this email")
    lines.append("immediately if anything looks wrong. Once kickoff happens,")
    lines.append("predictions are final.")
    lines.append("")
    lines.append(f"{_summary_counts(group_rows, bracket_rows, bonus_rows)}")
    lines.append(f"Sent: {rendered_at.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("")
    lines.append("-" * 40)
    lines.append("GROUP-STAGE SCORES")
    lines.append("-" * 40)

    if not group_rows:
        lines.append("(none submitted)")
    else:
        by_group: dict[str, list[tuple[MatchPrediction, Fixture]]] = {}
        for pred, fixture in group_rows:
            by_group.setdefault(fixture.group or "?", []).append((pred, fixture))
        for group, rows in sorted(by_group.items()):
            lines.append("")
            lines.append(f"Group {group}")
            for pred, fixture in rows:
                lines.append(
                    f"  {fixture.home_team} {pred.home_score}-{pred.away_score} {fixture.away_team}"
                )

    lines.append("")
    lines.append("-" * 40)
    lines.append("BRACKET")
    lines.append("-" * 40)

    if not bracket_rows:
        lines.append("(none submitted)")
    else:
        by_stage: dict[str, list[str]] = {}
        winner: str | None = None
        for pred in bracket_rows:
            if pred.stage == "winner":
                winner = pred.team
            else:
                by_stage.setdefault(pred.stage, []).append(pred.team)
        for stage_key in BRACKET_STAGES_IN_ORDER:
            teams = by_stage.get(stage_key, [])
            if teams:
                lines.append(f"  {STAGE_LABELS[stage_key]}: {', '.join(sorted(teams))}")
        if winner:
            lines.append(f"  WINNER: {winner}")

    lines.append("")
    lines.append("-" * 40)
    lines.append("BONUS PICKS")
    lines.append("-" * 40)

    if not bonus_rows:
        lines.append("(none submitted)")
    else:
        for pred in sorted(bonus_rows, key=lambda b: b.question_id):
            label = question_labels.get(pred.question_id, pred.question_id)
            lines.append(f"  {label}")
            lines.append(f"    → {pred.answer}")

    lines.append("")
    lines.append("-" * 40)
    lines.append("predictor.laarohi.xyz")
    lines.append("")
    return "\n".join(lines)


# ── helpers ─────────────────────────────────────────────────────────────────


def _summary_counts(
    group_rows: list, bracket_rows: list, bonus_rows: list
) -> str:
    return (
        f"{len(group_rows)} group · "
        f"{len(bracket_rows)} bracket · "
        f"{len(bonus_rows)} bonus"
    )


def _esc(s: str | None) -> str:
    """Minimal HTML escape for user-supplied strings (team names, answers)."""
    if s is None:
        return ""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ── batch send ─────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class BatchSendResult:
    """Counts from one batch invocation. Useful for scheduler logging."""

    sent: int = 0
    skipped_already_sent: int = 0
    skipped_no_predictions: int = 0
    skipped_no_api_key: int = 0
    skipped_not_in_allowlist: int = 0
    failed: int = 0


async def send_phase1_receipts(
    session: AsyncSession, competition: Competition
) -> BatchSendResult:
    """Send Phase 1 receipts to every active user with at least one
    prediction in this competition, skipping anyone already recorded
    in `email_sends` for (this user, this competition, "phase1").

    Designed to be called repeatedly — the idempotency table makes
    duplicate invocations safe. Transient send failures (5xx, network)
    don't write a row, so the next invocation retries them.

    Per-user commits: each successful send commits its own
    idempotency row before moving on. That way a crash mid-batch
    preserves the "user N was already sent" state and the next tick
    picks up from user N+1.
    """
    # All active users — ordered by id for deterministic iteration order.
    # Ghosts have unroutable placeholder emails; never send to them.
    users_result = await session.execute(
        select(User)
        .where(User.is_active == True, User.is_ghost == False)  # noqa: E712
        .order_by(User.id)
    )
    users = list(users_result.scalars().all())

    # Pre-load idempotency rows for this competition+kind in one query
    # so we don't do an N+1 SELECT inside the loop.
    sent_result = await session.execute(
        select(EmailSend.user_id)
        .where(EmailSend.competition_id == competition.id)
        .where(EmailSend.deadline_kind == DEADLINE_KIND_PHASE_1)
    )
    already_sent_user_ids = {row for row in sent_result.scalars().all()}

    allowlist = _parse_allowlist(get_settings().email_to_allowlist)
    if allowlist is not None:
        logger.warning(
            "send_phase1_receipts: EMAIL_TO_ALLOWLIST is active — sends "
            "restricted to %d address(es)",
            len(allowlist),
        )

    counts = {
        "sent": 0,
        "skipped_already_sent": 0,
        "skipped_no_predictions": 0,
        "skipped_no_api_key": 0,
        "skipped_not_in_allowlist": 0,
        "failed": 0,
    }

    for user in users:
        if user.id in already_sent_user_ids:
            counts["skipped_already_sent"] += 1
            continue

        # Allowlist gate (live-fire test safety). Checked BEFORE building
        # the receipt to avoid burning a DB query per skipped user.
        if allowlist is not None and user.email.lower() not in allowlist:
            counts["skipped_not_in_allowlist"] += 1
            continue

        receipt = await build_phase1_receipt(session, user)
        # Skip users with no predictions — "you didn't submit anything"
        # emails feel passive-aggressive in a friend-group context.
        # The summary line is the cheapest way to detect this.
        if "0 group · 0 bracket · 0 bonus" in receipt.text:
            counts["skipped_no_predictions"] += 1
            continue

        try:
            result = await send_email(
                to=user.email,
                subject=receipt.subject,
                html=receipt.html,
                text=receipt.text,
            )
        except EmailSendError as e:
            # Permanent failure (4xx) or retries exhausted. Log loud
            # and move on — no idempotency row written, so next tick
            # retries (which for permanent failures means more loud
            # logs until admin fixes the root cause).
            logger.error(
                "send_phase1_receipts failed for user_id=%s email=%s: %s",
                user.id, user.email, e,
            )
            counts["failed"] += 1
            continue

        if result.message_id == EMAIL_SKIPPED:
            # API key blank — abort the whole batch. Sending to one
            # user but not others would be inconsistent, and there's
            # nothing for the scheduler to recover from later (the
            # next tick will hit the same blank key).
            counts["skipped_no_api_key"] += 1
            logger.warning("send_phase1_receipts: RESEND_API_KEY blank, aborting batch")
            break

        # Successful send → write idempotency row, commit per-user.
        session.add(
            EmailSend(
                user_id=user.id,
                competition_id=competition.id,
                deadline_kind=DEADLINE_KIND_PHASE_1,
                resend_message_id=result.message_id,
            )
        )
        await session.commit()
        counts["sent"] += 1

    return BatchSendResult(**counts)


# ── Phase 2 knockout-bracket receipt ─────────────────────────────────────────
#
# Sent when `phase2_bracket_deadline` passes — the inbox-archived snapshot of
# each player's LOCKED knockout bracket (who advances from R16 → Winner). Same
# dispute-prevention purpose as the Phase 1 receipt. Bracket only: KO match
# *scores* lock per-match at each kickoff, not at this single deadline.

DEADLINE_KIND_PHASE_2_BRACKET = "phase2_bracket"


async def _load_phase2_bracket_predictions(
    session: AsyncSession, user_id: uuid.UUID
) -> list[TeamPrediction]:
    """The user's Phase 2 (knockout re-pick) bracket rows."""
    result = await session.execute(
        select(TeamPrediction)
        .where(TeamPrediction.user_id == user_id)
        .where(TeamPrediction.phase == PredictionPhase.PHASE_2)
    )
    return list(result.scalars().all())


async def build_phase2_bracket_receipt(
    session: AsyncSession, user: User
) -> tuple[Receipt, bool]:
    """Build the user's Phase 2 knockout-bracket receipt.

    Returns ``(receipt, has_bracket)``. ``has_bracket`` is False only when the
    user has NEITHER a Phase 2 bracket NOR a Phase 1 bracket to carry over —
    the batch sender skips those (an empty "you predicted nothing" email is
    noise in a friend group).

    Mirrors the read-time scoring fallback EXACTLY: if the user re-picked (>=1
    Phase 2 row) we show that; otherwise their Phase 1 bracket carries over and
    is what actually gets scored, so the receipt shows that bracket with a clear
    note. Either way the email reflects the truth of what's locked.
    """
    phase2_rows = await _load_phase2_bracket_predictions(session, user.id)
    if phase2_rows:
        bracket_rows, carried_over = phase2_rows, False
    else:
        bracket_rows = await _load_bracket_predictions(session, user.id)
        carried_over = True

    has_bracket = len(bracket_rows) > 0
    rendered_at = datetime.now(timezone.utc)
    subject = "Your World Cup 2026 knockout bracket — locked in"
    html = _render_phase2_html(user, bracket_rows, carried_over, rendered_at)
    text = _render_phase2_text(user, bracket_rows, carried_over, rendered_at)
    return Receipt(subject=subject, html=html, text=text), has_bracket


def _phase2_note(carried_over: bool) -> str:
    if carried_over:
        return (
            "You didn't update your bracket after the group stage, so your "
            "original Phase 1 bracket carries over — this is what will be scored."
        )
    return "This is your updated knockout bracket, re-picked against the real Round of 32."


def _render_phase2_html(
    user: User,
    bracket_rows: list[TeamPrediction],
    carried_over: bool,
    rendered_at: datetime,
) -> str:
    bracket_html = _html_bracket_section(bracket_rows)
    rendered_at_str = rendered_at.strftime("%Y-%m-%d %H:%M UTC")
    note = _phase2_note(carried_over)

    return f"""\
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Your World Cup 2026 knockout bracket — locked in</title>
</head>
<body style="margin:0; padding:0; background:{PAPER}; font-family:'Helvetica Neue',Helvetica,Arial,sans-serif; color:{INK};">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAPER};">
    <tr>
      <td align="center" style="padding:24px 12px;">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px; background:{PAPER}; border:2px solid {INK};">
          <tr>
            <td style="padding:18px 22px 14px; border-bottom:2px solid {INK}; background:{PAPER_2};">
              <div style="font-size:11px; letter-spacing:0.1em; text-transform:uppercase; color:{INK_3};">CxF Predict<span style="color:#d49a2e;">aa</span> · World Cup 2026 · Phase II</div>
              <div style="font-family:'Archivo Black','Helvetica Neue',Helvetica,Arial,sans-serif; font-size:24px; line-height:1.2; margin-top:4px; letter-spacing:0.01em;">Your knockout bracket is locked in</div>
              <div style="font-size:13px; color:{INK_2}; margin-top:6px;">Hi {_esc(user.name)}, here's a record of the knockout bracket you have locked for the rest of the tournament.</div>
            </td>
          </tr>
          <tr>
            <td style="padding:16px 22px;">
              <p style="margin:0 0 14px; font-size:14px; line-height:1.5; color:{INK_2};">
                {note} <strong>The bracket deadline has passed</strong>, so these advancement picks are final — reply to this email immediately if anything looks wrong. (Knockout match <em>scores</em> are separate and lock per match, 15 minutes before each kickoff.)
              </p>
              <div style="font-size:12px; font-family:'IBM Plex Mono',Menlo,Consolas,monospace; color:{INK_3}; margin-bottom:8px;">
                {len(bracket_rows)} bracket pick{"s" if len(bracket_rows) != 1 else ""} · sent {rendered_at_str}
              </div>
            </td>
          </tr>
          {bracket_html}
          <tr>
            <td style="padding:14px 22px 22px; border-top:2px solid {INK}; background:{PAPER_2}; font-size:11px; color:{INK_3}; letter-spacing:0.03em;">
              You're receiving this because you registered for CxF Predictaa.
              <div style="margin-top:6px;"><a href="https://predictor.laarohi.xyz" style="color:{INK_2};">predictor.laarohi.xyz</a></div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _render_phase2_text(
    user: User,
    bracket_rows: list[TeamPrediction],
    carried_over: bool,
    rendered_at: datetime,
) -> str:
    rendered_at_str = rendered_at.strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "CxF PREDICTAA — WORLD CUP 2026 — PHASE II",
        "Your knockout bracket is locked in",
        "",
        f"Hi {user.name},",
        "",
        _phase2_note(carried_over),
        "The bracket deadline has passed, so these advancement picks are final.",
        "Reply to this email immediately if anything looks wrong. (Knockout",
        "match scores are separate and lock per match, 15 min before kickoff.)",
        "",
        f"{len(bracket_rows)} bracket pick{'s' if len(bracket_rows) != 1 else ''} · sent {rendered_at_str}",
        "",
        "-" * 40,
        "KNOCKOUT BRACKET",
        "-" * 40,
    ]
    if not bracket_rows:
        lines.append("(none submitted)")
    else:
        by_stage: dict[str, list[str]] = {}
        winner: str | None = None
        for pred in bracket_rows:
            if pred.stage == "winner":
                winner = pred.team
            else:
                by_stage.setdefault(pred.stage, []).append(pred.team)
        for stage_key in BRACKET_STAGES_IN_ORDER:
            teams = by_stage.get(stage_key, [])
            if teams:
                lines.append(f"  {STAGE_LABELS[stage_key]}: {', '.join(sorted(teams))}")
        if winner:
            lines.append(f"  WINNER: {winner}")

    lines += ["", "-" * 40, "predictor.laarohi.xyz", ""]
    return "\n".join(lines)


async def send_phase2_bracket_receipts(
    session: AsyncSession, competition: Competition
) -> BatchSendResult:
    """Send the Phase 2 knockout-bracket receipt to every active user who has a
    bracket (re-picked OR carried-over Phase 1), idempotent via `email_sends`
    for (user, competition, "phase2_bracket").

    Same structure as send_phase1_receipts: per-user commit of the idempotency
    row, transient failures left un-committed for the next tick to retry.
    """
    users_result = await session.execute(
        select(User)
        .where(User.is_active == True, User.is_ghost == False)  # noqa: E712
        .order_by(User.id)
    )
    users = list(users_result.scalars().all())

    sent_result = await session.execute(
        select(EmailSend.user_id)
        .where(EmailSend.competition_id == competition.id)
        .where(EmailSend.deadline_kind == DEADLINE_KIND_PHASE_2_BRACKET)
    )
    already_sent_user_ids = {row for row in sent_result.scalars().all()}

    allowlist = _parse_allowlist(get_settings().email_to_allowlist)
    if allowlist is not None:
        logger.warning(
            "send_phase2_bracket_receipts: EMAIL_TO_ALLOWLIST is active — sends "
            "restricted to %d address(es)",
            len(allowlist),
        )

    counts = {
        "sent": 0,
        "skipped_already_sent": 0,
        "skipped_no_predictions": 0,
        "skipped_no_api_key": 0,
        "skipped_not_in_allowlist": 0,
        "failed": 0,
    }

    for user in users:
        if user.id in already_sent_user_ids:
            counts["skipped_already_sent"] += 1
            continue

        if allowlist is not None and user.email.lower() not in allowlist:
            counts["skipped_not_in_allowlist"] += 1
            continue

        receipt, has_bracket = await build_phase2_bracket_receipt(session, user)
        if not has_bracket:
            counts["skipped_no_predictions"] += 1
            continue

        try:
            result = await send_email(
                to=user.email,
                subject=receipt.subject,
                html=receipt.html,
                text=receipt.text,
            )
        except EmailSendError as e:
            logger.error(
                "send_phase2_bracket_receipts failed for user_id=%s email=%s: %s",
                user.id, user.email, e,
            )
            counts["failed"] += 1
            continue

        if result.message_id == EMAIL_SKIPPED:
            counts["skipped_no_api_key"] += 1
            logger.warning("send_phase2_bracket_receipts: RESEND_API_KEY blank, aborting batch")
            break

        session.add(
            EmailSend(
                user_id=user.id,
                competition_id=competition.id,
                deadline_kind=DEADLINE_KIND_PHASE_2_BRACKET,
                resend_message_id=result.message_id,
            )
        )
        await session.commit()
        counts["sent"] += 1

    return BatchSendResult(**counts)
