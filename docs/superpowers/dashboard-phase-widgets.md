# Dashboard Widget Plan — Per Phase

This doc defines **what each phase's dashboard needs**, so the visual layouts can be handed to claude-design. Once designs come back, we'll build them out.

The site had a phase-blind dashboard greeting every user with the same nine widgets regardless of where the competition was in its lifecycle. This change introduces a **UX-phase taxonomy** and a **dispatcher** so each phase can have its own landing layout in follow-up plans.

**Five UX phases** (derived in `frontend/src/lib/stores/phase.ts` via `deriveUxPhase`):

| `UxPhase` value     | Detection                                                | What the dashboard should be |
|---------------------|----------------------------------------------------------|------------------------------|
| `pre_tournament`    | `!phase1_locked` (also the defensive default when `phaseStatus` is null) | Registration funnel, prediction completion progress |
| `group_stage`       | `phase1_locked && !is_phase2_active`                     | Live match watching + leaderboard movement (the current 9-widget dashboard) |
| `between_phases`    | `is_phase2_active && !phase2_bracket_locked`             | "Redo your bracket using real groups" hero + actual standings |
| `knockout_stage`    | `is_phase2_active && phase2_bracket_locked`              | Next KO match + three-source points breakdown |
| `post_competition`  | Final fixture (`stage === 'final'`) status is `finished` | Champion + retrospective; finished-final wins over lingering locked-bracket state |


## Context

The site has five UX phases derived from `$uxPhase` in `frontend/src/lib/stores/phase.ts`:

1. **pre_tournament** — Phase 1 still open
2. **group_stage** — Phase 1 locked, Phase 2 not yet activated
3. **between_phases** — Phase 2 active, bracket still open
4. **knockout_stage** — Phase 2 bracket locked, KO matches running
5. **post_competition** — Final fixture finished

Each gets its own dashboard component (already scaffolded in `frontend/src/lib/components/panini/dashboard/`). This plan replaces the placeholder scaffolds (and refreshes the group-stage build) with intentional layouts.

## Dashboard principles

Every dashboard layout in this plan is held to the following rubric:

1. **Fits within one desktop viewport** (~900px tall at typical breakpoints). Mobile naturally stacks, but desktop should not require scrolling to see the whole dashboard at a glance.
2. **Summarises rather than details.** If a widget would need a second screen of data to be useful, it doesn't belong on the dashboard. Show the headline; link out for the breakdown.
3. **Routes to the right page for deep dives.** Every dashboard widget that summarises tournament data should link to `/predictions` (for prediction breakdowns), `/leaderboard` (for standings detail), `/results` (for match-level analysis), or `/rules` (for scoring rules).
4. **The wizard transforms post-lock.** Once Phase 1 locks, `/predictions` is no longer an input form — it becomes a *detailed breakdown view* of every prediction the user made and how it scored. The dashboard's "details →" CTAs route there. This is a deferred follow-up to the per-page tweaks plan; until built, the wizard shows its current locked-state view.
5. **Visual continuity with existing pages.** Match cards on the dashboard should echo the score cards used on `/results` (`PnResultsCard`) but in a more compact form. KO score-entry cards should echo the wizard's match cards in a compact form. The dashboard isn't a separate visual language — it's a tighter sampling of the rest of the site.
6. **Adjacent widgets fill each other's vertical gaps.** When two side-by-side widgets have unequal content heights (e.g. Recent Results has 1 match, Today's Games has 3), the widgets in the row *below* should absorb the released vertical space rather than leaving an empty rectangle. Dev shouldn't bake in fixed heights for paired widgets — adjacent widgets in subsequent rows expand to fill.
7. **Delta indicators use directional arrows, not signs.** `▲ 2` and `▼ 1` (with colour — green up, red down) instead of `(+2)` and `(-1)`. Delta sits *to the right* of the main metric, not below.
8. **KPI cards are straight, never tilted.** Round-2 reinforcement of an existing Panini-system rule: no `transform: rotate(...)` on sticker/KPI/match cards. The Panini visual language allows tilt only on small decorative accents (corner-tag pills, avatar chips). KPI row stickers stay axis-aligned. Same applies to match cards on the dashboard.

**Tagging system:**

- `REUSE` — existing component used as-is or with trivial prop change
- `EXTRACT` — currently inline in `DashGroupStage.svelte`; lift to `dashboard/widgets/` with no/minimal behavior change
- `REDESIGN` — exists but needs visual rework to fit the new role
- `NEW` — needs to be designed from scratch

## Shared atoms (available to every phase)

These are visual primitives every phase can compose. No design work needed — already production-grade.

| Atom | File | Use |
|---|---|---|
| `PnFlag` | `frontend/src/lib/components/panini/PnFlag.svelte` | Country flags wherever a team appears |
| `PnIcon` | `frontend/src/lib/components/panini/PnIcon.svelte` | 18-piece icon set (ball, lock, trophy, etc.) |
| `PnSparkline` | `frontend/src/lib/components/panini/PnSparkline.svelte` | 7-point rank trajectory line |
| `PnDropdown` | `frontend/src/lib/components/panini/PnDropdown.svelte` | Themed `<select>` replacement |
| `PnPageShell` | `frontend/src/lib/components/panini/PnPageShell.svelte` | Wraps every dashboard (masthead, strip, bottom nav) |
| `.pn-card` `.pn-sticker` `.pn-tag` `.pn-btn` `.pn-banner` | `panini-base.css` | Compositional CSS classes |
| `DwPredictionNudge` | `dashboard/widgets/DwPredictionNudge.svelte` | Calm/urgent prediction-progress nudge, multi-phase |

---

## Phase 1 — Pre-tournament

### User goal

Get registered → complete Phase 1 predictions → understand scoring → see who else is in.

**No leaderboard, no live ticker, no rank** — the user has no points yet. This phase is a *funnel into the prediction wizard* with social proof (the roster) and rules clarity.

### Desktop layout (sketch)

```
+===============================================================+
|  ⚠ UNSAVED PREDICTIONS                                       |
|    You have 7 picks saved on this device but not on the      |
|    server. Switch devices and they're gone.                  |
|              [  SAVE ALL NOW  →  ]                           |
+===============================================================+
       ↑ only when $unsavedChangesCount > 0 OR bracket has
         unsaved state OR phase-2 bracket has unsaved state

+===============================================================+
|                                                               |
|   HERO — Phase 1 locks in 5d 12h 30m                         |
|                                                               |
|   OVERALL PROGRESS                                            |
|   [==========                                  ] 20/75       |
|                                                               |
|              [  OPEN PREDICTIONS  →  ]                        |
|                                                               |
+===============================================================+
+================+==================+========================+
|  SCORING PEEK  |  RULES PEEK      |  PLAYERS · 18 of 30   |
|  +5 outcome    |  Phases ·        |  Full leaderboard      |
|  +15 exact     |  multipliers ·   |  table (pos/name/pts) |
|  bracket ·     |  entry fee       |  All at 0 pts;        |
|  rarity bonus  |                  |  acts as roster pre-  |
|  [ rules → ]   |  [ rules → ]     |  comp                  |
+================+==================+========================+
```

### Mobile layout

Single column: unsaved alert (if any) → countdown hero with overall progress bar → scoring peek → rules peek → players list (scrollable).

### Widgets

| Widget | Status | Data source | Brief |
|---|---|---|---|
| `DwUnsavedAlert` | **NEW** | `$unsavedChangesCount`, `$hasUnsavedBracketChanges`, `$unsavedPhase2BracketPrediction` (all already in `$stores/predictions`) | Gold-bordered banner above hero. Renders only when localStorage-backed drafts exist that haven't been persisted to the backend. CTA triggers `saveAllPredictions()` (or scoped save based on which store is dirty). Multi-phase: also rendered in `between_phases` and `knockout_stage` when their editable predictions have drafts. |
| `DwPreCountdownHero` | **NEW** | `$phase1Deadline`, `$phase1Countdown` + one overall progress count (sum across sections) | Full-width hero. Big mono digits, ONE overall progress bar (e.g. 20/75 filled), primary CTA. **Carries the whole progress story** — there's no separate per-section breakdown widget on the dashboard. Section detail lives in the wizard (post-lock breakdown view). |
| ~~`DwCompletionBars`~~ | **DROPPED (round 1 feedback)** | — | Was: three labeled progress bars (group / bracket / bonus). **Dropped after round-1 design review** — the hero's single overall progress bar already conveys the "how done am I" signal, and per-section bars duplicated that information. If users need per-section detail, the wizard itself is one click away. |
| `DwScoringPeek` | **NEW** | `getScoringConfig()` (already exists) | Short summary of scoring rules — outcome, exact, bracket, rarity bonus. Links to `/rules`. |
| `DwRulesPeek` | **NEW** | `getCompetitionInfo()` | Short summary of tournament structure — phases, multipliers, entry fee. Links to `/rules`. |
| `DwLeaderboard` (`limit="all"`, header="Players") | **REUSE** | `$leaderboard` | Doubles as roster in pre-tournament: shows all N players with rank=1 (everyone at 0 points) and acts as the social-proof "who's playing" widget. Same widget used in every other phase with `limit=5` and header="Top 5". |
| `DwPredictionNudge` (scope=`phase_1_open`) | **REUSE** | `$predictionsByFixture` | Calm by default; loud red banner when <12h to lock AND gaps remain. Distinct from `DwUnsavedAlert`: nudge = "you haven't predicted X"; alert = "you predicted X but didn't save it". |

### Design intent — `DwUnsavedAlert`

- **Visual**: gold border (`var(--gold)` accent), paper background. **Not red** — red is reserved for the "you're about to lose data because of a deadline" urgent nudge. Gold says "heads up, action needed" without panic.
- **Behaviour**: appears only when at least one unsaved-prediction store is non-empty. CTA "Save all now" calls the relevant save action(s) and dismisses on success.
- **Multi-phase**: identical widget renders in `between_phases` (when `$unsavedPhase2BracketPrediction` is non-null) and `knockout_stage` (when `$unsavedChangesCount > 0` for KO fixtures). The widget itself doesn't care about phase — it just renders when there's localStorage drift.

### Design intent — `DwLeaderboard`

- **Props**: `limit: number | 'all'`, `headerLabel: string` (default `"Top 5"`), `phaseFilter: 'overall' | 'phase_1' | 'phase_2'` (default `'overall'`).
- **Behaviour**: identical row rendering across phases; only the header text and row count differ. In pre-tournament with `limit="all"` and all rows at 0 pts, the widget reads as a roster — rank column shows "1" for everyone (or could be suppressed entirely via a `hideRanks` prop if visually noisy — defer to claude-design).
- **Lifts from**: the existing leaderboard table in `frontend/src/routes/leaderboard/+page.svelte`. Extract into `dashboard/widgets/DwLeaderboard.svelte` and reuse on both the dashboard and the `/leaderboard` page itself (single source of truth for leaderboard rendering).
- **Replaces**: the previous `DwTop5` extraction-target — `DwLeaderboard` with `limit=5` is the same thing.

---

## Phase 2 — Group stage (full redesign under one-viewport principle)

### User goal

Spectate. Predictions are **locked**. The user opens the dashboard during group stage to know: what's happening right now, how I'm doing, where my recent points came from, who I'm competing with, what's coming up.

### Desktop layout

```
+================================================================+
|  KPI ROW · 5 stickers · 1/5 width each                         |
|  ┌────────┬────────┬────────┬────────┬─────────┐              |
|  │ RANK   │ TOTAL  │ EXACT  │OUTCOMES│TRAJECTORY│             |
|  │ 1/24   │  20    │  0/1   │  1/1   │[sparkline]│            |
|  │ (+2)   │ (+5)   │ (+0)   │ (+1)   │ ▲2·7d    │             |
|  │ last   │ 0 ex + │ +0 pts │ 100%   │ Today:+5 │             |
|  │ update │ 1 outc │ exact  │ hit rt │ pts      │             |
|  └────────┴────────┴────────┴────────┴─────────┘              |
|                              [ see full breakdown → ]          |
+================================================================+
+===================+========================+===================+
|  PAST 24h          |  UPCOMING 24h          |  TOP 5 · OF 24   |
|  (round-2: matches |  (round-2: includes    |  (round-2: moved |
|   the Phase 4      |   LIVE matches until   |   into row 2 to  |
|   layout)          |   scorer is final)     |   align Phase 2  |
|                    |                        |   with Phase 4)  |
|  Yesterday · 3     |  ● LIVE · ARG vs BRA   |                  |
|                    |    pick 2-1            |  1. YOU      20  |
|  ┌──────────────┐  |                        |  2. PlayerA  15  |
|  │ 🇦🇷 ARG  2-1│  |  Next · ENG vs FRA     |  3. PlayerB  15  |
|  │ 🇧🇷 BRA     │  |  · 2h 14m              |  4. PlayerC  15  |
|  │ pick 2-1     │  |    pick 1-1            |  5. PlayerD   5  |
|  │   [ +15 ]    │  |                        |  ───             |
|  └──────────────┘  |  Later · USA vs MEX    |  7. ...          |
|  ┌──────────────┐  |  · 5h 30m              |  (neighborhood   |
|  │ 🇫🇷 FRA  0-0│  |    pick 2-1            |   if below #5)   |
|  │ 🇩🇰 DEN     │  |                        |                  |
|  │ pick 1-1     │  |  (cards click → match  |  [ see full      |
|  │   [ +0 ]     │  |   detail)              |    standings → ] |
|  └──────────────┘  |                        |                  |
|  (cards click →   |                        |                  |
|   match detail)    |                        |                  |
+===================+========================+===================+
```

Heights estimate: KPI ~140px + 3-col row ~480px = ~620px + chrome. Fits one viewport.

**Vertical-gap absorption (round-1 feedback, still applies)**: when Past 24h has fewer cards than Upcoming 24h (or vice versa), the columns balance via the leaderboard column absorbing height differences. The leaderboard already supports a flexible row count (top 5 + neighborhood with optional padding rows), so it naturally fills the taller side. Dev should NOT bake fixed heights for these paired columns.

### Mobile layout

Stack order: KPI compact (2×2 + trajectory full-width) → upcoming 24h (priority — most relevant for in-flight events) → past 24h → top 5 + you.

### Widgets

| Widget | Status | Data source | Notes |
|---|---|---|---|
| `DwKpiRow` | **REDESIGN** | `$currentUserPosition` + `/leaderboard/snapshots/me?days=7` for deltas | Keep current sticker treatment from the existing build. **Changes**: (1) Add deltas to all four numeric stickers — **`▲ 2` / `▼ 1` / `—` arrow indicators (round-1 feedback), positioned to the right of the main number, not below**. Green ▲ for up, red ▼ for down, paper-grey `—` for no change. Derived from yesterday's snapshot vs today. Fractions preserved (`1/24`, `0/1`, `1/1`). (2) Replace BONUS HAUL sticker with TRAJECTORY: compact inline `PnSparkline` + `▲ 2 · 7d` + "Today: +N pts" subtext. (3) Add `[ see full breakdown → ]` link below the row, right-aligned, routes to `/predictions` (wizard's post-lock breakdown view). **Backend**: snapshot extension landed — `exact_scores` + `correct_outcomes` columns now persisted per-day; deltas computable directly from yesterday's snapshot vs today's leaderboard. |
| `DwRecentResults` | **NEW** | `$fixtures` filtered to `status === 'finished'` within last 24h + `$predictionsByFixture` + breakdown calc | Card per yesterday's match. Card shows: team flags, final score, your pick, points earned. **Each card click → `/results/[fixture_id]`** (match detail page with `PnBubbleGrid`, `PnPointsBar`, `PnMatchLeaderboard`). 2/5 column width on desktop. |
| `DwTodaysGames` | **NEW** | `$fixtures` filtered to next 24h + `$predictionsByFixture` | **Round-2 rename in concept**: now the "Upcoming 24h" column. State-aware per card: **live (still rendered IN this column until the scorer marks the match final** — round-2 feedback; live matches stay alongside upcoming until they fully resolve), upcoming (kickoff time + countdown + your pick). **Each card click → `/results/[fixture_id]`**. 1/3 column width on desktop in the 3-column row 2 layout. Shares the `DwMatchCard` atom with `DwRecentResults`. |
| `DwLeaderboard` (`limit=5, neighborhood=true`) | **REUSE** | `$leaderboard` | **Round-2: moved into row 2** alongside Past 24h + Upcoming 24h (was previously in its own row 3 paired with Up Next). Same widget as other phases. Neighborhood mode: when current user is below #5, pin user's row below the cut with ±1 around. `[ see full standings → ]` link routes to `/leaderboard`. |
| ~~`DwUpcomingMatches`~~ (Up Next table) | **DROPPED (round 2)** | — | Was: full upcoming-fixtures table from existing `DashGroupStage.svelte` (kickoff/match/stage/pick/status columns) in its own row 3 column. **Dropped in round 2** — the "Upcoming 24h" card column carries the same information for the immediate horizon; users wanting a longer schedule view go to `/predictions` or `/results`. Aligns Phase 2 with Phase 4's structure. |

### Dropped from current build

- **Live broadcast (standalone)** — merged into `DwTodaysGames` as a state-aware card style
- **Next-lock countdown (standalone)** — merged into `DwTodaysGames` (first upcoming card carries the countdown)
- **Rank trajectory (standalone)** — folded into the TRAJECTORY sticker in `DwKpiRow`
- **Closest rivals** — merged into `DwLeaderboard` (neighborhood mode)
- **Hot pick** — dropped. Predictions are locked; no "open" pick to be hot about
- **Bracket exposure** — dropped. R32-entry points now live in `DwGroupStageSummary` (used in between/post phases, not group_stage); R16+ doesn't pay out until KO

### Design intent — `DwMatchCard` (shared atom) — REVISED round 1

Single card component used by both `DwRecentResults` and `DwTodaysGames`. **Visual continuity** with `PnResultsCard` from `/results` — dashboard cards are a *compact version of the same design language*. Round-1 design feedback established these structural rules:

**Layout (top to bottom):**
1. **Team flags + country names** at the top, prominent — flags slightly bigger than KPI-row size, names readable (~14-16px). Two rows: home team, away team.
2. **Actual score** in large mono digits between or next to the teams (echoing PnResultsCard's scoreline).
3. **Your pick** *underneath* the actual score — clear separation, smaller font. Format: `pick 2-1` or `your pick: 2-1`.
4. **Points earned** as the bottom-right element. **Just the number** — `+15`, `+5`, `+0` — **no word label** (no "exact" / "outc" / "miss"). The number sits *inside* a small **coloured box**, not just coloured text:
   - Gold box for exact (`+15`)
   - Green box for outcome (`+5`)
   - Paper-grey box for miss (`+0`)
   - Live pending state: `[ … ]` with the box outlined but unfilled

**State variants** (driven by `kind: 'live' | 'finished' | 'upcoming'`):
- **`finished`**: scoreline visible, pick visible underneath, points box bottom-right. Whole card click → match detail.
- **`live`**: red `● LIVE` pip + minute label, current score live-updating, pick underneath, points box shows provisional value with an outlined "pending exact" style if applicable.
- **`upcoming`**: no scoreline yet, instead shows kickoff time + countdown + stage label. Pick underneath. Points box hidden (nothing earned yet).

**No points-source breakdown copy** ("exact +15 from exact scores" etc.) — that's wizard-breakdown territory. The card just says +15.

**Compact constraint**: card should be ~40% the vertical height of the equivalent `PnResultsCard` on `/results`. Dashboard isn't the result page — it's a teaser that links to the result page.

### Two new CTAs (dashboard-principle wiring)

- **KPI row** → `[ see full breakdown → ]` below the row, routes to `/predictions` (wizard breakdown view post-lock)
- **Leaderboard** → `[ see full standings → ]` at the bottom of the widget, routes to `/leaderboard`

Both styled as small uppercase mono links in ink colour with a hover state. Shared treatment so the "go deeper" pattern feels consistent. Any future widget that summarises tournament data should follow this pattern.

---

## Phase 3 — Between phases

### User goal

**Re-pick your Phase 2 bracket using real group results, before the deadline.**

This phase has a single dominant goal. The dashboard should feel *one-track* — the bracket update is the primary CTA, everything else supports.

### Desktop layout

```
+================================================================+
|  ⚠ UNSAVED PREDICTIONS (conditional)                          |
+================================================================+
+================================================================+
|  HERO — Phase 2 bracket locks in 2d 4h 12m                    |
|  "Phase 1 ended. Group stage scored you 475 points."           |
|  "Real groups are in — re-pick your knockout bracket."         |
|             [  UPDATE BRACKET  →  ]                            |
+================================================================+
+================================================================+
|  KPI ROW (round-1 feedback — kept in this phase, still         |
|  relevant: P1 final position + total persist into P2)          |
|  Rank · Total · Exact · Outcomes · Trajectory                  |
|  [ see full breakdown → ]                                      |
+================================================================+
+==========================================+=====================+
|  GROUP STAGE SUMMARY                    |  LEADERBOARD       |
|         Outc  Exact  Qual  Total        |  Top 5 P1 final    |
|   A      15    0     20    35           |                    |
|   B      10   15     15    40           |                    |
|   C      20    0     30    50           |                    |
|   ... (12 groups)                        |                    |
|         --------------------             |                    |
|   Σ    150   60    240   450             |                    |
|                                          |                    |
|   + 4 group-stage bonuses: 25 pts        |                    |
|   GROUP STAGE TOTAL: 475 pts             |                    |
|   [  details in Predict →  ]             |                    |
+==========================================+=====================+
```

Fits one desktop viewport: hero (~140px) + KPI row (~140px) + summary+leaderboard row (~380px) + chrome. No `DwP1BracketRetro` (R32-entry points are already captured in the `Qual` column of the summary — that's the only overlap between bracket and group-stage scoring, and it lives visually with the groups).

### Mobile layout

Stack: unsaved alert (if any) → hero → KPI row (compact 2×2 + trajectory) → summary table (full-width) → leaderboard (compact, full-width). All above-the-fold-ish; one swipe at most.

### Widgets

| Widget | Status | Data source | Notes |
|---|---|---|---|
| `DwUnsavedAlert` | **REUSE** | `$unsavedPhase2BracketPrediction` | Same widget as Phase 1, watches the Phase 2 bracket draft store. |
| `DwBetweenHero` | **NEW** | `$phase2BracketDeadline` + `getPhaseBreakdown(me)` for group-stage total | Full-width hero. Countdown + group-stage total teaser + primary CTA "Update bracket". |
| `DwKpiRow` | **REUSE** | `$currentUserPosition` + snapshots for deltas | **Added back in round-1 feedback** — the P1 final position and total persist into between_phases and remain meaningful context. Same shape as group_stage KPI row (Rank / Total / Exact / Outcomes / Trajectory) with `▲/▼` deltas. Deltas may be near-zero in this phase (no live scoring between phases), but the row still anchors the user's current standing. |
| `DwGroupStageSummary` | **NEW (multi-phase)** | `getPhaseBreakdown(me)` + per-fixture breakdown computation (existing `matchBreakdown.ts`) + bonus question results | Compact 12-row table with 3 scoring columns (Outc / Exact / Qual) + per-group totals + 4 group-stage bonus questions + grand total. The **Qual column is progressive**: only populated for a given group once all 6 matches in that group are FINISHED — shows `—` or pending indicator until then. **Visual choice**: R32-entry points (which the scoring model considers "bracket" points for team advancement + group position) sit in the Qual column of the corresponding group row, grouped with that group's other scoring sources. This is the only place bracket and group-stage scoring overlap; presenting them together makes the per-group story coherent. The wizard's bracket breakdown view (deferred follow-up) will show R32+ stages only, no double-count. |
| `DwLeaderboard` (`limit=5, phaseFilter=phase_1`) | **REUSE** | `$leaderboard` | Phase 1 final standings — where everyone finished. Less central than in group_stage (no live movement), but worth keeping for context. |
| `DwPredictionNudge` (scope=`phase_2_bracket`) | **REUSE** | `$phase2BracketPrediction` | Calm → urgent when <12h to bracket lock with gaps. |

### Design intent — `DwGroupStageSummary`

- **Three scoring columns** per group row:
  - **Outc** — outcome points (1/X/2) summed across the group's matches, **includes rarity bonus**.
  - **Exact** — exact-score points summed across the group's matches.
  - **Qual** — `10 × correct-advancement + 5 × correct-position` for that group's four teams. Conceptually these are bracket scoring (R32-entry), but visually housed with the group.
- **Progressive scoring** (important for the group_stage phase too): the `Outc` and `Exact` columns update as individual matches finish. The `Qual` column only populates once **all 6 matches in that group are finished** (because correct advancement and position can only be determined once the group's final standings are settled). Until then, render as `—` or a small "pending" indicator.
- **Bonus row** at the bottom totals the 4 group-stage bonus questions (top scorer of group stage, most yellow cards, etc. — admin-resolved as Phase 1 closes).
- **Grand total** combines all groups + bonus.
- **CTA** "details →" routes to `/predictions` (the wizard's breakdown view).
- **Used in**: group_stage (live, progressive), between_phases (final), KO (still relevant — see KO phase notes), post-competition (frozen).

---

## Phase 4 — Knockout stage

### User goal

**Predict KO match scores before each kickoff (deadlines are per-match, 5 mins before kickoff). Understand where points are coming from across three simultaneous sources.**

Unique characteristics:
- **Per-match deadlines** (vs. phase-wide deadlines in pre/between). Each match needs a pick.
- **Three sources of points pay out simultaneously**: match scores (1.0×), Phase 1 bracket as KO progresses (1.0×), Phase 2 bracket as KO progresses (0.7× multiplier).
- **Fewer matches per day** than group stage (often 1, sometimes 2). Spotlight-style content density.

### Desktop layout

```
+================================================================+
|  🔴 4 MATCHES MISSING PREDICTIONS                              |
|              [ PREDICT NOW → ]                                 |
+================================================================+
       ↑ red banner, conditional (when KO matches have set teams
         but no user score prediction)

+================================================================+
|  ⚠ UNSAVED PREDICTIONS (gold, conditional)                    |
+================================================================+

+================================================================+
|  KPI ROW · 5 stickers · same as group_stage                    |
|              [ see full breakdown → ]                          |
+================================================================+

+===================+========================+===================+
|  PAST 24h          |  UPCOMING 24h          |  TOP 5 · OF 24   |
|                    |                        |                  |
|  Match cards from  |  Match cards (next     |  1. YOU      265 |
|  the last 24h.     |  24h):                 |  2. PlayerA  245 |
|                    |  - Live: score + pick  |  3. PlayerB  230 |
|  Whole card click  |    + provisional pts   |  4. PlayerC  220 |
|  → match detail.   |  - Upcoming: inline    |  5. PlayerD  210 |
|                    |    score entry (no     |  ───             |
|                    |    pick) OR "pick X-Y  |  Your row pinned |
|                    |    + change" (has pick)|  if below #5     |
|                    |                        |                  |
|                    |  Score boxes = inline  |  [ see full      |
|                    |  entry. Rest of card → |    standings → ] |
|                    |  match detail.         |                  |
+===================+========================+===================+

+===================================================================+
|  YOUR SCORING JOURNEY                    [ see full breakdown → ]  |
|                                                                     |
|  PHASE 1 · ORIGINAL · earned 80 pts · available 275 pts             |
|                  EARNED                  AVAILABLE                  |
|  R16     [██████████  40 pts (8/16)]    [                       ]   |
|  QF      [██  20 pts (1/2)         ]    [██████  80 pts (4/6)   ]   |
|  SF      [                          ]    [█████   60 pts (3/4)   ]   |
|  FINAL   [                          ]    [████    25 pts (1/2)   ]   |
|  WINNER  [                          ]    [██     100 pts (1/1)   ]   |
|                                                                     |
|  PHASE 2 · RE-PICK · earned 180 pts · available 18 pts              |
|                  EARNED                  AVAILABLE                  |
|  R16     [████████  28 pts (6/16)  ]    [                       ]   |
|  QF      [█████  21 pts (3/4)      ]    [██       7 pts (1/4)   ]   |
|  SF      [██  18 pts (1/2)         ]    [█        9 pts (1/4)   ]   |
|  FINAL   [██  28 pts (1/2)         ]    [                       ]   |
|  WINNER  [█   70 pts (1/1)         ]    [                       ]   |
+===================================================================+
```

Heights (no alerts firing): KPI ~140 + 3-col row 2 ~340 + scoring-journey row ~360 = ~840px + chrome ✓ (just over one viewport — slightly taller than the round-4 spec but materially more readable).

**Round-5 layout change (latest)**: widget is **transposed + stacked**. Stages are rows (R16 / QF / SF / FINAL / WINNER); buckets are columns (EARNED / AVAILABLE). Phases stack vertically (P1 on top, P2 below). Phase headers carry the totals — `DwBracketStatusLine` dropped (folded into the per-phase header lines). Bars are wider with the number at the right-end of the fill, "pts" suffix, fraction as parenthetical. Row labels are text (`EARNED` / `AVAILABLE` — formerly `✓ Correct` / `◐ In-play`). The `×1.0` / `×0.7` multiplier badges are dropped from headers (live in `/rules` if anyone needs them).

### Mobile layout

Stack order: missing-picks alert (conditional) → unsaved alert (conditional) → KPI compact (2×2 + trajectory) → upcoming 24h (priority — has the actions) → past 24h → top 5 → points by source → bracket alive.

### Widgets

| Widget | Status | Data source | Notes |
|---|---|---|---|
| `DwKoMissingPicksAlert` | **NEW** | `$upcomingFixtures` filtered to KO + `$predictionsByFixture` | Red top banner. Just the count: "4 MATCHES MISSING PREDICTIONS" + `[ PREDICT NOW → ]` CTA. No per-match names or countdowns — the upcoming-24h column shows that detail. Renders when at least one upcoming KO match has teams set but no user score prediction. Live-updates as picks are made or new teams get resolved by completed matches. |
| `DwUnsavedAlert` | **REUSE** | `$unsavedChangesCount` | Gold banner for KO score drafts. Renders below missing-picks alert if both fire. |
| `DwKpiRow` | **REUSE** | `$currentUserPosition` + snapshots for deltas | Identical to group_stage including the `[ see full breakdown → ]` link to `/predictions`. KO deltas often spike due to bracket payouts — the trajectory sticker tells that story. |
| `DwRecentResults` (2/5) | **REUSE** | `$fixtures` filtered to `status === 'finished'` within last 24h + `$predictionsByFixture` + breakdown calc | Same widget as group_stage. Past 24h matches as cards, whole card click → `/results/[fixture_id]`. |
| `DwTodaysGames` (3/5, **`allowEntry={true}`**) | **REUSE+** | `$fixtures` filtered to next 24h + `$predictionsByFixture` | Same widget as group_stage, but with **inline entry enabled**. Card states: live (score + pick + provisional pts), upcoming-with-pick (pick visible + `[ change ]` button), upcoming-no-pick (`[ _ ] – [ _ ] [ ✓ ]` inline score inputs, capped at 15 per side per `worldcup2026.yml`, saves via existing `savePrediction(fixtureId)` action). Score inputs stay on the dashboard; rest of card click → `/results/[fixture_id]`. |
| `DwLeaderboard` (1/3 in row 2, `limit=5, neighborhood=true`) | **REUSE** | `$leaderboard` | **Round-2: moved into row 2** alongside Past + Upcoming (matches Phase 2's row-2 structure). Same widget as other phases with neighborhood behaviour and `[ see full standings → ]` link. |
| ~~`DwBracketStatusLine`~~ | **DROPPED (round 5)** | — | Was: thin subline beneath the KPI row carrying bracket totals. Round 5: folded into the per-phase headers of `DwScoringJourney` so the widget self-narrates. One fewer widget. |
| `DwScoringJourney` (~60–70% width, row 3, transposed + stacked) | **NEW (round-3 unification, reshaped round 5)** | `getBracketExposure('phase_1')` + `getBracketExposure('phase_2')` extended with progressive per-bucket counts + team lists | **Round 5**: stages-as-rows, buckets-as-columns, phases stacked. Per-phase headers carry totals. See *Design intent — `DwScoringJourney`* below. |
| ~~`DwPointsBySource`~~ | **DROPPED (round 3)** | — | Absorbed into `DwScoringJourney`. |
| ~~`DwBracketAlive`~~ | **DROPPED (round 3)** | — | Absorbed into `DwScoringJourney`. |

### Design intent — `DwKoMissingPicksAlert`

- **Visual**: red banner (`var(--red)`), white text, full-width across top of dashboard
- **Behaviour**: shown at top of dashboard whenever any KO match has its teams determined, kickoff in the future, and no user score prediction. Always urgent in KO (no calm state) — per-match deadlines mean every uncovered match is a potential miss.
- **Content**: count + single CTA. No match names, no per-match countdowns. The upcoming-24h column directly below carries the detail.
- **Routing**: CTA goes to `/predictions` which deep-links to the next-most-urgent missing match.
- **Subsumes**: `DwPredictionNudge` is dropped from KO. The missing-picks alert is more aggressive (always urgent, no calm state) because KO deadlines are per-match.

### Design intent — `DwTodaysGames` with `allowEntry={true}` — REVISED round 1

The same widget as group_stage, parameterised for KO's editable state. **Visual continuity** (round-1 feedback) with the prediction wizard's match cards on `/predictions` — KO score-entry cards on the dashboard should feel like a **compact version of the wizard cards**, not a separate design.

**Card structure** (top to bottom):
1. **Stage label + countdown** ("QF · in 2h 14m") as a header strip
2. **Both team flags + names** in a horizontal row, prominent
3. **Score row centered**: the actual score (or score-entry inputs) and the user's pick are both **centered** in the card — not left/right aligned. The wizard's match-card pattern uses centred score inputs and the dashboard should mirror that.

**Card states**:
- **No-pick state**: centred score inputs `[ _ ] – [ _ ]` + save button `[ ✓ ]`. Inputs cap at 15 per side (per `worldcup2026.yml`). Saves via `savePrediction(fixtureId)`.
- **With-pick state**: centred "pick 2-1" display + small `[ change ]` affordance to re-enter
- **Live state**: live score (centred) + minute + pick underneath + provisional points box (same `+15` / `+5` / `+0` coloured-box convention as `DwMatchCard`)
- **Finished-today state** (rare in KO): final score + pick + points box

**Why centred**: visual continuity with wizard cards keeps the user's mental model intact — the same component shape that takes their input in the wizard takes it on the dashboard. Reduces the cognitive cost of "this is the same action in a different place."

**Whole card** is clickable to match detail except the inline score-entry inputs themselves (so clicks on the boxes go to typing, not navigation). Save buttons don't navigate.

The most urgent (earliest kickoff with no pick) card is positioned at the top of the column.

### Design intent — `DwScoringJourney` (revised through mockup round 1 + round 5 reshape)

Widget that replaces `DwPointsBySource` + `DwBracketAlive` in Phase 4. Tells the *present-tense* "where do I stand right now" story across the user's bracket picks per stage and per phase.

**Round-5 reshape** (after seeing round 1 mockup):
1. **Transposed**: stages are now ROWS (R16 / QF / SF / FINAL / WINNER) instead of columns. Buckets are COLUMNS (EARNED / AVAILABLE) instead of rows. Mirrors the user's mental model of picking the bracket stage-by-stage.
2. **Stacked**: Phase 1 sub-grid on top, Phase 2 sub-grid below. Widget is narrower (~60-70% dashboard width) and taller. Enables direct vertical comparison of P1 vs P2 at the same stage.
3. **Text row labels**: `EARNED` and `AVAILABLE` instead of ✓ / ◐ symbol-only. Bucket labels appear as column headers above the bars.
4. **"AVAILABLE" replaces "In-play"** as the bucket name. Pairs with `EARNED` in matching grammatical shape. Also rename the bracket-status vernacular from "alive" → "available" everywhere for one-vocabulary consistency.
5. **Wider bars with number inside-right**: bar fills proportionally; the points value sits at the right-end of the *filled* portion (outside the fill) in row colour. Format: `40 pts (8/16)` — `pts` suffix always present.
6. **Phase headers absorb the totals**: `PHASE 1 · ORIGINAL · earned 80 pts · available 275 pts`. The separate `DwBracketStatusLine` widget is dropped — its content folds into these per-phase headers.
7. **Multiplier badges dropped from headers** (`×1.0` / `×0.7`). Power users know the multiplier; new users don't need it surfaced on the dashboard. Multipliers live in `/rules`.

**Earlier carried-forward decisions** (from rounds 1–4, still apply):
- ✗ Out row dropped entirely (was in round-3 spec; killed in round 4)
- Progressive denominators (round 4) — see *Data model* below
- Empty cells are empty (no "—" placeholders)
- Thin inter-row rules for structure

**Layout (round 5)**: horizontal split into two stacked sub-grids — Phase 1 on top, Phase 2 below. Each sub-grid is a 5-row × 2-column matrix:
- **Rows** are the 5 KO stages (R16, QF, SF, FINAL, WINNER) — top to bottom in tournament order.
- **Columns** are the two buckets: **EARNED** (green) and **AVAILABLE** (gold). The third "Out" bucket was dropped after mockup round 1.
- **Progressive denominators**: EARNED denominator = teams currently confirmed at stage X (grows as matches resolve); AVAILABLE denominator = TBD slots still to be determined at stage X (shrinks as matches resolve). Stage size = known + TBD (still equals 16/8/4/2/1 in total).

**Each cell shows (round 5)**:
1. A **wider horizontal bar** (~12-16px tall, taller than the round-4 spec because each row now has a full-width slot). Filled portion = count's share of progressive denominator, coloured per column (green for EARNED / gold for AVAILABLE), against `var(--paper-3)` background. Hard-edged, no rounded corners.
2. **Points value at the right-end of the filled portion** (outside the fill, in row colour): `40 pts`. The "pts" suffix is mandatory — every number is self-narrating.
3. **Fraction in parentheses immediately after**: `40 pts (8/16)`. Smaller font, subdued colour (`var(--ink-2)`). Provides the "how many of how many" precision without competing visually with the points figure.

**Empty cells are empty** — no "—" placeholders. The visual asymmetry between EARNED and AVAILABLE columns IS the story (early KO = mostly AVAILABLE filled, EARNED empty; late KO = inverse).

**Row labels**: stage names on the far left in mono uppercase (`R16`, `QF`, `SF`, `FINAL`, `WINNER`). Bucket column headers in mono uppercase above the bars (`EARNED`, `AVAILABLE`).

**Bucket definitions** (precise data model — REVISED round 4 with progressive denominators):

For each stage X:
- `known_at_X` = teams currently confirmed at stage X (winners of finished previous-round matches)
- `tbd_at_X` = unplayed previous-round matches; each will produce one team at stage X
- `|known_at_X| + |tbd_at_X| = stage_size` (16 / 8 / 4 / 2 / 1)

For a user pick `T` at stage X:
- T ∈ `known_at_X` → counts in **✓ Correct** (numerator++, denominator = `|known_at_X|`)
- T is in an unplayed match of `tbd_at_X` → counts in **◐ In-play** (numerator++, denominator = `|tbd_at_X|`)
- Else (T eliminated) → not shown (the ✗ Out row was dropped)

**Subtle dedup**: if the user picked *both* teams in the same TBD match (only one can advance), count as 1 in-play, not 2. Implementation: walk TBD matches and increment in-play once per match if either team is a user pick.

**Cell visibility rules** (round-4 — drives the natural empty-state visual asymmetry):
- Stage fully resolved (previous round complete): only ✓ shows; ◐ is empty
- Stage partially resolved: both rows visible
- Stage untouched (previous round not started): only ◐ shows; ✓ is empty

The asymmetry IS the story. Early KO is mostly gold (lots of in-play); green grows from R16 outward as matches resolve.

**Tooltips** (hover desktop / tap mobile): each cell reveals the specific team names making up that bucket plus the points value. For ✓: "ARG · BRA · ENG · FRA · earned 40 pts". For ◐: "USA · MEX · GER · ITA · potential 80 pts".

**Visual treatment** (Panini tokens):
- ✓ green fill: `var(--green)` `#1b6c3e`
- ◐ gold fill: `var(--gold)` `#d49a2e`
- Bar background: `var(--paper-3)` `#dfd4ba`
- Inter-stage rule between rows: `var(--paper-3)` at ~0.5px for structure
- Each phase sub-grid wrapped in `pn-card` style box with hard offset shadow
- Phase headers (round 5 — no multiplier badge): `PHASE 1 · ORIGINAL · earned 80 pts · available 275 pts` and `PHASE 2 · RE-PICK · earned 180 pts · available 18 pts`

**Phase totals (round 5)**: integrated into the phase HEADERS, not a separate widget. `DwBracketStatusLine` is dropped — no longer needed.

**Mobile (<700px)**: same stacked structure works as-is on mobile (P1 then P2). Each phase sub-grid is full-width on narrow viewports. Widget height stays similar (~340-380px) since rows-as-stages is already mobile-friendly.

**Backend extension required (revised round 4)**: `getBracketExposure(phase)` needs to be extended to return, **per stage X**:
- `known_count` (= `|known_at_X|`, the ✓ denominator — progressive)
- `tbd_count` (= `|tbd_at_X|`, the ◐ denominator — progressive)
- `correct_count` (= ✓ numerator)
- `in_play_count` (= ◐ numerator, with TBD-match dedup applied)
- `correct_teams`, `in_play_teams` (lists for tooltips)
- `correct_points`, `in_play_points` (earned vs potential)

Compute uses existing `_compute_teams_that_made_stage` + a new helper that walks unplayed previous-round matches and buckets user picks. The dedup step is a one-pass over TBD matches checking which match each in-play pick belongs to. The ✗ Out bucket is no longer needed (dropped from display).

### Dropped from earlier proposal

- **`DwKoSpotlight`** — absorbed into the upcoming-24h column. Inline entry lives on individual upcoming cards.
- **`DwPredictionNudge` (scope=`phase_2_scores`)** — subsumed by `DwKoMissingPicksAlert`.
- **"P1 winner / P2 winner" lines on individual match cards** — dropped. The bracket-alive widget carries the "what's still possible" story across the whole bracket; per-card bracket context was redundant.

---

## Phase 5 — Post-competition

### User goal

See who won. See where I finished. Relive the run.

The competition is **over**. No CTAs to action. The dashboard is a *memorial* — trophy moment, retrospective stats, and links to deep dives.

### Desktop layout

```
+================================================================+
|                  🏆  CHAMPION PODIUM (full width)             |
|                                                                |
|              ┌──── OVERALL WINNER ────┐                        |
|              │       ALICE            │                        |
|     ┌──────┐ │       380 pts          │ ┌─────────┐           |
|     │ P2 W │ │       🏆 trophy        │ │ GS WIN  │           |
|     │ BOB  │ │                        │ │ CHARLIE │           |
|     │ 168  │ │                        │ │  220    │           |
|     └──────┘ └────────────────────────┘ └─────────┘           |
|                                                                |
|     Tournament won by 🇦🇷 ARG · 4 of 30 picked it             |
|                          [ full standings → ] ← bottom-right   |
+================================================================+

(Round-2 reinterpretation: the side podiums are no longer "2nd and 3rd
by total points" — they're now "Phase 2 Winner" (most points earned
during Phase 2) and "Group Stage Winner" (most points earned during
the group stage portion of Phase 1). Three different *competitions*,
three different stories — much more interesting than the same ranking
restated three times.)

+================================================================+
|  FINAL KPI ROW (round-1 feedback — DwFinalPosition becomes a   |
|  KPI row instead of a single card)                             |
|  ┌────────┬────────┬────────┬────────┬─────────┐              |
|  │ RANK   │ TOTAL  │ PEAK   │ EXACT  │ OUTCOMES│              |
|  │ 5/30   │  290   │  3rd   │   6    │   18    │              |
|  │ FINAL  │  pts   │ (day 12)│ scores │ correct │             |
|  └────────┴────────┴────────┴────────┴─────────┘              |
+================================================================+

+============================+===================================+
|  SCORING JOURNEY (frozen) |  HIGHLIGHTS                       |
|                            |                                   |
|  Same widget as KO,        |  🎯 Best exact streak: 4 matches  |
|  but ◐ In-play row         |  📈 Biggest climb: ▲8 (Day 12)   |
|  collapses to 0 (no        |  ⭐ Most contrarian win: BRA 2-1 |
|  pending picks). Just      |     MEX (you + 3 of 30)           |
|  ✓ Correct + ✗ Out per     |  🔥 Best phase: Phase 1 (180 pts)|
|  stage × phase.            |                                   |
|                            |                                   |
|  [ see full breakdown → ]  |                                   |
+============================+===================================+
```

Heights: podium ~200 + KPI row ~140 + journey/highlights ~280 = ~620px + chrome ✓ (tighter than before — dropped Final Standings widget per round-1 feedback)

### Mobile layout

Stack: champion podium (full width, prominent) → final KPI row (compact) → scoring journey (frozen) → highlights.

### Widgets

| Widget | Status | Data source | Notes |
|---|---|---|---|
| `DwChampionPodium` | **NEW** | `GET /leaderboard?phase=null` for overall winner + `GET /leaderboard?phase=phase_2` for Phase 2 winner + `GET /leaderboard?phase=phase_1` filtered/scoped to group stage for Group Stage winner + `GET /leaderboard/tournament-winner` for picker count | Full-width hero. **Round-2 reinterpretation**: the three slots are no longer "top 3 by total points" — they are now **Overall Winner** (centre, gold trophy), **Phase 2 Winner** (left), and **Group Stage Winner** (right). The side slots celebrate different competitions within the tournament, not a re-statement of the same ranking. **Gold trophy on Overall Winner only**. Bottom line: "Tournament won by [TEAM] · N of M picked it correctly". `[ full standings → ]` CTA in the bottom-right corner of the hero. Routes to `/leaderboard`. |
| `DwFinalKpiRow` | **NEW** (was `DwFinalPosition`) | `$currentUserPosition` + `getMyRankTrajectory(all_time=true)` for peak + breakdown | **Round-1 feedback**: this is a *KPI row* of 5 stickers (like group_stage/KO), not a single card. Stickers: **Rank** (final position), **Total** (total points), **Peak** (best rank reached, with the date in parens — "3rd · day 12"), **Exact** (count of exact-score hits), **Outcomes** (count of correct outcomes). **No deltas** — these are final, frozen values. The "Trajectory" sticker from earlier phases is replaced here by **Peak** since trajectory is no longer evolving. |
| `DwScoringJourney` (frozen variant, 1/2) | **REUSE** | `getBracketExposure(phase_1)` + `getBracketExposure(phase_2)` extended | **Round-3 update**: Phase 5 reuses the KO `DwScoringJourney` widget in its **frozen** form — the ◐ In-play row collapses to empty (no picks pending; tournament is over). Layout becomes a 2-row grid per phase (✓ Correct / ✗ Out), but visual structure is identical. Tooltips still surface team lists. Alternative under consideration: a smaller standalone "final source breakdown" widget if 2 rows × 5 stages × 2 phases reads as too sparse in the frozen state. |
| ~~`DwLeaderboard` (final standings)~~ | **DROPPED (round 1)** | — | Was: top 5 + neighborhood in a third row. **Dropped in round 1** — top 3 is already in the podium hero, and the `[ full standings → ]` CTA in the hero handles the deep-dive routing. Saves a whole row vertically. |
| `DwHighlights` (1/2) | **NEW** | `GET /leaderboard/me/highlights` (endpoint shipped) | 4-5 emoji-tagged retrospective stats: best exact streak, biggest single-day climb, most contrarian-correct, best phase. **Backend shipped**: endpoint computes personal-bests by querying breakdown + snapshots + agreements + predictions server-side. Response shape: `MyHighlights { best_exact_streak, biggest_climb, most_contrarian_correct, best_phase }` — any field nullable when insufficient data. |
| `DwPostCelebration` | **NEW** | localStorage flag for "seen-before" | One-time celebration sequence that fires on the **first** post-comp visit. See *Design intent* below. |

### Design intent — `DwPostCelebration` (the fun bit)

A one-time orchestrated reveal that runs when the user lands on the post-comp dashboard for the first time. Detection: localStorage key `predictor_post_celebration_seen_${competition_id}`. If unset, fire the sequence and set the flag.

Sequence sketch:
1. **Page loads dimmed** (paper background with a soft overlay)
2. **Confetti burst** — Canvas-based confetti in `var(--red)`, `var(--gold)`, `var(--navy)`, `var(--paper)`. Bursts from top-center, falls naturally
3. **Trophy thwack** — trophy graphic slides in from above and "thwacks" into place on the 1st-place podium card (CSS transform + Panini's hard-shadow style — the trophy "stamps" onto the sticker like a Panini sticker landing in an album)
4. **Podium stickers reveal** — 1st/2nd/3rd cards animate in with a slight overshoot bounce, staggered ~150ms apart, each landing with their hard offset shadow
5. **Numbers count up** — final points totals on the podium animate from 0 to their actual values (~1.2s ease-out), matching the bouncing-counter style of sports broadcasts
6. **"Tournament won by ARG" line fades in** with a small flag-flutter
7. **Your final position card pops in** with a personal "and you finished Xth" reveal
8. **Highlights stickers cascade in** one by one (~80ms apart), each with its emoji
9. **Page fully lit** — overlay fades, dashboard is now in its steady state

The whole sequence is ~4-5 seconds. After it completes, the dashboard behaves normally on all subsequent visits. A subtle replay icon in the corner of the podium (small "↻") lets the user re-trigger if they want.

**Accessibility**: respects `prefers-reduced-motion: reduce` — when set, skip the confetti and bounces; just fade everything in over ~400ms with no movement.

**Implementation notes**:
- Confetti can use a small Canvas-based library or hand-rolled <50 lines of code (the visual is simple)
- All other animations are CSS transforms + opacity + counter (no library needed)
- Sound effect (trophy clang?) — *flag as nice-to-have for design*; would need toggle/respect for system sound preferences
- The seen-flag is per-competition (`predictor_post_celebration_seen_${competition_id}`) so future tournaments retrigger it

### Widgets considered and rejected

- **`DwKpiRow`** (used in every other phase, with deltas) — dropped in favour of `DwFinalKpiRow` which is the same visual shape but with frozen-final values and no deltas. The KPI-row form is preserved (round-1 feedback); only the content changes.
- **`DwLeaderboard` as a third row** — dropped in round 1. Top 3 is in the podium; `[ full standings → ]` in the hero corner handles drill-down.
- **`DwBracketAlive`** — dropped in round 3 (no longer exists as a separate widget — folded into `DwScoringJourney`).
- **`DwUnsavedAlert`, `DwPredictionNudge`, `DwKoMissingPicksAlert`** — all predicate on editable predictions; none apply post-tournament.
- **`DwGroupStageSummary`** — settled long ago; the breakdown link from `DwScoringJourney` is where to drill in.
- **`DwRecentResults` / `DwTodaysGames`** — no recent or upcoming matches; full results live in `/results`.

---

## New widgets summary table

| Widget | Phases | Data source | Backend ready? |
|---|---|---|---|
| `DwUnsavedAlert` | Pre, Between, KO | `$unsavedChangesCount` + bracket/phase-2-bracket unsaved stores | ✓ (stores exist) |
| `DwPreCountdownHero` | Pre | phase store + one overall progress count | ✓ |
| `DwCompletionBars` | Pre | predictions + bracket + bonus stores | ✓ |
| `DwScoringPeek` | Pre | `getScoringConfig()` | ✓ |
| `DwRulesPeek` | Pre | `getCompetitionInfo()` | ✓ |
| `DwLeaderboard` (configurable) | Pre, Group, Between, KO, Post | `$leaderboard` | ✓ |
| `DwRecentResults` | Group | fixtures + predictions + breakdown calc | ✓ |
| `DwTodaysGames` | Group | fixtures + predictions stores | ✓ |
| `DwMatchCard` (shared atom inside Recent/Today) | Group, KO | fixture + prediction props | ✓ |
| `DwBetweenHero` | Between | phase store + `getPhaseBreakdown(me)` for group-stage total | ✓ |
| `DwGroupStageSummary` | Group, Between, KO, Post | `getPhaseBreakdown(me)` + per-fixture breakdown + bonus answers | ✓ |
| `DwKoMissingPicksAlert` | KO | `$upcomingFixtures` KO-filtered + `$predictionsByFixture` | ✓ |
| ~~`DwBracketStatusLine`~~ | — | — | DROPPED in round 5 (folded into `DwScoringJourney` per-phase headers) |
| `DwScoringJourney` | KO | `getBracketExposure(phase_1)` + `getBracketExposure(phase_2)` **extended** with `in_play_per_stage`, `out_per_stage`, `teams_by_cell` | ◑ (**round-3 backend extension**: extend `BracketExposureResponse` to bucket picks into correct/in-play/out and include team-name lists per cell for tooltips) |
| ~~`DwPointsBySource`~~ | — | — | DROPPED in round 3 (folded into `DwScoringJourney`); note: this widget was also planned for Post phase — for post, fall back to a frozen version of `DwScoringJourney` with no In-play row (collapses to ✓ + ✗ only), OR re-introduce a standalone widget at that point |
| ~~`DwBracketAlive`~~ | — | — | DROPPED in round 3 (folded into `DwScoringJourney`) |
| `DwChampionPodium` | Post | `GET /leaderboard?phase=null` (overall) + `?phase=phase_2` (P2 winner) + scope=group_stage (GS winner) + `GET /leaderboard/tournament-winner` | ◑ (**round-2 backend gap**: Group Stage Winner needs a `scope=group_stage` filter on `/leaderboard` — sum of group-stage scoring components only [outcomes + exacts + rarity + group_advance + group_position + group-stage bonus questions], excluding R16-Winner bracket stages. Either extend the existing `phase` param to accept `group_stage` or add a dedicated `/leaderboard/group-stage-winner` endpoint.) |
| `DwFinalKpiRow` (was `DwFinalPosition`) | Post | `$currentUserPosition` + `getMyRankTrajectory(all_time=true)` + breakdown | ✓ (snapshot extension + `all_time` shipped) |
| `DwHighlights` | Post | `GET /leaderboard/me/highlights` | ✓ (endpoint shipped) |
| `DwPostCelebration` | Post | localStorage seen-flag; no API data | ✓ |

## Reuse / extraction plan

| Existing widget | Currently in | Phases needed | Action |
|---|---|---|---|
| KPI row | `DashGroupStage.svelte` inline | Group, KO, Post | **EXTRACT** to `DwKpiRow.svelte` |
| Live broadcast | `DashGroupStage.svelte` inline | Group, KO (during live KOs) | **EXTRACT** to `DwLiveBroadcast.svelte` |
| Next-lock countdown | `DashGroupStage.svelte` inline | Group only (KO uses different design via `DwNextKoMatch`) | **EXTRACT** to `DwNextLockCountdown.svelte` |
| Rank trajectory | `DashGroupStage.svelte` inline | Group, KO, Post | **EXTRACT** to `DwRankTrajectory.svelte` (wraps `PnSparkline`) |
| Closest rivals | `DashGroupStage.svelte` inline | Group, KO | **EXTRACT** to `DwClosestRivals.svelte` |
| Hot pick | `DashGroupStage.svelte` inline | Group | **REDESIGN** — visually too dense; needs one-glance simplification |
| Bracket exposure (single) | `DashGroupStage.svelte` inline | Group | **REDESIGN** — currently stub; redesign visual once real data lands |
| Top 5 / leaderboard | `DashGroupStage.svelte` inline + `/leaderboard` page table | **All 5 phases** | **EXTRACT** to `DwLeaderboard.svelte` with `limit` + `headerLabel` props. Lift the leaderboard table render from `/leaderboard/+page.svelte` so the same component drives both the dashboard widget and the standings page. Consider sticky-self row for users below the limit. |
| ~~Upcoming matches table~~ | `DashGroupStage.svelte` inline | — | **DROPPED in round 2** — Phase 2 layout absorbs the Up Next role into the "Upcoming 24h" cards column. Longer-horizon schedule view available at `/predictions` and `/results`. |
| `PnResultsCard` | `/results` page | KO (today's results) | **REUSE** as-is; pass smaller fixture set |

## Group-stage redesign focus

Two concrete weaknesses in the current build worth flagging to claude-design:

1. **`DwHotPick`** — too dense. Currently shows: home/away flag + code, your predicted score, agreement count, total, potential points, multiplier. Five facts in one small card. Reduce to: matchup + your score + ONE primary signal (e.g. "Only 3 of 32 picked this — high EV"). Move details to hover/tap.

2. **Mobile "insights row"** — Rivals / Hot pick / Bracket exposure don't fit gracefully on mobile. Either compress to a horizontally-scrollable carousel of single-purpose cards OR pick the ONE most relevant for the current state (e.g. if user's rank is moving = show rivals; if there's an open fixture = show hot pick).

Beyond those two, the rest of the group-stage layout is solid in concept; the redesign work is mostly visual polish (rhythm, hierarchy, breathing room).

## Handoff to claude-design

Chronological order (mirrors user lifecycle and lets the dashboard principle be applied uniformly from the start):

1. **Pre-tournament** — currently a scaffold with placeholder.
2. **Group stage (redesign pass)** — has a working baseline but violates the "fits in viewport" principle today (long scroll). Tackle second so the redesign benefits from the principle being applied early.
3. **Between phases** — also currently a scaffold; clear single CTA so the design is constrained.
4. **Knockout** — most novel widgets (`DwNextKoMatch`, `DwPhaseSplitDonut`, `DwDualBracketExposure`); needs the most invention.
5. **Post-competition** — celebratory; can borrow heavily from podium / trophy visual language.

For each phase, request **desktop + mobile** comps, plus a **breakpoint behaviour note** for the 700px threshold (where Panini's chrome mode flips).
