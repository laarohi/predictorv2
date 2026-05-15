"""Predictions API routes."""

import uuid
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import selectinload
from sqlmodel import select, delete

from app.dependencies import CurrentUser, DbSession, OptionalUser
from app.models._datetime import utc_now
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
from app.models.bonus import BonusPrediction
from app.services.bonus import BonusQuestion, get_questions as get_bonus_questions
from app.services.bracket_exposure import compute_bracket_exposure
from app.services.locking import check_fixture_locked, get_current_phase, is_phase1_locked

router = APIRouter()


class BonusQuestionResponse(BaseModel):
    """A bonus question as rendered for the wizard/admin UI."""

    id: str
    category: str  # 'group_stage' | 'top_flop' | 'awards'
    label: str
    input_type: str  # 'team' | 'player'
    points: int


class BonusPredictionResponse(BaseModel):
    """One user's answer to one bonus question."""

    question_id: str
    answer: str


class BonusPredictionUpdate(BaseModel):
    """Payload for upserting a single bonus pick."""

    question_id: str
    answer: str


class BonusPredictionBatch(BaseModel):
    """Payload for upserting multiple bonus picks at once."""

    predictions: list[BonusPredictionUpdate]


class BracketExposureResponse(BaseModel):
    """How many bracket points the calling user still has on the line."""

    points_available: int
    picks_locked: int
    picks_total: int
    # The user's predicted finalists (FIFA 3-letter codes are produced
    # client-side from team names via teamCodes.ts).
    final_winner: str | None
    final_opponent: str | None


class FixtureAgreement(BaseModel):
    """Per-fixture agreement counts vs the calling user's pick.

    All three counts include the calling user themselves where applicable.
    """

    fixture_id: uuid.UUID
    # How many users (including caller) made the exact same score prediction.
    agrees_exact: int
    # How many picked the same outcome (1 / X / 2).
    agrees_outcome: int
    # Total users who made any prediction on this fixture.
    total: int


def _outcome_sign(home: int, away: int) -> int:
    """Returns 1 (home win), 0 (draw), or -1 (away win)."""
    if home > away:
        return 1
    if home < away:
        return -1
    return 0


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
        prediction.updated_at = utc_now()
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
            prediction.updated_at = utc_now()
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


@router.get("/bonus/questions", response_model=list[BonusQuestionResponse])
async def get_bonus_questions_route(
    _user: CurrentUser,
) -> list[BonusQuestionResponse]:
    """Return the list of bonus questions (loaded from worldcup2026.yml).

    Labels have {top_n} already substituted with the configured value.
    Points are per-category. Frontend renders these as the wizard's Bonus
    tab; question IDs are stable strings used as upsert keys for picks.
    """
    qs = get_bonus_questions()
    return [
        BonusQuestionResponse(
            id=q.id,
            category=q.category,
            label=q.label,
            input_type=q.input_type,
            points=q.points,
        )
        for q in qs
    ]


@router.get("/bonus", response_model=list[BonusPredictionResponse])
async def get_my_bonus_predictions(
    session: DbSession,
    current_user: CurrentUser,
) -> list[BonusPredictionResponse]:
    """The calling user's current bonus picks. Empty list if none saved yet."""
    result = await session.execute(
        select(BonusPrediction).where(BonusPrediction.user_id == current_user.id)
    )
    return [
        BonusPredictionResponse(question_id=p.question_id, answer=p.answer)
        for p in result.scalars().all()
    ]


@router.post("/bonus", response_model=list[BonusPredictionResponse])
async def save_bonus_predictions(
    payload: BonusPredictionBatch,
    session: DbSession,
    current_user: CurrentUser,
) -> list[BonusPredictionResponse]:
    """Upsert the calling user's bonus picks. Locks with Phase 1 — once the
    phase1_deadline passes, this endpoint returns 403.

    Unknown question_ids are silently ignored (defends against YAML edits
    that remove or rename a question). Empty `answer` strings delete the
    prediction so users can clear an unwanted pick.
    """
    if await is_phase1_locked(session):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bonus predictions are locked",
        )

    valid_ids = {q.id for q in get_bonus_questions()}

    # Load existing predictions in one query for upsert.
    existing_rows = (
        await session.execute(
            select(BonusPrediction).where(BonusPrediction.user_id == current_user.id)
        )
    ).scalars().all()
    by_qid: dict[str, BonusPrediction] = {p.question_id: p for p in existing_rows}

    for update in payload.predictions:
        if update.question_id not in valid_ids:
            continue
        existing = by_qid.get(update.question_id)
        clean_answer = update.answer.strip()
        if not clean_answer:
            # Empty string → delete the prediction.
            if existing is not None:
                await session.delete(existing)
            continue
        if existing is not None:
            existing.answer = clean_answer
            existing.updated_at = utc_now()
        else:
            session.add(
                BonusPrediction(
                    user_id=current_user.id,
                    question_id=update.question_id,
                    answer=clean_answer,
                )
            )
    await session.commit()

    # Re-read for return
    refreshed = (
        await session.execute(
            select(BonusPrediction).where(BonusPrediction.user_id == current_user.id)
        )
    ).scalars().all()
    return [
        BonusPredictionResponse(question_id=p.question_id, answer=p.answer)
        for p in refreshed
    ]


@router.get("/bracket-exposure", response_model=BracketExposureResponse)
async def get_bracket_exposure(
    session: DbSession,
    current_user: CurrentUser,
    phase: str = "phase_1",
) -> BracketExposureResponse:
    """How many bracket points the calling user still has on the line.

    Replaces stubBracketExposure on the dashboard. Currently returns the
    MAXIMUM exposure (sum of stage points for all picks, assuming none of
    the teams have been eliminated). When match results start coming in,
    this can subtract picks whose team was knocked out — that's a deferred
    follow-up tied to live-scores wiring.
    """
    phase_enum = PredictionPhase.PHASE_2 if phase == "phase_2" else PredictionPhase.PHASE_1
    result = await compute_bracket_exposure(session, current_user.id, phase_enum)
    return BracketExposureResponse(
        points_available=result.points_available,
        picks_locked=result.picks_locked,
        picks_total=result.picks_total,
        final_winner=result.final_winner,
        final_opponent=result.final_opponent,
    )


@router.get("/agreements", response_model=list[FixtureAgreement])
async def get_agreements(
    session: DbSession,
    current_user: CurrentUser,
    fixture_ids: list[uuid.UUID] | None = Query(default=None),
) -> list[FixtureAgreement]:
    """Per-fixture agreement counts vs the calling user's pick.

    For each requested fixture (or all the user has predicted, if no ids
    supplied), return how many other users made the same exact score and
    how many made the same outcome (1/X/2).

    Privacy: only counts are returned, never individual picks. Counts are
    computed *relative to the caller's own pick*, so revealing them pre-lock
    cannot leak any other user's prediction. The caller's own pick is
    already known to them.

    Empty list if the caller hasn't predicted any of the requested fixtures.
    """
    # 1. Caller's predictions for the requested fixtures (or all if none specified).
    user_preds_q = select(MatchPrediction).where(MatchPrediction.user_id == current_user.id)
    if fixture_ids:
        user_preds_q = user_preds_q.where(MatchPrediction.fixture_id.in_(fixture_ids))
    user_preds_result = await session.execute(user_preds_q)
    user_preds: dict[uuid.UUID, MatchPrediction] = {
        p.fixture_id: p for p in user_preds_result.scalars().all()
    }
    if not user_preds:
        return []

    # 2. All predictions for those fixtures, in one query.
    relevant_ids = list(user_preds.keys())
    all_preds_result = await session.execute(
        select(MatchPrediction).where(MatchPrediction.fixture_id.in_(relevant_ids))
    )
    by_fixture: dict[uuid.UUID, list[MatchPrediction]] = defaultdict(list)
    for p in all_preds_result.scalars().all():
        by_fixture[p.fixture_id].append(p)

    # 3. Aggregate per-fixture in Python.
    out: list[FixtureAgreement] = []
    for fixture_id, my_pred in user_preds.items():
        my_h, my_a = my_pred.home_score, my_pred.away_score
        my_sign = _outcome_sign(my_h, my_a)
        preds = by_fixture[fixture_id]
        exact = sum(1 for p in preds if p.home_score == my_h and p.away_score == my_a)
        outcome = sum(1 for p in preds if _outcome_sign(p.home_score, p.away_score) == my_sign)
        out.append(
            FixtureAgreement(
                fixture_id=fixture_id,
                agrees_exact=exact,
                agrees_outcome=outcome,
                total=len(preds),
            )
        )
    return out
