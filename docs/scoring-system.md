# Scoring System

This document describes the configurable scoring system for the Predictor v2 application.

## Overview

The scoring system calculates points for two types of predictions:
1. **Match Predictions** - Predicting the score of individual matches
2. **Advancement Predictions** - Predicting which teams advance through the tournament

All scoring rules are configurable via the YAML configuration file at `config/worldcup2026.yml`.

## Configuration

### File Location

```
config/worldcup2026.yml
```

### Scoring Section

```yaml
scoring:
  # Scoring mode: "fixed" or "hybrid"
  mode: "hybrid"

  match:
    correct_outcome: 5      # Points for correct 1-X-2 prediction
    exact_score: 10         # Bonus points for exact score
    hybrid_cap: 10          # Max hybrid bonus (only for hybrid mode)

  advancement:
    group_advance: 10       # Team advances from group
    group_position: 5       # Correct group position (1st/2nd)
    round_of_32: 10
    round_of_16: 15
    quarter_final: 20
    semi_final: 40
    final: 60
    winner: 100

  phase_multipliers:
    phase_1: 1.0            # Pre-tournament predictions (full points)
    phase_2: 0.7            # Post-group stage predictions (70% points)
```

## Scoring Modes

### Fixed Scoring

In **fixed** mode, players receive flat points for correct predictions regardless of how many other players got it right.

**Example:**
- Correct outcome: 5 points
- Exact score: +10 points
- Total for exact score: 15 points

### Hybrid Scoring

In **hybrid** mode, players receive base points plus a rarity bonus. The fewer players who predicted correctly, the higher the bonus.

**Formula:**
```
outcome_points + min(hybrid_cap, total_players / correct_players) + exact_score_bonus
```

**Example (30 players):**
- Only 3 players got the outcome right: 5 + min(10, 30/3) = 5 + 10 = 15 points
- 15 players got the outcome right: 5 + min(10, 30/15) = 5 + 2 = 7 points
- Exact score bonus is always flat: +10 points

The `hybrid_cap` prevents runaway bonus points when very few players are correct.

## Match Prediction Points

| Prediction | Fixed Mode | Hybrid Mode |
|------------|-----------|-------------|
| Correct outcome (1-X-2) | 5 pts | 5 pts + rarity bonus (0-10 pts) |
| Exact score bonus | +10 pts | +10 pts |
| **Maximum per match** | 15 pts | 25 pts |

### Outcome Types
- **1** = Home team wins
- **X** = Draw
- **2** = Away team wins

## Advancement Prediction Points

Points are awarded when a team reaches at least the predicted stage.

| Stage | Phase 1 Points | Phase 2 Points (70%) |
|-------|---------------|---------------------|
| Group advance | 10 | 7 |
| Correct group position | 5 | 3.5 |
| Round of 32 | 10 | 7 |
| Round of 16 | 15 | 10.5 |
| Quarter-final | 20 | 14 |
| Semi-final | 40 | 28 |
| Final | 60 | 42 |
| Winner | 100 | 70 |

**Note:** Phase 2 predictions (made after group stage) receive reduced points because players have more information when making predictions.

## API Endpoint

You can fetch the current scoring configuration via the API:

```
GET /api/leaderboard/scoring-rules
```

**Response:**
```json
{
  "mode": "hybrid",
  "available_modes": ["fixed", "hybrid"],
  "match": {
    "correct_outcome": 5,
    "exact_score": 10,
    "hybrid_cap": 10
  },
  "advancement": {
    "group_advance": 10,
    "group_position": 5,
    "round_of_32": 10,
    "round_of_16": 15,
    "quarter_final": 20,
    "semi_final": 40,
    "final": 60,
    "winner": 100
  },
  "phase_multipliers": {
    "phase_1": 1.0,
    "phase_2": 0.7
  }
}
```

## Extending the Scoring System

To add a new scoring mode:

### 1. Create a Strategy Class

In `backend/app/services/scoring.py`:

```python
class MyCustomScoring:
    """Description of the scoring mode."""

    def calculate(
        self,
        prediction: MatchPrediction,
        score: Score,
        config: dict[str, Any],
        total_players: int,
        correct_players: int,
    ) -> tuple[int, bool, bool]:
        """
        Calculate match points.

        Args:
            prediction: User's prediction
            score: Actual match result
            config: Match scoring config from YAML
            total_players: Total players in competition
            correct_players: Players who got correct outcome

        Returns:
            Tuple of (points, correct_outcome, exact_score)
        """
        # Your scoring logic here
        outcome_points = config.get("correct_outcome", 5)
        exact_points = config.get("exact_score", 10)

        correct_outcome = prediction.predicted_outcome == score.outcome
        exact_score = (
            prediction.home_score == score.final_home_score
            and prediction.away_score == score.final_away_score
        )

        points = 0
        if correct_outcome:
            points += outcome_points
            # Add custom bonus logic here
        if exact_score:
            points += exact_points

        return points, correct_outcome, exact_score
```

### 2. Register the Strategy

Add to the `SCORING_STRATEGIES` dict:

```python
SCORING_STRATEGIES: dict[str, MatchScoringStrategy] = {
    "fixed": FixedScoring(),
    "hybrid": HybridScoring(),
    "my_custom": MyCustomScoring(),  # Add your new mode
}
```

### 3. Update Config

Set the mode in `config/worldcup2026.yml`:

```yaml
scoring:
  mode: "my_custom"
```

### 4. Add Tests

Add test cases in `backend/tests/test_scoring.py` to verify your scoring logic.

## Testing

Run scoring tests:

```bash
# In docker
docker-compose exec backend pytest tests/test_scoring.py -v

# Or copy test file first if tests dir isn't mounted
docker cp backend/tests/test_scoring.py predictor-backend:/app/tests/
docker-compose exec backend pytest tests/test_scoring.py -v
```

## Implementation Details

### Files

| File | Purpose |
|------|---------|
| `config/worldcup2026.yml` | Scoring configuration |
| `backend/app/services/scoring.py` | Scoring logic and strategies |
| `backend/app/api/leaderboard.py` | Scoring rules API endpoint |
| `backend/tests/test_scoring.py` | Scoring tests |

### Key Functions

- `get_scoring_config()` - Load and merge config with defaults
- `get_scoring_strategy(mode)` - Get scoring strategy by name
- `calculate_match_points()` - Calculate points for a match prediction
- `calculate_advancement_points()` - Calculate points for team advancement
- `calculate_user_points()` - Calculate total points for a user

### Default Values

If the config file is missing or incomplete, the system uses these defaults:

```python
DEFAULT_SCORING_CONFIG = {
    "mode": "hybrid",
    "match": {
        "correct_outcome": 5,
        "exact_score": 10,
        "hybrid_cap": 10,
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
    "phase_multipliers": {
        "phase_1": 1.0,
        "phase_2": 0.7,
    },
}
```

Partial configs are merged with defaults, so you only need to specify values you want to change.
