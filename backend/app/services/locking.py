"""Prediction locking service."""

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.fixture import Fixture
from app.models.prediction import MatchPrediction, PredictionPhase

# Lock predictions 5 minutes before kickoff
LOCK_MINUTES = 5


def check_fixture_locked(fixture: Fixture, lock_minutes: int = LOCK_MINUTES) -> bool:
    """Check if a fixture is locked for predictions.

    Args:
        fixture: The fixture to check
        lock_minutes: Minutes before kickoff to lock (default 5)

    Returns:
        True if predictions are locked, False otherwise
    """
    lock_time = fixture.kickoff - timedelta(minutes=lock_minutes)
    return datetime.utcnow() >= lock_time


def get_time_until_lock(fixture: Fixture, lock_minutes: int = LOCK_MINUTES) -> timedelta | None:
    """Get time remaining until predictions lock.

    Args:
        fixture: The fixture to check
        lock_minutes: Minutes before kickoff to lock

    Returns:
        Time remaining as timedelta, or None if already locked
    """
    lock_time = fixture.kickoff - timedelta(minutes=lock_minutes)
    remaining = lock_time - datetime.utcnow()
    return remaining if remaining.total_seconds() > 0 else None


def get_current_phase() -> PredictionPhase:
    """Determine the current prediction phase based on tournament state.

    In a real implementation, this would check:
    - If group stage has started
    - If group stage has finished
    - Competition deadlines

    For now, returns PHASE_1 as default.
    """
    # TODO: Implement proper phase detection based on competition config
    return PredictionPhase.PHASE_1


async def lock_predictions(session: AsyncSession, fixture_id: str) -> int:
    """Lock all predictions for a fixture.

    This is called when a match is about to start (5 min before kickoff)
    to permanently lock all predictions.

    Args:
        session: Database session
        fixture_id: The fixture ID to lock predictions for

    Returns:
        Number of predictions locked
    """
    result = await session.execute(
        select(MatchPrediction).where(
            MatchPrediction.fixture_id == fixture_id,
            MatchPrediction.locked_at.is_(None),
        )
    )
    predictions = result.scalars().all()

    locked_count = 0
    now = datetime.utcnow()

    for prediction in predictions:
        prediction.locked_at = now
        locked_count += 1

    await session.commit()
    return locked_count


async def check_and_lock_upcoming_fixtures(session: AsyncSession) -> dict[str, int]:
    """Check all fixtures and lock predictions for those about to start.

    This should be called periodically (e.g., every minute via cron/scheduler).

    Returns:
        Dict mapping fixture_id to number of locked predictions
    """
    # Get fixtures within lock window that haven't started
    lock_threshold = datetime.utcnow() + timedelta(minutes=LOCK_MINUTES)

    result = await session.execute(
        select(Fixture).where(
            Fixture.kickoff <= lock_threshold,
            Fixture.status == "scheduled",
        )
    )
    fixtures = result.scalars().all()

    results = {}
    for fixture in fixtures:
        locked = await lock_predictions(session, str(fixture.id))
        if locked > 0:
            results[str(fixture.id)] = locked

    return results
