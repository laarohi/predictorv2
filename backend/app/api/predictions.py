"""Predictions API routes."""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from app.dependencies import CurrentUser, DbSession
from app.models.fixture import Fixture
from app.models.prediction import MatchPrediction, PredictionPhase, TeamPrediction
from app.schemas.prediction import (
    BracketPrediction,
    BracketPredictionUpdate,
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

    current_phase = get_current_phase()

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
    current_phase = get_current_phase()

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
    session: DbSession, current_user: CurrentUser
) -> BracketPrediction | None:
    """Get bracket predictions for the current user."""
    result = await session.execute(
        select(TeamPrediction).where(TeamPrediction.user_id == current_user.id)
    )
    predictions = result.scalars().all()

    if not predictions:
        return None

    # Organize predictions into bracket structure
    group_winners: dict[str, list[str]] = {}
    stages: dict[str, list[str]] = {
        "round_of_32": [],
        "round_of_16": [],
        "quarter_final": [],
        "semi_final": [],
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
        quarter_finals=stages["quarter_final"],
        semi_finals=stages["semi_final"],
        final=stages["final"],
        winner=winner,
    )


@router.put("/bracket")
async def update_bracket_predictions(
    bracket_data: BracketPredictionUpdate,
    session: DbSession,
    current_user: CurrentUser,
) -> dict[str, str]:
    """Update bracket predictions."""
    current_phase = get_current_phase()

    for pred_data in bracket_data.predictions:
        # Check if prediction already exists
        result = await session.execute(
            select(TeamPrediction).where(
                TeamPrediction.user_id == current_user.id,
                TeamPrediction.team == pred_data.team,
                TeamPrediction.stage == pred_data.stage,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.group_position = pred_data.group_position
            existing.updated_at = datetime.utcnow()
        else:
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
