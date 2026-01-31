"""Scoring calculation service.

Point calculation for match predictions and advancement predictions.
All scoring rules are configurable via YAML.
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import get_tournament_config
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction, PredictionPhase, TeamPrediction
from app.models.score import Score
from app.schemas.leaderboard import PointBreakdown


def get_scoring_config() -> dict[str, Any]:
    """Get scoring configuration from tournament config."""
    try:
        config = get_tournament_config()
        return config.get("scoring", {})
    except FileNotFoundError:
        # Return default scoring if config not found
        return {
            "match": {
                "correct_outcome": 5,
                "exact_score": 10,
            },
            "advancement": {
                "group_advance": 10,
                "group_position": 5,
                "round_of_32": 10,
                "round_of_16": 15,
                "quarter_final": 20,
                "semi_final": 40,
                "final": 60,
                "winner": 100,
            },
        }


def calculate_match_points(
    prediction: MatchPrediction,
    score: Score,
    total_players: int = 30,
    correct_players: int = 1,
) -> tuple[int, bool, bool]:
    """Calculate points for a single match prediction.

    Uses hybrid scoring:
    - Base points for correct outcome (1-X-2)
    - Bonus points for exact score

    Args:
        prediction: User's prediction
        score: Actual match result
        total_players: Total number of players (for hybrid calculation)
        correct_players: Number of players with correct outcome (for hybrid)

    Returns:
        Tuple of (points, correct_outcome, exact_score)
    """
    config = get_scoring_config()
    match_config = config.get("match", {})

    outcome_points = match_config.get("correct_outcome", 5)
    exact_points = match_config.get("exact_score", 10)
    cap = match_config.get("cap", 10)

    # Determine outcomes
    pred_outcome = prediction.predicted_outcome
    actual_outcome = score.outcome

    correct_outcome = pred_outcome == actual_outcome
    exact_score = (
        prediction.home_score == score.final_home_score
        and prediction.away_score == score.final_away_score
    )

    points = 0

    if correct_outcome:
        # Base points for correct outcome
        points += outcome_points

        # Hybrid bonus (capped at cap)
        if correct_players > 0:
            bonus = min(cap, total_players // correct_players)
            points += bonus

    if exact_score:
        # Flat bonus for exact score
        points += exact_points

    return points, correct_outcome, exact_score


def calculate_advancement_points(
    team_prediction: TeamPrediction,
    actual_advancement: dict[str, str],
    phase: PredictionPhase,
) -> int:
    """Calculate points for team advancement prediction.

    Args:
        team_prediction: User's prediction for team advancement
        actual_advancement: Dict mapping team -> highest stage reached
        phase: Which phase the prediction was made in

    Returns:
        Points earned for this prediction
    """
    config = get_scoring_config()
    adv_config = config.get("advancement", {})

    # Get phase-specific multiplier
    phase_multipliers = config.get("phase_multipliers", {"phase_1": 1.0, "phase_2": 0.7})
    multiplier = phase_multipliers.get(phase.value, 1.0)

    team = team_prediction.team
    predicted_stage = team_prediction.stage
    actual_stage = actual_advancement.get(team)

    if not actual_stage:
        return 0

    # Define stage ordering
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

    # Team must have reached at least the predicted stage
    if actual_idx >= predicted_idx:
        base_points = adv_config.get(predicted_stage, 0)
        return int(base_points * multiplier)

    return 0


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


async def calculate_user_points(session: AsyncSession, user_id: uuid.UUID) -> PointBreakdown:
    """Calculate total points for a user.

    Args:
        session: Database session
        user_id: User to calculate points for

    Returns:
        PointBreakdown with detailed point categories
    """
    breakdown = PointBreakdown()

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

        # TODO: Calculate actual correct_players count for hybrid scoring
        points, correct_outcome, exact_score = calculate_match_points(
            prediction, score, total_players=30, correct_players=10
        )

        if correct_outcome:
            breakdown.match_outcome_points += 5  # Base points only
        if exact_score:
            breakdown.exact_score_points += points - 5 if correct_outcome else points

    # Get team advancement predictions
    result = await session.execute(
        select(TeamPrediction).where(TeamPrediction.user_id == user_id)
    )
    team_predictions = result.scalars().all()

    # Calculate advancement points
    actual_advancement = await get_actual_advancement(session)
    for pred in team_predictions:
        points = calculate_advancement_points(pred, actual_advancement, pred.phase)
        if pred.stage == "group":
            breakdown.group_advancement_points += points
        else:
            breakdown.knockout_advancement_points += points

    return breakdown


async def get_outcome_counts(session: AsyncSession, fixture_id: uuid.UUID) -> dict[str, int]:
    """Get count of each predicted outcome for a fixture.

    Used for hybrid scoring calculation.

    Returns:
        Dict with keys '1', 'X', '2' and counts
    """
    result = await session.execute(
        select(MatchPrediction).where(MatchPrediction.fixture_id == fixture_id)
    )
    predictions = result.scalars().all()

    counts = {"1": 0, "X": 0, "2": 0}
    for pred in predictions:
        outcome = pred.predicted_outcome
        counts[outcome] = counts.get(outcome, 0) + 1

    return counts
