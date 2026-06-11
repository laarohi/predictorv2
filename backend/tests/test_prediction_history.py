"""Tests that prediction-history rows are written at every mutation site.

These are unit tests that verify the *capture wiring* — that each API
mutation point calls into `app.services.prediction_history.record_*`
with the correct action, source, and snapshot data. The history rows
themselves are tested indirectly: we assert that `session.add` was
called with a row of the right shape.

Why mock the session rather than hit Postgres: the test only needs to
verify the capture wiring, not the SQL round-trip. Postgres-level
behaviour (TIMESTAMPTZ, JSON, indexes) is the migration's responsibility.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.predictions import (
    batch_update_predictions,
    save_bonus_predictions,
    update_bracket_predictions,
    update_match_prediction,
)
from app.dependencies import RequestContext
from app.models.bonus import BonusPrediction
from app.models.fixture import Fixture
from app.models.prediction import MatchPrediction, PredictionPhase, TeamPrediction
from app.models.prediction_history import (
    BonusPredictionHistory,
    MatchPredictionHistory,
    PredictionAction,
    PredictionSource,
    TeamPredictionHistory,
)
from app.models.user import User
from app.schemas.prediction import (
    BracketPredictionUpdate,
    MatchPredictionCreate,
    MatchPredictionUpdate,
    TeamAdvancementPrediction,
)


def _ctx() -> RequestContext:
    return RequestContext(
        request_id=uuid.uuid4(),
        client_ip="127.0.0.1",
        user_agent="pytest",
    )


def _user() -> User:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    return user


def _knockout_fixture() -> Fixture:
    fixture = MagicMock(spec=Fixture)
    fixture.id = uuid.uuid4()
    fixture.stage = "round_of_16"
    fixture.group = None
    fixture.home_team = "Brazil"
    fixture.away_team = "Germany"
    fixture.kickoff = datetime.now(timezone.utc) + timedelta(hours=24)
    fixture.is_locked.return_value = False
    return fixture


def _added_rows_of_type(session: AsyncMock, model_type) -> list:
    """Extract all instances of `model_type` passed to session.add()."""
    return [
        call.args[0]
        for call in session.add.call_args_list
        if isinstance(call.args[0], model_type)
    ]


class TestMatchPredictionHistoryCapture:
    """Single-PUT and batch endpoints must append history rows."""

    @pytest.mark.asyncio
    @patch("app.api.predictions.is_phase1_locked", new_callable=AsyncMock)
    @patch("app.api.predictions.get_current_phase", new_callable=AsyncMock)
    async def test_insert_records_history(self, mock_phase, mock_phase1):
        mock_phase1.return_value = False
        mock_phase.return_value = PredictionPhase.PHASE_2

        fixture = _knockout_fixture()
        user = _user()

        session = AsyncMock()
        # 1: fetch fixture, 2: fetch existing prediction (none).
        fixture_result = MagicMock()
        fixture_result.scalar_one_or_none.return_value = fixture
        prediction_result = MagicMock()
        prediction_result.scalar_one_or_none.return_value = None
        session.execute.side_effect = [fixture_result, prediction_result]
        session.add = MagicMock()
        session.refresh = AsyncMock()

        await update_match_prediction(
            fixture_id=fixture.id,
            prediction_data=MatchPredictionUpdate(home_score=3, away_score=1),
            session=session,
            current_user=user,
            ctx=_ctx(),
        )

        history_rows = _added_rows_of_type(session, MatchPredictionHistory)
        assert len(history_rows) == 1
        row = history_rows[0]
        assert row.action == PredictionAction.INSERT
        assert row.source == PredictionSource.API_SINGLE
        assert row.user_id == user.id
        assert row.fixture_id == fixture.id
        assert row.performed_by_user_id == user.id
        assert row.old_values is None
        assert row.new_values is not None
        assert row.new_values["home_score"] == 3
        assert row.new_values["away_score"] == 1

    @pytest.mark.asyncio
    @patch("app.api.predictions.is_phase1_locked", new_callable=AsyncMock)
    @patch("app.api.predictions.get_current_phase", new_callable=AsyncMock)
    async def test_update_records_history_with_old_and_new(self, mock_phase, mock_phase1):
        mock_phase1.return_value = False
        mock_phase.return_value = PredictionPhase.PHASE_2

        fixture = _knockout_fixture()
        user = _user()
        existing = MatchPrediction(
            id=uuid.uuid4(),
            user_id=user.id,
            fixture_id=fixture.id,
            home_score=1,
            away_score=1,
            phase=PredictionPhase.PHASE_2,
        )

        session = AsyncMock()
        fixture_result = MagicMock()
        fixture_result.scalar_one_or_none.return_value = fixture
        prediction_result = MagicMock()
        prediction_result.scalar_one_or_none.return_value = existing
        session.execute.side_effect = [fixture_result, prediction_result]
        session.add = MagicMock()
        session.refresh = AsyncMock()

        await update_match_prediction(
            fixture_id=fixture.id,
            prediction_data=MatchPredictionUpdate(home_score=3, away_score=2),
            session=session,
            current_user=user,
            ctx=_ctx(),
        )

        history_rows = _added_rows_of_type(session, MatchPredictionHistory)
        assert len(history_rows) == 1
        row = history_rows[0]
        assert row.action == PredictionAction.UPDATE
        assert row.source == PredictionSource.API_SINGLE
        assert row.old_values["home_score"] == 1
        assert row.old_values["away_score"] == 1
        assert row.new_values["home_score"] == 3
        assert row.new_values["away_score"] == 2

    @pytest.mark.asyncio
    @patch("app.api.predictions.is_phase1_locked", new_callable=AsyncMock)
    @patch("app.api.predictions.get_current_phase", new_callable=AsyncMock)
    async def test_batch_records_source_api_batch(self, mock_phase, mock_phase1):
        mock_phase1.return_value = False
        mock_phase.return_value = PredictionPhase.PHASE_2

        fixture = _knockout_fixture()
        user = _user()

        session = AsyncMock()
        fixture_result = MagicMock()
        fixture_result.scalar_one_or_none.return_value = fixture
        prediction_result = MagicMock()
        prediction_result.scalar_one_or_none.return_value = None
        session.execute.side_effect = [fixture_result, prediction_result]
        session.add = MagicMock()
        session.refresh = AsyncMock()

        await batch_update_predictions(
            predictions_data=[
                MatchPredictionCreate(fixture_id=fixture.id, home_score=2, away_score=0),
            ],
            session=session,
            current_user=user,
            ctx=_ctx(),
        )

        history_rows = _added_rows_of_type(session, MatchPredictionHistory)
        assert len(history_rows) == 1
        assert history_rows[0].source == PredictionSource.API_BATCH
        assert history_rows[0].action == PredictionAction.INSERT


class TestBracketRewriteHistoryCapture:
    """Bracket rewrite must record one delete row per removed pick AND one
    insert row per new pick — so the audit trail is reconstructible."""

    @pytest.mark.asyncio
    @patch("app.api.predictions.validate_phase1_bracket", new_callable=AsyncMock)
    @patch("app.api.predictions.is_phase2_bracket_locked", new_callable=AsyncMock)
    @patch("app.api.predictions.is_phase1_locked", new_callable=AsyncMock)
    @patch("app.api.predictions.get_current_phase", new_callable=AsyncMock)
    async def test_records_delete_then_insert_pair(
        self, mock_phase, mock_phase1, mock_phase2_bracket, mock_validate
    ):
        mock_phase.return_value = PredictionPhase.PHASE_1
        mock_phase1.return_value = False
        mock_phase2_bracket.return_value = False
        # Consistency validation is stubbed out (it would consume this test's
        # mocked session.execute side_effects); its real behaviour is covered
        # in test_bracket_consistency.py.
        mock_validate.return_value = []

        user = _user()
        # Two existing picks the user is overwriting.
        existing_brazil = TeamPrediction(
            id=uuid.uuid4(), user_id=user.id, team="Brazil", stage="final",
            phase=PredictionPhase.PHASE_1,
        )
        existing_france = TeamPrediction(
            id=uuid.uuid4(), user_id=user.id, team="France", stage="semi_final",
            phase=PredictionPhase.PHASE_1,
        )

        session = AsyncMock()
        existing_result = MagicMock()
        existing_result.scalars.return_value.all.return_value = [
            existing_brazil, existing_france
        ]
        delete_result = MagicMock()
        session.execute.side_effect = [existing_result, delete_result]
        session.add = MagicMock()

        result = await update_bracket_predictions(
            bracket_data=BracketPredictionUpdate(
                predictions=[
                    TeamAdvancementPrediction(team="Argentina", stage="final"),
                ]
            ),
            session=session,
            current_user=user,
            ctx=_ctx(),
        )
        assert result == {"status": "ok"}

        history_rows = _added_rows_of_type(session, TeamPredictionHistory)
        # 2 deletes (Brazil, France) + 1 insert (Argentina) = 3 rows.
        assert len(history_rows) == 3
        actions = [r.action for r in history_rows]
        assert actions.count(PredictionAction.DELETE) == 2
        assert actions.count(PredictionAction.INSERT) == 1
        # All rows share the same source.
        for row in history_rows:
            assert row.source == PredictionSource.API_BRACKET_REWRITE
        # The delete rows must have old_values (so we can reconstruct what
        # was there) and no new_values.
        delete_rows = [r for r in history_rows if r.action == PredictionAction.DELETE]
        for row in delete_rows:
            assert row.old_values is not None
            assert row.new_values is None
        # The insert row mirrors this in reverse.
        insert_rows = [r for r in history_rows if r.action == PredictionAction.INSERT]
        assert insert_rows[0].new_values["team"] == "Argentina"
        assert insert_rows[0].old_values is None


class TestBonusHistoryCapture:
    """Bonus endpoint must capture insert/update/delete for every change."""

    @pytest.mark.asyncio
    @patch("app.api.predictions.is_phase1_locked", new_callable=AsyncMock)
    @patch("app.api.predictions.get_bonus_questions")
    async def test_update_existing_bonus_records_history(self, mock_questions, mock_phase1):
        mock_phase1.return_value = False
        # Mock the bonus question list — the endpoint validates question_id
        # against this set.
        q = MagicMock()
        q.id = "best_player"
        mock_questions.return_value = [q]

        user = _user()
        existing = BonusPrediction(
            id=uuid.uuid4(),
            user_id=user.id,
            question_id="best_player",
            answer="Vinicius Jr",
        )

        session = AsyncMock()
        existing_result = MagicMock()
        existing_result.scalars.return_value.all.return_value = [existing]
        # Second execute() call is the post-save re-read.
        refreshed_result = MagicMock()
        refreshed_result.scalars.return_value.all.return_value = [existing]
        session.execute.side_effect = [existing_result, refreshed_result]
        session.add = MagicMock()

        from app.api.predictions import BonusPredictionBatch, BonusPredictionUpdate

        await save_bonus_predictions(
            payload=BonusPredictionBatch(
                predictions=[
                    BonusPredictionUpdate(question_id="best_player", answer="Lamine Yamal"),
                ]
            ),
            session=session,
            current_user=user,
            ctx=_ctx(),
        )

        history_rows = _added_rows_of_type(session, BonusPredictionHistory)
        assert len(history_rows) == 1
        row = history_rows[0]
        assert row.action == PredictionAction.UPDATE
        assert row.source == PredictionSource.API_BONUS_BATCH
        assert row.old_values["answer"] == "Vinicius Jr"
        assert row.new_values["answer"] == "Lamine Yamal"
