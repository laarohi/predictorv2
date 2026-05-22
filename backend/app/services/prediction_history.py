"""Capture helpers for prediction-history audit rows.

Each helper appends one row to the appropriate history table within
the caller's transaction. The caller's `session.commit()` persists both
the prediction change and the history row atomically — if either fails,
both roll back.

All helpers take an optional `ctx: RequestContext | None`. Pass it for
user-triggered changes (so IP, user-agent, request_id are captured);
pass None for server-side automation like the lock scheduler.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import RequestContext
from app.models.bonus import BonusPrediction
from app.models.prediction import MatchPrediction, TeamPrediction
from app.models.prediction_history import (
    BonusPredictionHistory,
    MatchPredictionHistory,
    PredictionAction,
    PredictionSource,
    TeamPredictionHistory,
)


# ── snapshot helpers ────────────────────────────────────────────────────────

def snapshot_match(pred: MatchPrediction) -> dict[str, Any]:
    """Serialise a MatchPrediction's mutable state for history."""
    return {
        "home_score": pred.home_score,
        "away_score": pred.away_score,
        "phase": pred.phase.value if hasattr(pred.phase, "value") else str(pred.phase),
        "locked_at": pred.locked_at.isoformat() if pred.locked_at else None,
    }


def snapshot_team(pred: TeamPrediction) -> dict[str, Any]:
    """Serialise a TeamPrediction's mutable state for history."""
    return {
        "team": pred.team,
        "stage": pred.stage,
        "group_position": pred.group_position,
        "phase": pred.phase.value if hasattr(pred.phase, "value") else str(pred.phase),
        "locked_at": pred.locked_at.isoformat() if pred.locked_at else None,
    }


def snapshot_bonus(pred: BonusPrediction) -> dict[str, Any]:
    """Serialise a BonusPrediction's mutable state for history.

    `phase` is read from the model (structurally always PHASE_1 — bonus
    picks lock with phase1_deadline) so the audit log treats bonus
    events the same as match/team events with no special-case.
    """
    return {
        "question_id": pred.question_id,
        "answer": pred.answer,
        "phase": pred.phase.value if hasattr(pred.phase, "value") else str(pred.phase),
    }


# ── record helpers ──────────────────────────────────────────────────────────


def _ctx_fields(
    ctx: RequestContext | None,
    performed_by_user_id: uuid.UUID | None,
) -> dict[str, Any]:
    """Common context fields for any history row."""
    return {
        "performed_by_user_id": performed_by_user_id,
        "request_id": ctx.request_id if ctx else None,
        "client_ip": ctx.client_ip if ctx else None,
        "user_agent": ctx.user_agent if ctx else None,
    }


def record_match_prediction_change(
    session: AsyncSession,
    *,
    prediction: MatchPrediction,
    old_values: dict[str, Any] | None,
    new_values: dict[str, Any] | None,
    action: PredictionAction,
    source: PredictionSource,
    performed_by_user_id: uuid.UUID | None,
    ctx: RequestContext | None,
) -> None:
    """Append one row to match_prediction_history.

    Pass old_values=None for inserts, new_values=None for deletes/locks
    if the row was removed (the lock path keeps the row, so new_values
    will be populated).
    """
    session.add(
        MatchPredictionHistory(
            entity_id=prediction.id,
            user_id=prediction.user_id,
            fixture_id=prediction.fixture_id,
            action=action,
            source=source,
            old_values=old_values,
            new_values=new_values,
            **_ctx_fields(ctx, performed_by_user_id),
        )
    )


def record_team_prediction_change(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    team: str,
    stage: str,
    entity_id: uuid.UUID | None,
    old_values: dict[str, Any] | None,
    new_values: dict[str, Any] | None,
    action: PredictionAction,
    source: PredictionSource,
    performed_by_user_id: uuid.UUID | None,
    ctx: RequestContext | None,
) -> None:
    """Append one row to team_prediction_history.

    The bracket-rewrite path deletes rows and re-inserts new ones, so
    the caller passes user_id/team/stage explicitly rather than a row.
    """
    session.add(
        TeamPredictionHistory(
            entity_id=entity_id,
            user_id=user_id,
            team=team,
            stage=stage,
            action=action,
            source=source,
            old_values=old_values,
            new_values=new_values,
            **_ctx_fields(ctx, performed_by_user_id),
        )
    )


def record_bonus_prediction_change(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    question_id: str,
    entity_id: uuid.UUID | None,
    old_values: dict[str, Any] | None,
    new_values: dict[str, Any] | None,
    action: PredictionAction,
    source: PredictionSource,
    performed_by_user_id: uuid.UUID | None,
    ctx: RequestContext | None,
) -> None:
    """Append one row to bonus_prediction_history."""
    session.add(
        BonusPredictionHistory(
            entity_id=entity_id,
            user_id=user_id,
            question_id=question_id,
            action=action,
            source=source,
            old_values=old_values,
            new_values=new_values,
            **_ctx_fields(ctx, performed_by_user_id),
        )
    )
