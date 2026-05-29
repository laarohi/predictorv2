# Performance & Caching Audit

> Part of the pre-launch audit. See [README](./README.md) for methodology and the [Implementation Map](./IMPLEMENTATION.md) for fix status.

**12 findings:** 2 medium · 8 low · 2 info

## What this area does well

- Leaderboard results are cached per-phase with a 30s TTL and explicitly invalidated on score sync and bonus-answer changes (services/score_sync.py:121, api/admin.py:622), so steady-state reads are cheap.
- Single uvicorn worker in both dev compose and the Dockerfile (no --workers flag), so the per-process in-memory leaderboard cache is consistent — no cross-worker staleness bug at current scale.
- Async DB driver (asyncpg) and async httpx are used throughout the request path; email is a non-blocking HTTP call to Resend with its own retry/backoff, and the heavy email batch runs in the background scheduler tick, never on a user request.
- Settings and tournament YAML config are @lru_cache'd (config.py:82,100), so scoring config is not re-parsed from disk on every scoring call.
- Several aggregation endpoints were deliberately written to avoid N+1: the roster (api/users.py:125-141) and receipt idempotency pre-load (services/receipts.py:500) use single GROUP BY / IN queries with explanatory comments.
- FK and hot single-column indexes exist where expected: match_predictions.user_id/fixture_id, team_predictions.user_id, scores.fixture_id (unique), fixtures.kickoff, plus the snapshot (user_id, captured_date) unique constraint backs idempotent daily writes.
- Daily snapshot write uses INSERT ... ON CONFLICT DO NOTHING (services/snapshots.py:65-69), so the per-minute scheduler tick is a cheap idempotent no-op after the first call of the day.
- The score scheduler gates external API polling behind a cheap has_active_or_imminent_match() check (services/score_sync.py:42), avoiding wasted work and API quota outside match windows.
- Stores are module-level singletons (frontend/src/lib/stores/*.ts), so fetched data (fixtures, predictions, leaderboard) persists across route navigation rather than being lost on unmount — the building block for caching is in place.
- Results page precomputes a per-fixture MatchBreakdown Map ONCE per data change (results/+page.svelte:76-90) instead of recomputing inline per render when sort/filter flips — an explicit, well-documented memoization.
- The localStorage unsaved-draft mirror (unsavedPersistence.ts) is debounced at 300ms and per-key deduped with a stringify cache, avoiding write storms on every keystroke and breaking the cross-tab echo loop.
- Fonts load with display=swap plus preconnect to fonts.gstatic.com (app.html:10-12), so there's no FOIT and minimal layout shift.
- Code-splitting works in the app's favor: login/register/auth pages don't import PnFlag or any heavy chrome, so the flag bundle only loads on routes that actually show flags.
- Polling and the 1s countdown ticker are both correctly torn down: leaderboard onDestroy calls stopPolling() (leaderboard/+page.svelte:33-35) and the currentTime readable returns a clearInterval cleanup (phase.ts:25) — no obvious interval leaks.
- Lists are intentionally NOT virtualized, which is the right proportionate choice for ~30 rows / 63 fixed bracket matches; virtualization would be needless complexity here.
- The dashboard dispatcher uses <svelte:component> rather than an if-chain to avoid re-evaluating every branch on uxPhase change (+page.svelte:14-20), and uxPhase is deliberately decoupled from the heavy fixtures writable to avoid a reactive cascade (phase.ts:79-140).

## Assessment by sub-dimension

### Backend Performance & Caching (10-20 concurrent users)

The leaderboard is the dominant performance risk. Its cold-path recomputation is a deeply nested N+1 explosion: for each active user it re-scans all match predictions, runs one `get_outcome_counts` query per finished fixture, recomputes `get_actual_advancement` and the entire group-standings + third-place + FIFA-rankings chain (the latter computed two-to-three times per user), and recomputes bonus points. With the full 104-match group stage scored and 30 users, a single cold build is on the order of several thousand SQL round-trips. A 30s in-memory TTL masks this for steady-state reads, but it is unprotected against cache stampede (the public, unauthenticated `/leaderboard/` endpoint with `refresh=true` bypasses the cache entirely and forces a full recompute on demand), and the same recompute is reused by snapshots, trajectory, profile, highlights, and (per-user, in a loop) the deadline receipt batch. None of these are blocking-driver or sync-IO issues — the async DB driver (asyncpg) and httpx are used correctly, email is HTTP-based, and config is LRU-cached — so the problem is purely query volume and recompute amplification, which is tolerable at 30 users only because of the cache and because the heaviest paths fire mostly post-group-stage. There are also a handful of true per-row N+1 loops in prediction/profile list endpoints and a couple of missing composite indexes on hot filter columns. Severity is calibrated down for a 30-person hobby app behind Cloudflare, but the leaderboard recompute cost and stampede exposure are real and worth addressing before the group stage finishes.

### Frontend Performance & Responsiveness

For a 30-person hobby app behind Cloudflare, the frontend is generally well-built and proportionate: stores are module-level singletons that cache across navigation, the results page memoizes per-fixture breakdowns, the localStorage draft mirror is debounced and deduped, fonts use display=swap with preconnect (minimal layout shift), and code-splitting keeps the auth pages free of heavy chunks. Lists (leaderboard ~30 rows, roster ~30, bracket 63 matches) are small enough that NOT virtualizing them is the correct call. The real defects are concentrated in two areas: (1) bundle weight — the PnFlag component eagerly inlines all ~260 flag-icons SVGs as raw strings into the JS bundle on any flag-using route, far more than the ~50 ever shown at once; and (2) the leaderboard live-poll, which every 60s silently resets the user's Phase I/II tab back to "Overall" and flashes a loading state. Several routes also refetch all data on every navigation with no staleness guard, which is wasteful but cheap at this scale. None of this touches the security/cheating/snooping threat model — these are purely sluggishness/UX issues. No data-integrity or blind-pool problems were found on the frontend performance surface.

## Findings

## 🟡 MEDIUM findings

### 🟡 MEDIUM — Leaderboard cold recompute is a nested N+1 explosion (per-user, per-finished-fixture queries)

- **Ref:** `perf-backend:PERF-1`  ·  **Effort:** medium  ·  **Confidence:** 0.95
- **Location:** `backend/app/services/leaderboard.py:138-140; backend/app/services/scoring.py:611-620,692-710`

**Problem.** calculate_leaderboard loops over every active user and calls calculate_user_points + get_user_match_stats for each. calculate_user_points then issues one get_outcome_counts() query PER finished fixture (scoring.py:620 inside the row loop), plus get_actual_advancement (a full knockout-fixtures scan, scoring.py:654) recomputed for every user, plus calculate_group_position_bonus and calculate_bonus_points. With the 104-match group stage fully scored and ~30 users, a single cold build is on the order of 30 * (104 outcome-count queries + ~10 standings/advancement/bonus queries) ≈ several thousand SQL round-trips. The 30s TTL hides this in steady state, but every cache miss (TTL expiry, or any invalidate_cache() call after a score/bonus update) pays the full cost, and the same calculate_user_points/calculate_leaderboard is reused by profile, trajectory, highlights, and snapshots. At 30 users this is survivable but slow (likely multi-second) on a small VPS, and it scales as O(users * fixtures).

**Recommendation.** Hoist the per-fixture and tournament-global computations out of the per-user loop: compute outcome_counts for all fixtures once (single GROUP BY fixture_id, outcome query), compute get_actual_advancement and actual group standings once per build, and pass them into a refactored calculate_user_points. Replace the per-fixture get_outcome_counts call with a dict lookup. This collapses the cold build from O(users*fixtures) queries to a small constant number of queries.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🟡 MEDIUM — Public leaderboard endpoint allows uncached, on-demand full recompute (cache-stampede / abuse vector)

- **Ref:** `perf-backend:PERF-2`  ·  **Effort:** small  ·  **Confidence:** 0.9
- **Location:** `backend/app/api/leaderboard.py:94-117; backend/app/services/leaderboard.py:117-119`

**Problem.** GET /leaderboard/ is OptionalUser (effectively public) and accepts refresh=true, which sets force_refresh and bypasses the TTL entirely, forcing the full PERF-1 recompute on every such request. There is no stampede guard: the cache is a plain dict with no lock, so when the TTL expires (or after invalidate_cache during a live match-day score sync) multiple concurrent requests from the 10-20 active users all miss simultaneously and each runs the full recompute in parallel, multiplying DB load at exactly the moment scores are changing. A curious/technical friend hammering ?refresh=true could also pin the single worker. Not a data-integrity or cheating issue, but a genuine availability defect on match day.

**Recommendation.** Restrict refresh=true to admins (or remove it; invalidate_cache already covers the legitimate 'scores changed' case). Add a simple per-cache-key asyncio.Lock around the recompute so only one coroutine rebuilds while others await the result (single-flight). Optionally serve slightly-stale cache while a refresh is in flight.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

## 🔵 LOW findings

### 🔵 LOW — Redundant standings/rankings recomputation inside the per-user group-position bonus

- **Ref:** `perf-backend:PERF-3`  ·  **Effort:** medium  ·  **Confidence:** 0.9
- **Location:** `backend/app/services/scoring.py:419-424; backend/app/services/standings.py:451-456,537-565`

**Problem.** calculate_group_position_bonus (called once per user from the leaderboard loop at scoring.py:672) calls get_predicted_group_standings, get_actual_group_standings, AND get_qualifying_third_place_teams. get_qualifying_third_place_teams internally calls get_actual_group_standings_with_warnings AGAIN, so actual standings are computed twice per user, and _resolve_fifa_rankings (a DB query) runs three-plus times per user. Across 30 users on the leaderboard cold path this multiplies into dozens of full group-fixture scans and rankings queries that all produce identical tournament-global results.

**Recommendation.** Compute actual group standings + qualifying thirds + FIFA rankings once per leaderboard build and thread them through to calculate_group_position_bonus, rather than recomputing per user. The user-specific part (predicted standings) is the only thing that legitimately varies per user.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🔵 LOW — Phase-1 receipt batch recomputes per user and runs serially inside the scheduler tick

- **Ref:** `perf-backend:PERF-6`  ·  **Effort:** medium  ·  **Confidence:** 0.8
- **Location:** `backend/app/services/score_scheduler.py:67-70,86-116; backend/app/services/receipts.py:524-549`

**Problem.** At the moment phase1_deadline passes, every scheduler tick (every 60s) calls send_phase1_receipts, which loops over all active users and for each builds the full receipt (multiple per-user queries) and awaits an external Resend HTTP send serially. Idempotency rows prevent re-sending, so after the first successful pass it no-ops — but the FIRST pass blocks that tick for the duration of ~30 sequential email round-trips (each up to a 20s httpx timeout, plus retry backoff on transient failures). Because the scheduler is a single asyncio task, a slow/failing Resend during that window also delays the in-tick score sync. Any user whose send keeps failing (permanent 4xx) is retried every single tick forever, re-building their receipt each time.

**Recommendation.** Run the receipt batch as its own background task rather than inline in the polling tick, or cap retries for permanent failures (record a 'failed' state so they aren't re-built every minute). For 30 users serial sends are acceptable once, but decouple it from the score-sync tick so a slow Resend can't stall live-score updates on match day.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🔵 LOW — Missing composite indexes on the hottest filter pairs (predictions.user_id+phase, fixtures.status, fixtures.stage)

- **Ref:** `perf-backend:PERF-7`  ·  **Effort:** small  ·  **Confidence:** 0.6
- **Location:** `backend/app/models/prediction.py:30-35,67-72; backend/app/models/fixture.py:39-47; backend/app/services/scoring.py:600-607`

**Problem.** The dominant query shape is `MatchPrediction WHERE user_id=? JOIN Fixture WHERE status=FINISHED` and `TeamPrediction WHERE user_id=? AND phase=?`. user_id is indexed but phase is not, and Fixture.status / Fixture.stage have no index (only home_team/away_team/kickoff/external_id do). At 30 users * ~136 predictions and ~104 fixtures the tables are tiny enough that Postgres will seq-scan them in microseconds, so this is genuinely low impact at launch scale — but the recurring leaderboard/standings/advancement queries filter on Fixture.status=FINISHED and Fixture.stage repeatedly, so a partial or composite index would help the (frequent, cached-miss) cold rebuild and is cheap insurance.

**Recommendation.** Only if PERF-1/PERF-3 don't already remove the hot loops: add a composite index on match_predictions(user_id, fixture_id) (covers the join+filter) and a partial index on fixtures(status) WHERE status='finished' / fixtures(stage). Skip if you collapse the recompute to a few set-based queries, since the planner will scan the tiny tables fine.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🔵 LOW — Background scheduler creates a second SQLAlchemy engine / connection pool

- **Ref:** `perf-backend:PERF-8`  ·  **Effort:** trivial  ·  **Confidence:** 0.7
- **Location:** `backend/app/services/score_scheduler.py:38-42; backend/app/database.py:33-50`

**Problem.** _make_session_factory builds its own create_async_engine separate from the app's module-level engine, so the process holds two independent asyncpg pools (default ~5+10 each). At 30 users on one worker this is harmless and even slightly isolates scheduler load from request load, but it doubles idle connection count against Postgres for no functional reason and the engine is never disposed. Worth noting for the deployment's max_connections budget on a small VPS.

**Recommendation.** Reuse the app's async_session_maker (import from database.py) in the scheduler instead of constructing a second engine, or explicitly size both pools small (pool_size=2) so two pools don't exhaust Postgres max_connections under any future multi-worker config.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🔵 LOW — All ~260 flag-icons SVGs eagerly inlined into the JS bundle as raw strings

- **Ref:** `perf-frontend:PERF-1`  ·  **Effort:** medium  ·  **Confidence:** 0.9
- **Location:** `frontend/src/lib/utils/flagSvgs.ts:17-21`

**Problem.** flagSvgs.ts uses `import.meta.glob('/node_modules/flag-icons/flags/4x3/*.svg', { eager: true, query: '?raw', import: 'default' })`. `eager: true` means EVERY 4x3 flag SVG (flag-icons 7.5.0 ships ~260 country flags, many with detailed coats of arms) is inlined as a JavaScript string into the chunk that imports this module. PnFlag and PnAxisFlag both pull it, and those are transitively imported by the dashboard, predictions wizard, results, profile and bracket routes. So the first flag-using route a player visits downloads the full set even though a World Cup has 48 teams and any single screen shows at most ~50 flags. The flag-icons 4x3 raw set is on the order of 1.5-2 MB uncompressed (a few hundred KB gzipped) of pure data shipped to every player on a phone. The component's own comment acknowledges this trade-off ('all 271 SVGs land in the JS bundle as strings'). CLAUDE.md still describes PnFlag as lightweight '2/3-stripe gradient placeholders', so this regression isn't reflected in the docs.

**Recommendation.** Drop `eager: true` so the glob becomes a map of lazy import() factories, and have rawFlagSvg/flagDataUrl resolve only the codes actually needed (await the factory, cache the result). Even simpler given the closed team set: at build time, narrow the glob to only the ISO codes that can appear (teamCodes.ts already maps team->code), or generate a small static module containing just those flags. Either approach cuts the flag payload by ~80% and removes hundreds of KB from the first flag-route load.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🔵 LOW — Leaderboard 60s poll silently resets the user's Phase I/II tab and flashes a loading state

- **Ref:** `perf-frontend:PERF-2`  ·  **Effort:** small  ·  **Confidence:** 0.85
- **Location:** `frontend/src/lib/stores/leaderboard.ts:97-113`

**Problem.** The leaderboard route starts a 60s poll (startPolling(60000)). Every cycle pollLiveData() runs: it sets leaderboardLoading=true (line 98), then on success sets leaderboardPhase='overall' (line 108). The page's tab buttons bind class:on to $leaderboardPhase, and the rendered point columns are computed via matchPts/exactPts/etc. keyed on $leaderboardPhase. So if a player taps 'Phase I' to inspect group-stage standings, up to 60 seconds later the poll silently snaps them back to 'Overall' and recomputes every row's columns — their selection is lost mid-read. Separately, leaderboardLoading=true on every poll makes the header flip to 'LOADING…' once a minute even when data is already on screen, a visible flicker. The phase reset is the clearer defect: live polling and the phase filter are entangled, but the poll only ever returns overall data so it clobbers the filter rather than refreshing it in place.

**Recommendation.** Don't mutate leaderboardPhase from the poll. Either (a) poll the currently-selected phase, or (b) keep the poll writing to overall but store live data in a separate store and let the displayed table stay on whatever phase the user picked. Also gate the loading flag: only set leaderboardLoading on the FIRST poll (when leaderboard is empty), not on every refresh, so the header doesn't flash 'LOADING…' every 60s over already-rendered rows.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🔵 LOW — Every route/dashboard refetches all data on each navigation; module-store caching is never used as a cache

- **Ref:** `perf-frontend:PERF-3`  ·  **Effort:** medium  ·  **Confidence:** 0.8
- **Location:** `frontend/src/lib/components/panini/dashboard/DashGroupStage.svelte:38-47`

**Problem.** Stores are module-level singletons, so data survives navigation — but no fetch function honors that. fetchAllFixtures/fetchLeaderboard/fetchMatchPredictions unconditionally hit the network and call .set() on each onMount. Navigating dashboard -> leaderboard -> dashboard re-runs DashGroupStage.onMount and refetches fixtures + leaderboard + predictions + rank trajectory from scratch; the same is true for DashboardPre/Between/KO/Post, the predictions wizard (onMount Promise.all of three fetches), and results. With data-sveltekit-preload-data='hover' in app.html, simply hovering nav links can also kick module loads early. At 30 users this is harmless backend load, but it means the dashboard shows a fresh loading pass on every return visit instead of rendering the cached data instantly and revalidating. The phase store already half-solves this elsewhere via a hasLoadedPhase guard in +layout.svelte:34.

**Recommendation.** Add a lightweight freshness guard to the fetch functions (e.g. a module-level lastFetched timestamp; skip the network call if the store is non-empty and fetched < N seconds ago, or expose a forceRefresh flag). Render the cached store value immediately on remount and revalidate in the background. This removes the per-navigation loading flash without changing the data model.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🔵 LOW — Full knockout bracket mounts ~126 inlined-SVG flags at once (no lazy mount of off-screen mobile pages)

- **Ref:** `perf-frontend:PERF-4`  ·  **Effort:** small  ·  **Confidence:** 0.7
- **Location:** `frontend/src/lib/components/panini/PnKnockoutBracket.svelte:442-474`

**Problem.** The bracket renders all rounds (R32 32 + R16 16 + QF 8 + SF 4 + F 1 ≈ 63 matches), each PnBracketMatch rendering two PnFlag instances, so ~126 flags exist in the DOM simultaneously. On desktop that's the intended wall chart. On mobile, the 'swipeable' layout still renders every round into a single translateX track (line 439-474) — all pages are in the DOM at once, just shifted off-screen — so the mobile view doesn't actually reduce flag/DOM count. Each PnFlag does `{@html svg}` to inject a full SVG string (PnFlag.svelte:42). For a fixed 63-match tournament this is acceptable, but combined with PERF-1 it makes the bracket the heaviest screen to paint, and it's a screen players open repeatedly during predictions.

**Recommendation.** Primarily fix PERF-1 (lazy flags) which directly lightens this screen. Optionally, on the mobile track only render the active page +/- 1 round (key off `page`) instead of all rounds, since they're translated off-screen anyway. Low priority — the bracket size is fixed and small.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

## ⚪ INFO findings

### ⚪ INFO — In-memory leaderboard cache is per-process — correct for one worker today, silently wrong if --workers>1 is ever added

- **Ref:** `perf-backend:PERF-9`  ·  **Effort:** trivial  ·  **Confidence:** 0.85
- **Location:** `backend/app/services/leaderboard.py:40-42,196-202; backend/Dockerfile:22`

**Problem.** _cache is a module-level dict, so it lives per Python process. The Dockerfile and dev compose both run a single uvicorn worker with no --workers flag, so today this is correct and stampede/movement tracking work. But invalidate_cache() only clears the calling process's dict — if a future deploy adds gunicorn -w N or uvicorn --workers N for headroom, each worker keeps its own stale cache, invalidate_cache (called from score sync / bonus updates) clears only one of them, and position-movement deltas become per-worker nondeterministic. Recording as info because nothing is broken at the current single-worker config; it's a latent footgun tied to a config change.

**Recommendation.** Add a code comment + a deployment note that the in-memory cache assumes a single worker; if you ever scale workers, move the cache and invalidation signal to a shared store (even a tiny Redis, or a DB-stored last_invalidated timestamp the cache checks). No action needed while single-worker.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### ⚪ INFO — Live poll keeps running on hidden/backgrounded tabs

- **Ref:** `perf-frontend:PERF-6`  ·  **Effort:** trivial  ·  **Confidence:** 0.7
- **Location:** `frontend/src/lib/stores/leaderboard.ts:81-93`

**Problem.** startPolling sets a 60s setInterval with no Page Visibility check, so a player who leaves the standings tab open in a background tab keeps hitting /scores/poll every minute indefinitely. For ~30 users this is trivial backend load and not worth heavy infra, but pausing on visibilitychange is a cheap courtesy that also avoids the PERF-2 phase-reset firing while the tab is unattended.

**Recommendation.** Optionally add a document visibilitychange listener that calls stopPolling() when hidden and startPolling() when visible. Genuinely optional at this scale.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---
