"""Builds the prettified audit-log view for the admin endpoint.

Each event has two layers:

- `summary`: short, friendly strings ("Brazil 2-1 Germany → 3-0",
  "iPhone Safari") suitable for screenshots a non-technical friend would
  accept as an authoritative record.
- `raw`: the underlying data (full IP, full user-agent, raw JSON
  diffs, request_id, source enum, entity_id) for forensic completeness.

The page expands a row to reveal `raw`, so a screenshot of the
collapsed row is the friendly version and the expanded row is the
unimpeachable version.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fixture import Fixture
from app.models.prediction_history import (
    BonusPredictionHistory,
    MatchPredictionHistory,
    PredictionAction,
    PredictionSource,
    TeamPredictionHistory,
)
from app.services.bonus import get_questions as get_bonus_questions


# ── User-agent parsing ──────────────────────────────────────────────────────


def parse_user_agent(ua: str | None) -> str:
    """Compact friendly device summary, e.g. "iPhone Safari".

    Hand-rolled for the predictable device mix of the ~30-user friend
    group (iPhones, Androids, desktops) — avoids a UA-parser dependency.
    Unknown UAs return "Unknown". The full UA string is preserved in
    the raw layer of the audit-log response.
    """
    if not ua:
        return "Unknown"
    s = ua.lower()

    # Device family
    if "iphone" in s:
        device = "iPhone"
    elif "ipad" in s:
        device = "iPad"
    elif "android" in s:
        device = "Android"
    elif "macintosh" in s or "mac os" in s:
        device = "Mac"
    elif "windows" in s:
        device = "Windows"
    elif "linux" in s:
        device = "Linux"
    elif "cfnetwork" in s:
        # iOS apps frequently send CFNetwork UAs (e.g. the Mail app
        # opening a link). Treat as iPhone — close enough for context.
        device = "iPhone"
    else:
        device = "Unknown device"

    # Browser. Order matters: Edge/Chrome both mention "safari" so check
    # those first; Chrome contains "safari" too.
    if "edg/" in s or "edge/" in s:
        browser = "Edge"
    elif "chrome/" in s and "chromium" not in s and "edg" not in s:
        browser = "Chrome"
    elif "firefox/" in s:
        browser = "Firefox"
    elif "fxios" in s:  # Firefox on iOS
        browser = "Firefox"
    elif "crios" in s:  # Chrome on iOS
        browser = "Chrome"
    elif "safari/" in s:
        browser = "Safari"
    elif "curl/" in s or "python" in s or "httpx" in s:
        browser = "(API client)"
    else:
        browser = ""

    if device == "Unknown device" and not browser:
        return "Unknown"
    return f"{device} {browser}".strip()


# ── Diff formatters ─────────────────────────────────────────────────────────


def _score_str(v: dict | None) -> str | None:
    """Render a snapshot dict as 'H-A', or None if missing."""
    if not v:
        return None
    h, a = v.get("home_score"), v.get("away_score")
    if h is None or a is None:
        return None
    return f"{h}-{a}"


def _format_match_change(
    home_team: str,
    away_team: str,
    old: dict | None,
    new: dict | None,
    action: PredictionAction,
) -> str:
    """Score change as 'Brazil 2-1 Germany → 3-0' style strings."""
    old_s = _score_str(old)
    new_s = _score_str(new)

    if action == PredictionAction.INSERT and new_s:
        return f"{home_team} {new_s} {away_team}"
    if action == PredictionAction.DELETE and old_s:
        return f"Removed: {home_team} {old_s} {away_team}"
    if action == PredictionAction.LOCK:
        return f"Locked: {home_team} {old_s or '—'} {away_team}"
    if action == PredictionAction.UPDATE and old_s and new_s:
        return f"{home_team} {old_s} → {new_s} {away_team}"
    # Fallback when one snapshot is missing.
    return f"{home_team} {old_s or '—'} → {new_s or '—'} {away_team}"


_STAGE_LABELS = {
    "round_of_32": "Round of 32",
    "round_of_16": "Round of 16",
    "quarter_final": "Quarter-finals",
    "semi_final": "Semi-finals",
    "final": "Final",
    "winner": "Winner",
    "group": "Group stage",
}


def _format_team_change(
    team: str,
    stage: str,
    old: dict | None,
    new: dict | None,
    action: PredictionAction,
) -> str:
    """Bracket pick change. Each TeamPrediction row is a single team in a
    single stage, so an update is rare — usually inserts and deletes."""
    stage_label = _STAGE_LABELS.get(stage, stage)
    if action == PredictionAction.INSERT:
        return f"{stage_label}: added {team}"
    if action == PredictionAction.DELETE:
        return f"{stage_label}: removed {team}"
    if action == PredictionAction.UPDATE and old and new:
        old_team = old.get("team", team)
        new_team = new.get("team", team)
        if old_team != new_team:
            return f"{stage_label}: {old_team} → {new_team}"
        return f"{stage_label}: {team} (updated)"
    return f"{stage_label}: {team}"


def _format_bonus_change(
    question_label: str,
    old: dict | None,
    new: dict | None,
    action: PredictionAction,
) -> str:
    old_a = old.get("answer") if old else None
    new_a = new.get("answer") if new else None
    if action == PredictionAction.INSERT:
        return f"{question_label}: {new_a}"
    if action == PredictionAction.DELETE:
        return f"{question_label}: cleared (was {old_a})"
    if action == PredictionAction.UPDATE:
        return f"{question_label}: {old_a} → {new_a}"
    return f"{question_label}: {new_a or old_a or ''}"


# ── Entity labels (group-by handle for the page) ────────────────────────────


def _match_entity_label(home: str, away: str, group: str | None) -> str:
    g = f" (Group {group})" if group else ""
    return f"{home} v {away}{g}"


def _team_entity_label(team: str, stage: str) -> str:
    return f"Bracket — {_STAGE_LABELS.get(stage, stage)}: {team}"


def _bonus_entity_label(question_label: str) -> str:
    return f"Bonus — {question_label}"


# ── Builder ─────────────────────────────────────────────────────────────────


@dataclass
class AuditEvent:
    """One event in the user's audit timeline. The endpoint returns these
    as dicts so the frontend can render without binding to Python types."""

    id: uuid.UUID
    timestamp: datetime
    kind: str  # "match" | "team" | "bonus"
    action: str
    source: str
    entity_id: uuid.UUID | None
    entity_label: str
    change_summary: str
    client_device: str       # parsed UA summary
    client_ip: str | None
    user_agent: str | None   # full UA
    request_id: uuid.UUID | None
    performed_by_user_id: uuid.UUID | None
    old_values: dict[str, Any] | None
    new_values: dict[str, Any] | None
    # Phase derived from the snapshot (for filter toggle), or None if
    # unknown (lock rows for old data may not carry phase).
    phase: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "timestamp": self.timestamp.isoformat(),
            "kind": self.kind,
            "action": self.action,
            "source": self.source,
            "entity_id": str(self.entity_id) if self.entity_id else None,
            "entity_label": self.entity_label,
            "change_summary": self.change_summary,
            "client_device": self.client_device,
            "client_ip": self.client_ip,
            "user_agent": self.user_agent,
            "request_id": str(self.request_id) if self.request_id else None,
            "performed_by_user_id": (
                str(self.performed_by_user_id) if self.performed_by_user_id else None
            ),
            "old_values": self.old_values,
            "new_values": self.new_values,
            "phase": self.phase,
        }


def _phase_from(old: dict | None, new: dict | None) -> str | None:
    for snap in (new, old):
        if snap and "phase" in snap and snap["phase"]:
            return snap["phase"]
    return None


async def build_user_history(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> list[AuditEvent]:
    """Fetch and prettify all audit events for one user, newest first.

    Pulls from the three history tables, joins match-history to
    `fixtures` for team-name rendering, looks up bonus question labels
    from the YAML. No filtering is applied here — the page-level toggles
    (phase, show locks, group-by) all run client-side on this flat list.
    """
    # ── Match history (joined to fixtures for team names + group) ──────────
    match_q = (
        select(MatchPredictionHistory, Fixture)
        .join(Fixture, MatchPredictionHistory.fixture_id == Fixture.id)
        .where(MatchPredictionHistory.user_id == user_id)
    )
    match_rows = (await session.execute(match_q)).all()

    events: list[AuditEvent] = []

    for hist, fixture in match_rows:
        action = hist.action if isinstance(hist.action, PredictionAction) else PredictionAction(hist.action)
        events.append(
            AuditEvent(
                id=hist.id,
                timestamp=hist.created_at,
                kind="match",
                action=action.value,
                source=hist.source.value if isinstance(hist.source, PredictionSource) else str(hist.source),
                entity_id=fixture.id,
                entity_label=_match_entity_label(fixture.home_team, fixture.away_team, fixture.group),
                change_summary=_format_match_change(
                    fixture.home_team, fixture.away_team,
                    hist.old_values, hist.new_values, action,
                ),
                client_device=parse_user_agent(hist.user_agent),
                client_ip=hist.client_ip,
                user_agent=hist.user_agent,
                request_id=hist.request_id,
                performed_by_user_id=hist.performed_by_user_id,
                old_values=hist.old_values,
                new_values=hist.new_values,
                phase=_phase_from(hist.old_values, hist.new_values),
            )
        )

    # ── Team (bracket) history ─────────────────────────────────────────────
    team_q = select(TeamPredictionHistory).where(TeamPredictionHistory.user_id == user_id)
    team_rows = (await session.execute(team_q)).scalars().all()

    for hist in team_rows:
        action = hist.action if isinstance(hist.action, PredictionAction) else PredictionAction(hist.action)
        events.append(
            AuditEvent(
                id=hist.id,
                timestamp=hist.created_at,
                kind="team",
                action=action.value,
                source=hist.source.value if isinstance(hist.source, PredictionSource) else str(hist.source),
                entity_id=hist.entity_id,
                entity_label=_team_entity_label(hist.team, hist.stage),
                change_summary=_format_team_change(
                    hist.team, hist.stage, hist.old_values, hist.new_values, action,
                ),
                client_device=parse_user_agent(hist.user_agent),
                client_ip=hist.client_ip,
                user_agent=hist.user_agent,
                request_id=hist.request_id,
                performed_by_user_id=hist.performed_by_user_id,
                old_values=hist.old_values,
                new_values=hist.new_values,
                phase=_phase_from(hist.old_values, hist.new_values),
            )
        )

    # ── Bonus history (with question-label lookup) ─────────────────────────
    question_labels: dict[str, str] = {q.id: q.label for q in get_bonus_questions()}

    bonus_q = select(BonusPredictionHistory).where(BonusPredictionHistory.user_id == user_id)
    bonus_rows = (await session.execute(bonus_q)).scalars().all()

    for hist in bonus_rows:
        action = hist.action if isinstance(hist.action, PredictionAction) else PredictionAction(hist.action)
        # Fallback to the raw id if the YAML no longer carries this question.
        q_label = question_labels.get(hist.question_id, hist.question_id)
        events.append(
            AuditEvent(
                id=hist.id,
                timestamp=hist.created_at,
                kind="bonus",
                action=action.value,
                source=hist.source.value if isinstance(hist.source, PredictionSource) else str(hist.source),
                entity_id=hist.entity_id,
                entity_label=_bonus_entity_label(q_label),
                change_summary=_format_bonus_change(
                    q_label, hist.old_values, hist.new_values, action,
                ),
                client_device=parse_user_agent(hist.user_agent),
                client_ip=hist.client_ip,
                user_agent=hist.user_agent,
                request_id=hist.request_id,
                performed_by_user_id=hist.performed_by_user_id,
                old_values=hist.old_values,
                new_values=hist.new_values,
                # Phase is read from the snapshot (BonusPrediction.phase is
            # always PHASE_1, but coming from the model means the audit
            # log doesn't need to hardcode the value). Defensive fallback
            # to "phase_1" for any history rows written before the
            # BonusPrediction.phase column existed.
            phase=_phase_from(hist.old_values, hist.new_values) or "phase_1",
            )
        )

    events.sort(key=lambda e: e.timestamp, reverse=True)
    return events
