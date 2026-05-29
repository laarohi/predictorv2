# Scoring Calibration Report

Monte Carlo simulation across **500 tournaments** with **30 predictors** per tournament. The simulator uses the real `LogarithmicScoring` and `calculate_advancement_points` code so the numbers reflect what the actual app would award.

**Methodology** — Each team has a strength on a log-odds scale (FIFA top-25 ranking + synthetic mid/lower tiers). Match outcomes are Poisson(strength-difference) goals. Each predictor has a personal *skill* (perception precision); they predict matches using their noisy perception through the same Poisson model. Higher skill = better predictions, but never deterministic. Predictors also run a 'mental tournament' to produce their bracket. Phase 1 + Phase 2 advancement predictions are both scored (Phase 2 at the multiplier in config).

## Reading the table

Each row is one config variant. Columns:

- **Winner pts** — average total points of the tournament-winning predictor
- **% picked champ** — fraction of tournaments where the winning predictor's bracket had the actual champion at `stage=winner`. **Higher is better** (the user wants winners to typically have nailed the champion).
- **Skill→rank corr** — correlation between predictor skill and final rank. Negative is better — means higher-skill predictors finish higher. A corr close to 0 means luck is dominating skill.
- **Group %** / **Knockout %** / **Bracket %** / **Bonus %** — for the average winner, what fraction of their total came from each source
- **Exact %** — fraction of winner's total that came from the +10 exact-score bonus

---

| Variant | Winner pts | % picked champ | Skill→rank corr | Group % | Knockout match % | Bracket % | Bonus % | Exact % | Rarity % |
|---|---|---|---|---|---|---|---|---|---|
| baseline (current YAML) | 909 | 55% | -0.32 | 33% | 11% | 52% | 4% | 8% | 3% |
| tame_rarity_bonus (cap 5) | 908 | 55% | -0.32 | 33% | 11% | 52% | 4% | 8% | 3% |
| tame_exact_score (exact 7) | 888 | 57% | -0.30 | 32% | 11% | 53% | 4% | 5% | 3% |
| boost_phase2 (closer to Phase 1) | 1006 | 57% | -0.31 | 30% | 10% | 56% | 4% | 7% | 3% |
| tame_phase2 (R16=0, deeper discount) | 865 | 55% | -0.33 | 35% | 12% | 49% | 5% | 8% | 4% |
| boost_winner (P1 W 200 / P2 W 140) | 967 | 70% | -0.31 | 30% | 10% | 56% | 4% | 7% | 3% |
| tame_group_position (3 pts) | 886 | 56% | -0.31 | 31% | 12% | 53% | 4% | 8% | 4% |
| no_group_position (0 pts) | 863 | 62% | -0.31 | 28% | 12% | 56% | 5% | 8% | 4% |

---

## Detailed breakdown per variant

### baseline (current YAML)

- avg winner total: **909 pts**
- avg winner skill: 1.07
- % tournaments where winner picked the actual champion: **55%**
- skill-vs-rank correlation: -0.32

Winner's avg points by source:

| source | avg pts |
|---|---:|
| group_match_outcome | 172 |
| group_match_exact | 49 |
| group_match_rarity | 20 |
| group_position | 57 |
| knockout_match_outcome | 70 |
| knockout_match_exact | 22 |
| knockout_match_rarity | 11 |
| r32 | 114 |
| r16 | 69 |
| qf | 48 |
| sf | 53 |
| final | 45 |
| winner | 138 |
| bonus | 39 |

### tame_rarity_bonus (cap 5)

- avg winner total: **908 pts**
- avg winner skill: 1.07
- % tournaments where winner picked the actual champion: **55%**
- skill-vs-rank correlation: -0.32

Winner's avg points by source:

| source | avg pts |
|---|---:|
| group_match_outcome | 172 |
| group_match_exact | 49 |
| group_match_rarity | 20 |
| group_position | 57 |
| knockout_match_outcome | 70 |
| knockout_match_exact | 22 |
| knockout_match_rarity | 11 |
| r32 | 114 |
| r16 | 69 |
| qf | 48 |
| sf | 54 |
| final | 46 |
| winner | 138 |
| bonus | 39 |

### tame_exact_score (exact 7)

- avg winner total: **888 pts**
- avg winner skill: 1.06
- % tournaments where winner picked the actual champion: **57%**
- skill-vs-rank correlation: -0.30

Winner's avg points by source:

| source | avg pts |
|---|---:|
| group_match_outcome | 171 |
| group_match_exact | 33 |
| group_match_rarity | 20 |
| group_position | 57 |
| knockout_match_outcome | 70 |
| knockout_match_exact | 15 |
| knockout_match_rarity | 11 |
| r32 | 114 |
| r16 | 70 |
| qf | 47 |
| sf | 52 |
| final | 46 |
| winner | 143 |
| bonus | 39 |

### boost_phase2 (closer to Phase 1)

- avg winner total: **1006 pts**
- avg winner skill: 1.07
- % tournaments where winner picked the actual champion: **57%**
- skill-vs-rank correlation: -0.31

Winner's avg points by source:

| source | avg pts |
|---|---:|
| group_match_outcome | 172 |
| group_match_exact | 48 |
| group_match_rarity | 20 |
| group_position | 57 |
| knockout_match_outcome | 70 |
| knockout_match_exact | 22 |
| knockout_match_rarity | 11 |
| r32 | 172 |
| r16 | 89 |
| qf | 53 |
| sf | 55 |
| final | 46 |
| winner | 153 |
| bonus | 38 |

### tame_phase2 (R16=0, deeper discount)

- avg winner total: **865 pts**
- avg winner skill: 1.08
- % tournaments where winner picked the actual champion: **55%**
- skill-vs-rank correlation: -0.33

Winner's avg points by source:

| source | avg pts |
|---|---:|
| group_match_outcome | 172 |
| group_match_exact | 50 |
| group_match_rarity | 21 |
| group_position | 58 |
| knockout_match_outcome | 71 |
| knockout_match_exact | 23 |
| knockout_match_rarity | 11 |
| r32 | 114 |
| r16 | 51 |
| qf | 42 |
| sf | 47 |
| final | 40 |
| winner | 126 |
| bonus | 40 |

### boost_winner (P1 W 200 / P2 W 140)

- avg winner total: **967 pts**
- avg winner skill: 1.05
- % tournaments where winner picked the actual champion: **70%**
- skill-vs-rank correlation: -0.31

Winner's avg points by source:

| source | avg pts |
|---|---:|
| group_match_outcome | 168 |
| group_match_exact | 46 |
| group_match_rarity | 20 |
| group_position | 56 |
| knockout_match_outcome | 70 |
| knockout_match_exact | 21 |
| knockout_match_rarity | 11 |
| r32 | 113 |
| r16 | 68 |
| qf | 44 |
| sf | 46 |
| final | 31 |
| winner | 239 |
| bonus | 35 |

### tame_group_position (3 pts)

- avg winner total: **886 pts**
- avg winner skill: 1.07
- % tournaments where winner picked the actual champion: **56%**
- skill-vs-rank correlation: -0.31

Winner's avg points by source:

| source | avg pts |
|---|---:|
| group_match_outcome | 171 |
| group_match_exact | 49 |
| group_match_rarity | 20 |
| group_position | 34 |
| knockout_match_outcome | 71 |
| knockout_match_exact | 22 |
| knockout_match_rarity | 11 |
| r32 | 114 |
| r16 | 69 |
| qf | 47 |
| sf | 54 |
| final | 45 |
| winner | 140 |
| bonus | 39 |

### no_group_position (0 pts)

- avg winner total: **863 pts**
- avg winner skill: 1.06
- % tournaments where winner picked the actual champion: **62%**
- skill-vs-rank correlation: -0.31

Winner's avg points by source:

| source | avg pts |
|---|---:|
| group_match_outcome | 171 |
| group_match_exact | 49 |
| group_match_rarity | 20 |
| group_position | 0 |
| knockout_match_outcome | 69 |
| knockout_match_exact | 21 |
| knockout_match_rarity | 11 |
| r32 | 113 |
| r16 | 68 |
| qf | 47 |
| sf | 57 |
| final | 42 |
| winner | 155 |
| bonus | 39 |
