"""Push-notification triggers — the events that actually fire Web Push.

Four triggers, all driven by the 60-second scheduler tick (Phase 2's
broadcast is scheduler-driven too, so activating it returns instantly):

  send_phase1_deadline_reminders  — "predictions close soon" (24h + 2h nudges)
  send_knockout_lock_reminders    — per-KO-match "locks soon" (Phase 2)
  send_match_result_pushes        — "England 2-1 France · +15 pts"
  send_phase2_opened              — one-shot "knockouts are live" broadcast

Delivery is **at-most-once** per (user, kind, ref_id): _notify_once writes
the PushSend idempotency row and commits BEFORE sending, so a crash/commit
failure yields a missed buzz rather than a duplicate — the right trade for a
"buzz everyone" app. The scheduler runs one tick at a time, so there are no
concurrent sends.

Only users with an active push subscription are ever considered, so deviceless
users cost nothing per tick. Notification copy is content-first — iOS shows
"from Predictaa" as the source line, so the title carries the news.
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import get_lock_minutes, get_settings
from app.models._datetime import utc_now
from app.models.bonus import BonusPrediction
from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction, PredictionPhase, TeamPrediction
from app.models.push_send import PushSend
from app.models.push_subscription import PushSubscription
from app.models.score import Score
from app.models.user import User
from app.services.bonus import get_questions as get_bonus_questions
from app.services.locking import get_active_competition
from app.services.push import send_to_user
from app.services.scoring import calculate_match_points, get_outcome_counts

logger = logging.getLogger(__name__)

# PushSend.kind values — the idempotency key is keyed on these exact strings,
# so they live here as the single source of truth (renaming one resets
# idempotency and would re-notify everyone).
KIND_PHASE1_24H = "phase1_deadline_24h"
KIND_PHASE1_2H = "phase1_deadline_2h"
KIND_KO_LOCK = "ko_lock_reminder"
KIND_RESULT = "result"
KIND_PHASE2 = "phase2_opened"
KIND_DAILY_DROP = "daily_drop"

# Full Phase-1 bracket: R32(32)+R16(16)+QF(8)+SF(4)+F(2)+winner(1).
BRACKET_TOTAL_SLOTS = 63
# Knockout TeamPrediction stages (group_position picks also live in
# TeamPrediction but aren't bracket picks).
KO_STAGES = ("round_of_32", "round_of_16", "quarter_final", "semi_final", "final", "winner")

# Only consider matches finished within this window for result pushes — keeps
# the per-tick query cheap and avoids notifying on long-past results if the
# scheduler was down. Idempotency prevents dupes within the window.
_RESULT_WINDOW = timedelta(hours=6)
# Phase-1 deadline nudge buckets (hours before phase1_deadline).
_P1_EARLY_HOURS = 24.0
_P1_LAST_HOURS = 2.0
# KO per-match reminder lead: fire while the lock is within this many minutes
# (lock is at kickoff - lock_minutes, so ~lock_minutes + lead before kickoff).
_KO_REMINDER_LEAD_MIN = 15


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
async def _subscribed_user_ids(session: AsyncSession) -> set[uuid.UUID]:
    """Active users with at least one active push subscription.

    The recipient universe for every trigger — deviceless users are excluded
    so they're never evaluated or queried per tick.
    """
    rows = await session.execute(
        select(PushSubscription.user_id)
        .join(User, User.id == PushSubscription.user_id)
        .where(
            PushSubscription.active.is_(True),
            User.is_active.is_(True),
            User.is_ghost.is_(False),
        )
        .distinct()
    )
    return set(rows.scalars().all())


async def _already_sent(session: AsyncSession, kind: str, ref_id: uuid.UUID) -> set[uuid.UUID]:
    """User ids that already have a PushSend row for (kind, ref_id)."""
    rows = await session.execute(
        select(PushSend.user_id).where(PushSend.kind == kind, PushSend.ref_id == ref_id)
    )
    return set(rows.scalars().all())


async def _notify_once(
    session: AsyncSession,
    user_id: uuid.UUID,
    kind: str,
    ref_id: uuid.UUID,
    payload: dict,
    already: set[uuid.UUID],
) -> bool:
    """Record-then-send, at most once per (user, kind, ref_id).

    The PushSend row is committed BEFORE delivery, so a crash or commit failure
    leaves a recorded row and no duplicate (at-most-once: a rare missed buzz,
    never a repeat). `already` is the caller's pre-loaded set for this
    (kind, ref_id). Returns True if we recorded + attempted a send.
    """
    if user_id in already:
        return False
    session.add(PushSend(user_id=user_id, kind=kind, ref_id=ref_id))
    try:
        await session.commit()
    except IntegrityError:
        # A concurrent path already recorded this — treat as sent.
        await session.rollback()
        already.add(user_id)
        return False
    except Exception:  # noqa: BLE001
        # Couldn't record — nothing was sent yet, so a retry next tick is safe.
        await session.rollback()
        logger.exception("push: failed to record send (kind=%s user=%s)", kind, user_id)
        return False
    already.add(user_id)
    await send_to_user(session, user_id, payload)
    return True


# --------------------------------------------------------------------------- #
# 1. Phase-1 deadline reminders (24h + 2h nudges to incomplete users)
# --------------------------------------------------------------------------- #
async def _incomplete_users(session: AsyncSession) -> dict[uuid.UUID, int]:
    """Active users who haven't filled every Phase-1 prediction.

    Returns {user_id: remaining_count}. Mirrors the dashboard/roster
    completeness: filled = group match preds + KO bracket picks + non-empty
    bonus answers; total = group fixtures + 63 bracket slots + bonus questions.
    """
    total_group = (
        await session.execute(select(func.count(Fixture.id)).where(Fixture.stage == "group"))
    ).scalar_one()
    total_bonus = len(get_bonus_questions())
    overall_total = total_group + BRACKET_TOTAL_SLOTS + total_bonus

    match_counts = dict(
        (
            await session.execute(
                select(MatchPrediction.user_id, func.count(MatchPrediction.id))
                .where(MatchPrediction.phase == PredictionPhase.PHASE_1)
                .group_by(MatchPrediction.user_id)
            )
        ).all()
    )
    bracket_counts = dict(
        (
            await session.execute(
                select(TeamPrediction.user_id, func.count(TeamPrediction.id))
                .where(TeamPrediction.stage.in_(KO_STAGES))
                .where(TeamPrediction.phase == PredictionPhase.PHASE_1)
                .group_by(TeamPrediction.user_id)
            )
        ).all()
    )
    bonus_counts = dict(
        (
            await session.execute(
                select(BonusPrediction.user_id, func.count(BonusPrediction.id))
                .where(BonusPrediction.answer != "")
                .group_by(BonusPrediction.user_id)
            )
        ).all()
    )

    users = (await session.execute(select(User).where(User.is_active.is_(True)))).scalars().all()
    incomplete: dict[uuid.UUID, int] = {}
    for u in users:
        filled = match_counts.get(u.id, 0) + bracket_counts.get(u.id, 0) + bonus_counts.get(u.id, 0)
        if filled < overall_total:
            incomplete[u.id] = overall_total - filled
    return incomplete


def _deadline_phrase(remaining: timedelta) -> str:
    hrs = remaining.total_seconds() / 3600
    if hrs <= _P1_LAST_HOURS:
        return "in under 2 hours"
    return f"in ~{round(hrs)} hours"


async def send_phase1_deadline_reminders(session: AsyncSession) -> None:
    """Nudge subscribers with unfilled predictions before phase1_deadline.

    Two buckets — an early heads-up (<=24h out) and a last call (<=2h out) —
    each fired at most once per user via a distinct PushSend kind.
    """
    competition = await get_active_competition(session)
    if not competition or not competition.phase1_deadline:
        return
    remaining = competition.phase1_deadline - utc_now()
    seconds = remaining.total_seconds()
    if seconds <= 0:
        return  # deadline passed — nothing to remind about
    hrs = seconds / 3600
    if hrs <= _P1_LAST_HOURS:
        kind = KIND_PHASE1_2H
    elif hrs <= _P1_EARLY_HOURS:
        kind = KIND_PHASE1_24H
    else:
        return  # too early for either nudge

    subscribers = await _subscribed_user_ids(session)
    if not subscribers:
        return
    ref = competition.id
    already = await _already_sent(session, kind, ref)
    if subscribers <= already:
        return  # everyone with a device already nudged — skip the heavy scan

    incomplete = await _incomplete_users(session)
    phrase = _deadline_phrase(remaining)
    sent = 0
    for user_id, missing in incomplete.items():
        if user_id not in subscribers:
            continue
        plural = "s" if missing != 1 else ""
        payload = {
            "title": f"⏰ Predictions close {phrase}",
            "body": f"You've still got {missing} pick{plural} to fill before kickoff.",
            "url": "/predictions",
        }
        if await _notify_once(session, user_id, kind, ref, payload, already):
            sent += 1
    if sent:
        logger.info("push: phase1 deadline reminders (%s) sent=%d", kind, sent)


# --------------------------------------------------------------------------- #
# 2. Knockout per-match lock reminders (Phase 2)
# --------------------------------------------------------------------------- #
async def send_knockout_lock_reminders(session: AsyncSession) -> None:
    """Remind subscribers who haven't predicted a KO match that it locks soon."""
    competition = await get_active_competition(session)
    if not competition or not competition.is_phase2_active:
        return

    lock_min = get_lock_minutes()
    now = utc_now()
    # Lock time = kickoff - lock_min. Fire while lock is within the lead window
    # and the match hasn't locked yet: kickoff in [now+lock_min, now+lock_min+lead].
    window_start = now + timedelta(minutes=lock_min)
    window_end = now + timedelta(minutes=lock_min + _KO_REMINDER_LEAD_MIN)

    fixtures = (
        await session.execute(
            select(Fixture).where(
                Fixture.status == MatchStatus.SCHEDULED,
                Fixture.stage != "group",  # knockout fixtures
                Fixture.kickoff >= window_start,
                Fixture.kickoff <= window_end,
            )
        )
    ).scalars().all()
    if not fixtures:
        return

    subscribers = await _subscribed_user_ids(session)
    if not subscribers:
        return

    for fixture in fixtures:
        ref = fixture.id
        predicted = set(
            (
                await session.execute(
                    select(MatchPrediction.user_id).where(MatchPrediction.fixture_id == fixture.id)
                )
            ).scalars().all()
        )
        already = await _already_sent(session, KIND_KO_LOCK, ref)
        payload = {
            "title": "⏰ Predictions lock soon",
            "body": f"{fixture.home_team} v {fixture.away_team} kicks off shortly — get your score in.",
            "url": "/predictions",
        }
        for user_id in subscribers:
            if user_id in predicted:
                continue
            await _notify_once(session, user_id, KIND_KO_LOCK, ref, payload, already)


# --------------------------------------------------------------------------- #
# 3. Match result + points
# --------------------------------------------------------------------------- #
async def send_match_result_pushes(session: AsyncSession) -> None:
    """Notify every subscriber who predicted a just-finished match of the result + points.

    Uses the SAME inputs as the leaderboard (calculate_match_points with
    sum(counts) / counts[score.outcome]) so the displayed "+N pts" matches the
    standings exactly, including ET/penalty knockout matches.
    """
    cutoff = utc_now() - _RESULT_WINDOW
    rows = (
        await session.execute(
            select(Fixture, Score)
            .join(Score, Score.fixture_id == Fixture.id)
            .where(Fixture.status == MatchStatus.FINISHED, Score.updated_at >= cutoff)
        )
    ).all()
    if not rows:
        return

    subscribers = await _subscribed_user_ids(session)
    if not subscribers:
        return

    for fixture, score in rows:
        ref = fixture.id
        predictions = (
            await session.execute(
                select(MatchPrediction).where(MatchPrediction.fixture_id == fixture.id)
            )
        ).scalars().all()
        if not predictions:
            continue

        already = await _already_sent(session, KIND_RESULT, ref)
        pending = [
            p for p in predictions if p.user_id in subscribers and p.user_id not in already
        ]
        if not pending:
            continue

        counts = await get_outcome_counts(session, fixture.id)
        total_predictors = sum(counts.values())
        correct_predictors = counts.get(score.outcome, 0)  # ET/penalty-aware, matches leaderboard

        fh, fa = score.final_home_score, score.final_away_score
        title = f"{fixture.home_team} {fh}–{fa} {fixture.away_team}"
        if score.home_penalties is not None and score.away_penalties is not None:
            title += f" ({score.home_penalties}–{score.away_penalties} pens)"

        for prediction in pending:
            points, correct_outcome, exact = calculate_match_points(
                prediction,
                score,
                total_predictors=total_predictors,
                correct_predictors=correct_predictors,
            )
            emoji = "\U0001f3af" if exact else "✅" if correct_outcome else "❌"
            body = (
                f"You predicted {prediction.home_score}–{prediction.away_score} "
                f"— +{points} pts {emoji}"
            )
            payload = {"title": title, "body": body, "url": "/results"}
            await _notify_once(session, prediction.user_id, KIND_RESULT, ref, payload, already)


# --------------------------------------------------------------------------- #
# 4. Phase 2 opened (scheduler-driven broadcast — fires within a tick of activation)
# --------------------------------------------------------------------------- #
async def broadcast_phase2_opened(session: AsyncSession, competition: Competition) -> int:
    """Tell every subscriber the knockouts are live. Idempotent per (user, competition)."""
    ref = competition.id
    subscribers = await _subscribed_user_ids(session)
    if not subscribers:
        return 0
    already = await _already_sent(session, KIND_PHASE2, ref)
    if subscribers <= already:
        return 0
    payload = {
        "title": "Knockouts are live \U0001f3c6",
        "body": "Phase 2 is open — make your knockout picks.",
        "url": "/predictions",
    }
    sent = 0
    for user_id in subscribers:
        if await _notify_once(session, user_id, KIND_PHASE2, ref, payload, already):
            sent += 1
    if sent:
        logger.info("push: phase2-opened broadcast sent=%d", sent)
    return sent


async def send_phase2_opened(session: AsyncSession) -> None:
    """Scheduler hook: broadcast once Phase 2 is active (idempotent no-op after)."""
    competition = await get_active_competition(session)
    if not competition or not competition.is_phase2_active:
        return
    await broadcast_phase2_opened(session, competition)


# --------------------------------------------------------------------------- #
# 5. Daily Drop morning broadcast (scheduler-driven, once per local morning)
# --------------------------------------------------------------------------- #
async def send_daily_drop_notification(session: AsyncSession) -> int:
    """Build today's Drop once local time passes the configured morning hour, then
    broadcast a single "it's in" push to every subscriber.

    Idempotent two ways: ``build_daily_drop`` upserts one row per ``drop_date``,
    and the push is keyed on (user, KIND_DAILY_DROP, drop.id) — so the first tick
    after the morning hour fires it and every later tick that day is a no-op. The
    drop's own id is the perfect per-day ref (no synthetic date→uuid needed).
    """
    # Local import: daily_drop pulls in leaderboard/scoring; importing it at module
    # load would widen this module's import graph for every trigger.
    from app.services.daily_drop import build_daily_drop

    settings = get_settings()
    try:
        tz = ZoneInfo(settings.daily_drop_tz)
    except Exception:  # noqa: BLE001 — bad/absent tz data → fall back to UTC
        logger.warning("daily-drop: unknown tz %r, using UTC", settings.daily_drop_tz)
        tz = ZoneInfo("UTC")
    now_local = utc_now().astimezone(tz)
    if now_local.hour < settings.daily_drop_hour:
        return 0  # before the morning drop

    drop = await build_daily_drop(session, drop_date=now_local.date())

    subscribers = await _subscribed_user_ids(session)
    if not subscribers:
        return 0
    already = await _already_sent(session, KIND_DAILY_DROP, drop.id)
    if subscribers <= already:
        return 0
    payload = {
        "title": "The Daily Drop is in \U0001f5de️",
        "body": "Today's winners, bottlers and the roast — see where you stand.",
        "url": "/",
    }
    sent = 0
    for user_id in subscribers:
        if await _notify_once(session, user_id, KIND_DAILY_DROP, drop.id, payload, already):
            sent += 1
    if sent:
        logger.info("push: daily-drop broadcast sent=%d date=%s", sent, drop.drop_date)
    return sent
