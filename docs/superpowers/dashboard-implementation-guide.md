# Dashboard Implementation Guide

**Purpose**: complete reference for implementing the per-phase dashboards from claude-design files + the backend work that's already shipped + the small remaining backend extension. Written as a handoff so the work can resume after context is compacted.

**Companion docs** (read in this order if unfamiliar):
1. `docs/superpowers/dashboard-phase-widgets.md` — canonical widget plan, all five phases, all rounds of design feedback
2. `docs/superpowers/panini-redesign-decisions.md` — design system + decision log
3. This file — implementation playbook

---

## 0. Where we are right now

- **Dashboard plan**: complete through round 5 of design feedback. See `dashboard-phase-widgets.md`.
- **Backend support**: 5 of 6 endpoints shipped. One extension remaining (`DwScoringJourney` per-stage buckets). See *§5 Backend state*.
- **Frontend scaffolding**: dispatcher + 5 phase components exist. `DashGroupStage` is the moved-verbatim original dashboard; the other four are placeholder scaffolds waiting for designs.
- **Design files**: coming from claude-design. Implementation = combine designs + the data sources documented here.

---

## 1. The five UX phases

Derived in `frontend/src/lib/stores/phase.ts` via `deriveUxPhase`. Override-driven dev tooling already wired.

| `UxPhase` | Detection | Dashboard component |
|---|---|---|
| `pre_tournament` | `!phase1_locked` (defensive default when `phaseStatus` is null) | `DashboardPre.svelte` |
| `group_stage` | `phase1_locked && !is_phase2_active` | `DashGroupStage.svelte` (was DashboardGroup; renamed to escape svelte-hmr cache bug) |
| `between_phases` | `is_phase2_active && !phase2_bracket_locked` | `DashboardBetween.svelte` |
| `knockout_stage` | `is_phase2_active && phase2_bracket_locked` | `DashboardKO.svelte` |
| `post_competition` | Final fixture (`stage === 'final'`) status is `finished` (overrides lock states) | `DashboardPost.svelte` |

**Dev override**: visit `/?uxPhase=group_stage` (or any other value) in DEV. Also a floating `PnDevPhasePill` bottom-right with a phase-selector dropdown. See `frontend/src/lib/components/panini/PnDevPhasePill.svelte` + `+layout.svelte` URL handler.

---

## 2. Dispatcher + dashboard architecture

```
frontend/src/routes/+page.svelte                ← thin dispatcher (~40 lines)
└─ switches on $uxPhase via <svelte:component>
   ├─ DashboardPre.svelte                       (frontend/src/lib/components/panini/dashboard/)
   ├─ DashGroupStage.svelte                     ← preserves existing group-stage build verbatim
   ├─ DashboardBetween.svelte
   ├─ DashboardKO.svelte
   └─ DashboardPost.svelte

frontend/src/lib/components/panini/dashboard/widgets/
└─ DwPredictionNudge.svelte                     (built; calm/urgent visual states)
```

**The dispatcher uses `<svelte:component this={ActiveDashboard}>`** rather than `{#if/else if}` because svelte-hmr's proxy registry interacted badly with the if-chain pattern during the original build. **Critical lesson**: if you ever see `RangeError: Maximum call stack size exceeded` in `scheduler.flush` after a file move, the issue is svelte-hmr cache + path collision — fix by renaming the affected file to a path the registry has never seen.

**Why `DashGroupStage.svelte`** (not `DashboardGroup.svelte`): the original `+page.svelte` was `mv`-ed into `dashboard/DashboardGroup.svelte` during the dispatcher build, but svelte-hmr cross-wired the proxy registry between the old `+page.svelte` path and the new `DashboardGroup.svelte` path because they briefly held similar content. Renaming broke the cache association. Don't rename it back.

---

## 3. Final widget list per phase

These are the widgets to build, post round-5 feedback. **Cross-phase widgets are shared atoms** — build once, reuse with props.

### Cross-phase shared widgets (build first)

| Widget | Phases | File target |
|---|---|---|
| `DwUnsavedAlert` | Pre, Between, KO | `dashboard/widgets/DwUnsavedAlert.svelte` |
| `DwLeaderboard` (configurable: `limit`, `headerLabel`, `phaseFilter`, `neighborhood`) | All 5 | `dashboard/widgets/DwLeaderboard.svelte` |
| `DwKpiRow` (configurable per phase) | Group, Between, KO | `dashboard/widgets/DwKpiRow.svelte` |
| `DwMatchCard` (state-aware: live/upcoming/finished) | Group, KO | `dashboard/widgets/DwMatchCard.svelte` |
| `DwRecentResults` | Group, KO | `dashboard/widgets/DwRecentResults.svelte` |
| `DwTodaysGames` (with `allowEntry` prop for KO inline score entry) | Group, KO | `dashboard/widgets/DwTodaysGames.svelte` |
| `DwPredictionNudge` (already built) | Pre, Between | `dashboard/widgets/DwPredictionNudge.svelte` |

### Phase 1 — Pre-tournament

| # | Widget | Status | Data source |
|---|---|---|---|
| 1 | `DwUnsavedAlert` | REUSE | `$unsavedChangesCount`, `$hasUnsavedBracketChanges`, `$unsavedPhase2BracketPrediction` from `$stores/predictions` |
| 2 | `DwPreCountdownHero` | NEW | `$phase1Deadline`, `$phase1Countdown` + overall progress count (sum across sections) |
| 3 | `DwScoringPeek` | NEW | `getScoringConfig()` |
| 4 | `DwRulesPeek` | NEW | `getCompetitionInfo()` |
| 5 | `DwLeaderboard` (`limit="all"`, header="Players") | REUSE | `$leaderboard` |
| 6 | `DwPredictionNudge` (scope=`phase_1_open`) | REUSE | `$predictionsByFixture` |

Layout: alerts row → hero (full-width) → row 2 (3 cols: Scoring | Rules | Players).

### Phase 2 — Group stage

| # | Widget | Status | Notes |
|---|---|---|---|
| 1 | `DwKpiRow` | REDESIGN | 5 stickers: Rank / Total / Exact / Outcomes / Trajectory. Deltas use `▲ N` / `▼ N` arrows positioned **right of the main number**, not below. Trajectory sticker = inline `PnSparkline` + 7d delta + "Today: +N pts" subtext. Add `[ see full breakdown → ]` link below the row right-aligned. **No card tilts**. |
| 2 | `DwRecentResults` (1/3 row 2) | REUSE | Past 24h match cards. Click → `/results/[fixture_id]`. |
| 3 | `DwTodaysGames` (1/3 row 2) | REUSE | Upcoming 24h match cards. **Live matches stay in this column** until the scorer marks them final. |
| 4 | `DwLeaderboard` (`limit=5, neighborhood=true`, 1/3 row 2) | REUSE | Same widget; pin user's row + neighborhood if below #5. |

Layout: KPI row (full-width with breakdown link) → row 2 (3 cols: Past 24h | Upcoming 24h | Leaderboard). No row 3. No Up Next table (folded into Upcoming 24h).

### Phase 3 — Between phases

| # | Widget | Status | Notes |
|---|---|---|---|
| 1 | `DwUnsavedAlert` | REUSE | Watches `$unsavedPhase2BracketPrediction` |
| 2 | `DwBetweenHero` | NEW | Countdown + group-stage total teaser + primary CTA "Update bracket" |
| 3 | `DwKpiRow` | REUSE | Round-2 feedback: KPI row kept in this phase |
| 4 | `DwGroupStageSummary` | NEW (multi-phase) | 12-row table, Outc/Exact/Qual + bonus row + grand total + `[ details in Predict → ]` |
| 5 | `DwLeaderboard` (`limit=5, phaseFilter=phase_1`) | REUSE | Phase 1 final standings |
| 6 | `DwPredictionNudge` (scope=`phase_2_bracket`) | REUSE | Urgent escalation if <12h to bracket lock with gaps |

Layout: unsaved alert → hero (full-width) → KPI row (full-width) → row with summary table (~70%) + leaderboard (~30%).

### Phase 4 — Knockout stage

| # | Widget | Status | Notes |
|---|---|---|---|
| 1 | `DwKoMissingPicksAlert` | NEW | Red top banner. Just count + CTA: "4 MATCHES MISSING PREDICTIONS · [ PREDICT NOW → ]". No match names. Subsumes `DwPredictionNudge` for KO. |
| 2 | `DwUnsavedAlert` | REUSE | KO score drafts (`$unsavedChangesCount`) |
| 3 | `DwKpiRow` | REUSE | Same as group_stage |
| 4 | `DwRecentResults` (1/3 row 2) | REUSE | Past 24h |
| 5 | `DwTodaysGames` with `allowEntry={true}` (1/3 row 2) | REUSE+ | **Inline score entry** for upcoming KO matches. Score-input boxes capped at 15 per side. Save via existing `savePrediction(fixtureId)`. Card click (outside the inputs) → match detail. Wizard-card visual continuity. |
| 6 | `DwLeaderboard` (1/3 row 2, `limit=5, neighborhood=true`) | REUSE | |
| 7 | `DwScoringJourney` (~60-70% width, row 3) | NEW | **Round-5 design**: transposed (stages = rows), stacked (P1 on top, P2 below), 2 columns per phase (EARNED / AVAILABLE). Phase headers carry totals — no separate bracket-status line. See *§7 DwScoringJourney spec* below. |

Layout: missing-picks alert (conditional) → unsaved alert (conditional) → KPI row → row 2 (3 cols) → row 3 (DwScoringJourney, narrower).

### Phase 5 — Post-competition

| # | Widget | Status | Notes |
|---|---|---|---|
| 1 | `DwChampionPodium` | NEW | Hero, full-width. Three slots: **Overall Winner** (centre, gold trophy), **Phase 2 Winner** (left, no medal), **Group Stage Winner** (right, no medal). Bottom line: "Tournament won by [TEAM] · N of M picked it correctly". `[ full standings → ]` CTA bottom-right. |
| 2 | `DwFinalKpiRow` | NEW | 5-sticker row like group_stage but frozen: Rank (final), Total, **Peak** (best rank reached + day), Exact, Outcomes. No deltas. |
| 3 | `DwScoringJourney` (frozen variant, 1/2 width) | REUSE | AVAILABLE column collapses to empty everywhere (no in-play after tournament ends). Same widget shape. |
| 4 | `DwHighlights` (1/2 width) | NEW | 4-5 emoji-tagged retrospective stats from `GET /leaderboard/me/highlights` |
| 5 | `DwPostCelebration` | NEW | One-time confetti + trophy reveal on first visit per competition. localStorage seen-flag. Respect `prefers-reduced-motion`. |

---

## 4. Critical design principles (from `dashboard-phase-widgets.md`)

These apply globally to every widget being built:

1. **One viewport rule**: each dashboard fits within ~900px tall on desktop. Mobile naturally stacks but desktop should not scroll.
2. **Summarise, don't detail**: widgets are summary-level; deep dives live in `/predictions`, `/leaderboard`, `/results`, `/rules`.
3. **Route out for deep dives**: every summarising widget has a `[ see full ... → ]` link.
4. **The wizard transforms post-lock**: once Phase 1 locks, `/predictions` becomes a breakdown view. Dashboard CTAs route there. (This wizard transformation is a deferred follow-up; until built, the wizard shows its current locked-state view.)
5. **Visual continuity**: match cards on dashboard echo `PnResultsCard` from `/results` (compact form); KO score-entry cards echo wizard cards. Don't invent a separate visual language.
6. **Adjacent widgets fill vertical gaps**: don't bake fixed heights on paired widgets — below-row widgets expand to match the row above's max height.
7. **Delta indicators use arrows**: `▲ 2` (green), `▼ 1` (red), `—` (grey), positioned RIGHT of the main metric, never below.
8. **No card tilts**: KPI / sticker / match cards stay straight. `transform: rotate(...)` is reserved for small decorative accents only. **Reinforcement of the existing Panini-system rule.**

---

## 5. Backend state

### Shipped (no further work needed)

1. **`LeaderboardSnapshot` model + migration `cadef7c2acd7`**
   - Added columns: `exact_scores`, `correct_outcomes`
   - File: `backend/app/models/leaderboard_snapshot.py`
   - Snapshot creation populates them: `backend/app/services/snapshots.py:take_daily_snapshots`
   - **Existing rows backfilled with 0** via `server_default='0'`

2. **`GET /leaderboard/snapshots/me`** (extended)
   - File: `backend/app/api/leaderboard.py:189`
   - New params: `days` cap raised 90 → 365; new `all_time: bool` flag
   - Response includes `exact_scores` + `correct_outcomes` per snapshot point
   - Service: `get_user_trajectory(session, user_id, days, all_time)` — when `all_time=True`, the days filter is skipped
   - Used for: KPI row deltas + post-comp peak calculation

3. **`GET /leaderboard/tournament-winner`** (new)
   - File: `backend/app/api/leaderboard.py` (search `get_tournament_winner_pickers`)
   - Returns: `actual_winner` (from finished FINAL fixture), per-phase picker counts + totals
   - Used for: `DwChampionPodium` "N of M picked it correctly" line

4. **`GET /predictions/bracket-exposure`** (extended)
   - File: `backend/app/api/predictions.py:752`, service in `backend/app/services/bracket_exposure.py`
   - Existing extension: `alive_per_stage[stage]` + `teams_per_stage[stage]` (R16=16, QF=8, SF=4, F=2, W=1)
   - Used for: `DwBracketAlive` (deprecated) AND for `DwScoringJourney`'s correct-row data
   - **NOTE**: needs further extension for round-5 — see *§6 Remaining backend work* below

5. **`GET /leaderboard/me/highlights`** (new)
   - File: `backend/app/api/leaderboard.py` (search `get_my_highlights`)
   - Returns: `MyHighlights { best_exact_streak, biggest_climb, most_contrarian_correct, best_phase }` — all nullable when insufficient data
   - Computes from existing tables (MatchPrediction, Score, Fixture, LeaderboardSnapshot, PointBreakdown)
   - Used for: `DwHighlights` post-comp widget

### Already-existing endpoints to use as-is

- `GET /leaderboard/?phase=phase_1|phase_2|null` — leaderboard with phase filter
- `GET /leaderboard/breakdown/{user_id}` — PointBreakdown structure (cleanly separated phase1/phase2/bonus_question_points)
- `GET /predictions/agreements` — used by post-comp highlights (most contrarian-correct)
- `GET /competition/info` — `CompetitionInfo` (phase deadlines, entry fee, etc.) — `DwRulesPeek`
- `GET /leaderboard/scoring-rules` — scoring config — `DwScoringPeek`
- `GET /fixtures/` — all fixtures with status — `DwRecentResults`, `DwTodaysGames`
- `GET /fixtures/standings/actual` — actual group standings (gated when Phase 2 active) — `DwGroupStageSummary`
- `POST /predictions/matches` (via `savePrediction(fixtureId)`) — inline KO score entry on `DwTodaysGames`

---

## 6. Remaining backend work

**Only one extension needed before implementation can fully proceed.**

### `getBracketExposure(phase)` — extend for `DwScoringJourney` (round-5 spec)

Per stage X, the response needs:

- `known_count` — `|known_at_X|`, the EARNED denominator (teams currently confirmed at stage X based on finished previous-round matches)
- `tbd_count` — `|tbd_at_X|`, the AVAILABLE denominator (unplayed previous-round matches; each will produce one team at stage X)
- `correct_count` — EARNED numerator (user picks at X that are in `known_at_X`)
- `in_play_count` — AVAILABLE numerator (user picks at X that are teams in any unplayed previous-round match), **deduplicated per TBD match** (if user picked both teams in the same TBD match, count as 1, not 2)
- `correct_teams` — list of team names for the EARNED tooltip
- `in_play_teams` — list of team names for the AVAILABLE tooltip
- `correct_points` — points value of the EARNED cell (with phase multiplier applied)
- `in_play_points` — potential points value of the AVAILABLE cell (with phase multiplier applied)

### Implementation hints

- Existing helper `_compute_teams_that_made_stage` in `backend/app/services/bracket_exposure.py:107` returns `{stage: set_of_teams}` — directly gives us `known_at_X`.
- For `tbd_at_X`: query `Fixture` where stage = previous round and status != FINISHED. Each such fixture is a TBD match.
- For the dedup: when iterating user picks at stage X for the in-play count, group by which TBD match the team is in (look up each pick's team's upcoming match at the previous stage). Increment in_play by 1 per TBD match where the user has at least one pick.
- Phase 2: same structure but stage_points uses the `phase_2` nested key in scoring config (the round-3 manual fix in `bracket_exposure.py:161` already handles this).
- Update `BracketExposureResponse` in `backend/app/api/predictions.py:88` accordingly.

### Round-4 spec for the data model (precise rules)

For each stage X:
- `known_at_X` = winners of finished previous-round matches (R32 winners → R16 entry; R16 winners → QF entry; etc.)
- `tbd_at_X` = unplayed previous-round matches
- `|known_at_X| + |tbd_at_X| = stage_size` (16 / 8 / 4 / 2 / 1)

For a user pick T at stage X:
- If T ∈ `known_at_X` → EARNED (numerator++, denominator = `|known_at_X|`)
- If T is a team in any unplayed match of `tbd_at_X` → AVAILABLE (numerator++, denominator = `|tbd_at_X|`)
- Else (T eliminated) → not shown

**Subtle dedup**: per-TBD-match deduplication for AVAILABLE (only one team per match can advance).

### Cell visibility (driven by the data shape)

- `known_count > 0, tbd_count == 0` (stage fully resolved) → EARNED row shows, AVAILABLE empty
- `known_count > 0, tbd_count > 0` (stage partially resolved) → both rows show
- `known_count == 0, tbd_count > 0` (stage untouched) → only AVAILABLE row shows
- Empty cells: render empty, NO `—` placeholders

---

## 7. `DwScoringJourney` spec (round-5 final design)

Most-detailed widget; deserves its own section.

### Layout

- ~60-70% of dashboard width on desktop (the user opted not to fill the right-side space; treat as breathing room)
- Stages are ROWS (R16, QF, SF, FINAL, WINNER — top to bottom in tournament order)
- Buckets are COLUMNS (EARNED / AVAILABLE)
- Two phase sub-grids stacked vertically: **PHASE 1 (top)**, then **PHASE 2 (below)**
- Each sub-grid wrapped in a `pn-card` box with hard offset shadow

### Per-cell content

Each cell is a wider horizontal bar (~12-16px tall) with:

1. **Fill**: filled portion = count / progressive denominator; coloured per column (EARNED = `var(--green)` `#1b6c3e`; AVAILABLE = `var(--gold)` `#d49a2e`)
2. **Bar background**: `var(--paper-3)` `#dfd4ba`
3. **Points value**: positioned at the right-end of the *filled* portion, OUTSIDE the fill, in row colour. Format: `40 pts` — `pts` suffix is mandatory.
4. **Fraction in parens**: immediately after the points value, smaller font, in `var(--ink-2)` `#514a3d`. Format: `(8/16)`.
5. Hard-edged, no rounded corners.

Full cell content example: `[████████████ 40 pts (8/16)]`.

### Phase headers

Each phase sub-grid has a header in mono uppercase:

```
PHASE 1 · ORIGINAL · earned 80 pts · available 275 pts
PHASE 2 · RE-PICK  · earned 180 pts · available 18 pts
```

- **No multiplier badges** (`×1.0` / `×0.7` dropped from headers — info lives in `/rules`)
- Earned + available totals fold INTO the header (the separate `DwBracketStatusLine` widget has been dropped)

### Row labels

- Stage names on the far left in mono uppercase: `R16`, `QF`, `SF`, `FINAL`, `WINNER`
- Bucket column headers above the bars: `EARNED`, `AVAILABLE`
- Inter-row rule between stages: `var(--paper-3)` at ~0.5px for structure

### Tooltips

Hover desktop / tap mobile reveals team names plus points:
- EARNED tooltip: `ARG · BRA · ENG · FRA · earned 40 pts`
- AVAILABLE tooltip: `USA · MEX · GER · ITA · potential 80 pts`

Use existing Panini tooltip pattern (paper background, ink border, hard shadow).

### Frozen variant (Post phase)

In post-competition, the AVAILABLE column for every row collapses to empty (no in-play after tournament ends). Same widget structure — just data driven empty for AVAILABLE.

### Vocabulary

The vocabulary is **EARNED + AVAILABLE** across the entire dashboard. Earlier drafts had "alive" — that's been replaced with "available" everywhere for one-word-consistency. Don't reintroduce "alive" or "in-play" in any UI string.

---

## 8. Phase scaffolds — what's already built

The five `Dashboard*.svelte` components in `frontend/src/lib/components/panini/dashboard/` exist as scaffolds. Implementation = replacing each scaffold's placeholder content with the real widgets.

- `DashboardPre.svelte` — has the prediction nudge + a "coming soon" placeholder hero
- `DashGroupStage.svelte` — **has the original full 9-widget dashboard verbatim**. The redesign per round-5 spec replaces this in-place.
- `DashboardBetween.svelte` — placeholder hero + nudge
- `DashboardKO.svelte` — placeholder hero + conditional nudge
- `DashboardPost.svelte` — placeholder hero

Each scaffold wraps its own `<PnPageShell>` (so don't add another wrapper).

---

## 9. Implementation order (recommended)

### Step 1 — Build the cross-phase widgets first (one-time investment, reused 5× over)

1. `DwUnsavedAlert.svelte` (already built — reuse as-is)
2. `DwPredictionNudge.svelte` (already built — reuse as-is)
3. `DwLeaderboard.svelte` (configurable; extract from current leaderboard table on `/leaderboard`)
4. `DwKpiRow.svelte` (extract from `DashGroupStage.svelte`'s inline KPI row; apply round-5 visual tweaks: arrow deltas right of number, trajectory sticker variant)
5. `DwMatchCard.svelte` (shared atom; state-aware: `kind: 'live' | 'finished' | 'upcoming'`; for KO `allowEntry={true}` adds inline score inputs)
6. `DwRecentResults.svelte` (uses DwMatchCard)
7. `DwTodaysGames.svelte` (uses DwMatchCard, takes `allowEntry` prop)

### Step 2 — Backend extension for `DwScoringJourney`

Extend `getBracketExposure` per §6 above. This unblocks Phase 4.

### Step 3 — Phase 1 (Pre-tournament)

Build:
- `DwPreCountdownHero.svelte`
- `DwScoringPeek.svelte`
- `DwRulesPeek.svelte`

Replace `DashboardPre.svelte` placeholder with the real composition.

### Step 4 — Phase 2 (Group stage redesign)

This is the biggest single component change because `DashGroupStage.svelte` currently holds the ~760-line legacy dashboard. The redesign is essentially a full rewrite of this file using the new widgets.

Use the new layout from `dashboard-phase-widgets.md` Phase 2 section: KPI row + 3-column row (Past 24h | Upcoming 24h | Leaderboard). No row 3.

### Step 5 — Phase 3 (Between phases)

Build:
- `DwBetweenHero.svelte`
- `DwGroupStageSummary.svelte` (multi-phase; also used in KO + Post)

Replace `DashboardBetween.svelte` placeholder.

### Step 6 — Phase 4 (Knockout)

Build:
- `DwKoMissingPicksAlert.svelte`
- `DwScoringJourney.svelte` (the biggest new widget; relies on Step 2's backend extension)

Replace `DashboardKO.svelte` placeholder. Also enables `allowEntry={true}` on `DwTodaysGames`.

### Step 7 — Phase 5 (Post-competition)

Build:
- `DwChampionPodium.svelte`
- `DwFinalKpiRow.svelte` (variant of `DwKpiRow` — frozen values, Peak sticker replaces Trajectory)
- `DwHighlights.svelte`
- `DwPostCelebration.svelte` (one-time animated reveal; respect `prefers-reduced-motion`)

Replace `DashboardPost.svelte` placeholder.

---

## 10. Testing / verification

### Visual smoke test all 5 phases

The dev URL override is wired. Visit each:

```
http://localhost:5173/?uxPhase=pre_tournament
http://localhost:5173/?uxPhase=group_stage
http://localhost:5173/?uxPhase=between_phases
http://localhost:5173/?uxPhase=knockout_stage
http://localhost:5173/?uxPhase=post_competition
```

The floating `PnDevPhasePill` (bottom-right, DEV only) also lets you switch phases interactively without typing URLs.

### Phase seed scripts (data-path testing)

Visual override only fakes the dispatcher; data-path testing needs real backend state. Use the seed scripts in `backend/scripts/`:

```bash
# Pre-tournament (Phase 1 deadline = now + 7d; clears scores; resets fixtures)
docker-compose exec backend python -m scripts.seed_phase_pretournament
docker-compose exec backend python -m scripts.seed_phase_pretournament --undo

# Between phases (wraps seed_phase2_test; sets phase2_bracket_deadline = now + 24h)
docker-compose exec backend python -m scripts.seed_phase_between
docker-compose exec backend python -m scripts.seed_phase_between --undo

# Post-competition (marks FINAL fixture FINISHED with a score)
docker-compose exec backend python -m scripts.seed_phase_post
docker-compose exec backend python -m scripts.seed_phase_post --undo
```

These are idempotent and reversible.

### Frontend tests

```bash
# All frontend tests
cd frontend && npx vitest run

# Specific file
cd frontend && npx vitest run src/lib/stores/phase.test.ts
```

Current baseline: **137 tests pass**, 0 failures. Don't regress.

### Frontend type check

```bash
cd frontend && npm run check
```

Current baseline: **0 errors, 59 warnings** (pre-existing). Don't add errors.

### Production build sanity

```bash
cd frontend && npm run build
```

Should succeed in ~30s. Catches issues that vitest doesn't.

### Backend tests

```bash
# backend image is dev-dep-free — install pytest transiently:
docker-compose exec backend pip install pytest pytest-asyncio httpx
docker-compose exec backend python -m pytest tests/ -v
```

Current baseline: **267 tests pass**, 1 unrelated pre-existing failure (`test_wikipedia_html_snapshot_is_available` — missing HTML file in `docs/`). Don't regress past that.

---

## 11. Gotchas / lessons learned (don't relearn the hard way)

### 1. svelte-hmr proxy bug with file moves

If you `mv` a Svelte component and the new path's content is similar to what the old path had, `svelte-hmr`'s proxy registry can cross-wire and produce `RangeError: Maximum call stack size exceeded` in `scheduler.flush`. **Fix**: rename the new file to a path the registry has never seen. Don't restart the container — that's not enough.

### 2. No card tilts

Panini-system rule. `transform: rotate(...)` is allowed only on small decorative accents (logo, corner-tag pills, avatar chips). KPI / sticker / match cards stay axis-aligned. Reinforced in round-2 design feedback.

### 3. Avoid bare semantic class names (DaisyUI collisions)

DaisyUI defines `.menu`, `.stat`, `.card`, `.btn`, `.modal`, `.alert` etc. globally. Always prefix new component classes with `pn-` to avoid collisions. Memory: `feedback_daisyui_class_collisions.md`.

### 4. Pytest in backend container

Backend image is built without dev deps. Before running tests:
```bash
docker-compose exec backend pip install pytest pytest-asyncio httpx
```
Memory: `feedback_pytest_in_backend_container.md`.

### 5. Parallel dev container needs network connect

If running an extra dev container outside docker-compose:
```bash
docker network connect predictorv2_default <container-name>
```
Otherwise Vite proxy can't resolve `backend`. Memory: `feedback_parallel_dev_container_network.md`.

### 6. Don't edit CLAUDE.md inside a worktree

Only land CLAUDE.md edits on main; the user only lands worktrees if successful. Memory: `feedback_claude_md_in_worktree.md`.

### 7. Datetime invariant: always UTC-aware

Every datetime in the system is `TIMESTAMPTZ`. Use `utc_now()` from `app.models._datetime`, never `datetime.utcnow()` (deprecated and naive). See CLAUDE.md "Datetime Rule".

---

## 12. Key file paths

### Frontend

```
frontend/src/lib/stores/
├── phase.ts                              ← uxPhase derivation + dev override + currentTime readable
├── phase.test.ts                         ← 9 vitest specs for deriveUxPhase
├── fixtures.ts                           ← fixtures + liveFixtures + upcomingFixtures + actualStandings
├── leaderboard.ts                        ← leaderboard + currentUserPosition + totalParticipants
├── predictions.ts                        ← matchPredictions + bracketPrediction + phase2BracketPrediction
│                                            + unsavedChangesCount + hasUnsavedBracketChanges + savePrediction
├── auth.ts                               ← user + isAuthenticated
└── unsavedPersistence.ts                 ← localStorage-backed drafts

frontend/src/lib/api/
├── leaderboard.ts                        ← getMyRankTrajectory + getSteepestClimbers + (NEW) tournament-winner + highlights
├── predictions.ts                        ← getAgreements + getBracketExposure (extended round 5)
├── competition.ts                        ← getCompetitionInfo + getPhaseStatus + getScoringConfig
└── fixtures.ts                           ← getAllFixtures + getActualStandings + getKnockoutFixtures

frontend/src/lib/components/panini/
├── PnPageShell.svelte                    ← wraps every dashboard
├── PnMast.svelte / PnBottomNav.svelte    ← chrome
├── PnStrip.svelte                        ← red sub-strip beneath masthead
├── PnFlag.svelte / PnAxisFlag.svelte     ← team flags
├── PnIcon.svelte                         ← 18-piece icon set
├── PnSparkline.svelte                    ← 7-point trajectory chart
├── PnDropdown.svelte                     ← themed select
├── PnDevPhasePill.svelte                 ← dev URL/dropdown phase switcher
├── PnResultsCard.svelte                  ← /results match card (compact form on dashboard)
├── PnBubbleGrid.svelte / PnPointsBar.svelte / PnMatchLeaderboard.svelte  ← match-detail visualisations
├── PnKnockoutBracket.svelte / PnBracketMatch.svelte                       ← bracket components
└── dashboard/
    ├── DashboardPre.svelte               ← scaffold
    ├── DashGroupStage.svelte             ← current full dashboard (to be redesigned)
    ├── DashboardBetween.svelte           ← scaffold
    ├── DashboardKO.svelte                ← scaffold
    ├── DashboardPost.svelte              ← scaffold
    └── widgets/
        └── DwPredictionNudge.svelte      ← built; calm/urgent states

frontend/src/lib/styles/
├── panini-base.css                       ← tokens + .pn-card / .pn-sticker / .pn-tag / .pn-btn / .pn-banner
├── panini-dashboard.css                  ← dashboard-specific layout (KPI row, etc.)
├── panini-leaderboard.css
├── panini-results.css                    ← match-card patterns; visual continuity reference
├── panini-wizard.css                     ← wizard match-card patterns; reference for KO score-entry
└── panini-bracket.css

frontend/src/routes/+page.svelte          ← thin dispatcher; <svelte:component this={ActiveDashboard}>
frontend/src/routes/+layout.svelte        ← phase override URL handler + PnDevPhasePill mount

frontend/src/lib/types/index.ts           ← UxPhase, PhaseStatus, PointBreakdown, etc.
```

### Backend

```
backend/app/models/
├── competition.py                        ← Competition model (phase1_deadline, is_phase2_active, etc.)
├── fixture.py                            ← Fixture + MatchStatus enum
├── score.py                              ← Score model (outcome string "1"/"X"/"2")
├── prediction.py                         ← MatchPrediction + TeamPrediction + PredictionPhase enum
├── leaderboard_snapshot.py               ← extended with exact_scores + correct_outcomes (migration cadef7c2acd7)
└── _datetime.py                          ← UTC datetime factory; use this for timestamps

backend/app/api/
├── leaderboard.py                        ← /leaderboard, /breakdown/{user_id}, /snapshots/me (extended),
│                                           /tournament-winner (new), /me/highlights (new)
├── predictions.py                        ← /predictions/matches, /predictions/bracket-exposure (extended),
│                                           /predictions/agreements
├── competition.py                        ← /competition/info, /competition/phase-status
├── fixtures.py                           ← /fixtures/, /fixtures/groups, /fixtures/standings/actual
└── admin.py                              ← phase ops, score sync, user toggles

backend/app/services/
├── leaderboard.py                        ← calculate_leaderboard + invalidate_cache + calculate_user_points
├── snapshots.py                          ← take_daily_snapshots + get_user_trajectory (all_time param)
│                                           + get_steepest_climbers
├── bracket_exposure.py                   ← compute_bracket_exposure + _compute_teams_that_made_stage
│                                            (needs round-5 extension; see §6)
├── scoring.py                            ← scoring strategies + get_scoring_config
├── standings.py                          ← actual group standings
└── score_scheduler.py                    ← background score sync + daily snapshot trigger

backend/scripts/
├── seed_phase_pretournament.py           ← Phase 1 deadline = now + 7d
├── seed_phase_between.py                 ← wraps seed_phase2_test + sets phase2_bracket_deadline = now + 24h
├── seed_phase_post.py                    ← marks FINAL fixture FINISHED
├── seed_phase2_test.py                   ← Phase 2 activation + KO fixtures
├── seed_data.py / seed_fixtures.py       ← base seeders
└── seed_test_predictions.py              ← prediction seeders

backend/alembic/versions/
└── cadef7c2acd7_add_exact_scores_and_correct_outcomes_.py  ← snapshot extension migration
```

### Memory pointers (`~/.claude/projects/-Users-lukeaarohi-pyfiles-predictorv2/memory/`)

- `MEMORY.md` — index
- `feedback_svelte_hmr_rename_on_mv.md` — the file-move bug
- `feedback_no_card_tilts.md` — Panini design rule
- `feedback_daisyui_class_collisions.md` — class prefix rule
- `feedback_pytest_in_backend_container.md` — install pytest transiently
- `feedback_substantial_changes_need_discussion.md` — multi-page plans need per-page discussion
- `feedback_understand_before_executing.md` — explain before non-routine prod commands
- `feedback_parallel_dev_container_network.md` — docker network connect
- `feedback_claude_md_in_worktree.md` — defer CLAUDE.md edits

---

## 13. How to read claude-design files when they arrive

The user will provide image mockups (PNG / screenshot) for each phase. Mapping to implementation:

1. **Identify which widget the design represents** — match against the widget table in `§3` above.
2. **Confirm the data source** — every widget has a documented data source. If the design needs data that isn't covered, flag it (don't make up an endpoint).
3. **Check the design against principles in `§4`** — particularly: no card tilts, arrow-delta indicators right of metrics, visual continuity with `PnResultsCard` / wizard cards where relevant.
4. **For Phase 4's `DwScoringJourney`** — most invented widget; double-check it matches the round-5 spec (transposed, stacked, EARNED/AVAILABLE column headers, points-at-right-of-fill, "pts" suffix, no multiplier badges).
5. **Build with existing tokens** — use `var(--green)` / `var(--gold)` / `var(--red)` / `var(--ink)` / `var(--paper)` etc. from `panini-base.css`; don't introduce new colours.

---

## 14. End-to-end smoke checklist (after each phase is built)

For each phase implemented, before marking complete:

- [ ] `npm run check` — 0 errors (warnings count ≤ baseline + 5)
- [ ] `npm run build` — succeeds
- [ ] `npx vitest run` — all pass
- [ ] Visit `/?uxPhase=<phase>` in DEV — page renders, no console errors
- [ ] Click `PnDevPhasePill` to switch in/out of this phase — clean transition
- [ ] Mobile breakpoint (375px) — widget stack works, no horizontal overflow
- [ ] All `[ see full ... → ]` CTAs route correctly
- [ ] If the phase has predictable data states, run the matching seed script and verify the widget reflects real data:
  - Pre: `seed_phase_pretournament.py` then check progress bar matches
  - Between: `seed_phase_between.py` then check group-stage summary populates
  - Post: `seed_phase_post.py` then check podium + highlights render

---

## 15. Why this iteration was good (note for future-me)

Every round of design feedback **removed** widgets/elements rather than adding them:
- Round 1: dropped `DwCompletionBars`, `DwFinalStandings`, simplified `DwMatchCard` (no word labels)
- Round 2: dropped `DwUpcomingMatches` (Up Next table), simplified missing-picks alert (no names), dropped card tilts globally
- Round 3: collapsed `DwPointsBySource` + `DwBracketAlive` into `DwScoringJourney`
- Round 4: dropped ✗ Out row from scoring-journey, moved to progressive denominators
- Round 5: dropped multiplier badges, dropped `DwBracketStatusLine` (folded into phase headers), renamed In-play → Available

The widget count went from **30+ cells visible on Phase 4** in round 1 to **20 cells** in round 5, while every change made the dashboard *more* useful, not less. Keep that pruning instinct alive — when in doubt, remove not add.

---

**End of guide.** If anything here is ambiguous or contradicts `dashboard-phase-widgets.md`, the widget plan doc wins (it's the canonical source). This guide is the implementation playbook; the plan is the contract.
