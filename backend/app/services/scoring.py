"""Scoring calculation service.

Point calculation for match predictions and advancement predictions.
All scoring rules are configurable via YAML.

Supports multiple scoring modes:
- "fixed": Flat points for correct outcome
- "hybrid": Base points + integer-division rarity bonus (legacy, kept for
  comparison)
- "logarithmic": Base points + Shannon-surprisal rarity bonus
  R = min(cap, round(alpha * log2(1 / (2f))))
  where f = correct_predictors / total_predictors and
  alpha = 10/log2(15) so f = 1/30 hits the cap of 10.

Scoring modes are extensible via the SCORING_STRATEGIES dict.
"""

import math
import uuid
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import get_tournament_config
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction, PredictionPhase, TeamPrediction
from app.models.score import Score
from app.models.user import User
from app.schemas.leaderboard import PhaseBreakdown, PointBreakdown


# Default scoring configuration (used when YAML config is unavailable)
DEFAULT_SCORING_CONFIG: dict[str, Any] = {
    "mode": "logarithmic",
    "match": {
        "correct_outcome": 5,
        "exact_score": 10,
        "hybrid_cap": 10,
        "rarity_cap": 10,
    },
    "advancement": {
        # Phase 1 — pre-tournament, full reward.
        "round_of_32": 10,
        "round_of_16": 15,
        "quarter_final": 25,
        "semi_final": 55,
        "final": 85,
        "winner": 150,
        # Phase 1 group-position bonus. See `calculate_group_position_bonus`
        # and `services/standings.get_predicted_group_standings`.
        "group_position": 5,
        # Phase 2 — post-group-stage. Explicit per-stage values (no
        # multiplier); R32/R16 deliberately squashed because they're
        # largely redundant with Phase 2 match-outcome scoring.
        "phase_2": {
            "round_of_32": 0,
            "round_of_16": 5,
            "quarter_final": 15,
            "semi_final": 40,
            "final": 60,
            "winner": 100,
        },
    },
}


def get_scoring_config() -> dict[str, Any]:
    """Get scoring configuration from tournament config.

    Returns merged config with defaults for any missing values.
    """
    try:
        config = get_tournament_config()
        scoring = config.get("scoring", {})
        # Merge with defaults to ensure all required keys exist
        return _merge_config(DEFAULT_SCORING_CONFIG, scoring)
    except FileNotFoundError:
        return DEFAULT_SCORING_CONFIG


def _merge_config(default: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge override config into default config."""
    result = default.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge_config(result[key], value)
        else:
            result[key] = value
    return result


# =============================================================================
# Scoring Strategy Pattern
# =============================================================================


class MatchScoringStrategy(Protocol):
    """Protocol for match scoring strategies."""

    def calculate(
        self,
        prediction: MatchPrediction,
        score: Score,
        config: dict[str, Any],
        total_predictors: int,
        correct_predictors: int,
    ) -> tuple[int, bool, bool]:
        """Calculate match points.

        Args:
            prediction: User's prediction
            score: Actual match result
            config: Match scoring config
            total_predictors: Number of users who submitted a prediction for
                this fixture
            correct_predictors: Number of those who picked the actual outcome

        Returns:
            Tuple of (points, correct_outcome, exact_score)
        """
        ...


class FixedScoring:
    """Fixed scoring: flat points for correct predictions."""

    def calculate(
        self,
        prediction: MatchPrediction,
        score: Score,
        config: dict[str, Any],
        total_predictors: int,
        correct_predictors: int,
    ) -> tuple[int, bool, bool]:
        return compute_match_points(
            mode="fixed",
            predicted_home=prediction.home_score,
            predicted_away=prediction.away_score,
            actual_home=score.final_home_score,
            actual_away=score.final_away_score,
            total_predictors=total_predictors,
            correct_predictors=correct_predictors,
            outcome_points=config.get("correct_outcome", 5),
            exact_points=config.get("exact_score", 10),
            cap=config.get("rarity_cap", config.get("hybrid_cap", 10)),
        )


class HybridScoring:
    """Legacy hybrid scoring: base points + integer-division rarity bonus.

    Formula: outcome_points + min(cap, total_predictors // correct_predictors)

    Superseded by LogarithmicScoring; kept registered for backward
    compatibility with any deployment still configured with mode="hybrid".
    """

    def calculate(
        self,
        prediction: MatchPrediction,
        score: Score,
        config: dict[str, Any],
        total_predictors: int,
        correct_predictors: int,
    ) -> tuple[int, bool, bool]:
        return compute_match_points(
            mode="hybrid",
            predicted_home=prediction.home_score,
            predicted_away=prediction.away_score,
            actual_home=score.final_home_score,
            actual_away=score.final_away_score,
            total_predictors=total_predictors,
            correct_predictors=correct_predictors,
            outcome_points=config.get("correct_outcome", 5),
            exact_points=config.get("exact_score", 10),
            cap=config.get("hybrid_cap", 10),
        )


# Anchor: alpha chosen so that f = 1/30 (one of thirty predictors correct)
# hits the cap of 10. log2(15) ~= 3.9069, so alpha ~= 2.5596. Defined as a
# module-level constant so a single number drives the published table.
_LOG_ALPHA = 10.0 / math.log2(15.0)


def _logarithmic_rarity_bonus(
    total_predictors: int, correct_predictors: int, cap: int
) -> int:
    """Shannon-surprisal rarity bonus, capped and integer-rounded.

    R = min(cap, round(alpha * log2(1 / (2f)))) for f < 0.5, else 0.
    Returns 0 defensively when there are no predictors.
    """
    if total_predictors <= 0 or correct_predictors <= 0:
        return 0
    f = correct_predictors / total_predictors
    if f >= 0.5:
        return 0
    raw = _LOG_ALPHA * math.log2(1.0 / (2.0 * f))
    return min(cap, max(0, round(raw)))


def _outcome(home: int, away: int) -> str:
    """1/X/2 outcome from a scoreline. Convention is irrelevant as long as
    both the predicted and actual lines are classified by the same function."""
    if home > away:
        return "1"
    if home < away:
        return "2"
    return "X"


def compute_match_points(
    *,
    mode: str,
    predicted_home: int,
    predicted_away: int,
    actual_home: int,
    actual_away: int,
    total_predictors: int,
    correct_predictors: int,
    outcome_points: int,
    exact_points: int,
    cap: int,
) -> tuple[int, bool, bool]:
    """Pure match-points calculation shared with the frontend
    (`computeMatchPoints` in `frontend/src/lib/utils/matchBreakdown.ts`).

    Takes only primitives — no model objects, no config-dict key names — so
    the two language implementations validate against the SAME shared golden
    cases (`shared/scoring-parity-cases.json`). The three strategy classes
    below and the frontend Results card both route through this, so the
    tested path is the production path.

    Returns (points, correct_outcome, exact_score). `cap` bounds the rarity
    bonus; it's unused for mode 'fixed'.
    """
    correct_outcome = _outcome(predicted_home, predicted_away) == _outcome(
        actual_home, actual_away
    )
    exact_score = predicted_home == actual_home and predicted_away == actual_away

    points = 0
    if correct_outcome:
        points += outcome_points
        if mode == "hybrid":
            if correct_predictors > 0:
                points += min(cap, total_predictors // correct_predictors)
        elif mode == "logarithmic":
            points += _logarithmic_rarity_bonus(
                total_predictors, correct_predictors, cap
            )
        # mode "fixed": no rarity bonus.
    if exact_score:
        points += exact_points

    return points, correct_outcome, exact_score


class LogarithmicScoring:
    """Logarithmic rarity scoring: base points + Shannon-surprisal bonus.

    The rarity bonus measures bits of information the crowd was wrong by,
    scaled so f = 1/30 hits the cap. Gated at f >= 0.5 (consensus picks
    earn no premium). Each ~1 bit of additional surprisal adds ~2.5 points.

    See docs/scoring-system.md for the published percentage-band table.
    """

    def calculate(
        self,
        prediction: MatchPrediction,
        score: Score,
        config: dict[str, Any],
        total_predictors: int,
        correct_predictors: int,
    ) -> tuple[int, bool, bool]:
        return compute_match_points(
            mode="logarithmic",
            predicted_home=prediction.home_score,
            predicted_away=prediction.away_score,
            actual_home=score.final_home_score,
            actual_away=score.final_away_score,
            total_predictors=total_predictors,
            correct_predictors=correct_predictors,
            outcome_points=config.get("correct_outcome", 5),
            exact_points=config.get("exact_score", 10),
            cap=config.get("rarity_cap", config.get("hybrid_cap", 10)),
        )


# Registry of available scoring strategies
# Add new strategies here to make them available via config
SCORING_STRATEGIES: dict[str, MatchScoringStrategy] = {
    "fixed": FixedScoring(),
    "hybrid": HybridScoring(),
    "logarithmic": LogarithmicScoring(),
}


def get_scoring_strategy(mode: str | None = None) -> MatchScoringStrategy:
    """Get the scoring strategy based on config mode.

    Args:
        mode: Optional override for scoring mode. If None, uses config.

    Returns:
        The scoring strategy implementation.

    Raises:
        ValueError: If the configured mode is not registered.
    """
    if mode is None:
        config = get_scoring_config()
        mode = config.get("mode", "logarithmic")

    strategy = SCORING_STRATEGIES.get(mode)
    if strategy is None:
        available = ", ".join(SCORING_STRATEGIES.keys())
        raise ValueError(f"Unknown scoring mode '{mode}'. Available: {available}")

    return strategy


def calculate_match_points(
    prediction: MatchPrediction,
    score: Score,
    total_predictors: int = 30,
    correct_predictors: int = 1,
    mode: str | None = None,
) -> tuple[int, bool, bool]:
    """Calculate points for a single match prediction.

    Uses the configured scoring mode (fixed, hybrid, or logarithmic).

    Args:
        prediction: User's prediction
        score: Actual match result
        total_predictors: Number of users who submitted a prediction for this
            fixture (used by rarity-bonus modes)
        correct_predictors: Number of those who picked the actual outcome
        mode: Optional override for scoring mode. If None, uses config.

    Returns:
        Tuple of (points, correct_outcome, exact_score)
    """
    config = get_scoring_config()
    match_config = config.get("match", {})
    strategy = get_scoring_strategy(mode)

    return strategy.calculate(
        prediction, score, match_config, total_predictors, correct_predictors
    )


def calculate_advancement_points(
    team_prediction: TeamPrediction,
    actual_advancement: dict[str, str],
    phase: PredictionPhase,
) -> int:
    """Calculate points for a team advancement prediction.

    Phase 1 and Phase 2 read from independent point tables in the YAML
    (`scoring.advancement` for Phase 1, `scoring.advancement.phase_2`
    for Phase 2). There is no implicit multiplier — every stage's value
    is explicit. Phase 2 R32 = 0 because the R32 line-up is published
    after the group stage and there's no prediction skill to reward;
    Phase 2 R16 = 5 because R32 match-outcome scoring already pays for
    "team X beats team Y" insight.

    Args:
        team_prediction: User's prediction for team advancement
        actual_advancement: Dict mapping team -> highest stage reached
        phase: Which phase the prediction was made in

    Returns:
        Points earned for this prediction
    """
    config = get_scoring_config()
    adv_config = config.get("advancement", {})

    # Phase-specific point table. Phase 2 values are nested under
    # `advancement.phase_2`; Phase 1 reads the top level directly.
    if phase == PredictionPhase.PHASE_2:
        stage_points = adv_config.get("phase_2", {})
    else:
        stage_points = adv_config

    team = team_prediction.team
    predicted_stage = team_prediction.stage
    actual_stage = actual_advancement.get(team)

    if not actual_stage:
        return 0

    # Stage ordering — team must have reached at least the predicted stage.
    stage_order = [
        "group",
        "round_of_32",
        "round_of_16",
        "quarter_final",
        "semi_final",
        "final",
        "winner",
    ]

    predicted_idx = stage_order.index(predicted_stage) if predicted_stage in stage_order else -1
    actual_idx = stage_order.index(actual_stage) if actual_stage in stage_order else -1

    if actual_idx >= predicted_idx:
        return int(stage_points.get(predicted_stage, 0))

    return 0


async def calculate_group_position_bonus(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    actual_standings: dict | None = None,
    qualifying_thirds: list | None = None,
    group_completion: tuple[set[str], set[str]] | None = None,
) -> int:
    """Phase 1 bonus: reward correctly predicting a team's group position.

    The user's *predicted* group standings are derived from their Phase 1
    group match score predictions (see
    `services.standings.get_predicted_group_standings`). For each team
    whose predicted position matches their actual position AND who
    qualified for the knockout stage, award `advancement.group_position`
    points (default 5).

    Eligibility rules (settled in the calibration discussion):
      - Position 1 or 2 in any group → always qualifies → bonus paid on match
      - Position 3 → bonus only if the team is one of the 8 best thirds
      - Position 4 → never (team eliminated)

    A group's positions only count once that group is COMPLETE (all of its
    fixtures finished) — partial standings after one match would pay the
    bonus immediately and revoke it as later results reshuffle the table.
    Third-place bonuses additionally wait for ALL groups to complete,
    because the best-8-thirds ranking is a cross-group comparison.

    Phase 2 has no group match predictions, so this bonus is Phase 1 only.
    """
    # Imported inside the function to avoid pulling standings (which imports
    # MatchPrediction) into the import chain that scoring.py participates in.
    from app.services.standings import (
        get_actual_group_standings,
        get_group_completion,
        get_predicted_group_standings,
        get_qualifying_third_place_teams,
    )

    config = get_scoring_config()
    bonus_value = config.get("advancement", {}).get("group_position", 0)
    if bonus_value <= 0:
        return 0

    # The user's predicted standings vary per user; the actual standings,
    # qualifying-thirds and group completion are global, so the leaderboard
    # build passes them in precomputed (computed once instead of per user).
    completed_groups, all_groups = (
        group_completion
        if group_completion is not None
        else await get_group_completion(session)
    )
    if not completed_groups:
        return 0
    all_groups_complete = completed_groups == all_groups

    predicted, _ = await get_predicted_group_standings(session, user_id)
    actual = (
        actual_standings
        if actual_standings is not None
        else await get_actual_group_standings(session)
    )
    if not predicted or not actual:
        return 0

    thirds = (
        qualifying_thirds
        if qualifying_thirds is not None
        else await get_qualifying_third_place_teams(session)
    )
    qualifying_third_names = {t["team"] for t in thirds}

    total = 0
    for group, predicted_teams in predicted.items():
        if group not in completed_groups:
            continue
        actual_teams = actual.get(group, [])
        if not actual_teams:
            continue
        # Build {team_name: 1-indexed actual position}.
        actual_positions = {t["team"]: i + 1 for i, t in enumerate(actual_teams)}

        for i, predicted_team in enumerate(predicted_teams):
            predicted_position = i + 1
            team_name = predicted_team["team"]
            actual_position = actual_positions.get(team_name)
            if actual_position != predicted_position:
                continue
            # Position 4 never qualifies; skip.
            if predicted_position == 4:
                continue
            # Position 1/2 always qualifies → bonus.
            # Position 3 only if best-8-thirds — undecidable (and unstable)
            # until every group is complete, so it waits for all of them.
            if predicted_position in (1, 2) or (
                predicted_position == 3
                and all_groups_complete
                and team_name in qualifying_third_names
            ):
                total += bonus_value

    return total


async def get_actual_advancement(session: AsyncSession) -> dict[str, str]:
    """Determine which teams advanced to each stage based on completed fixtures.

    Queries finished knockout fixtures and determines the highest stage
    reached by each team.

    Args:
        session: Database session

    Returns:
        Dict mapping team name -> highest stage reached
        e.g., {"France": "winner", "Germany": "semi_final", ...}
    """
    # Define stage progression for determining highest stage
    # Higher index = further in tournament
    stage_ranking = {
        "round_of_32": 1,
        "round_of_16": 2,
        "quarter_final": 3,
        "semi_final": 4,
        "final": 5,
    }

    # Track highest stage reached by each team
    team_advancement: dict[str, str] = {}

    # Get all finished knockout fixtures with scores
    result = await session.execute(
        select(Fixture, Score)
        .outerjoin(Score, Fixture.id == Score.fixture_id)
        .where(
            Fixture.stage != "group",
            Fixture.status == MatchStatus.FINISHED,
        )
    )
    rows = result.all()

    for fixture, score in rows:
        if not score:
            continue

        stage = fixture.stage
        home_team = fixture.home_team
        away_team = fixture.away_team

        # Both teams at least reached this stage
        for team in [home_team, away_team]:
            if team:
                current_stage = team_advancement.get(team)
                if not current_stage or stage_ranking.get(stage, 0) > stage_ranking.get(
                    current_stage, 0
                ):
                    team_advancement[team] = stage

        # Determine winner and advance them to next stage
        winner = None
        if score.outcome == "1":
            winner = home_team
        elif score.outcome == "2":
            winner = away_team

        if winner:
            # Map current stage to advancement stage
            advancement_map = {
                "round_of_32": "round_of_16",
                "round_of_16": "quarter_final",
                "quarter_final": "semi_final",
                "semi_final": "final",
                "final": "winner",
            }
            next_stage = advancement_map.get(stage)
            if next_stage:
                current_stage = team_advancement.get(winner)
                if not current_stage or stage_ranking.get(
                    next_stage, 6
                ) > stage_ranking.get(current_stage, 0):
                    team_advancement[winner] = next_stage

    return team_advancement


def _add_match_points_to_phase(
    phase_breakdown: PhaseBreakdown,
    base_outcome_points: int,
    exact_score_points: int,
    points: int,
    correct_outcome: bool,
    exact_score: bool,
) -> None:
    """Add match prediction points to a phase breakdown."""
    if correct_outcome:
        phase_breakdown.match_outcome_points += base_outcome_points
        # Hybrid bonus is the difference between total points and base + exact
        hybrid_bonus = points - base_outcome_points - (exact_score_points if exact_score else 0)
        if hybrid_bonus > 0:
            phase_breakdown.hybrid_bonus_points += hybrid_bonus

    if exact_score:
        phase_breakdown.exact_score_points += exact_score_points


def _add_advancement_points_to_phase(
    phase_breakdown: PhaseBreakdown,
    stage: str,
    points: int,
) -> None:
    """Add advancement prediction points to a phase breakdown."""
    if stage == "round_of_32":
        phase_breakdown.round_of_32_points += points
    elif stage == "round_of_16":
        phase_breakdown.round_of_16_points += points
    elif stage == "quarter_final":
        phase_breakdown.quarter_final_points += points
    elif stage == "semi_final":
        phase_breakdown.semi_final_points += points
    elif stage == "final":
        phase_breakdown.final_points += points
    elif stage == "winner":
        phase_breakdown.winner_points += points


async def calculate_user_points(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    outcome_counts_by_fixture: dict[uuid.UUID, dict[str, int]] | None = None,
    actual_advancement_cache: dict[str, str] | None = None,
    actual_standings_cache: dict | None = None,
    qualifying_thirds_cache: list | None = None,
    group_completion_cache: tuple[set[str], set[str]] | None = None,
) -> PointBreakdown:
    """Calculate total points for a user.

    Args:
        session: Database session
        user_id: User to calculate points for

    The keyword-only ``*_cache`` args let the leaderboard build precompute the
    per-fixture outcome counts and the tournament-global advancement/standings
    ONCE and pass them in, instead of this function re-querying them per user
    (an O(users × fixtures) explosion on a cold rebuild). When omitted, the
    function computes everything itself, so behaviour is identical for the
    direct callers (profile, breakdown, highlights).

    Returns:
        PointBreakdown with detailed point categories by phase
    """
    config = get_scoring_config()
    match_config = config.get("match", {})
    base_outcome_points = match_config.get("correct_outcome", 5)
    exact_score_points = match_config.get("exact_score", 10)

    # Create phase breakdowns
    phase1 = PhaseBreakdown()
    phase2 = PhaseBreakdown()

    # Aggregate stats
    total_predictions = 0
    correct_outcomes = 0
    exact_scores = 0

    # Get all match predictions with scores
    result = await session.execute(
        select(MatchPrediction, Score, Fixture)
        .join(Fixture, MatchPrediction.fixture_id == Fixture.id)
        .outerjoin(Score, Fixture.id == Score.fixture_id)
        .where(
            MatchPrediction.user_id == user_id,
            Fixture.status == MatchStatus.FINISHED,
        )
    )
    rows = result.all()

    for prediction, score, fixture in rows:
        if not score:
            continue

        total_predictions += 1

        # Rarity bonus uses per-fixture predictor counts: "the room that
        # showed up", not all active users. Sum of outcome buckets gives
        # the total predictors for this fixture.
        if outcome_counts_by_fixture is not None:
            outcome_counts = outcome_counts_by_fixture.get(fixture.id, {"1": 0, "X": 0, "2": 0})
        else:
            outcome_counts = await get_outcome_counts(session, fixture.id)
        total_predictors = sum(outcome_counts.values())
        correct_predictors = outcome_counts.get(score.outcome, 0)

        # Calculate points using configured strategy
        points, is_correct_outcome, is_exact_score = calculate_match_points(
            prediction, score,
            total_predictors=total_predictors,
            correct_predictors=correct_predictors,
        )

        if is_correct_outcome:
            correct_outcomes += 1
        if is_exact_score:
            exact_scores += 1

        # Add to appropriate phase breakdown
        phase_breakdown = phase1 if prediction.phase == PredictionPhase.PHASE_1 else phase2
        _add_match_points_to_phase(
            phase_breakdown,
            base_outcome_points,
            exact_score_points,
            points,
            is_correct_outcome,
            is_exact_score,
        )

    # Get team advancement predictions
    result = await session.execute(
        select(TeamPrediction).where(TeamPrediction.user_id == user_id)
    )
    team_predictions = result.scalars().all()

    # Calculate advancement points by stage
    actual_advancement = (
        actual_advancement_cache
        if actual_advancement_cache is not None
        else await get_actual_advancement(session)
    )
    for pred in team_predictions:
        points = calculate_advancement_points(pred, actual_advancement, pred.phase)
        if points == 0:
            continue

        # Add to appropriate phase breakdown
        phase_breakdown = phase1 if pred.phase == PredictionPhase.PHASE_1 else phase2
        _add_advancement_points_to_phase(
            phase_breakdown,
            pred.stage,
            points,
        )

    # Phase 1 group-position bonus — derived from match score predictions,
    # paid only for correctly-placed teams that qualify. Lives in
    # phase1.group_position_points so the existing leaderboard breakdown
    # bucket picks it up automatically.
    phase1.group_position_points += await calculate_group_position_bonus(
        session,
        user_id,
        actual_standings=actual_standings_cache,
        qualifying_thirds=qualifying_thirds_cache,
        group_completion=group_completion_cache,
    )

    # Bonus-question points (cross-phase). Imported here to avoid a circular
    # import at module load: services.bonus depends on the config layer
    # already loaded by this file.
    from app.services.bonus import calculate_bonus_points
    bonus_points = await calculate_bonus_points(session, user_id)

    return PointBreakdown(
        phase1=phase1,
        phase2=phase2,
        correct_outcomes=correct_outcomes,
        exact_scores=exact_scores,
        total_predictions=total_predictions,
        bonus_question_points=bonus_points,
    )


async def get_outcome_counts(session: AsyncSession, fixture_id: uuid.UUID) -> dict[str, int]:
    """Get count of each predicted outcome for a fixture.

    Used for hybrid scoring calculation.

    Returns:
        Dict with keys '1', 'X', '2' and counts
    """
    result = await session.execute(
        select(MatchPrediction)
        .join(User, MatchPrediction.user_id == User.id)
        .where(
            MatchPrediction.fixture_id == fixture_id,
            User.is_ghost == False,  # noqa: E712 — ghosts must never move rarity
        )
    )
    predictions = result.scalars().all()

    counts = {"1": 0, "X": 0, "2": 0}
    for pred in predictions:
        outcome = pred.predicted_outcome
        counts[outcome] = counts.get(outcome, 0) + 1

    return counts


async def get_all_outcome_counts(
    session: AsyncSession,
) -> dict[uuid.UUID, dict[str, int]]:
    """Outcome counts for EVERY fixture, in a single query.

    Equivalent to calling get_outcome_counts() per fixture, but the leaderboard
    build calls this once and passes the result into calculate_user_points
    instead of issuing one query per fixture per user.
    """
    result = await session.execute(
        select(MatchPrediction)
        .join(User, MatchPrediction.user_id == User.id)
        .where(User.is_ghost == False)  # noqa: E712 — ghosts must never move rarity
    )
    by_fixture: dict[uuid.UUID, dict[str, int]] = {}
    for pred in result.scalars().all():
        counts = by_fixture.setdefault(pred.fixture_id, {"1": 0, "X": 0, "2": 0})
        outcome = pred.predicted_outcome
        counts[outcome] = counts.get(outcome, 0) + 1
    return by_fixture
