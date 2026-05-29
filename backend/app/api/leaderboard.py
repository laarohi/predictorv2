"""Leaderboard API routes."""

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.dependencies import AdminUser, CurrentUser, DbSession, OptionalUser
from app.models._datetime import utc_now
from app.schemas.leaderboard import LeaderboardResponse, PointBreakdown
from app.services.leaderboard import calculate_leaderboard, invalidate_cache
from app.services.scoring import calculate_user_points, get_scoring_config, SCORING_STRATEGIES
from app.services.snapshots import get_user_trajectory

router = APIRouter()


class RankSnapshotPoint(BaseModel):
    """One day's rank + points for a user.

    `exact_scores` and `correct_outcomes` are included so the dashboard's
    KPI row can compute day-over-day deltas (e.g. "Outcomes 18 (+2)") by
    diffing today's leaderboard against yesterday's snapshot.
    """

    position: int
    total_points: int
    exact_scores: int = 0
    correct_outcomes: int = 0
    captured_date: date


class RankTrajectoryResponse(BaseModel):
    """A user's rank trajectory over the last N days.

    `points` is oldest → newest. The final entry is the user's CURRENT live
    rank (not the last DB snapshot) — the endpoint appends it so the chart's
    most recent dot is always current, even if today's daily snapshot is
    still pending.
    """

    user_id: uuid.UUID
    points: list[RankSnapshotPoint]
    total_participants: int


class ScoringConfigResponse(BaseModel):
    """Response model for scoring configuration."""

    mode: str
    available_modes: list[str]
    match: dict[str, Any]
    advancement: dict[str, Any]


@router.get("/scoring-rules", response_model=ScoringConfigResponse)
async def get_scoring_rules() -> ScoringConfigResponse:
    """Get the current scoring configuration.

    Returns the scoring rules in effect, including:
    - Current scoring mode (fixed, hybrid, or logarithmic)
    - Available scoring modes
    - Match prediction point values
    - Advancement prediction point values (Phase 2 values are nested
      under `advancement.phase_2`)
    """
    config = get_scoring_config()
    return ScoringConfigResponse(
        mode=config.get("mode", "logarithmic"),
        available_modes=list(SCORING_STRATEGIES.keys()),
        match=config.get("match", {}),
        advancement=config.get("advancement", {}),
    )


@router.get("/", response_model=LeaderboardResponse)
async def get_leaderboard(
    session: DbSession,
    _user: OptionalUser,
    refresh: bool = Query(False, description="Force cache refresh"),
    phase: str | None = Query(None, description="Filter by phase: 'phase_1', 'phase_2', or null for overall"),
) -> LeaderboardResponse:
    """Get full leaderboard with standings.

    Uses 30-second caching for performance. Pass refresh=true to force recalculation.
    Includes correct outcomes, exact scores, and position movement tracking.

    The `phase` parameter allows filtering:
    - `null` or omitted: Overall leaderboard (sum of all phases)
    - `phase_1`: Phase 1 points only
    - `phase_2`: Phase 2 points only

    Position rankings are recalculated based on the selected phase's points.
    """
    # Validate phase parameter
    if phase is not None and phase not in ("phase_1", "phase_2"):
        phase = None  # Default to overall for invalid values

    # force_refresh bypasses the 30s cache and triggers a full recompute.
    # Restrict it to admins so a curious friend can't pin the worker by
    # hammering ?refresh=true during a live match (the cache + internal
    # invalidation already keep regular users' data fresh).
    force = refresh and _user is not None and _user.is_admin
    return await calculate_leaderboard(session, force_refresh=force, phase=phase)


@router.post("/invalidate")
async def invalidate_leaderboard_cache(_admin: AdminUser) -> dict[str, str]:
    """Invalidate the leaderboard cache (admin only).

    Score and admin writes already invalidate the cache internally, so this is
    just a manual escape hatch. Gated to admins so it can't be used as an
    unauthenticated way to force cache rebuilds.
    """
    invalidate_cache()
    return {"status": "cache invalidated"}


@router.get("/breakdown/{user_id}")
async def get_user_breakdown(
    user_id: uuid.UUID, session: DbSession, _user: OptionalUser
) -> PointBreakdown:
    """Get detailed point breakdown for a user."""
    return await calculate_user_points(session, user_id)


async def _build_trajectory(
    session: DbSession,
    user_id: uuid.UUID,
    days: int,
    all_time: bool = False,
) -> RankTrajectoryResponse:
    """Shared implementation for the two trajectory endpoints. Pulls the
    user's snapshot history then appends the current live rank as the
    last point so the chart's tip is always up to date.

    When `all_time` is True, the `days` parameter is ignored and the full
    snapshot history is returned. Used by the post-competition dashboard's
    DwFinalPosition widget to derive the user's peak rank across the
    entire tournament.
    """
    snaps = await get_user_trajectory(session, user_id, days=days, all_time=all_time)
    live = await calculate_leaderboard(session, phase=None)
    live_entry = next((e for e in live.entries if e.user_id == user_id), None)

    points = [
        RankSnapshotPoint(
            position=s.position,
            total_points=s.total_points,
            exact_scores=s.exact_scores,
            correct_outcomes=s.correct_outcomes,
            captured_date=s.captured_date,
        )
        for s in snaps
    ]
    if live_entry is not None:
        live_point = RankSnapshotPoint(
            position=live_entry.position,
            total_points=live_entry.total_points,
            exact_scores=live_entry.exact_scores,
            correct_outcomes=live_entry.correct_outcomes,
            # UTC to match the snapshot write path; date.today() uses the
            # server's local calendar and can land on the wrong day, making
            # the live point overwrite/append against the wrong snapshot.
            captured_date=utc_now().date(),
        )
        # If the last snapshot is from today, overwrite it with the live
        # value so the chart doesn't show stale data for the current day.
        if points and points[-1].captured_date == live_point.captured_date:
            points[-1] = live_point
        else:
            points.append(live_point)

    return RankTrajectoryResponse(
        user_id=user_id,
        points=points,
        total_participants=live.total_participants,
    )


@router.get("/snapshots/me", response_model=RankTrajectoryResponse)
async def get_my_trajectory(
    session: DbSession,
    user: CurrentUser,
    days: int = Query(7, ge=2, le=365),
    all_time: bool = Query(False),
) -> RankTrajectoryResponse:
    """Rank trajectory for the current user, last `days` days (default 7).

    When `all_time=true`, returns the user's full snapshot history and the
    `days` parameter is ignored. Used by the post-comp dashboard's
    DwFinalPosition widget to compute peak rank across the whole tournament.

    Returned points are oldest → newest; the final point is always the
    user's live current rank, not the most recent stored snapshot.
    """
    return await _build_trajectory(session, user.id, days, all_time=all_time)


# ---------------------------------------------------------------------------
# Tournament winner pickers
# ---------------------------------------------------------------------------


class TournamentWinnerPickers(BaseModel):
    """Per-phase counts of users who picked the actual tournament winner.

    Used by the post-competition dashboard's DwChampionPodium widget for
    the "N of M picked it correctly" line beneath the podium. The
    `actual_winner` field is the team that won the FINAL fixture; null if
    the final hasn't been played or marked finished yet.
    """

    actual_winner: str | None
    phase1_picker_count: int
    phase2_picker_count: int
    total_phase1_predictors: int
    total_phase2_predictors: int


@router.get("/tournament-winner", response_model=TournamentWinnerPickers)
async def get_tournament_winner_pickers(
    session: DbSession,
    _user: CurrentUser,
) -> TournamentWinnerPickers:
    """Return how many users picked the actual tournament winner.

    Computes:
    - actual_winner: the team that won the FINAL fixture (null if final
      hasn't been played or marked finished)
    - phase1_picker_count, phase2_picker_count: how many users had that
      team as their `winner` stage pick in each phase
    - total_phase1_predictors, total_phase2_predictors: how many users
      made ANY winner pick in each phase (the denominator)
    """
    from sqlmodel import func, select  # local import — avoid widening top-level
    from app.models.fixture import Fixture, MatchStatus
    from app.models.prediction import PredictionPhase, TeamPrediction
    from app.models.score import Score

    # Step 1: find the actual tournament winner from the FINAL fixture's score
    result = await session.execute(
        select(Fixture, Score)
        .join(Score, Score.fixture_id == Fixture.id)
        .where(Fixture.stage == "final")
        .where(Fixture.status == MatchStatus.FINISHED)
        .limit(1)
    )
    final_row = result.first()
    actual_winner: str | None = None
    if final_row:
        fixture, score = final_row
        # Score.outcome is "1" (home wins), "X" (draw), "2" (away wins).
        # A KO final can't end in a draw, but extra-time / penalty rules
        # are honoured by the outcome field (the scorer resolves them).
        if score.outcome == "1":
            actual_winner = fixture.home_team
        elif score.outcome == "2":
            actual_winner = fixture.away_team
        # Outcome "X" leaves actual_winner=None (shouldn't happen for a
        # finished KO match, but defensive).

    # Step 2: count predictors per phase for the winner stage
    async def _count_for_phase(phase: PredictionPhase) -> tuple[int, int]:
        # Total predictors who made any winner pick in this phase
        total_result = await session.execute(
            select(func.count(func.distinct(TeamPrediction.user_id)))
            .where(TeamPrediction.stage == "winner")
            .where(TeamPrediction.phase == phase)
        )
        total = total_result.scalar() or 0

        # Picker count for the actual winner (0 if no winner yet)
        picker = 0
        if actual_winner is not None:
            picker_result = await session.execute(
                select(func.count(func.distinct(TeamPrediction.user_id)))
                .where(TeamPrediction.stage == "winner")
                .where(TeamPrediction.phase == phase)
                .where(TeamPrediction.team == actual_winner)
            )
            picker = picker_result.scalar() or 0
        return picker, total

    p1_picker, p1_total = await _count_for_phase(PredictionPhase.PHASE_1)
    p2_picker, p2_total = await _count_for_phase(PredictionPhase.PHASE_2)

    return TournamentWinnerPickers(
        actual_winner=actual_winner,
        phase1_picker_count=p1_picker,
        phase2_picker_count=p2_picker,
        total_phase1_predictors=p1_total,
        total_phase2_predictors=p2_total,
    )


# ---------------------------------------------------------------------------
# Personal highlights (post-comp retrospective)
# ---------------------------------------------------------------------------


class StreakHighlight(BaseModel):
    """The user's best run of consecutive exact-score match predictions.

    `count` is the run length. `fixture_ids` lists the fixtures in that run
    (oldest → newest) so the frontend can deep-link if needed.
    """

    count: int
    fixture_ids: list[uuid.UUID]


class ClimbHighlight(BaseModel):
    """The biggest positive rank change between two adjacent snapshot days.

    `places` is positive when the user climbed. `captured_date` is the day
    of the better (newer) snapshot.
    """

    places: int
    captured_date: date
    from_position: int
    to_position: int


class ContrarianHighlight(BaseModel):
    """An exact-score prediction where the user was correct AND the fewest
    other users matched their pick — the "I called it and no one else did"
    moment.
    """

    fixture_id: uuid.UUID
    home_team: str
    away_team: str
    actual_score: str  # "2-1"
    user_pick: str  # "2-1"
    agrees_exact: int  # includes the user
    total: int  # total predictors for the fixture


class PhaseHighlight(BaseModel):
    """Which phase yielded the user the most points."""

    phase: str  # "phase_1" or "phase_2"
    points: int


class MyHighlights(BaseModel):
    """Retrospective stats for the calling user — drives the DwHighlights
    widget on the post-competition dashboard. Any field may be null if
    insufficient data exists to compute it (no finished matches yet, no
    snapshot history, etc.)."""

    best_exact_streak: StreakHighlight | None
    biggest_climb: ClimbHighlight | None
    most_contrarian_correct: ContrarianHighlight | None
    best_phase: PhaseHighlight | None


def _outcome_sign(home: int, away: int) -> str:
    """1 home wins, X draw, 2 away wins. Mirrors predictions.py:_outcome_sign."""
    if home > away:
        return "1"
    if home == away:
        return "X"
    return "2"


@router.get("/me/highlights", response_model=MyHighlights)
async def get_my_highlights(
    session: DbSession,
    user: CurrentUser,
) -> MyHighlights:
    """Personal retrospective stats for the post-competition dashboard.

    Computes four highlights from existing data:
    1. **best_exact_streak**: longest run of consecutive exact-score
       predictions on finished matches (ordered by kickoff).
    2. **biggest_climb**: largest positive between-day rank change from
       the user's snapshot history.
    3. **most_contrarian_correct**: the exact-score hit with the lowest
       agreement ratio (you nailed a score no one else did).
    4. **best_phase**: which phase yielded more points.

    Any field is null when there isn't enough data yet (no finished
    matches, no snapshot history, no exact hits, no points).
    """
    from collections import defaultdict
    from sqlmodel import select
    from app.models.fixture import Fixture, MatchStatus
    from app.models.prediction import MatchPrediction
    from app.models.score import Score
    from app.services.scoring import calculate_user_points

    # --- best_exact_streak + most_contrarian_correct ------------------------
    # Pull all of the user's match predictions for finished fixtures, joined
    # with the actual scores, ordered by kickoff. Same query feeds both
    # computations to avoid round-trips.
    result = await session.execute(
        select(Fixture, MatchPrediction, Score)
        .join(MatchPrediction, MatchPrediction.fixture_id == Fixture.id)
        .join(Score, Score.fixture_id == Fixture.id)
        .where(MatchPrediction.user_id == user.id)
        .where(Fixture.status == MatchStatus.FINISHED)
        .order_by(Fixture.kickoff.asc())
    )
    rows: list[tuple[Fixture, MatchPrediction, Score]] = list(result.all())

    # Streak
    best_count = 0
    best_run_ids: list[uuid.UUID] = []
    cur_count = 0
    cur_run_ids: list[uuid.UUID] = []
    exact_hits: list[tuple[Fixture, MatchPrediction, Score]] = []
    for fixture, pred, score in rows:
        is_exact = pred.home_score == score.home_score and pred.away_score == score.away_score
        if is_exact:
            cur_count += 1
            cur_run_ids.append(fixture.id)
            exact_hits.append((fixture, pred, score))
            if cur_count > best_count:
                best_count = cur_count
                best_run_ids = list(cur_run_ids)
        else:
            cur_count = 0
            cur_run_ids = []
    best_exact_streak: StreakHighlight | None = (
        StreakHighlight(count=best_count, fixture_ids=best_run_ids) if best_count > 0 else None
    )

    # Most contrarian-correct: of the exact hits, find the one with the
    # lowest agrees_exact-to-total ratio. Need agreement counts per hit
    # fixture, which requires aggregating all predictions for those fixtures.
    most_contrarian: ContrarianHighlight | None = None
    if exact_hits:
        hit_fixture_ids = [f.id for f, _p, _s in exact_hits]
        all_preds_result = await session.execute(
            select(MatchPrediction).where(MatchPrediction.fixture_id.in_(hit_fixture_ids))
        )
        by_fixture: dict[uuid.UUID, list[MatchPrediction]] = defaultdict(list)
        for p in all_preds_result.scalars().all():
            by_fixture[p.fixture_id].append(p)
        lowest_ratio: float | None = None
        for fixture, pred, score in exact_hits:
            preds = by_fixture.get(fixture.id, [])
            total = len(preds)
            if total == 0:
                continue
            agrees_exact = sum(
                1 for p in preds
                if p.home_score == pred.home_score and p.away_score == pred.away_score
            )
            ratio = agrees_exact / total
            if lowest_ratio is None or ratio < lowest_ratio:
                lowest_ratio = ratio
                most_contrarian = ContrarianHighlight(
                    fixture_id=fixture.id,
                    home_team=fixture.home_team,
                    away_team=fixture.away_team,
                    actual_score=f"{score.home_score}-{score.away_score}",
                    user_pick=f"{pred.home_score}-{pred.away_score}",
                    agrees_exact=agrees_exact,
                    total=total,
                )

    # --- biggest_climb ------------------------------------------------------
    # Pull the user's full snapshot history, compare adjacent days for the
    # largest positive rank change.
    snaps = await get_user_trajectory(session, user.id, all_time=True)
    biggest_climb: ClimbHighlight | None = None
    for prev, curr in zip(snaps, snaps[1:]):
        places = prev.position - curr.position  # positive = climbed
        if biggest_climb is None or places > biggest_climb.places:
            biggest_climb = ClimbHighlight(
                places=places,
                captured_date=curr.captured_date,
                from_position=prev.position,
                to_position=curr.position,
            )
    # Don't surface a "biggest climb" that's zero or negative — only
    # interesting if the user actually moved up.
    if biggest_climb is not None and biggest_climb.places <= 0:
        biggest_climb = None

    # --- best_phase ---------------------------------------------------------
    breakdown = await calculate_user_points(session, user.id)
    p1_total = breakdown.phase1.total
    p2_total = breakdown.phase2.total
    best_phase: PhaseHighlight | None = None
    if max(p1_total, p2_total) > 0:
        if p1_total >= p2_total:
            best_phase = PhaseHighlight(phase="phase_1", points=p1_total)
        else:
            best_phase = PhaseHighlight(phase="phase_2", points=p2_total)

    return MyHighlights(
        best_exact_streak=best_exact_streak,
        biggest_climb=biggest_climb,
        most_contrarian_correct=most_contrarian,
        best_phase=best_phase,
    )
