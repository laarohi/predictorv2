"""Guards in /api/predictions that enforce the phase-lock model.

These tests exist because the original implementation only checked the
per-fixture T-lock window for match-prediction edits and didn't check
any lock for bracket rewrites — which meant a user could edit Phase 1
group scores after `competition.phase1_deadline` (in the gap until the
match's own T-lock fired), and could rewrite their entire Phase 2
bracket after `phase2_bracket_deadline`. The endpoint guards added
here close those gaps.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.predictions import (
    batch_update_predictions,
    update_bracket_predictions,
    update_match_prediction,
)
from app.dependencies import RequestContext
from app.models.competition import Competition
from app.models.fixture import Fixture
from app.models.prediction import MatchPrediction, PredictionPhase
from app.models.user import User
from app.schemas.prediction import (
    BracketPredictionUpdate,
    MatchPredictionCreate,
    MatchPredictionUpdate,
)


def _ctx() -> RequestContext:
    """Synthetic request context for tests."""
    return RequestContext(
        request_id=uuid.uuid4(),
        client_ip="127.0.0.1",
        user_agent="pytest",
    )


def _user() -> User:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    return user


def _group_fixture(kickoff_in_hours: float = 24) -> Fixture:
    fixture = MagicMock(spec=Fixture)
    fixture.id = uuid.uuid4()
    fixture.stage = "group"
    fixture.group = "A"
    fixture.home_team = "Brazil"
    fixture.away_team = "Germany"
    fixture.kickoff = datetime.now(timezone.utc) + timedelta(hours=kickoff_in_hours)
    fixture.is_locked.return_value = False
    return fixture


def _knockout_fixture(kickoff_in_hours: float = 24) -> Fixture:
    fixture = MagicMock(spec=Fixture)
    fixture.id = uuid.uuid4()
    fixture.stage = "round_of_16"
    fixture.group = None
    fixture.home_team = "Brazil"
    fixture.away_team = "Germany"
    fixture.kickoff = datetime.now(timezone.utc) + timedelta(hours=kickoff_in_hours)
    fixture.is_locked.return_value = False
    return fixture


def _session_with_fixture(fixture: Fixture | None) -> AsyncMock:
    """Session whose `execute().scalar_one_or_none()` returns `fixture`,
    and whose subsequent calls (for fetching the existing prediction)
    return None — i.e. this is a first-time prediction insert path."""
    session = AsyncMock()
    fixture_result = MagicMock()
    fixture_result.scalar_one_or_none.return_value = fixture

    prediction_result = MagicMock()
    prediction_result.scalar_one_or_none.return_value = None

    # First execute returns the fixture; subsequent ones return no prediction.
    session.execute.side_effect = [fixture_result, prediction_result, prediction_result]
    # session.add is sync on the real SQLAlchemy session — AsyncMock would
    # make it return an unawaited coroutine and emit a RuntimeWarning.
    session.add = MagicMock()
    return session


class TestUpdateMatchPredictionGuards:
    """update_match_prediction must respect both phase1_deadline AND per-fixture lock."""

    @pytest.mark.asyncio
    @patch("app.api.predictions.is_phase1_locked", new_callable=AsyncMock)
    async def test_group_fixture_blocked_when_phase1_locked(self, mock_phase1):
        mock_phase1.return_value = True
        fixture = _group_fixture()
        session = _session_with_fixture(fixture)

        with pytest.raises(HTTPException) as exc:
            await update_match_prediction(
                fixture_id=fixture.id,
                prediction_data=MatchPredictionUpdate(home_score=2, away_score=1),
                session=session,
                current_user=_user(),
                ctx=_ctx(),
            )
        assert exc.value.status_code == 403
        assert "phase 1" in exc.value.detail.lower()

    @pytest.mark.asyncio
    @patch("app.api.predictions.is_phase1_locked", new_callable=AsyncMock)
    async def test_knockout_fixture_ignores_phase1_lock(self, mock_phase1):
        """Phase 2 knockout matches must NOT be blocked by phase1_deadline —
        only their own per-fixture lock matters."""
        mock_phase1.return_value = True
        fixture = _knockout_fixture(kickoff_in_hours=24)
        session = _session_with_fixture(fixture)

        # get_current_phase needs to return something; also is_phase1_locked is
        # already mocked to True but the code path won't consult it for knockout.
        with patch("app.api.predictions.get_current_phase", new_callable=AsyncMock) as gcp:
            gcp.return_value = PredictionPhase.PHASE_2
            result = await update_match_prediction(
                fixture_id=fixture.id,
                prediction_data=MatchPredictionUpdate(home_score=2, away_score=1),
                session=session,
                current_user=_user(),
                ctx=_ctx(),
            )
        assert result.home_score == 2
        assert result.away_score == 1

    @pytest.mark.asyncio
    @patch("app.api.predictions.is_phase1_locked", new_callable=AsyncMock)
    async def test_per_fixture_lock_still_applies(self, mock_phase1):
        """If Phase 1 isn't locked but the per-fixture T-lock has fired, still deny."""
        mock_phase1.return_value = False
        fixture = _knockout_fixture()
        fixture.is_locked.return_value = True  # within the per-fixture lock window
        fixture.kickoff = datetime.now(timezone.utc) + timedelta(minutes=2)
        session = _session_with_fixture(fixture)

        with patch("app.api.predictions.check_fixture_locked", return_value=True):
            with pytest.raises(HTTPException) as exc:
                await update_match_prediction(
                    fixture_id=fixture.id,
                    prediction_data=MatchPredictionUpdate(home_score=2, away_score=1),
                    session=session,
                    current_user=_user(),
                    ctx=_ctx(),
                )
        assert exc.value.status_code == 403
        assert "locked for this match" in exc.value.detail.lower()


class TestPredictionPhaseDerivation:
    """Regression: match-prediction phase must derive from fixture.stage,
    NOT from the global get_current_phase. Otherwise a group-stage
    prediction inserted while Phase 2 is globally active gets tagged
    PHASE_2 — and then disappears from any view filtered by
    'phase == PHASE_1' (audit log, receipt email)."""

    @pytest.mark.asyncio
    @patch("app.api.predictions.is_phase1_locked", new_callable=AsyncMock)
    @patch("app.api.predictions.get_current_phase", new_callable=AsyncMock)
    async def test_group_fixture_insert_tags_phase_1_even_if_global_is_phase_2(
        self, mock_phase, mock_phase1_locked
    ):
        """The bug scenario: Phase 2 is globally active, user saves a
        group prediction — must still be tagged PHASE_1 (group fixtures
        are structurally Phase 1, regardless of global state)."""
        mock_phase.return_value = PredictionPhase.PHASE_2  # global says PHASE_2…
        mock_phase1_locked.return_value = False
        fixture = _group_fixture()
        session = _session_with_fixture(fixture)
        session.refresh = AsyncMock()

        # Capture what gets passed to session.add to verify the phase tag.
        added_predictions: list[MatchPrediction] = []
        original_add = session.add

        def capture_add(obj):
            if isinstance(obj, MatchPrediction):
                added_predictions.append(obj)
            original_add(obj)

        session.add = capture_add

        await update_match_prediction(
            fixture_id=fixture.id,
            prediction_data=MatchPredictionUpdate(home_score=2, away_score=1),
            session=session,
            current_user=_user(),
            ctx=_ctx(),
        )

        # The newly-inserted prediction must carry PHASE_1 because the
        # fixture is a group fixture — the global PHASE_2 value must NOT
        # leak into the row.
        assert len(added_predictions) == 1
        assert added_predictions[0].phase == PredictionPhase.PHASE_1


class TestBatchUpdatePredictionsGuards:
    """Batch endpoint silently skips locked fixtures (keeps the bulk-save UX
    of partial success), but the new Phase 1 check must also cause skipping."""

    @pytest.mark.asyncio
    @patch("app.api.predictions.is_phase1_locked", new_callable=AsyncMock)
    @patch("app.api.predictions.get_current_phase", new_callable=AsyncMock)
    async def test_group_fixtures_skipped_when_phase1_locked(self, mock_phase, mock_phase1):
        mock_phase1.return_value = True
        mock_phase.return_value = PredictionPhase.PHASE_2

        group_fix = _group_fixture()
        knockout_fix = _knockout_fixture()

        # Two execute() calls per fixture: one to load the fixture, one to look
        # up the existing prediction. The group fixture is rejected before the
        # prediction lookup, so it only burns one call.
        session = AsyncMock()
        group_lookup = MagicMock()
        group_lookup.scalar_one_or_none.return_value = group_fix
        knockout_lookup = MagicMock()
        knockout_lookup.scalar_one_or_none.return_value = knockout_fix
        existing_pred = MagicMock()
        existing_pred.scalar_one_or_none.return_value = None
        session.execute.side_effect = [group_lookup, knockout_lookup, existing_pred]

        # refresh() is async; add() is sync on the real session.
        session.refresh = AsyncMock()
        session.add = MagicMock()

        results = await batch_update_predictions(
            predictions_data=[
                MatchPredictionCreate(fixture_id=group_fix.id, home_score=1, away_score=0),
                MatchPredictionCreate(fixture_id=knockout_fix.id, home_score=2, away_score=1),
            ],
            session=session,
            current_user=_user(),
            ctx=_ctx(),
        )

        # Group fixture was skipped; only the knockout one came back.
        assert len(results) == 1
        assert results[0].fixture_id == knockout_fix.id


class TestUpdateBracketPredictionsGuards:
    """Bracket rewrite must be refused after the phase's bracket deadline."""

    @pytest.mark.asyncio
    @patch("app.api.predictions.is_phase1_locked", new_callable=AsyncMock)
    @patch("app.api.predictions.get_current_phase", new_callable=AsyncMock)
    async def test_phase1_bracket_blocked_when_phase1_locked(self, mock_phase, mock_phase1):
        mock_phase.return_value = PredictionPhase.PHASE_1
        mock_phase1.return_value = True

        session = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await update_bracket_predictions(
                bracket_data=BracketPredictionUpdate(predictions=[]),
                session=session,
                current_user=_user(),
                ctx=_ctx(),
            )
        assert exc.value.status_code == 403
        assert "phase 1" in exc.value.detail.lower()

    @pytest.mark.asyncio
    @patch("app.api.predictions.is_phase2_bracket_locked", new_callable=AsyncMock)
    @patch("app.api.predictions.is_phase1_locked", new_callable=AsyncMock)
    @patch("app.api.predictions.get_current_phase", new_callable=AsyncMock)
    async def test_phase2_bracket_blocked_when_phase2_bracket_locked(
        self, mock_phase, mock_phase1, mock_phase2_bracket
    ):
        mock_phase.return_value = PredictionPhase.PHASE_2
        mock_phase1.return_value = True  # irrelevant for PHASE_2 rewrites
        mock_phase2_bracket.return_value = True

        session = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await update_bracket_predictions(
                bracket_data=BracketPredictionUpdate(predictions=[]),
                session=session,
                current_user=_user(),
                ctx=_ctx(),
            )
        assert exc.value.status_code == 403
        assert "phase 2" in exc.value.detail.lower()

    @pytest.mark.asyncio
    @patch("app.api.predictions.validate_phase1_bracket", new_callable=AsyncMock)
    @patch("app.api.predictions.is_phase2_bracket_locked", new_callable=AsyncMock)
    @patch("app.api.predictions.is_phase1_locked", new_callable=AsyncMock)
    @patch("app.api.predictions.get_current_phase", new_callable=AsyncMock)
    async def test_bracket_writable_when_no_lock(
        self, mock_phase, mock_phase1, mock_phase2_bracket, mock_validate
    ):
        """Happy path: both lock predicates return False — rewrite proceeds.

        The Phase 1 consistency validator is stubbed out (it would otherwise
        consume this test's mocked session.execute side_effects); its real
        behaviour is covered in test_bracket_consistency.py."""
        mock_phase.return_value = PredictionPhase.PHASE_1
        mock_phase1.return_value = False
        mock_phase2_bracket.return_value = False
        mock_validate.return_value = []

        # Two execute() calls happen: SELECT existing picks, then DELETE.
        # First returns an empty list (no prior picks to capture); second is
        # the bulk delete whose result we don't inspect.
        session = AsyncMock()
        existing_result = MagicMock()
        existing_result.scalars.return_value.all.return_value = []
        delete_result = MagicMock()
        session.execute.side_effect = [existing_result, delete_result]

        result = await update_bracket_predictions(
            bracket_data=BracketPredictionUpdate(predictions=[]),
            session=session,
            current_user=_user(),
            ctx=_ctx(),
        )
        assert result == {"status": "ok"}
