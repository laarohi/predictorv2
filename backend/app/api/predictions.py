"""Predictions API routes."""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.orm import selectinload
from sqlmodel import select, delete

from app.dependencies import CurrentUser, DbSession, OptionalUser
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction, PredictionPhase, TeamPrediction
from app.models.user import User
from app.schemas.fixture import FixtureScore
from app.schemas.prediction import (
    BracketPrediction,
    BracketPredictionUpdate,
    CommunityPrediction,
    CommunityPredictionsResponse,
    MatchPredictionCreate,
    MatchPredictionRead,
    MatchPredictionUpdate,
)
from app.services.locking import check_fixture_locked, get_current_phase

router = APIRouter()


@router.get("/matches", response_model=list[MatchPredictionRead])
async def get_match_predictions(
    session: DbSession, current_user: CurrentUser
) -> list[MatchPredictionRead]:
    """Get all match predictions for the current user."""
    result = await session.execute(
        select(MatchPrediction, Fixture)
        .join(Fixture, MatchPrediction.fixture_id == Fixture.id)
        .where(MatchPrediction.user_id == current_user.id)
        .order_by(Fixture.kickoff)
    )
    rows = result.all()

    predictions = []
    for pred, fixture in rows:
        predictions.append(
            MatchPredictionRead(
                id=pred.id,
                fixture_id=pred.fixture_id,
                home_score=pred.home_score,
                away_score=pred.away_score,
                phase=pred.phase,
                locked_at=pred.locked_at,
                created_at=pred.created_at,
                updated_at=pred.updated_at,
                home_team=fixture.home_team,
                away_team=fixture.away_team,
                kickoff=fixture.kickoff,
                is_locked=fixture.is_locked(),
            )
        )

    return predictions


@router.put("/matches/{fixture_id}", response_model=MatchPredictionRead)
async def update_match_prediction(
    fixture_id: uuid.UUID,
    prediction_data: MatchPredictionUpdate,
    session: DbSession,
    current_user: CurrentUser,
) -> MatchPredictionRead:
    """Update a single match prediction."""
    # Get fixture
    result = await session.execute(select(Fixture).where(Fixture.id == fixture_id))
    fixture = result.scalar_one_or_none()

    if not fixture:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fixture not found")

    # Check if locked
    if check_fixture_locked(fixture):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Predictions are locked for this match",
        )

    # Get existing prediction or create new
    result = await session.execute(
        select(MatchPrediction).where(
            MatchPrediction.user_id == current_user.id,
            MatchPrediction.fixture_id == fixture_id,
        )
    )
    prediction = result.scalar_one_or_none()

    current_phase = await get_current_phase(session)

    if prediction:
        prediction.home_score = prediction_data.home_score
        prediction.away_score = prediction_data.away_score
        prediction.updated_at = datetime.utcnow()
    else:
        prediction = MatchPrediction(
            user_id=current_user.id,
            fixture_id=fixture_id,
            home_score=prediction_data.home_score,
            away_score=prediction_data.away_score,
            phase=current_phase,
        )
        session.add(prediction)

    await session.commit()
    await session.refresh(prediction)

    return MatchPredictionRead(
        id=prediction.id,
        fixture_id=prediction.fixture_id,
        home_score=prediction.home_score,
        away_score=prediction.away_score,
        phase=prediction.phase,
        locked_at=prediction.locked_at,
        created_at=prediction.created_at,
        updated_at=prediction.updated_at,
        home_team=fixture.home_team,
        away_team=fixture.away_team,
        kickoff=fixture.kickoff,
        is_locked=fixture.is_locked(),
    )


@router.post("/matches/batch", response_model=list[MatchPredictionRead])
async def batch_update_predictions(
    predictions_data: list[MatchPredictionCreate],
    session: DbSession,
    current_user: CurrentUser,
) -> list[MatchPredictionRead]:
    """Batch update multiple match predictions."""
    results = []
    current_phase = await get_current_phase(session)

    for pred_data in predictions_data:
        # Get fixture
        result = await session.execute(select(Fixture).where(Fixture.id == pred_data.fixture_id))
        fixture = result.scalar_one_or_none()

        if not fixture:
            continue  # Skip invalid fixtures

        # Check if locked
        if check_fixture_locked(fixture):
            continue  # Skip locked fixtures

        # Get existing prediction or create new
        result = await session.execute(
            select(MatchPrediction).where(
                MatchPrediction.user_id == current_user.id,
                MatchPrediction.fixture_id == pred_data.fixture_id,
            )
        )
        prediction = result.scalar_one_or_none()

        if prediction:
            prediction.home_score = pred_data.home_score
            prediction.away_score = pred_data.away_score
            prediction.updated_at = datetime.utcnow()
        else:
            prediction = MatchPrediction(
                user_id=current_user.id,
                fixture_id=pred_data.fixture_id,
                home_score=pred_data.home_score,
                away_score=pred_data.away_score,
                phase=current_phase,
            )
            session.add(prediction)

        await session.flush()
        await session.refresh(prediction)

        results.append(
            MatchPredictionRead(
                id=prediction.id,
                fixture_id=prediction.fixture_id,
                home_score=prediction.home_score,
                away_score=prediction.away_score,
                phase=prediction.phase,
                locked_at=prediction.locked_at,
                created_at=prediction.created_at,
                updated_at=prediction.updated_at,
                home_team=fixture.home_team,
                away_team=fixture.away_team,
                kickoff=fixture.kickoff,
                is_locked=fixture.is_locked(),
            )
        )

    await session.commit()
    return results


@router.get("/bracket", response_model=BracketPrediction | None)
async def get_bracket_predictions(
    session: DbSession,
    current_user: CurrentUser,
    phase: str | None = None,
) -> BracketPrediction | None:
    """Get bracket predictions for the current user.

    Args:
        phase: Optional phase filter ('phase_1' or 'phase_2').
               If not provided, uses current phase.
    """
    # Determine which phase to fetch
    if phase:
        target_phase = PredictionPhase(phase)
    else:
        target_phase = await get_current_phase(session)

    result = await session.execute(
        select(TeamPrediction).where(
            TeamPrediction.user_id == current_user.id,
            TeamPrediction.phase == target_phase,
        )
    )
    predictions = result.scalars().all()

    if not predictions:
        return None

    # Organize predictions into bracket structure
    group_winners: dict[str, list[str]] = {}
    stages: dict[str, list[str]] = {
        "round_of_32": [],
        "round_of_16": [],
        "quarter_finals": [],
        "semi_finals": [],
        "final": [],
    }
    winner = ""

    for pred in predictions:
        if pred.stage == "group":
            # Group winners - organize by position
            pass  # Would need group info to organize properly
        elif pred.stage == "winner":
            winner = pred.team
        elif pred.stage in stages:
            stages[pred.stage].append(pred.team)

    return BracketPrediction(
        group_winners=group_winners,
        round_of_32=stages["round_of_32"],
        round_of_16=stages["round_of_16"],
        quarter_finals=stages["quarter_finals"],
        semi_finals=stages["semi_finals"],
        final=stages["final"],
        winner=winner,
    )


@router.put("/bracket")
async def update_bracket_predictions(
    bracket_data: BracketPredictionUpdate,
    session: DbSession,
    current_user: CurrentUser,
) -> dict[str, str]:
    """Update bracket predictions for the current phase."""
    current_phase = await get_current_phase(session)

    # Clear existing bracket predictions for this user AND phase only
    # This ensures Phase 1 and Phase 2 predictions are kept separate
    statement = delete(TeamPrediction).where(
        TeamPrediction.user_id == current_user.id,
        TeamPrediction.phase == current_phase,
    )
    await session.execute(statement)

    for pred_data in bracket_data.predictions:
        prediction = TeamPrediction(
            user_id=current_user.id,
            team=pred_data.team,
            stage=pred_data.stage,
            group_position=pred_data.group_position,
            phase=current_phase,
        )
        session.add(prediction)

    await session.commit()
    return {"status": "ok"}


LOCK_MINUTES = 5


@router.get("/matches/{fixture_id}/community", response_model=CommunityPredictionsResponse)
async def get_community_predictions(
    fixture_id: uuid.UUID,
    session: DbSession,
    _user: OptionalUser,
) -> CommunityPredictionsResponse:
    """Get all players' predictions for a fixture (blind pool enforced).

    Only returns data if the fixture is locked or finished.
    """
    # Load fixture with score
    result = await session.execute(
        select(Fixture).options(selectinload(Fixture.score)).where(Fixture.id == fixture_id)
    )
    fixture = result.scalar_one_or_none()

    if not fixture:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fixture not found")

    # Blind pool enforcement: only visible after lock or when finished
    if not fixture.is_locked(LOCK_MINUTES) and fixture.status != MatchStatus.FINISHED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Predictions are not yet visible for this match",
        )

    # Query all predictions for this fixture with user names
    result = await session.execute(
        select(MatchPrediction, User.name)
        .join(User, MatchPrediction.user_id == User.id)
        .where(MatchPrediction.fixture_id == fixture_id)
    )
    rows = result.all()

    predictions = [
        CommunityPrediction(
            user_name=user_name,
            home_score=pred.home_score,
            away_score=pred.away_score,
        )
        for pred, user_name in rows
    ]

    # Build actual score if available
    actual = None
    if fixture.status == MatchStatus.FINISHED and fixture.score:
        actual = FixtureScore(
            home_score=fixture.score.home_score,
            away_score=fixture.score.away_score,
            home_score_et=fixture.score.home_score_et,
            away_score_et=fixture.score.away_score_et,
            home_penalties=fixture.score.home_penalties,
            away_penalties=fixture.score.away_penalties,
            outcome=fixture.score.outcome,
        )

    return CommunityPredictionsResponse(
        fixture_id=fixture.id,
        home_team=fixture.home_team,
        away_team=fixture.away_team,
        predictions=predictions,
        actual=actual,
    )
