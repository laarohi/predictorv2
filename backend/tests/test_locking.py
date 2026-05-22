"""Tests for the prediction locking service."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from app.models.fixture import Fixture, MatchStatus
from app.services.locking import (
    check_fixture_locked,
    get_fixture_lock_view,
    get_time_until_lock,
    get_current_phase,
    is_phase1_locked,
    is_phase2_bracket_locked,
)

# Tests pin a fixed lock window so they're independent of the YAML config.
# Real value lives in config/worldcup2026.yml -> locking.match_lock_before_kickoff.
TEST_LOCK_MINUTES = 5


class TestCheckFixtureLocked:
    """Tests for fixture lock checking."""

    @pytest.fixture
    def future_fixture(self) -> Fixture:
        """Create a fixture in the future."""
        fixture = MagicMock(spec=Fixture)
        fixture.kickoff = datetime.now(timezone.utc) + timedelta(hours=2)
        fixture.status = MatchStatus.SCHEDULED
        return fixture

    @pytest.fixture
    def imminent_fixture(self) -> Fixture:
        """Create a fixture about to start (within lock window)."""
        fixture = MagicMock(spec=Fixture)
        fixture.kickoff = datetime.now(timezone.utc) + timedelta(minutes=3)
        fixture.status = MatchStatus.SCHEDULED
        return fixture

    @pytest.fixture
    def started_fixture(self) -> Fixture:
        """Create a fixture that has already started."""
        fixture = MagicMock(spec=Fixture)
        fixture.kickoff = datetime.now(timezone.utc) - timedelta(minutes=10)
        fixture.status = MatchStatus.LIVE
        return fixture

    def test_future_fixture_not_locked(self, future_fixture):
        """Fixture 2 hours away should not be locked."""
        assert check_fixture_locked(future_fixture, lock_minutes=TEST_LOCK_MINUTES) is False

    def test_imminent_fixture_locked(self, imminent_fixture):
        """Fixture 3 minutes away should be locked (inside the 5-min lock window)."""
        assert check_fixture_locked(imminent_fixture, lock_minutes=TEST_LOCK_MINUTES) is True

    def test_started_fixture_locked(self, started_fixture):
        """Started fixture should definitely be locked."""
        assert check_fixture_locked(started_fixture, lock_minutes=TEST_LOCK_MINUTES) is True

    def test_custom_lock_minutes(self, future_fixture):
        """Should respect custom lock_minutes parameter."""
        # Fixture is 2 hours away, but with 3 hour lock window it's locked
        assert check_fixture_locked(future_fixture, lock_minutes=180) is True

    def test_exactly_at_lock_time(self):
        """Fixture exactly at lock boundary should be locked."""
        fixture = MagicMock(spec=Fixture)
        fixture.kickoff = datetime.now(timezone.utc) + timedelta(minutes=TEST_LOCK_MINUTES)

        # At exactly the boundary, should be locked
        assert check_fixture_locked(fixture, lock_minutes=TEST_LOCK_MINUTES) is True


class TestGetTimeUntilLock:
    """Tests for time until lock calculation."""

    def test_future_fixture_returns_timedelta(self):
        """Should return timedelta for unlocked fixture."""
        fixture = MagicMock(spec=Fixture)
        fixture.kickoff = datetime.now(timezone.utc) + timedelta(hours=1)

        result = get_time_until_lock(fixture, lock_minutes=TEST_LOCK_MINUTES)

        assert result is not None
        assert isinstance(result, timedelta)
        # Should be roughly 55 minutes (1 hour - 5 min lock window)
        assert result.total_seconds() > 50 * 60

    def test_locked_fixture_returns_none(self):
        """Should return None for locked fixture."""
        fixture = MagicMock(spec=Fixture)
        fixture.kickoff = datetime.now(timezone.utc) - timedelta(minutes=1)

        result = get_time_until_lock(fixture, lock_minutes=TEST_LOCK_MINUTES)

        assert result is None

    def test_returns_positive_values_only(self):
        """Should only return positive time remaining."""
        fixture = MagicMock(spec=Fixture)
        fixture.kickoff = datetime.now(timezone.utc) + timedelta(minutes=2)

        result = get_time_until_lock(fixture, lock_minutes=TEST_LOCK_MINUTES)

        # 2 minutes until kickoff, lock was 3 minutes ago
        assert result is None


class TestGetCurrentPhase:
    """Tests for prediction phase determination."""

    @pytest.mark.asyncio
    async def test_returns_phase_1_when_no_competition(self):
        """Should return PHASE_1 when no active competition exists."""
        from app.models.prediction import PredictionPhase
        from unittest.mock import AsyncMock

        # Mock session that returns no competition
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await get_current_phase(mock_session)

        assert result == PredictionPhase.PHASE_1

    @pytest.mark.asyncio
    async def test_returns_phase_2_when_active(self):
        """Should return PHASE_2 when competition has is_phase2_active=True."""
        from app.models.prediction import PredictionPhase
        from app.models.competition import Competition
        from unittest.mock import AsyncMock

        # Mock competition with Phase 2 active
        mock_competition = MagicMock(spec=Competition)
        mock_competition.is_phase2_active = True

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_competition
        mock_session.execute.return_value = mock_result

        result = await get_current_phase(mock_session)

        assert result == PredictionPhase.PHASE_2


def _mock_session_returning(competition):
    """Build a mocked AsyncSession whose .execute() returns the given competition."""
    from unittest.mock import AsyncMock

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = competition
    mock_session.execute.return_value = mock_result
    return mock_session


class TestIsPhase1Locked:
    """Phase 1 lock = competition.phase1_deadline has passed."""

    @pytest.mark.asyncio
    async def test_returns_false_when_no_competition(self):
        session = _mock_session_returning(None)
        assert await is_phase1_locked(session) is False

    @pytest.mark.asyncio
    async def test_returns_false_when_no_deadline(self):
        from app.models.competition import Competition

        comp = MagicMock(spec=Competition)
        comp.phase1_deadline = None
        assert await is_phase1_locked(_mock_session_returning(comp)) is False

    @pytest.mark.asyncio
    async def test_returns_false_before_deadline(self):
        from app.models.competition import Competition

        comp = MagicMock(spec=Competition)
        comp.phase1_deadline = datetime.now(timezone.utc) + timedelta(hours=1)
        assert await is_phase1_locked(_mock_session_returning(comp)) is False

    @pytest.mark.asyncio
    async def test_returns_true_at_or_after_deadline(self):
        from app.models.competition import Competition

        comp = MagicMock(spec=Competition)
        comp.phase1_deadline = datetime.now(timezone.utc) - timedelta(seconds=1)
        assert await is_phase1_locked(_mock_session_returning(comp)) is True


class TestGetFixtureLockView:
    """The phase-aware lock state used by API response builders.

    Encodes "locked means locked": group fixtures lock when phase1_deadline
    passes, even if their kickoff is still days away.
    """

    def _group_fixture_in(self, hours: float) -> Fixture:
        fixture = MagicMock(spec=Fixture)
        fixture.kickoff = datetime.now(timezone.utc) + timedelta(hours=hours)
        fixture.stage = "group"
        return fixture

    def _knockout_fixture_in(self, hours: float) -> Fixture:
        fixture = MagicMock(spec=Fixture)
        fixture.kickoff = datetime.now(timezone.utc) + timedelta(hours=hours)
        fixture.stage = "round_of_16"
        return fixture

    @pytest.mark.asyncio
    async def test_group_fixture_locked_by_phase1_even_when_kickoff_far_away(self):
        fixture = self._group_fixture_in(hours=48)
        session = AsyncMock()

        locked, time_until = await get_fixture_lock_view(
            session, fixture, phase1_locked=True
        )
        assert locked is True
        assert time_until is None

    @pytest.mark.asyncio
    async def test_group_fixture_unlocked_when_phase1_open_and_kickoff_far(self):
        fixture = self._group_fixture_in(hours=48)
        session = AsyncMock()

        locked, time_until = await get_fixture_lock_view(
            session, fixture, phase1_locked=False
        )
        assert locked is False
        assert time_until is not None

    @pytest.mark.asyncio
    async def test_knockout_fixture_ignores_phase1_lock(self):
        """Knockout fixtures only care about their own per-fixture lock."""
        fixture = self._knockout_fixture_in(hours=48)
        session = AsyncMock()

        # phase1_locked=True must NOT cause a knockout fixture to be locked.
        locked, time_until = await get_fixture_lock_view(
            session, fixture, phase1_locked=True
        )
        assert locked is False
        assert time_until is not None

    @pytest.mark.asyncio
    async def test_knockout_fixture_locked_by_per_fixture_window(self):
        # 10 minutes from kickoff with default 15-min lock window → locked.
        fixture = self._knockout_fixture_in(hours=10 / 60)
        session = AsyncMock()

        locked, time_until = await get_fixture_lock_view(
            session, fixture, phase1_locked=False
        )
        assert locked is True
        assert time_until is None


class TestIsPhase2BracketLocked:
    """Phase 2 bracket lock = phase2 active AND phase2_bracket_deadline passed."""

    @pytest.mark.asyncio
    async def test_returns_false_when_phase2_inactive(self):
        from app.models.competition import Competition

        comp = MagicMock(spec=Competition)
        comp.is_phase2_active = False
        comp.phase2_bracket_deadline = datetime.now(timezone.utc) - timedelta(hours=1)
        assert await is_phase2_bracket_locked(_mock_session_returning(comp)) is False

    @pytest.mark.asyncio
    async def test_returns_false_when_no_deadline(self):
        from app.models.competition import Competition

        comp = MagicMock(spec=Competition)
        comp.is_phase2_active = True
        comp.phase2_bracket_deadline = None
        assert await is_phase2_bracket_locked(_mock_session_returning(comp)) is False

    @pytest.mark.asyncio
    async def test_returns_true_after_deadline(self):
        from app.models.competition import Competition

        comp = MagicMock(spec=Competition)
        comp.is_phase2_active = True
        comp.phase2_bracket_deadline = datetime.now(timezone.utc) - timedelta(seconds=1)
        assert await is_phase2_bracket_locked(_mock_session_returning(comp)) is True
