"""Pre-launch hardening guards added in the Phase 1 lock audit.

Covers:
- the one-way phase1_deadline rule (cannot be changed once it has passed,
  which would silently reopen every Phase 1 prediction),
- AwareDatetime on the admin deadline payloads (a naive timestamp would
  shift the lock by the sender's UTC offset),
- Phase 2 activation sanity checks (bracket_deadline in the future and
  not after the first knockout kickoff),
- the batch-prediction size cap,
- bracket payload validation (stage whitelist, per-stage pick limits,
  duplicate rejection — duplicates previously surfaced as a DB 500).
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.admin import (
    Phase1DeadlineRequest,
    Phase2ActivateRequest,
    activate_phase2,
    set_phase1_deadline,
    update_phase2_deadline,
)
from app.api.predictions import batch_update_predictions
from app.dependencies import RequestContext
from app.models.competition import Competition
from app.models.user import User
from app.schemas.prediction import (
    BracketPredictionUpdate,
    MatchPredictionCreate,
)


def _admin() -> User:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.is_admin = True
    return user


def _ctx() -> RequestContext:
    return RequestContext(
        request_id=uuid.uuid4(),
        client_ip="127.0.0.1",
        user_agent="pytest",
    )


def _competition(phase1_deadline: datetime | None) -> Competition:
    competition = MagicMock(spec=Competition)
    competition.id = uuid.uuid4()
    competition.phase1_deadline = phase1_deadline
    competition.is_phase2_active = False
    return competition


def _session_returning(*scalars) -> AsyncMock:
    """Session whose successive execute() calls return the given scalars
    via scalar_one_or_none()."""
    session = AsyncMock()
    results = []
    for value in scalars:
        result = MagicMock()
        result.scalar_one_or_none.return_value = value
        results.append(result)
    session.execute.side_effect = results
    session.add = MagicMock()
    return session


class TestPhase1DeadlineOneWay:
    @pytest.mark.asyncio
    async def test_rejects_change_after_deadline_passed(self):
        passed = datetime.now(timezone.utc) - timedelta(hours=1)
        session = _session_returning(_competition(passed))

        with pytest.raises(HTTPException) as exc:
            await set_phase1_deadline(
                request=Phase1DeadlineRequest(
                    deadline=datetime.now(timezone.utc) + timedelta(days=1)
                ),
                session=session,
                _admin=_admin(),
            )
        assert exc.value.status_code == 409
        assert "already passed" in exc.value.detail

    @pytest.mark.asyncio
    async def test_allows_change_before_deadline(self):
        future = datetime.now(timezone.utc) + timedelta(hours=6)
        competition = _competition(future)
        session = _session_returning(competition)

        new_deadline = datetime.now(timezone.utc) + timedelta(hours=3)
        result = await set_phase1_deadline(
            request=Phase1DeadlineRequest(deadline=new_deadline),
            session=session,
            _admin=_admin(),
        )
        assert result["status"] == "Phase 1 deadline set"
        assert competition.phase1_deadline == new_deadline

    @pytest.mark.asyncio
    async def test_allows_setting_when_none(self):
        competition = _competition(None)
        session = _session_returning(competition)

        new_deadline = datetime.now(timezone.utc) + timedelta(days=1)
        result = await set_phase1_deadline(
            request=Phase1DeadlineRequest(deadline=new_deadline),
            session=session,
            _admin=_admin(),
        )
        assert result["status"] == "Phase 1 deadline set"

    def test_naive_deadline_rejected_at_schema(self):
        with pytest.raises(ValidationError):
            Phase1DeadlineRequest(deadline=datetime(2026, 6, 11, 18, 0, 0))

    def test_aware_deadline_accepted(self):
        request = Phase1DeadlineRequest(
            deadline=datetime(2026, 6, 11, 18, 0, 0, tzinfo=timezone.utc)
        )
        assert request.deadline.tzinfo is not None


class TestPhase2ActivationGuards:
    def test_naive_bracket_deadline_rejected_at_schema(self):
        with pytest.raises(ValidationError):
            Phase2ActivateRequest(bracket_deadline=datetime(2026, 6, 28, 12, 0, 0))

    @pytest.mark.asyncio
    async def test_past_bracket_deadline_rejected(self):
        session = _session_returning(_competition(None))

        with pytest.raises(HTTPException) as exc:
            await activate_phase2(
                request=Phase2ActivateRequest(
                    bracket_deadline=datetime.now(timezone.utc) - timedelta(hours=1)
                ),
                session=session,
                _admin=_admin(),
            )
        assert exc.value.status_code == 400
        assert "future" in exc.value.detail

    @pytest.mark.asyncio
    async def test_deadline_after_first_ko_kickoff_rejected(self):
        first_ko = datetime.now(timezone.utc) + timedelta(days=1)
        session = _session_returning(_competition(None), first_ko)

        with pytest.raises(HTTPException) as exc:
            await activate_phase2(
                request=Phase2ActivateRequest(
                    bracket_deadline=first_ko + timedelta(hours=2)
                ),
                session=session,
                _admin=_admin(),
            )
        assert exc.value.status_code == 400
        assert "first knockout" in exc.value.detail

    @pytest.mark.asyncio
    async def test_deadline_before_first_ko_kickoff_accepted(self):
        first_ko = datetime.now(timezone.utc) + timedelta(days=1)
        competition = _competition(None)
        session = _session_returning(competition, first_ko)

        result = await activate_phase2(
            request=Phase2ActivateRequest(
                bracket_deadline=first_ko - timedelta(hours=2)
            ),
            session=session,
            _admin=_admin(),
        )
        assert result["status"] == "Phase 2 activated"
        assert competition.is_phase2_active is True


class TestPhase2DeadlineUpdate:
    """The dedicated update-deadline endpoint moves the bracket deadline WITHOUT
    ever deactivating Phase 2. The deactivate→reactivate pattern it replaced
    could strand Phase 2 OFF pool-wide if the re-activate failed validation;
    these guard that a rejected update leaves is_phase2_active untouched."""

    @staticmethod
    def _active_comp() -> Competition:
        comp = _competition(None)
        comp.is_phase2_active = True
        return comp

    @pytest.mark.asyncio
    async def test_update_moves_deadline_and_stays_active(self):
        first_ko = datetime.now(timezone.utc) + timedelta(days=1)
        comp = self._active_comp()
        new_deadline = first_ko - timedelta(hours=2)
        result = await update_phase2_deadline(
            request=Phase2ActivateRequest(bracket_deadline=new_deadline),
            session=_session_returning(comp, first_ko),
            _admin=_admin(),
        )
        assert result["status"] == "Phase 2 deadline updated"
        assert comp.phase2_bracket_deadline == new_deadline
        assert comp.is_phase2_active is True  # never flipped off

    @pytest.mark.asyncio
    async def test_update_when_not_active_rejected(self):
        comp = _competition(None)  # is_phase2_active = False
        with pytest.raises(HTTPException) as exc:
            await update_phase2_deadline(
                request=Phase2ActivateRequest(
                    bracket_deadline=datetime.now(timezone.utc) + timedelta(hours=1)
                ),
                session=_session_returning(comp),
                _admin=_admin(),
            )
        assert exc.value.status_code == 400
        assert "not active" in exc.value.detail

    @pytest.mark.asyncio
    async def test_past_deadline_rejected_leaves_phase2_on(self):
        comp = self._active_comp()
        with pytest.raises(HTTPException) as exc:
            await update_phase2_deadline(
                request=Phase2ActivateRequest(
                    bracket_deadline=datetime.now(timezone.utc) - timedelta(hours=1)
                ),
                session=_session_returning(comp),
                _admin=_admin(),
            )
        assert exc.value.status_code == 400
        assert comp.is_phase2_active is True  # the key safety property

    @pytest.mark.asyncio
    async def test_deadline_after_first_ko_rejected_leaves_phase2_on(self):
        first_ko = datetime.now(timezone.utc) + timedelta(days=1)
        comp = self._active_comp()
        with pytest.raises(HTTPException) as exc:
            await update_phase2_deadline(
                request=Phase2ActivateRequest(
                    bracket_deadline=first_ko + timedelta(hours=2)
                ),
                session=_session_returning(comp, first_ko),
                _admin=_admin(),
            )
        assert exc.value.status_code == 400
        assert "first knockout" in exc.value.detail
        assert comp.is_phase2_active is True


class TestBatchSizeCap:
    @pytest.mark.asyncio
    async def test_oversized_batch_rejected(self):
        fixture_id = uuid.uuid4()
        payload = [
            MatchPredictionCreate(fixture_id=fixture_id, home_score=1, away_score=0)
            for _ in range(201)
        ]

        with pytest.raises(HTTPException) as exc:
            await batch_update_predictions(
                predictions_data=payload,
                session=AsyncMock(),
                current_user=_admin(),
                ctx=_ctx(),
            )
        assert exc.value.status_code == 413


class TestBracketPayloadValidation:
    def test_unknown_stage_rejected(self):
        with pytest.raises(ValidationError):
            BracketPredictionUpdate(
                predictions=[{"team": "Narnia", "stage": "intergalactic_final"}]
            )

    def test_duplicate_team_stage_rejected(self):
        with pytest.raises(ValidationError, match="duplicate"):
            BracketPredictionUpdate(
                predictions=[
                    {"team": "Brazil", "stage": "final"},
                    {"team": "Brazil", "stage": "final"},
                ]
            )

    def test_multiple_winner_rows_rejected(self):
        with pytest.raises(ValidationError, match="too many 'winner' picks"):
            BracketPredictionUpdate(
                predictions=[
                    {"team": "Brazil", "stage": "winner"},
                    {"team": "France", "stage": "winner"},
                    {"team": "Spain", "stage": "winner"},
                ]
            )

    def test_valid_full_bracket_accepted(self):
        payload = BracketPredictionUpdate(
            predictions=[
                {"team": "Brazil", "stage": "round_of_16"},
                {"team": "France", "stage": "round_of_16"},
                {"team": "Brazil", "stage": "winner"},
            ]
        )
        assert len(payload.predictions) == 3

    def test_empty_team_rejected(self):
        with pytest.raises(ValidationError):
            BracketPredictionUpdate(predictions=[{"team": "", "stage": "winner"}])
