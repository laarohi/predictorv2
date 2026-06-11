"""Predictions API routes."""

import time
import uuid
from collections import defaultdict
from datetime import date

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from sqlmodel import select, delete

from app.dependencies import CurrentUser, DbSession, OptionalUser, RequestCtx
from app.models._datetime import utc_now
from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction, PredictionPhase, TeamPrediction
from app.models.prediction_history import PredictionAction, PredictionSource
from app.models.user import User
from app.schemas.fixture import FixtureScore
from app.schemas.prediction import (
    BracketOverviewResponse,
    BracketOverviewTeamRow,
    BracketPrediction,
    BracketPredictionUpdate,
    CommunityPrediction,
    CommunityPredictionsResponse,
    GroupsOverviewResponse,
    MatchPredictionCreate,
    MatchPredictionRead,
    MatchPredictionUpdate,
    OverviewCountCell,
    OverviewFixtureRow,
    OverviewGroup,
    OverviewTeamRow,
)
from app.models.bonus import BonusPrediction
from app.models.player import Player
from app.services.bonus import (
    BonusQuestion,
    fetch_competition_teams,
    get_fifa_rankings,
    get_questions as get_bonus_questions,
)
from app.services.bracket_consistency import validate_phase1_bracket
from app.services.bracket_exposure import compute_bracket_exposure
from app.services.locking import (
    check_fixture_locked,
    get_current_phase,
    get_fixture_lock_view,
    is_phase1_locked,
    is_phase2_bracket_locked,
)
from app.services.prediction_history import (
    record_bonus_prediction_change,
    record_match_prediction_change,
    record_team_prediction_change,
    snapshot_bonus,
    snapshot_match,
    snapshot_team,
)
from app.services.standings import get_predicted_group_standings

router = APIRouter()


class BonusQuestionResponse(BaseModel):
    """A bonus question as rendered for the wizard/admin UI."""

    id: str
    category: str  # 'group_stage' | 'top_flop' | 'awards'
    label: str
    input_type: str  # 'team' | 'player'
    points: int
    # For team-input questions with a YAML cutoff (currently dark_horse and
    # flop), the pre-filtered list of competition teams the user is allowed
    # to pick from. The frontend filters its dropdown to just these teams.
    # None for questions without a cutoff or non-team inputs.
    eligible_teams: list[str] | None = None


class BonusPlayerResponse(BaseModel):
    """One squad player, used to back the award-question dropdowns.

    `value` is the canonical string written into bonus_predictions.answer when
    picked, so it matches the admin's correct answer exactly under scoring's
    normalized comparison. The frontend filters the full list client-side:
    Golden Glove → position == 'GK', Golden Boot → position != 'GK', Golden Boy
    → date_of_birth on/after the U21 cutoff. Golden Ball uses the full list.
    """

    full_name: str
    surname: str
    country: str
    country_code: str | None = None
    position: str
    date_of_birth: date | None = None


class BonusPredictionResponse(BaseModel):
    """One user's answer to one bonus question."""

    question_id: str
    answer: str


class BonusPredictionUpdate(BaseModel):
    """Payload for upserting a single bonus pick."""

    question_id: str
    answer: str = Field(max_length=100)


class BonusPredictionBatch(BaseModel):
    """Payload for upserting multiple bonus picks at once."""

    # There are ~12 bonus questions; cap generously to reject oversized batches.
    predictions: list[BonusPredictionUpdate] = Field(max_length=50)


class StageCellResponse(BaseModel):
    """One earned/available cell on the Scoring Journey grid."""

    n: int
    of: int
    pts: int
    teams: list[str]


class StageRowResponse(BaseModel):
    """One row of the Scoring Journey (a single KO destination stage)."""

    earned: StageCellResponse
    available: StageCellResponse


class BracketExposureResponse(BaseModel):
    """How many bracket points the calling user still has on the line."""

    points_available: int
    picks_locked: int
    picks_total: int
    # The user's predicted finalists (FIFA 3-letter codes are produced
    # client-side from team names via teamCodes.ts).
    final_winner: str | None
    final_opponent: str | None
    # Per-stage alive counts for the legacy DwBracketAlive widget.
    # alive_per_stage[stage] = count of user's picks at that stage that
    # are teams that actually made it to (or past) that stage.
    # teams_per_stage[stage] = total teams competing at that stage
    # (denominator for the dashboard table). Stages: round_of_16,
    # quarter_final, semi_final, final, winner.
    alive_per_stage: dict[str, int] = {}
    teams_per_stage: dict[str, int] = {}
    # v4 per-stage breakdown — drives DwScoringJourney. Each stage gets
    # an `earned` + `available` cell with progressive denominators (the
    # `of` field). See services/bracket_exposure.py for the algorithm.
    per_stage: dict[str, StageRowResponse] = {}


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
    phase1_locked = await is_phase1_locked(session)

    predictions = []
    for pred, fixture in rows:
        locked, _ = await get_fixture_lock_view(
            session, fixture, phase1_locked=phase1_locked
        )
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
                is_locked=locked,
            )
        )

    return predictions


@router.put("/matches/{fixture_id}", response_model=MatchPredictionRead)
async def update_match_prediction(
    fixture_id: uuid.UUID,
    prediction_data: MatchPredictionUpdate,
    session: DbSession,
    current_user: CurrentUser,
    ctx: RequestCtx,
) -> MatchPredictionRead:
    """Update a single match prediction."""
    # Get fixture
    result = await session.execute(select(Fixture).where(Fixture.id == fixture_id))
    fixture = result.scalar_one_or_none()

    if not fixture:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fixture not found")

    # Phase 1 group-stage matches lock en-masse at competition.phase1_deadline,
    # well before any group match kicks off. Without this check the per-fixture
    # T-lock window below would still admit edits in the gap between the Phase 1
    # deadline and the match's kickoff.
    if fixture.stage == "group" and await is_phase1_locked(session):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Phase 1 predictions are locked",
        )

    # Per-match lock (Phase 2 knockout matches only, in practice).
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

    # A match prediction's `phase` is determined by the fixture's stage —
    # group fixtures are Phase 1, knockout fixtures are Phase 2. Do NOT
    # derive from `get_current_phase` (the global "what UI is active"
    # flag) — that would tag group-match predictions PHASE_2 if the
    # global state was already Phase 2 when the user saved, which then
    # excludes them from Phase 1 audit and receipt views.
    prediction_phase = (
        PredictionPhase.PHASE_1 if fixture.stage == "group" else PredictionPhase.PHASE_2
    )

    if prediction:
        old_values = snapshot_match(prediction)
        prediction.home_score = prediction_data.home_score
        prediction.away_score = prediction_data.away_score
        prediction.updated_at = utc_now()
        new_values = snapshot_match(prediction)
        record_match_prediction_change(
            session,
            prediction=prediction,
            old_values=old_values,
            new_values=new_values,
            action=PredictionAction.UPDATE,
            source=PredictionSource.API_SINGLE,
            performed_by_user_id=current_user.id,
            ctx=ctx,
        )
    else:
        prediction = MatchPrediction(
            user_id=current_user.id,
            fixture_id=fixture_id,
            home_score=prediction_data.home_score,
            away_score=prediction_data.away_score,
            phase=prediction_phase,
        )
        session.add(prediction)
        # Flush so prediction.id is populated for the history row's entity_id.
        await session.flush()
        record_match_prediction_change(
            session,
            prediction=prediction,
            old_values=None,
            new_values=snapshot_match(prediction),
            action=PredictionAction.INSERT,
            source=PredictionSource.API_SINGLE,
            performed_by_user_id=current_user.id,
            ctx=ctx,
        )

    await session.commit()
    await session.refresh(prediction)

    locked, _ = await get_fixture_lock_view(session, fixture)
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
        is_locked=locked,
    )


@router.post("/matches/batch", response_model=list[MatchPredictionRead])
async def batch_update_predictions(
    predictions_data: list[MatchPredictionCreate],
    session: DbSession,
    current_user: CurrentUser,
    ctx: RequestCtx,
) -> list[MatchPredictionRead]:
    """Batch update multiple match predictions."""
    # Cap well above the ~104 tournament fixtures: each entry costs two DB
    # queries, so an unbounded payload is a trivial DoS vector.
    if len(predictions_data) > 200:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Too many predictions in one batch (max 200)",
        )

    results = []
    phase1_locked = await is_phase1_locked(session)

    for pred_data in predictions_data:
        # Get fixture
        result = await session.execute(select(Fixture).where(Fixture.id == pred_data.fixture_id))
        fixture = result.scalar_one_or_none()

        if not fixture:
            continue  # Skip invalid fixtures

        # Phase 1 group-stage matches lock en-masse at phase1_deadline.
        if fixture.stage == "group" and phase1_locked:
            continue

        # Per-match lock.
        if check_fixture_locked(fixture):
            continue  # Skip locked fixtures

        # Derive phase from the fixture, not from global state — see the
        # corresponding note in update_match_prediction.
        prediction_phase = (
            PredictionPhase.PHASE_1 if fixture.stage == "group" else PredictionPhase.PHASE_2
        )

        # Get existing prediction or create new
        result = await session.execute(
            select(MatchPrediction).where(
                MatchPrediction.user_id == current_user.id,
                MatchPrediction.fixture_id == pred_data.fixture_id,
            )
        )
        prediction = result.scalar_one_or_none()

        if prediction:
            old_values = snapshot_match(prediction)
            prediction.home_score = pred_data.home_score
            prediction.away_score = pred_data.away_score
            prediction.updated_at = utc_now()
            new_values = snapshot_match(prediction)
            record_match_prediction_change(
                session,
                prediction=prediction,
                old_values=old_values,
                new_values=new_values,
                action=PredictionAction.UPDATE,
                source=PredictionSource.API_BATCH,
                performed_by_user_id=current_user.id,
                ctx=ctx,
            )
        else:
            prediction = MatchPrediction(
                user_id=current_user.id,
                fixture_id=pred_data.fixture_id,
                home_score=pred_data.home_score,
                away_score=pred_data.away_score,
                phase=prediction_phase,
            )
            session.add(prediction)
            # Flush so prediction.id is set before we record the history row.
            await session.flush()
            record_match_prediction_change(
                session,
                prediction=prediction,
                old_values=None,
                new_values=snapshot_match(prediction),
                action=PredictionAction.INSERT,
                source=PredictionSource.API_BATCH,
                performed_by_user_id=current_user.id,
                ctx=ctx,
            )

        await session.flush()
        await session.refresh(prediction)

        locked, _ = await get_fixture_lock_view(
            session, fixture, phase1_locked=phase1_locked
        )
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
                is_locked=locked,
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

    # Organize predictions into bracket structure. Stored stage values are
    # singular (matching Fixture.stage + scoring); the BracketPrediction
    # response fields are plural for QF/SF as a frontend display convention.
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
    ctx: RequestCtx,
) -> dict[str, str]:
    """Update bracket predictions for the current phase.

    Destructive: clears the user's existing bracket rows for this phase
    and re-inserts. To keep the audit log complete we SELECT before
    DELETE so we can record one history row per removed pick (otherwise
    the bulk delete would tell us "N rows gone" but not which teams).
    """
    current_phase = await get_current_phase(session)

    # Each phase's bracket has its own deadline. After it passes, the rewrite
    # path (delete-all-then-insert) must be refused — otherwise a user could
    # erase their locked picks post-deadline and replace them.
    if current_phase == PredictionPhase.PHASE_1 and await is_phase1_locked(session):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Phase 1 predictions are locked",
        )
    if current_phase == PredictionPhase.PHASE_2 and await is_phase2_bracket_locked(session):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Phase 2 bracket predictions are locked",
        )

    # Phase 1 brackets derive from the user's predicted group standings —
    # reject payloads that contradict them (stale client, manual API use).
    # The schema validator above only checks shape; this checks meaning.
    # See services/bracket_consistency.py for what is (and isn't) enforced.
    if current_phase == PredictionPhase.PHASE_1:
        problems = await validate_phase1_bracket(
            session, current_user.id, bracket_data.predictions
        )
        if problems:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    "Bracket is inconsistent with your saved group predictions "
                    "— reload the page and re-save. (" + " | ".join(problems) + ")"
                ),
            )

    # Load existing picks for history capture before we delete them.
    existing_result = await session.execute(
        select(TeamPrediction).where(
            TeamPrediction.user_id == current_user.id,
            TeamPrediction.phase == current_phase,
        )
    )
    existing_predictions = existing_result.scalars().all()

    for existing in existing_predictions:
        record_team_prediction_change(
            session,
            user_id=existing.user_id,
            team=existing.team,
            stage=existing.stage,
            entity_id=existing.id,
            old_values=snapshot_team(existing),
            new_values=None,
            action=PredictionAction.DELETE,
            source=PredictionSource.API_BRACKET_REWRITE,
            performed_by_user_id=current_user.id,
            ctx=ctx,
        )

    # Clear existing bracket predictions for this user AND phase only.
    # Phase 1 and Phase 2 predictions are kept separate.
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
        # Flush so prediction.id is populated before we capture history.
        await session.flush()
        record_team_prediction_change(
            session,
            user_id=prediction.user_id,
            team=prediction.team,
            stage=prediction.stage,
            entity_id=prediction.id,
            old_values=None,
            new_values=snapshot_team(prediction),
            action=PredictionAction.INSERT,
            source=PredictionSource.API_BRACKET_REWRITE,
            performed_by_user_id=current_user.id,
            ctx=ctx,
        )

    await session.commit()
    return {"status": "ok"}


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

    # Blind pool enforcement: only visible after lock or when finished. For
    # Phase 1 group fixtures, "locked" means phase1_deadline has passed —
    # they become visible the moment Phase 1 closes, not 15 min before each
    # kickoff. get_fixture_lock_view encodes this rule.
    locked, _ = await get_fixture_lock_view(session, fixture)
    if not locked and fixture.status != MatchStatus.FINISHED:
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


# ---------------------------------------------------------------------------
# Overview — "who predicted what" aggregates. Same blind-pool philosophy as
# the community endpoint above, but bulk: one call paints a whole page.
#
# The prediction-derived aggregates are immutable once their phase locks
# (and the endpoints 403 before that), so they're cached in-process with a
# TTL. Only fixture status/scores change after lock — those are re-read
# fresh on every request and merged over the cached counts.
# ---------------------------------------------------------------------------

_KO_STAGES = (
    "round_of_32",
    "round_of_16",
    "quarter_final",
    "semi_final",
    "final",
    "winner",
)

# TTL covers the rare post-lock mutation (an admin correcting a prediction);
# regular users cannot change anything these aggregates read after lock.
_OVERVIEW_CACHE_TTL_SECONDS = 300.0
_overview_cache: dict[str, tuple[float, object]] = {}


def _overview_cache_get(key: str):
    hit = _overview_cache.get(key)
    if hit is not None and (time.monotonic() - hit[0]) < _OVERVIEW_CACHE_TTL_SECONDS:
        return hit[1]
    return None


def _overview_cache_put(key: str, value: object) -> None:
    _overview_cache[key] = (time.monotonic(), value)


def _count_cell(names: list[str]) -> OverviewCountCell:
    return OverviewCountCell(count=len(names), users=sorted(names, key=str.casefold))


async def _build_groups_aggregates(session: DbSession) -> dict:
    """The expensive, prediction-derived half of the groups overview.

    Returns {total_predictors, outcome_counts, team_rows_by_group} — all
    frozen once Phase 1 locks, hence cacheable.
    """
    pred_result = await session.execute(
        select(MatchPrediction, User.name)
        .join(Fixture, MatchPrediction.fixture_id == Fixture.id)
        .join(User, MatchPrediction.user_id == User.id)
        .where(
            Fixture.stage == "group",
            MatchPrediction.phase == PredictionPhase.PHASE_1,
        )
    )
    outcome_counts: dict[uuid.UUID, dict[str, int]] = defaultdict(
        lambda: {"1": 0, "X": 0, "2": 0}
    )
    predictor_names: dict[uuid.UUID, str] = {}
    for pred, user_name in pred_result.all():
        outcome_counts[pred.fixture_id][pred.predicted_outcome] += 1
        predictor_names[pred.user_id] = user_name

    # Who carries each team into their R32 (Phase 1 bracket).
    r32_result = await session.execute(
        select(TeamPrediction.team, User.name)
        .join(User, TeamPrediction.user_id == User.id)
        .where(
            TeamPrediction.stage == "round_of_32",
            TeamPrediction.phase == PredictionPhase.PHASE_1,
        )
    )
    advance_users: dict[str, list[str]] = defaultdict(list)
    for team, user_name in r32_result.all():
        advance_users[team].append(user_name)

    # Predicted finishing position (1st..4th) per team: each predictor's
    # implicit standings, derived from their score picks with the same
    # tiebreaker pipeline the group_position bonus scores against.
    position_users: dict[str, list[list[str]]] = defaultdict(
        lambda: [[], [], [], []]
    )
    for user_id, user_name in predictor_names.items():
        predicted, _ = await get_predicted_group_standings(session, user_id)
        for ranked_teams in predicted.values():
            for i, ranked in enumerate(ranked_teams[:4]):
                position_users[ranked["team"]][i].append(user_name)

    # Group membership from the fixtures table.
    fx_result = await session.execute(
        select(Fixture.group, Fixture.home_team, Fixture.away_team).where(
            Fixture.stage == "group"
        )
    )
    group_teams: dict[str, set[str]] = defaultdict(set)
    for g, home, away in fx_result.all():
        group_teams[g or "?"].update((home, away))

    team_rows_by_group: dict[str, list[OverviewTeamRow]] = {}
    for g in sorted(group_teams):
        rows = [
            OverviewTeamRow(
                team=t,
                positions=[_count_cell(names) for names in position_users[t]],
                advance=_count_cell(advance_users.get(t, [])),
            )
            for t in group_teams[g]
        ]
        rows.sort(key=lambda r: (-r.advance.count, -r.positions[0].count, r.team))
        team_rows_by_group[g] = rows

    return {
        "total_predictors": len(predictor_names),
        "outcome_counts": dict(outcome_counts),
        "team_rows_by_group": team_rows_by_group,
    }


@router.get("/overview/groups", response_model=GroupsOverviewResponse)
async def get_groups_overview(
    session: DbSession,
    _user: CurrentUser,
) -> GroupsOverviewResponse:
    """Aggregate distribution of everyone's Phase 1 group predictions.

    Per group: who put each team 1st/2nd/3rd/4th (derived from their score
    picks, exactly as the group_position bonus derives it) and who carried
    the team into their Round of 32; per fixture: the 1/X/2 split of all
    score picks plus the live status/score.

    Blind pool: 403 until the Phase 1 deadline passes. Group predictions
    lock en-masse at that moment, so afterwards the whole distribution is
    visible at once — there is no per-fixture trickle for Phase 1.
    """
    if not await is_phase1_locked(session):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The overview unlocks when Phase 1 predictions lock",
        )

    comp_result = await session.execute(
        select(Competition.id).where(Competition.is_active == True)  # noqa: E712
    )
    competition_id = comp_result.scalar_one_or_none()

    cache_key = f"overview:groups:{competition_id}"
    aggregates = _overview_cache_get(cache_key)
    if aggregates is None:
        aggregates = await _build_groups_aggregates(session)
        _overview_cache_put(cache_key, aggregates)

    # Fixture rows are rebuilt fresh every request: status and actual
    # scores keep moving during match days even though the picks don't.
    fx_result = await session.execute(
        select(Fixture)
        .options(selectinload(Fixture.score))
        .where(Fixture.stage == "group")
        .order_by(Fixture.kickoff)
    )
    fixtures_by_group: dict[str, list[Fixture]] = defaultdict(list)
    for f in fx_result.scalars().all():
        fixtures_by_group[f.group or "?"].append(f)

    outcome_counts = aggregates["outcome_counts"]
    groups: list[OverviewGroup] = []
    for g, team_rows in aggregates["team_rows_by_group"].items():
        fixture_rows = []
        for f in fixtures_by_group.get(g, []):
            oc = outcome_counts.get(f.id, {"1": 0, "X": 0, "2": 0})
            fixture_rows.append(
                OverviewFixtureRow(
                    fixture_id=f.id,
                    home_team=f.home_team,
                    away_team=f.away_team,
                    kickoff=f.kickoff,
                    status=f.status,
                    home_count=oc["1"],
                    draw_count=oc["X"],
                    away_count=oc["2"],
                    actual_home=f.score.home_score if f.score else None,
                    actual_away=f.score.away_score if f.score else None,
                )
            )
        groups.append(OverviewGroup(group=g, teams=team_rows, fixtures=fixture_rows))

    return GroupsOverviewResponse(
        total_predictors=aggregates["total_predictors"], groups=groups
    )


@router.get("/overview/bracket", response_model=BracketOverviewResponse)
async def get_bracket_overview(
    session: DbSession,
    _user: CurrentUser,
    phase: int = Query(default=1, ge=1, le=2),
) -> BracketOverviewResponse:
    """Who (and how many) predicted each team to reach each knockout stage.

    Phase 1 unlocks at the Phase 1 deadline; Phase 2 at the Phase 2
    bracket deadline (admin-set when activating Phase 2). Fully immutable
    once visible, so the whole response is cached.
    """
    if phase == 1:
        if not await is_phase1_locked(session):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="The overview unlocks when Phase 1 predictions lock",
            )
        pred_phase = PredictionPhase.PHASE_1
    else:
        if not await is_phase2_bracket_locked(session):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="The Phase 2 overview unlocks when the Phase 2 bracket locks",
            )
        pred_phase = PredictionPhase.PHASE_2

    comp_result = await session.execute(
        select(Competition.id).where(Competition.is_active == True)  # noqa: E712
    )
    competition_id = comp_result.scalar_one_or_none()

    cache_key = f"overview:bracket:{competition_id}:{phase}"
    cached = _overview_cache_get(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    rows_result = await session.execute(
        select(TeamPrediction.team, TeamPrediction.stage, User.name)
        .join(User, TeamPrediction.user_id == User.id)
        .where(
            TeamPrediction.phase == pred_phase,
            TeamPrediction.stage.in_(_KO_STAGES),  # type: ignore[union-attr]
        )
    )
    stage_users: dict[str, dict[str, list[str]]] = defaultdict(
        lambda: defaultdict(list)
    )
    predictor_names: set[str] = set()
    for team, stage, user_name in rows_result.all():
        stage_users[team][stage].append(user_name)
        predictor_names.add(user_name)

    # Group letters come from the fixtures table (home/away of group games).
    fx_result = await session.execute(
        select(Fixture.group, Fixture.home_team, Fixture.away_team).where(
            Fixture.stage == "group"
        )
    )
    team_group: dict[str, str] = {}
    for g, home, away in fx_result.all():
        if g:
            team_group[home] = g
            team_group[away] = g

    all_teams = set(team_group) | set(stage_users)
    team_rows = [
        BracketOverviewTeamRow(
            team=t,
            group=team_group.get(t),
            round_of_32=_count_cell(stage_users[t].get("round_of_32", [])),
            round_of_16=_count_cell(stage_users[t].get("round_of_16", [])),
            quarter_final=_count_cell(stage_users[t].get("quarter_final", [])),
            semi_final=_count_cell(stage_users[t].get("semi_final", [])),
            final=_count_cell(stage_users[t].get("final", [])),
            winner=_count_cell(stage_users[t].get("winner", [])),
        )
        for t in all_teams
    ]
    team_rows.sort(
        key=lambda r: (
            -r.winner.count,
            -r.final.count,
            -r.semi_final.count,
            -r.quarter_final.count,
            -r.round_of_16.count,
            -r.round_of_32.count,
            r.team,
        )
    )

    response = BracketOverviewResponse(
        phase=phase, total_predictors=len(predictor_names), teams=team_rows
    )
    _overview_cache_put(cache_key, response)
    return response


@router.get("/bonus/questions", response_model=list[BonusQuestionResponse])
async def get_bonus_questions_route(
    session: DbSession,
    _user: OptionalUser,
) -> list[BonusQuestionResponse]:
    """Return the list of bonus questions (loaded from worldcup2026.yml).

    Labels have any `{n}` token substituted with the question's own
    cutoff.rank. Points are per-category. For team-input questions with a
    cutoff (currently dark_horse and flop), `eligible_teams` is the
    pre-filtered list of competition teams the user is allowed to pick —
    derived from the DB fixtures table so the list reflects real qualifiers
    rather than YAML scaffold.

    Public — the /rules page lists these for prospective joiners. Question
    definitions are config, not user data, so making this optionally-authed
    leaks nothing.
    """
    competition_teams = await fetch_competition_teams(session)
    rankings = await get_fifa_rankings(session)
    qs = get_bonus_questions(competition_teams=competition_teams, rankings=rankings)
    return [
        BonusQuestionResponse(
            id=q.id,
            category=q.category,
            label=q.label,
            input_type=q.input_type,
            points=q.points,
            eligible_teams=q.eligible_teams,
        )
        for q in qs
    ]


@router.get("/bonus/players", response_model=list[BonusPlayerResponse])
async def get_bonus_players(
    session: DbSession,
    _user: OptionalUser,
) -> list[BonusPlayerResponse]:
    """All squad players for the award-question dropdowns (Golden Ball/Boot/
    Boy/Glove), populated by scripts/sync_squads.py.

    Returns the full list (~1.2k players) sorted by surname; the frontend
    filters and fuzzy-searches client-side, so no query params are needed.
    Optionally-authed for the same reason as /bonus/questions — squad data is
    public reference, not user data. Empty list until the first squad sync.
    """
    result = await session.execute(select(Player).order_by(Player.surname, Player.full_name))
    return [
        BonusPlayerResponse(
            full_name=p.full_name,
            surname=p.surname,
            country=p.country,
            country_code=p.country_code,
            position=p.position,
            date_of_birth=p.date_of_birth,
        )
        for p in result.scalars().all()
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
    ctx: RequestCtx,
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
                record_bonus_prediction_change(
                    session,
                    user_id=existing.user_id,
                    question_id=existing.question_id,
                    entity_id=existing.id,
                    old_values=snapshot_bonus(existing),
                    new_values=None,
                    action=PredictionAction.DELETE,
                    source=PredictionSource.API_BONUS_BATCH,
                    performed_by_user_id=current_user.id,
                    ctx=ctx,
                )
                await session.delete(existing)
            continue
        if existing is not None:
            old_values = snapshot_bonus(existing)
            existing.answer = clean_answer
            existing.updated_at = utc_now()
            record_bonus_prediction_change(
                session,
                user_id=existing.user_id,
                question_id=existing.question_id,
                entity_id=existing.id,
                old_values=old_values,
                new_values=snapshot_bonus(existing),
                action=PredictionAction.UPDATE,
                source=PredictionSource.API_BONUS_BATCH,
                performed_by_user_id=current_user.id,
                ctx=ctx,
            )
        else:
            new_pred = BonusPrediction(
                user_id=current_user.id,
                question_id=update.question_id,
                answer=clean_answer,
            )
            session.add(new_pred)
            await session.flush()
            record_bonus_prediction_change(
                session,
                user_id=new_pred.user_id,
                question_id=new_pred.question_id,
                entity_id=new_pred.id,
                old_values=None,
                new_values=snapshot_bonus(new_pred),
                action=PredictionAction.INSERT,
                source=PredictionSource.API_BONUS_BATCH,
                performed_by_user_id=current_user.id,
                ctx=ctx,
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

    Used by the DwBracketAlive widget on the KO dashboard. Returns both
    the maximum exposure (points still in play) and per-stage alive
    counts (how many user picks at each stage are teams that actually
    made it there based on finished match results).
    """
    phase_enum = PredictionPhase.PHASE_2 if phase == "phase_2" else PredictionPhase.PHASE_1
    result = await compute_bracket_exposure(session, current_user.id, phase_enum)
    per_stage_response = {
        stage: StageRowResponse(
            earned=StageCellResponse(
                n=row.earned.n,
                of=row.earned.of,
                pts=row.earned.pts,
                teams=row.earned.teams,
            ),
            available=StageCellResponse(
                n=row.available.n,
                of=row.available.of,
                pts=row.available.pts,
                teams=row.available.teams,
            ),
        )
        for stage, row in result.per_stage.items()
    }
    return BracketExposureResponse(
        points_available=result.points_available,
        picks_locked=result.picks_locked,
        picks_total=result.picks_total,
        final_winner=result.final_winner,
        final_opponent=result.final_opponent,
        alive_per_stage=result.alive_per_stage,
        teams_per_stage=result.teams_per_stage,
        per_stage=per_stage_response,
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

    Privacy: only counts are returned, never individual picks, and only for
    fixtures that are already locked or finished. Counts are computed relative
    to the caller's own pick, so exposing them *before lock* would let a caller
    sweep their own score and watch the counts move to reconstruct everyone
    else's predictions (and boundary cases like agrees_exact == total leak
    outright) — so unlocked fixtures are excluded entirely.

    Empty list if the caller hasn't predicted any locked/finished fixtures.
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

    # 2. Blind pool: keep only fixtures that are already locked or finished.
    relevant_ids = list(user_preds.keys())
    fixtures_result = await session.execute(
        select(Fixture).where(Fixture.id.in_(relevant_ids))
    )
    fixtures = {f.id: f for f in fixtures_result.scalars().all()}
    phase1_locked = await is_phase1_locked(session)
    visible_ids: list[uuid.UUID] = []
    for fid in relevant_ids:
        fixture = fixtures.get(fid)
        if fixture is None:
            continue
        locked, _ = await get_fixture_lock_view(session, fixture, phase1_locked=phase1_locked)
        if locked or fixture.status == MatchStatus.FINISHED:
            visible_ids.append(fid)
    if not visible_ids:
        return []
    visible_set = set(visible_ids)

    # 3. All predictions for the visible fixtures, in one query.
    all_preds_result = await session.execute(
        select(MatchPrediction).where(MatchPrediction.fixture_id.in_(visible_ids))
    )
    by_fixture: dict[uuid.UUID, list[MatchPrediction]] = defaultdict(list)
    for p in all_preds_result.scalars().all():
        by_fixture[p.fixture_id].append(p)

    # 4. Aggregate per-fixture in Python (visible fixtures only).
    out: list[FixtureAgreement] = []
    for fixture_id, my_pred in user_preds.items():
        if fixture_id not in visible_set:
            continue
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
