# Scoring System: 2026 Calibration Changes

> **Status:** Live in `config/worldcup2026.yml` as of the May 2026
> calibration session.
>
> **Audience:** developers working anywhere near scoring, points
> breakdowns, the leaderboard, the prediction wizard, the rules page,
> email receipts, or the `/scoring-rules` API.
>
> **Why this doc exists:** the canonical scoring reference
> (`docs/scoring-system.md`) was written when the scoring system used a
> Phase 2 = 70% Phase 1 multiplier, and several places in the code +
> user-facing copy still reflect that model. This doc explains what
> actually runs today and lists every place we know still needs
> updating.

---

## TL;DR

Three substantive changes landed:

1. **`phase_multipliers` is gone.** Phase 1 and Phase 2 advancement
   points are now **independent point tables** in the YAML
   (`scoring.advancement` for Phase 1, `scoring.advancement.phase_2` for
   Phase 2). There is no implicit multiplication — every stage's value
   for every phase is explicit.
2. **Group position scoring is now live** for Phase 1. Previously the
   YAML had a `group_position: 5` key that **was never read** — it was
   dead config. It now pays 5 pts per team whose predicted group
   position (derived from the user's group match score predictions)
   matches their actual position, conditional on the team qualifying
   for the knockout stage.
3. **Two real bugs were fixed**:
   - The frontend wrote QF/SF stages as `quarter_finals` / `semi_finals`
     (plural) while scoring only recognized `quarter_final` /
     `semi_final` (singular). Every QF and SF advancement prediction was
     silently scoring zero before the fix.
   - The `group_advance` and `group_position` YAML keys were never read
     by `calculate_advancement_points` (the keys didn't match the
     `stage_order` chain). `group_advance` is now removed (its job is
     implicitly done by `round_of_32`); `group_position` is now wired
     correctly.

If your mental model is "Phase 2 is just Phase 1 × 0.7", update it.

---

## Why we changed it

A calibration sim (Monte Carlo over 500 tournaments × 30 predictors,
using the real scoring code; see `backend/scripts/simulate_scoring.py`)
showed three things about the old setup:

- The percentage of competition winners who actually picked the
  tournament champion was ~49% — basically a coin flip. The competition
  rewarded *consistency over many predictions* much more strongly than
  *deep insight about who wins the trophy*. Stakeholder explicitly
  wanted this skewed toward "winning predictor usually picked the
  champion."
- The R32 and R16 advancement points dominated the bracket payoff
  (~33% of the average winner's total) because they were scored in both
  phases at 1.0× and 0.7× of the same base, while QF/SF/Final/Winner
  rounds combined only contributed ~17% of total points. Boosting deep
  stages was the obvious lever.
- The R32 and R16 picks in Phase 2 specifically are largely redundant
  with the Phase 2 match-outcome scoring (if you correctly predict the
  R32 game's outcome you've already implicitly predicted R16
  advancement). Phase 2 advancement points at those rounds were
  double-paying.

The calibration set the new YAML to a target of ~55–60% champion-pick
rate at ~33% group share, with Phase 2's R32/R16 zeroed out / squashed
to reflect their post-groups redundancy.

---

## The new architecture

### YAML shape (current, live)

```yaml
scoring:
  mode: logarithmic
  match:
    correct_outcome: 5      # base outcome reward (per match)
    exact_score: 10         # exact score bonus (per match)
    rarity_cap: 10          # cap on the logarithmic rarity bonus
    hybrid_cap: 10          # legacy fallback alias for rarity_cap

  advancement:
    # Phase 1 — pre-tournament picks, full reward
    round_of_32: 10
    round_of_16: 15
    quarter_final: 25
    semi_final: 55
    final: 85
    winner: 150
    group_position: 5

    # Phase 2 — explicit per-stage, independent table
    phase_2:
      round_of_32: 0
      round_of_16: 5
      quarter_final: 15
      semi_final: 40
      final: 60
      winner: 100
```

There is no `phase_multipliers:` block any more, anywhere. Don't
re-introduce one.

### How `calculate_advancement_points` looks up values

```python
# backend/app/services/scoring.py
if phase == PredictionPhase.PHASE_2:
    stage_points = adv_config.get("phase_2", {})
else:
    stage_points = adv_config

return int(stage_points.get(predicted_stage, 0))
```

That's the whole policy. Add a new phase? Add a new top-level key under
`advancement` and branch on it here. Match-prediction points are *not*
affected by phase (they never were — that was always handled
separately).

### How the leaderboard breakdown surfaces this

`PhaseBreakdown` (in `app/schemas/leaderboard.py`) already has separate
fields per stage per phase (`phase1.r32_points`,
`phase2.r32_points`, etc.). Nothing on the API contract changed —
Phase 2 buckets just now read from the explicit table instead of being
the multiplied Phase 1 values.

`PhaseBreakdown.group_advance_points` and `group_position_points` are
still on the schema. `group_position_points` is now populated (was
always 0 before). `group_advance_points` remains 0 forever — it's a
legacy schema field that's tolerable to keep because removing it is an
API contract break for no functional benefit (it always sums to zero).

---

## The newly-live `group_position` feature

This is the bit most likely to surprise devs because it was in the
codebase as scaffolding for months but never paid out.

### What it does

For each team in each group, if the user's **predicted** group position
matches the **actual** group position AND the team qualified for the
knockout stage, the user earns `advancement.group_position` points
(currently 5). Eligibility rules:

- Position **1 or 2** → always qualifies → bonus paid on match
- Position **3** → bonus only if the team is one of the 8
  best-third-placed teams that qualify
- Position **4** → never qualifies, never paid

The bonus is **Phase 1 only**. Phase 2 has no group match score
predictions (groups are done by the time Phase 2 opens), so there are
no derived standings to compare.

### Where the predicted position comes from

There is no separate UI for "pick your group winners." The predicted
position is **derived** from the user's group match score predictions
via `services/standings.get_predicted_group_standings`, which runs the
same FIFA tiebreaker chain
(`_apply_fifa_tiebreakers` — H2H + alphabetical-with-warning) on
predicted scores instead of actual scores.

This was a deliberate design call:

- The wizard already derives predicted standings to seed the bracket
  display, so the user mental model "my match score picks imply a
  standings" is already established
- Avoids two sources of truth (explicit pick vs. derived from scores)
- Strengthens the value of careful score predictions

### What it cost

About **+57 points** to the average winner's total (12 groups × ~1.6
correctly-placed qualifiers × 5 pts). Group-stage share of the average
winner's total moved from 28% → 33%. As a side effect the
champion-pick rate dropped slightly (more group-experts can now beat
bracket-experts) — the deep-knockout boost in the Phase 1 advancement
table was sized to compensate.

### Where it lives in code

| Where | What |
|---|---|
| `config/worldcup2026.yml` → `scoring.advancement.group_position` | Point value |
| `backend/app/services/standings.py` → `get_predicted_group_standings` | Derive predicted standings from match preds |
| `backend/app/services/scoring.py` → `calculate_group_position_bonus` | Sum the bonus per user |
| `backend/app/services/scoring.py` → `calculate_user_points` | Adds the bonus into `phase1.group_position_points` |
| `backend/app/schemas/leaderboard.py` → `PhaseBreakdown.group_position_points` | Where the bonus surfaces in the API response |
| `backend/tests/test_scoring.py` → `TestGroupPositionBonus` | 7 test cases pinning the eligibility rules |

### The dead-code corollary

`group_advance` (worth 10 pts in the old YAML) is **gone** — fully
removed from YAML + `DEFAULT_SCORING_CONFIG`. The frontend bracket
wizard only writes stage values of `round_of_32` or higher (never
`group`), so there were never any rows for `group_advance` to score
against. Predicting a team into R32 = predicting they advanced from
their group, full stop. There is no separate "did they advance"
prediction distinct from the R32 pick.

---

## The QF/SF stage name fix

A historical artifact: the frontend `BracketPrediction` interface uses
plural field names (`quarter_finals: string[]`,
`semi_finals: string[]`) because the original UI exposed them that way.
When `bracketToPredictions` flattened those into the API payload, it
incorrectly used the plural form as the stored `stage` value. The
backend writer accepted it verbatim, the scoring chain looked for the
singular form, and every QF/SF bracket pick scored zero.

### What changed

- Frontend writer (`src/routes/predictions/+page.svelte` →
  `bracketToPredictions`) now writes singular stage values
- Backend GET endpoint (`api/predictions.py:get_bracket_predictions`)
  uses singular keys internally but still returns the plural-named
  response fields (preserved API contract for the frontend's
  `BracketPrediction` interface)
- `services/receipts.py` + `services/audit_log.py` stage-label maps
  now key on singular
- Migration `a1f4c9d2e731_normalize_qf_sf_stage_names.py` converted
  ~120 historical rows in `team_predictions` and
  `team_prediction_history`
- `tests/test_scoring.py` →
  `test_quarter_final_singular_stage` and `test_semi_final_singular_stage`
  pin singular = nonzero, plural = zero so this can't silently
  regress

### What didn't change

- Plural names are still used everywhere in the frontend response
  shape (`BracketPrediction.quarter_finals: string[]` etc.). That's a
  display convention only — only the stored DB `stage` value is
  singular.
- `BRACKET_STAGES_IN_ORDER` in receipts uses singular now; if you add
  a new map elsewhere, use singular.

---

## Lingering pre-calibration references — please update when you touch these

These are files that still describe or display the old 0.7× multiplier
model. They're not breaking anything, but they tell users / future devs
the wrong story.

### Highest priority (user-facing copy)

**`frontend/src/routes/rules/+page.svelte:148-173`** — the rules page
shown to players literally says **"Phase II points at 70% value"** and
contains a Phase II description that includes "Phase II points are
scaled to **70%** of their face value." This is wrong now. Suggested
rewording:

> *Phase II points are independently set per stage — generally smaller
> than Phase I (because you have more information), with R32 worth
> nothing and R16 worth only a token amount, since the R32 match-outcome
> scoring already implicitly rewards picking who advances.*

Or just point users at the `/scoring-rules` API response for the live
values.

### High priority (canonical docs)

**`docs/scoring-system.md:46, 153-164`** — the canonical scoring
reference still documents the `phase_multipliers: phase_2: 0.7` config
block and shows a Phase 2 points table computed as Phase 1 × 0.7
(group advance 7, R16 10.5, winner 70, etc.). The whole
"Advancement Prediction Points" section needs rewriting against the new
two-column-per-stage shape. While you're in there:

- Remove the `group_advance` row (key is gone from YAML)
- Update `group_position` row to reflect that it's now active and
  derived (not stored explicitly)
- Update Phase 1 numbers to the calibrated values
  (QF 25 / SF 55 / F 85 / W 150)
- Update Phase 2 numbers to the explicit table values
  (R32 0 / R16 5 / QF 15 / SF 40 / F 60 / W 100)

### Medium priority (code comments)

**`backend/app/services/bracket_exposure.py:11`** — docstring still
says *"Multiplied by the phase multiplier"*. Should now say something
like *"Read from the per-phase point table
(`advancement.phase_2` for Phase 2)."* The code itself
(`compute_bracket_exposure`, line ~155) was already updated to read
the per-phase table — only the docstring is stale.

### Where to double-check yourself

If you touch any of these areas, you're in the blast radius — search
for `phase_multiplier`, `0.7`, `70%`, or `reduced points` first:

```
backend/app/api/leaderboard.py             — /scoring-rules endpoint shape
backend/app/services/scoring.py            — calculate_advancement_points
backend/app/services/bracket_exposure.py   — points-available math
backend/app/schemas/leaderboard.py         — PhaseBreakdown buckets
frontend/src/routes/rules/+page.svelte     — user-facing copy
frontend/src/lib/types/index.ts            — PointBreakdown shape
frontend/src/lib/components/panini/...     — anywhere that displays Phase 2 vs Phase 1
docs/scoring-system.md                     — canonical reference
```

---

## Reasoning about future calibration changes

A permanent calibration tool ships at
`backend/scripts/simulate_scoring.py`. It generates synthetic
tournaments + synthetic predictors, runs them through the *real*
scoring code (imports `LogarithmicScoring` and
`calculate_advancement_points`), and reports point distributions per
source category.

Run a sweep before changing scoring values:

```bash
docker compose exec backend python scripts/simulate_scoring.py \
    --tournaments 500 --predictors 30 --seed 42
```

This generates `backend/scripts/scoring-calibration-report.md` (move
to `docs/` after). Sweep variants live in `all_variants()` — add a new
function + register it in the returned list to test your change against
the baseline.

Key metrics in the report:

- **% picked champ** — fraction of tournaments where the winning
  predictor's bracket had the actual champion. Stakeholder target is
  "more often than not" (50%+); current calibration lands at ~55%.
- **Skill→rank correlation** — should be meaningfully negative
  (~-0.30) if skill is being rewarded; closer to 0 means luck is
  drowning out skill.
- **Group / Bracket / Bonus %** — share of the average winner's total
  by source. Sanity-check no single source dominates.

If you change YAML and these shift unexpectedly, that's the calibration
contract breaking — investigate before merging.

---

## Reference: current calibration values

| Stage | Phase 1 | Phase 2 | Notes |
|---|---:|---:|---|
| Round of 32 | 10 | **0** | P2 zero: bracket published after groups |
| Round of 16 | 15 | **5** | P2 minimal: R32 match-outcome already pays for advancement |
| Quarter-final | 25 | 15 | |
| Semi-final | 55 | 40 | |
| Final | 85 | 60 | |
| Winner | 150 | 100 | |
| Group position bonus | 5 | — | Phase 1 only; derived from group match score predictions; only paid for qualifying positions |
| Group advance | — | — | Removed; implicitly covered by R32 |

| Match prediction | Value |
|---|---:|
| Correct outcome (1-X-2) | 5 |
| Exact score bonus | +10 |
| Rarity bonus (logarithmic, capped) | 0–10 |

| Bonus questions | Value per question |
|---|---:|
| Group stage (4 questions) | 15 |
| Top/Flop (2 questions) | 20 |
| Awards (4 questions) | 20 |

---

## Open questions / known follow-ups

- **`scoring-system.md` rewrite** (high priority) — bring the canonical
  doc in line with this calibration.
- **Rules page rewrite** (user-facing) — see above.
- **`PhaseBreakdown.group_advance_points`** — schema field that's now
  always zero. Could be removed in a future API-contract change; not
  worth doing on its own.
