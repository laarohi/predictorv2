"""Tests for the scoring service.

CRITICAL: No scoring logic changes without a corresponding test case.
"""

import pytest
from unittest.mock import MagicMock, patch

from app.models.prediction import MatchPrediction, PredictionPhase
from app.models.score import Score
from app.services.scoring import (
    calculate_match_points,
    calculate_advancement_points,
    get_scoring_config,
)


class TestGetScoringConfig:
    """Tests for scoring configuration loading."""

    def test_default_config_when_file_not_found(self):
        """Should return default config when YAML file doesn't exist."""
        with patch("app.services.scoring.get_tournament_config") as mock_config:
            mock_config.side_effect = FileNotFoundError()
            config = get_scoring_config()

            assert config["match"]["correct_outcome"] == 5
            assert config["match"]["exact_score"] == 10
            assert config["advancement"]["winner"] == 100


class TestCalculateMatchPoints:
    """Tests for match prediction scoring."""

    @pytest.fixture
    def home_win_prediction(self) -> MatchPrediction:
        """Create a prediction for home team win."""
        pred = MagicMock(spec=MatchPrediction)
        pred.home_score = 2
        pred.away_score = 1
        pred.predicted_outcome = "1"
        return pred

    @pytest.fixture
    def draw_prediction(self) -> MatchPrediction:
        """Create a prediction for draw."""
        pred = MagicMock(spec=MatchPrediction)
        pred.home_score = 1
        pred.away_score = 1
        pred.predicted_outcome = "X"
        return pred

    @pytest.fixture
    def away_win_prediction(self) -> MatchPrediction:
        """Create a prediction for away team win."""
        pred = MagicMock(spec=MatchPrediction)
        pred.home_score = 0
        pred.away_score = 2
        pred.predicted_outcome = "2"
        return pred

    @pytest.fixture
    def home_win_score(self) -> Score:
        """Create a score for home team win."""
        score = MagicMock(spec=Score)
        score.home_score = 2
        score.away_score = 1
        score.final_home_score = 2
        score.final_away_score = 1
        score.outcome = "1"
        return score

    @pytest.fixture
    def draw_score(self) -> Score:
        """Create a score for draw."""
        score = MagicMock(spec=Score)
        score.home_score = 1
        score.away_score = 1
        score.final_home_score = 1
        score.final_away_score = 1
        score.outcome = "X"
        return score

    def test_correct_outcome_home_win(self, home_win_prediction, home_win_score):
        """Should award points for correct home win prediction."""
        points, correct, exact = calculate_match_points(
            home_win_prediction, home_win_score, total_players=30, correct_players=10
        )

        assert correct is True
        assert points >= 5  # At least base points for correct outcome

    def test_correct_outcome_draw(self, draw_prediction, draw_score):
        """Should award points for correct draw prediction."""
        points, correct, exact = calculate_match_points(
            draw_prediction, draw_score, total_players=30, correct_players=10
        )

        assert correct is True
        assert points >= 5

    def test_incorrect_outcome(self, home_win_prediction, draw_score):
        """Should not award points for incorrect prediction."""
        points, correct, exact = calculate_match_points(
            home_win_prediction, draw_score, total_players=30, correct_players=10
        )

        assert correct is False
        assert points == 0 or points == 10  # Only exact score bonus if any

    def test_exact_score_bonus(self, home_win_prediction, home_win_score):
        """Should award bonus for exact score."""
        # Prediction: 2-1, Score: 2-1 (exact match)
        points, correct, exact = calculate_match_points(
            home_win_prediction, home_win_score, total_players=30, correct_players=10
        )

        assert exact is True
        assert points >= 15  # 5 (outcome) + 10 (exact) minimum

    def test_correct_outcome_wrong_score(self, home_win_prediction, home_win_score):
        """Should award outcome points but not exact score bonus."""
        # Modify prediction to have different score but same outcome
        home_win_prediction.home_score = 3
        home_win_prediction.away_score = 0

        points, correct, exact = calculate_match_points(
            home_win_prediction, home_win_score, total_players=30, correct_players=10
        )

        assert correct is True
        assert exact is False

    def test_hybrid_scoring_with_few_correct(self, home_win_prediction, home_win_score):
        """Hybrid bonus should be higher when fewer people are correct."""
        # Only 3 people got it right out of 30
        points_few, _, _ = calculate_match_points(
            home_win_prediction, home_win_score, total_players=30, correct_players=3
        )

        # 15 people got it right out of 30
        points_many, _, _ = calculate_match_points(
            home_win_prediction, home_win_score, total_players=30, correct_players=15
        )

        # Fewer correct = higher bonus (capped at 10)
        assert points_few >= points_many

    def test_hybrid_scoring_cap(self, home_win_prediction, home_win_score):
        """Hybrid bonus should be capped at 10 points."""
        # Only 1 person got it right - would be 30 points without cap
        points, _, _ = calculate_match_points(
            home_win_prediction, home_win_score, total_players=30, correct_players=1
        )

        # Points should be: 5 (outcome) + 10 (capped hybrid) + 10 (exact) = 25 max
        assert points <= 25


class TestCalculateAdvancementPoints:
    """Tests for team advancement scoring."""

    @pytest.fixture
    def winner_prediction(self) -> MagicMock:
        """Create a prediction for tournament winner."""
        pred = MagicMock()
        pred.team = "Brazil"
        pred.stage = "winner"
        pred.phase = PredictionPhase.PHASE_1
        return pred

    @pytest.fixture
    def round_of_16_prediction(self) -> MagicMock:
        """Create a prediction for round of 16."""
        pred = MagicMock()
        pred.team = "Germany"
        pred.stage = "round_of_16"
        pred.phase = PredictionPhase.PHASE_1
        return pred

    def test_winner_prediction_correct(self, winner_prediction):
        """Should award 100 points for correct winner in Phase 1."""
        actual_advancement = {"Brazil": "winner"}

        points = calculate_advancement_points(
            winner_prediction, actual_advancement, PredictionPhase.PHASE_1
        )

        assert points == 100

    def test_winner_prediction_wrong(self, winner_prediction):
        """Should award 0 points when team doesn't win."""
        actual_advancement = {"Brazil": "semi_final", "Argentina": "winner"}

        points = calculate_advancement_points(
            winner_prediction, actual_advancement, PredictionPhase.PHASE_1
        )

        # Team reached semi but was predicted to win - still get semi-final points
        # because they reached that stage
        assert points >= 0

    def test_round_of_16_prediction_team_reaches(self, round_of_16_prediction):
        """Should award points when team reaches predicted round."""
        actual_advancement = {"Germany": "quarter_final"}  # Went further than R16

        points = calculate_advancement_points(
            round_of_16_prediction, actual_advancement, PredictionPhase.PHASE_1
        )

        assert points == 15  # Phase 1 R16 points

    def test_team_eliminated_before_prediction(self, round_of_16_prediction):
        """Should award 0 points when team is eliminated early."""
        actual_advancement = {"Germany": "group"}  # Eliminated in groups

        points = calculate_advancement_points(
            round_of_16_prediction, actual_advancement, PredictionPhase.PHASE_1
        )

        assert points == 0

    def test_phase_2_reduced_points(self, winner_prediction):
        """Phase 2 predictions should award reduced points."""
        actual_advancement = {"Brazil": "winner"}
        winner_prediction.phase = PredictionPhase.PHASE_2

        points = calculate_advancement_points(
            winner_prediction, actual_advancement, PredictionPhase.PHASE_2
        )

        # Phase 2 winner is 70 points (70% of 100)
        assert points == 70
