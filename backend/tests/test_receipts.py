"""Tests for the Phase 1 receipt builder.

The receipt is the user-facing artefact that resolves disputes in
their favour or against them — so it's worth being defensive about
correctness. These tests check three things:

1. The data layer queries the right rows (Phase 1 only, group fixtures
   only for the score section).
2. The renderers handle empty / partial states without crashing.
3. The output contains the user's actual predictions in the expected
   format ("Brazil 2-1 Germany" not "{'home_score': 2, ...}").
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.bonus import BonusPrediction
from app.models.fixture import Fixture
from app.models.prediction import MatchPrediction, PredictionPhase, TeamPrediction
from app.models.user import User
from app.services.receipts import (
    _esc,
    _summary_counts,
    build_phase1_receipt,
)


def _user(name: str = "Aarohi") -> User:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.name = name
    user.email = f"{name.lower()}@example.com"
    return user


def _fixture(home: str, away: str, group: str = "A") -> Fixture:
    fixture = MagicMock(spec=Fixture)
    fixture.id = uuid.uuid4()
    fixture.home_team = home
    fixture.away_team = away
    fixture.kickoff = datetime.now(timezone.utc) + timedelta(days=10)
    fixture.stage = "group"
    fixture.group = group
    fixture.match_number = 1
    return fixture


def _match_pred(fixture_id: uuid.UUID, user_id: uuid.UUID, home: int, away: int) -> MatchPrediction:
    return MatchPrediction(
        id=uuid.uuid4(),
        user_id=user_id,
        fixture_id=fixture_id,
        home_score=home,
        away_score=away,
        phase=PredictionPhase.PHASE_1,
    )


def _bonus(user_id: uuid.UUID, question_id: str, answer: str) -> BonusPrediction:
    return BonusPrediction(
        id=uuid.uuid4(),
        user_id=user_id,
        question_id=question_id,
        answer=answer,
        phase=PredictionPhase.PHASE_1,
    )


def _team(user_id: uuid.UUID, team: str, stage: str) -> TeamPrediction:
    return TeamPrediction(
        id=uuid.uuid4(),
        user_id=user_id,
        team=team,
        stage=stage,
        phase=PredictionPhase.PHASE_1,
    )


def _mock_session(group_rows: list, bracket_rows: list, bonus_rows: list) -> AsyncMock:
    """Wire three sequential session.execute() calls — one per loader."""
    session = AsyncMock()
    group_result = MagicMock()
    group_result.all.return_value = group_rows
    bracket_result = MagicMock()
    bracket_result.scalars.return_value.all.return_value = bracket_rows
    bonus_result = MagicMock()
    bonus_result.scalars.return_value.all.return_value = bonus_rows
    session.execute.side_effect = [group_result, bracket_result, bonus_result]
    return session


class TestPhase1ReceiptHappyPath:
    """Full receipt with realistic data."""

    @pytest.mark.asyncio
    async def test_renders_full_receipt(self):
        user = _user("Luke")
        f1 = _fixture("Brazil", "Germany", group="A")
        f2 = _fixture("USA", "Morocco", group="A")
        group_rows = [
            (_match_pred(f1.id, user.id, 2, 1), f1),
            (_match_pred(f2.id, user.id, 0, 0), f2),
        ]
        bracket_rows = [
            _team(user.id, "Brazil", "semi_final"),
            _team(user.id, "Argentina", "final"),
            _team(user.id, "Brazil", "winner"),
        ]
        bonus_rows = [_bonus(user.id, "top_scorer", "Vinicius Jr")]

        session = _mock_session(group_rows, bracket_rows, bonus_rows)
        receipt = await build_phase1_receipt(session, user)

        # Subject line
        assert "locked in" in receipt.subject.lower()

        # User salutation in both bodies
        assert "Hi Luke" in receipt.html
        assert "Hi Luke" in receipt.text

        # Group section — scores rendered as "Brazil 2-1 Germany"
        assert "Brazil" in receipt.html
        assert "2–1" in receipt.html or "2-1" in receipt.html
        assert "Brazil 2-1 Germany" in receipt.text
        assert "USA 0-0 Morocco" in receipt.text

        # Bracket section
        assert "Semi-finals" in receipt.html
        assert "Argentina" in receipt.html
        assert "WINNER" in receipt.html.upper()
        assert "WINNER: Brazil" in receipt.text

        # Bonus section — answer appears verbatim
        assert "Vinicius Jr" in receipt.html
        assert "Vinicius Jr" in receipt.text

        # Summary counts
        assert "2 group" in receipt.html
        assert "3 bracket" in receipt.html
        assert "1 bonus" in receipt.html


class TestPhase1ReceiptEmptyStates:
    """Users with no predictions still get a renderable receipt."""

    @pytest.mark.asyncio
    async def test_no_predictions_at_all(self):
        user = _user()
        session = _mock_session([], [], [])
        receipt = await build_phase1_receipt(session, user)

        # Receipt still renders without crashing
        assert receipt.subject
        assert receipt.html
        assert receipt.text

        # Empty-state messaging appears
        assert "didn't submit" in receipt.html
        assert "(none submitted)" in receipt.text

    @pytest.mark.asyncio
    async def test_only_group_predictions(self):
        user = _user()
        f = _fixture("Brazil", "Germany")
        session = _mock_session([(_match_pred(f.id, user.id, 1, 0), f)], [], [])
        receipt = await build_phase1_receipt(session, user)

        assert "Brazil" in receipt.html
        # Empty bracket and bonus sections both rendered as empty-state.
        assert receipt.html.count("didn't submit") == 2


class TestPhase1ReceiptHtmlEscaping:
    """User-controlled strings (team names, bonus answers) must be escaped."""

    @pytest.mark.asyncio
    async def test_bonus_answer_html_escaped(self):
        user = _user()
        # An answer with HTML-special characters.
        session = _mock_session(
            [], [], [_bonus(user.id, "top_scorer", "<script>alert('xss')</script>")]
        )
        receipt = await build_phase1_receipt(session, user)

        assert "<script>" not in receipt.html
        assert "&lt;script&gt;" in receipt.html


class TestPhase1ReceiptCopy:
    """The dispute-resolution copy needs to be internally consistent.

    Earlier the email said 'once the tournament starts, predictions
    cannot be changed' in the top section AND 'disputes within 24 hours'
    in the footer — contradictory under the operational plan of
    sending receipts ~1 hour before kickoff. This test pins the
    consistent wording so a future regression doesn't re-introduce
    the conflicting language."""

    @pytest.mark.asyncio
    async def test_top_copy_mentions_kickoff_window(self):
        user = _user()
        session = _mock_session([], [], [])
        receipt = await build_phase1_receipt(session, user)

        # The actual operational window — ~1h between email and first kickoff.
        assert "kicks off in about an hour" in receipt.html
        assert "kicks off in about an hour" in receipt.text

    @pytest.mark.asyncio
    async def test_does_not_mention_24_hour_disputes(self):
        """Old footer copy claimed a 24h dispute window that didn't match
        the 1h-before-kickoff send cadence. Make sure it stays gone."""
        user = _user()
        session = _mock_session([], [], [])
        receipt = await build_phase1_receipt(session, user)

        assert "24 hours" not in receipt.html
        assert "24 hours" not in receipt.text


class TestHelpers:
    def test_esc_handles_none(self):
        assert _esc(None) == ""

    def test_esc_escapes_specials(self):
        assert _esc("Tom & Jerry") == "Tom &amp; Jerry"
        assert _esc('"quoted"') == "&quot;quoted&quot;"

    def test_summary_counts_format(self):
        assert _summary_counts([1, 2, 3], [4], [5, 6]) == "3 group · 1 bracket · 2 bonus"
