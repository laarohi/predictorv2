"""Prediction locking service."""

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import get_lock_minutes
from app.models._datetime import utc_now
from app.models.competition import Competition
from app.models.fixture import Fixture
from app.models.prediction import MatchPrediction, PredictionPhase


async def get_active_competition(session: AsyncSession) -> Competition | None:
    """Get the currently active competition.

    Returns:
        The active competition, or None if no active competition exists.
    """
    result = await session.execute(
        select(Competition).where(Competition.is_active == True)
    )
    return result.scalar_one_or_none()


def check_fixture_locked(fixture: Fixture, lock_minutes: int | None = None) -> bool:
    """Check if a fixture is locked for predictions.

    Args:
        fixture: The fixture to check
        lock_minutes: Minutes before kickoff to lock. If None, reads
                      `locking.match_lock_before_kickoff` from the
                      tournament YAML.

    Returns:
        True if predictions are locked, False otherwise
    """
    if lock_minutes is None:
        lock_minutes = get_lock_minutes()
    lock_time = fixture.kickoff - timedelta(minutes=lock_minutes)
    return utc_now() >= lock_time


def get_time_until_lock(fixture: Fixture, lock_minutes: int | None = None) -> timedelta | None:
    """Get time remaining until predictions lock."""
    if lock_minutes is None:
        lock_minutes = get_lock_minutes()
    lock_time = fixture.kickoff - timedelta(minutes=lock_minutes)
    remaining = lock_time - utc_now()
    return remaining if remaining.total_seconds() > 0 else None


async def get_current_phase(session: AsyncSession) -> PredictionPhase:
    """Determine the current prediction phase based on competition state.

    Phase 2 is active when an admin has explicitly activated it via
    the is_phase2_active flag on the competition.

    Args:
        session: Database session

    Returns:
        PHASE_2 if Phase 2 is active, otherwise PHASE_1
    """
    competition = await get_active_competition(session)
    if competition and competition.is_phase2_active:
        return PredictionPhase.PHASE_2
    return PredictionPhase.PHASE_1


async def is_phase1_locked(session: AsyncSession) -> bool:
    """Whether Phase 1 predictions (group matches, bracket, bonus questions)
    are locked for the active competition.

    Returns True iff the active competition has a `phase1_deadline` and the
    current time is at or past it. Returns False when no competition is
    active or no deadline has been set.
    """
    competition = await get_active_competition(session)
    if not competition or not competition.phase1_deadline:
        return False
    return utc_now() >= competition.phase1_deadline


async def get_fixture_lock_view(
    session: AsyncSession,
    fixture: Fixture,
    *,
    phase1_locked: bool | None = None,
    lock_minutes: int | None = None,
) -> tuple[bool, timedelta | None]:
    """Canonical lock state for a fixture's match-score predictions.

    Returns (is_locked, time_until_lock). Combines the two lock rules:

    1. Phase 1 group fixtures (stage == "group") are locked the moment
       `competition.phase1_deadline` passes — well before their own
       kickoff. This is the "locked means locked" rule from the lock
       model: once Phase 1 closes, nothing in Phase 1 can be edited.

    2. Independently, every fixture additionally locks at the per-match
       T-{lock_minutes} window (Phase 2 knockout fixtures use this in
       practice; Phase 1 group fixtures will already be locked via #1).

    Pass `phase1_locked` if you've already computed it in this request
    (e.g. a list endpoint looping over fixtures) to skip the redundant
    competition lookup.

    `time_until_lock` is None when the fixture is locked.
    """
    if fixture.stage == "group":
        if phase1_locked is None:
            phase1_locked = await is_phase1_locked(session)
        if phase1_locked:
            return True, None

    if check_fixture_locked(fixture, lock_minutes=lock_minutes):
        return True, None
    return False, get_time_until_lock(fixture, lock_minutes=lock_minutes)


async def is_phase2_bracket_locked(session: AsyncSession) -> bool:
    """Check if the Phase 2 bracket prediction deadline has passed.

    The Phase 2 bracket locks at the phase2_bracket_deadline, which is
    set by the admin when activating Phase 2.

    Args:
        session: Database session

    Returns:
        True if Phase 2 bracket is locked, False otherwise
    """
    competition = await get_active_competition(session)
    if not competition:
        return False
    if not competition.is_phase2_active:
        return False
    if not competition.phase2_bracket_deadline:
        return False
    return utc_now() >= competition.phase2_bracket_deadline


async def lock_predictions(session: AsyncSession, fixture_id: str) -> int:
    """Lock all predictions for a fixture.

    This is called when a match is about to start to permanently lock all
    predictions. Each transition writes an `action=lock` history row so
    we can later prove when each prediction became immutable.

    Args:
        session: Database session
        fixture_id: The fixture ID to lock predictions for

    Returns:
        Number of predictions locked
    """
    # Local import to avoid an import cycle: prediction_history imports
    # RequestContext from dependencies, dependencies imports from config,
    # and locking is used during app boot.
    from app.models.prediction_history import PredictionAction, PredictionSource
    from app.services.prediction_history import (
        record_match_prediction_change,
        snapshot_match,
    )

    result = await session.execute(
        select(MatchPrediction).where(
            MatchPrediction.fixture_id == fixture_id,
            MatchPrediction.locked_at.is_(None),
        )
    )
    predictions = result.scalars().all()

    locked_count = 0
    now = utc_now()

    for prediction in predictions:
        old_values = snapshot_match(prediction)
        prediction.locked_at = now
        record_match_prediction_change(
            session,
            prediction=prediction,
            old_values=old_values,
            new_values=snapshot_match(prediction),
            action=PredictionAction.LOCK,
            source=PredictionSource.LOCK_SCHEDULER,
            performed_by_user_id=None,
            ctx=None,
        )
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
    lock_threshold = utc_now() + timedelta(minutes=get_lock_minutes())

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
