"""Tests for the prediction locking service."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from app.models.fixture import Fixture, MatchStatus
from app.services.locking import (
    check_fixture_locked,
    get_time_until_lock,
    get_current_phase,
    LOCK_MINUTES,
)


class TestCheckFixtureLocked:
    """Tests for fixture lock checking."""

    @pytest.fixture
    def future_fixture(self) -> Fixture:
        """Create a fixture in the future."""
        fixture = MagicMock(spec=Fixture)
        fixture.kickoff = datetime.utcnow() + timedelta(hours=2)
        fixture.status = MatchStatus.SCHEDULED
        return fixture

    @pytest.fixture
    def imminent_fixture(self) -> Fixture:
        """Create a fixture about to start (within lock window)."""
        fixture = MagicMock(spec=Fixture)
        fixture.kickoff = datetime.utcnow() + timedelta(minutes=3)
        fixture.status = MatchStatus.SCHEDULED
        return fixture

    @pytest.fixture
    def started_fixture(self) -> Fixture:
        """Create a fixture that has already started."""
        fixture = MagicMock(spec=Fixture)
        fixture.kickoff = datetime.utcnow() - timedelta(minutes=10)
        fixture.status = MatchStatus.LIVE
        return fixture

    def test_future_fixture_not_locked(self, future_fixture):
        """Fixture 2 hours away should not be locked."""
        assert check_fixture_locked(future_fixture) is False

    def test_imminent_fixture_locked(self, imminent_fixture):
        """Fixture 3 minutes away should be locked (< 5 min lock window)."""
        assert check_fixture_locked(imminent_fixture) is True

    def test_started_fixture_locked(self, started_fixture):
        """Started fixture should definitely be locked."""
        assert check_fixture_locked(started_fixture) is True

    def test_custom_lock_minutes(self, future_fixture):
        """Should respect custom lock_minutes parameter."""
        # Fixture is 2 hours away, but with 3 hour lock window it's locked
        assert check_fixture_locked(future_fixture, lock_minutes=180) is True

    def test_exactly_at_lock_time(self):
        """Fixture exactly at lock boundary should be locked."""
        fixture = MagicMock(spec=Fixture)
        fixture.kickoff = datetime.utcnow() + timedelta(minutes=LOCK_MINUTES)

        # At exactly the boundary, should be locked
        assert check_fixture_locked(fixture) is True


class TestGetTimeUntilLock:
    """Tests for time until lock calculation."""

    def test_future_fixture_returns_timedelta(self):
        """Should return timedelta for unlocked fixture."""
        fixture = MagicMock(spec=Fixture)
        fixture.kickoff = datetime.utcnow() + timedelta(hours=1)

        result = get_time_until_lock(fixture)

        assert result is not None
        assert isinstance(result, timedelta)
        # Should be roughly 55 minutes (1 hour - 5 min lock window)
        assert result.total_seconds() > 50 * 60

    def test_locked_fixture_returns_none(self):
        """Should return None for locked fixture."""
        fixture = MagicMock(spec=Fixture)
        fixture.kickoff = datetime.utcnow() - timedelta(minutes=1)

        result = get_time_until_lock(fixture)

        assert result is None

    def test_returns_positive_values_only(self):
        """Should only return positive time remaining."""
        fixture = MagicMock(spec=Fixture)
        fixture.kickoff = datetime.utcnow() + timedelta(minutes=2)

        result = get_time_until_lock(fixture)

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
