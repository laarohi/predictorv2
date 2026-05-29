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
  # Scoring mode: "fixed" | "hybrid" (legacy) | "logarithmic" (default)
  mode: "logarithmic"

  match:
    correct_outcome: 5      # Points for correct 1-X-2 prediction
    exact_score: 10         # Bonus points for exact score
    rarity_cap: 10          # Max rarity bonus (logarithmic / hybrid modes)
    hybrid_cap: 10          # Legacy alias, read as fallback

  advancement:
    # Phase 1 — pre-tournament picks, full reward.
    round_of_32: 10
    round_of_16: 15
    quarter_final: 20
    semi_final: 40
    final: 60
    winner: 100
    # Phase 1 bonus: derived from group match score predictions (see
    # services/standings.get_predicted_group_standings). Paid only for
    # teams that qualify for R32 — positions 1 or 2 always, position 3
    # only if a best-8-thirds qualifier.
    group_position: 5
    # Phase 2 — post-group-stage. Independent per-stage table; there is
    # no multiplier on Phase 1. R32 = 0 because the R32 line-up is
    # published after groups (nothing to predict); R16 = 5 because R32
    # match-outcome scoring already implicitly pays for predicting who
    # advances. Deeper rounds carry most of the Phase 2 reward.
    phase_2:
      round_of_32: 0
      round_of_16: 5
      quarter_final: 15
      semi_final: 40
      final: 60
      winner: 100
```

> **Note on the architecture:** earlier versions of this scoring system
> used a `phase_multipliers:` block (Phase 2 = Phase 1 × 0.7). That
> block has been removed — Phase 1 and Phase 2 advancement points are
> now independent tables. See
> [`scoring-calibration-2026.md`](./scoring-calibration-2026.md) for the
> rationale and migration notes.

## Scoring Modes

### Fixed Scoring

In **fixed** mode, players receive flat points for correct predictions regardless of how many other players got it right.

**Example:**
- Correct outcome: 5 points
- Exact score: +10 points
- Total for exact score: 15 points

### Logarithmic Scoring (default)

In **logarithmic** mode, players receive base points plus a rarity bonus
derived from **Shannon surprisal** — bits of information the crowd's prior
was wrong by. Predicting outcomes the room avoided is rewarded; riding
consensus pays nothing extra.

**Formula:**

```
R = min(rarity_cap, round(alpha * log2(1 / (2f))))   for f < 0.5
R = 0                                                for f >= 0.5

where  f     = correct_predictors / total_predictors
       alpha = 10 / log2(15) ≈ 2.5596
```

`total_predictors` is the number of users who submitted a prediction for
*that fixture* ("the room that showed up"), not the global active-user
count. `correct_predictors` is the subset of those who picked the actual
outcome.

**Key properties:**

- **Gated at 50%.** Consensus picks (≥ half the predictors correct) earn
  no rarity premium — base points only.
- **Anchored.** Alpha is chosen so that a uniquely correct pick out of 30
  predictors (f = 1/30 ≈ 3.3%) hits the cap of 10. Rarer picks stay
  capped.
- **Scale-invariant.** The same fraction `f` produces the same bonus
  regardless of pool size — so the published band table below applies
  whether there are 12, 30, or 60 predictors.

**Published bonus by % of predictors who picked the correct outcome:**

| f (correct %) | Rarity bonus R |
|---:|---:|
| > 43.67% | 0 |
| 33.31% – 43.67% | 1 |
| 25.41% – 33.31% | 2 |
| 19.38% – 25.41% | 3 |
| 14.78% – 19.38% | 4 |
| 11.28% – 14.78% | 5 |
| 8.60% – 11.28% | 6 |
| 6.56% – 8.60% | 7 |
| 5.00% – 6.56% | 8 |
| 3.82% – 5.00% | 9 |
| ≤ 3.82% | 10 (cap) |

**Worked examples (30 predictors):**

- Uniquely correct (1 of 30, f ≈ 3.3%): 5 + 10 + (10 if exact) = **15 or 25**
- One-in-ten correct (3 of 30, f = 10%): 5 + 6 = **11** (or **21** with exact)
- Three-way split (10 of 30, f ≈ 33%): 5 + 1 = **6** (or **16** with exact)
- Half-right (15 of 30, f = 50%): 5 + 0 = **5** (or **15** with exact)
- Unanimous correct (30 of 30): 5 + 0 = **5** (or **15** with exact)

**Why logarithmic?** Log scoring is the unique *proper scoring rule* whose
payoff depends only on the probability assigned to the realized outcome
(Good, 1952). It treats "halving the underdog odds" as a fixed-size reward
— going from 20% to 10% adds the same ~2.5 points as going from 10% to 5%
— which matches how forecasters actually think about belief revision.

### Hybrid Scoring (legacy)

In **hybrid** mode, the rarity bonus uses integer division instead of a log:

```
R = min(hybrid_cap, total_predictors // correct_predictors)
```

Kept registered for backward compatibility with any deployment still
configured with `mode: "hybrid"`. The integer-divide formula has visible
plateaus and gaps that the logarithmic curve smooths out; logarithmic
should be preferred for new deployments.

## Match Prediction Points

| Prediction | Fixed Mode | Logarithmic / Hybrid Mode |
|------------|-----------|---------------------------|
| Correct outcome (1-X-2) | 5 pts | 5 pts + rarity bonus (0-10 pts) |
| Exact score bonus | +10 pts | +10 pts |
| **Maximum per match** | 15 pts | 25 pts |

### Outcome Types
- **1** = Home team wins
- **X** = Draw
- **2** = Away team wins

## Advancement Prediction Points

Points are awarded when a team reaches at least the predicted stage.
Phase 1 and Phase 2 read from **independent point tables** — there is
no implicit multiplier between them, and each stage's value for each
phase is set explicitly in YAML.

| Stage | Phase 1 | Phase 2 | Notes |
|---|---:|---:|---|
| Round of 32 | 10 | **0** | Phase 2 zero: bracket is published after groups, no prediction skill |
| Round of 16 | 15 | **5** | Phase 2 minimal: R32 match-outcome already pays for "X beats Y" |
| Quarter-final | 20 | 15 | |
| Semi-final | 40 | 40 | |
| Final | 60 | 60 | |
| Winner | 100 | 100 | |
| Group position bonus | 5 | — | Phase 1 only; derived from group match score predictions, paid only when the team qualifies (positions 1 or 2 always, position 3 only if a best-8-thirds qualifier). See below. |

The current values are illustrative — the live values come from
`config/worldcup2026.yml`. Fetch them at runtime via `GET
/api/leaderboard/scoring-rules` (Phase 2 values are nested under
`advancement.phase_2`).

### Group position bonus (Phase 1 only)

Predicting that a team finishes in a specific group position is *not*
a separate UI step. Instead, the user's predicted group standings are
**derived from their group match score predictions** via
[`services/standings.get_predicted_group_standings`](../backend/app/services/standings.py),
applying the same FIFA tiebreaker chain (points → GD → GF → H2H) used
on actual results. For each team where the user's predicted position
matches the actual position **and** the team qualifies for R32, the
user earns the `group_position` value (default 5) on top of the R32
base.

Eligibility rules:

- **Position 1 or 2** in any group → always qualifies → bonus paid on match
- **Position 3** → bonus only if the team is one of the 8 best-third-placed teams that qualify
- **Position 4** → never qualifies, never paid

Phase 2 has no group match score predictions (groups are done by then),
so the bonus is Phase 1 only.

### Why Phase 2's smaller R32 / R16 values?

When Phase 2 opens, the R32 bracket is already determined by the
actual group standings — predicting it is trivial, so it pays nothing.
R16 advancement is largely redundant with the user's R32 match-outcome
predictions: if you predict "Brazil beats Argentina 2-1" you've
already earned 5 + (exact + rarity) for that match; awarding a full
R16 advancement bonus on top would double-pay the same insight. The
token 5 points reflects only the marginal "you knew Brazil belonged
in R16" signal that isn't already captured by match scoring.

## API Endpoint

You can fetch the current scoring configuration via the API:

```
GET /api/leaderboard/scoring-rules
```

**Response:**
```json
{
  "mode": "logarithmic",
  "available_modes": ["fixed", "hybrid", "logarithmic"],
  "match": {
    "correct_outcome": 5,
    "exact_score": 10,
    "rarity_cap": 10,
    "hybrid_cap": 10
  },
  "advancement": {
    "round_of_32": 10,
    "round_of_16": 15,
    "quarter_final": 20,
    "semi_final": 40,
    "final": 60,
    "winner": 100,
    "group_position": 5,
    "phase_2": {
      "round_of_32": 0,
      "round_of_16": 5,
      "quarter_final": 15,
      "semi_final": 40,
      "final": 60,
      "winner": 100
    }
  }
}
```

The response no longer includes a `phase_multipliers` field — Phase 2
values are nested under `advancement.phase_2` and read directly by the
scoring engine. The frontend has never consumed `phase_multipliers`, so
removing it is invisible to UI; any third-party consumer that depended
on it needs to read the per-stage table instead.

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
        total_predictors: int,
        correct_predictors: int,
    ) -> tuple[int, bool, bool]:
        """
        Calculate match points.

        Args:
            prediction: User's prediction
            score: Actual match result
            config: Match scoring config from YAML
            total_predictors: Number of users who submitted a prediction
                for this fixture
            correct_predictors: Number of those who picked the actual outcome

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
    "logarithmic": LogarithmicScoring(),
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
        "quarter_final": 20,
        "semi_final": 40,
        "final": 60,
        "winner": 100,
        # Phase 1 group-position bonus (derived from match score
        # predictions; paid only for qualifying positions).
        "group_position": 5,
        # Phase 2 — explicit per-stage. No multiplier.
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
```

Partial configs are merged with defaults, so you only need to specify values you want to change. Setting `advancement.phase_2.winner: 90` in your YAML, for example, overrides just that one stage's Phase 2 reward; all other Phase 2 stages fall back to defaults.
