# Dead Code & Dev→Prod Cleanliness Audit

> Part of the pre-launch audit. See [README](./README.md) for methodology and the [Implementation Map](./IMPLEMENTATION.md) for fix status.

**12 findings:** 1 medium · 4 low · 7 info

## What this area does well

- Backend app/ is free of print() statements, TODO/FIXME/HACK markers, and debug logging — grep across backend/app returned zero hits for each.
- DEBUG defaults to False in config.py (line 20) and DEBUG=${DEBUG:-false} in docker-compose, so the FastAPI /api/docs and /api/redoc endpoints are correctly gated off in production (main.py:36-37).
- .env.example is a clean template with placeholder values only (JWT_SECRET_KEY=your-super-secret-key-change-in-production) — no real secrets committed.
- All 8 API routers are registered in app/api/__init__.py and all 11 Panini CSS modules are imported in app.css in the documented load-bearing order — no orphaned routers or stylesheets.
- Seed/test/calibration scripts under backend/scripts are NOT wired into any runtime path (not referenced by app/, docker-compose command, Makefile, or Dockerfile CMD) — they are manual tooling only.
- Frontend console usage is disciplined: the only console call is a dev-gated console.debug('[panini:stub]') in the stub module; production builds emit nothing.
- The dashboard widgets (DashGroupStage, DashboardKO, DashboardBetween, DashboardPost) correctly consume real APIs (getMyRankTrajectory, getBracketExposure) rather than stubs — the stub-to-real migration was genuinely completed for the dashboard surface.

## Assessment by sub-dimension

### Dead Code, Unused Assets & Dev→Prod Cleanliness

The codebase is, on the whole, unusually clean for a hobby project: the backend app/ has zero print()/TODO/debug-logging leakage, all 8 API routers are registered, all 11 Panini CSS modules are imported, the .env.example holds no real secrets, DEBUG defaults to False (gating /api/docs off in prod), and almost every component/util/store is wired. The dead code that remains is well-isolated. The single finding that actually matters for this threat model is the leaderboard "Trend · 7d" sparkline: it renders FABRICATED per-player rank-history data from stubRankTrajectory() for every row, even though a real backend endpoint (GET /leaderboard/snapshots/{user_id}) was purpose-built to feed exactly this column — for a real-money friend pool, showing invented trend lines as if they were real is misleading. The rest are tidy-up items: 7 fully-dead stub functions (kept alive only by their own tests), two dead util modules (flags.ts 243 lines, predictionResult.ts), an orphaned 277-line dashboard widget (DwPredictionNudge), two unused declared dependencies (svelte-motion, psycopg2-binary), two purpose-built-but-never-called backend endpoints, and a couple of stale TODOs. A force-lock dev script (test_match_detail.py) is worth flagging because of WHAT it does (shifts kickoffs into the past) even though it is not wired into runtime.

## Findings

## 🟡 MEDIUM findings

### 🟡 MEDIUM — Leaderboard "Trend · 7d" column shows FABRICATED rank-history data instead of the real endpoint built for it

- **Ref:** `clean-dead:STUB-1`  ·  **Effort:** medium  ·  **Confidence:** 0.95
- **Location:** `frontend/src/routes/leaderboard/+page.svelte:21,204`

**Problem.** The leaderboard table renders a per-row sparkline under a column literally labeled "Trend · 7d" (line 195), but the data comes from stubRankTrajectory(r.user_id, r.position, ...) — a deterministic-random rank walk seeded by user ID (stubs/panini.ts:71-90), NOT real rank history. A purpose-built backend endpoint GET /leaderboard/snapshots/{user_id} already exists and its docstring states it "powers the leaderboard's per-row sparkline column" (backend/app/api/leaderboard.py:208-218), with a matching frontend API fn getRankTrajectory() (api/leaderboard.ts:55) that is never called. In a real-money friend pool with technically-minded players, presenting invented trend lines as if they were genuine 7-day movement is misleading — a player could 'read' momentum into a chart that is pure RNG. This is the only stub-derived data still reaching users.

**Recommendation.** Wire the leaderboard sparkline to the real data: the leaderboard payload likely already carries enough, or batch-fetch via getRankTrajectory()/the snapshots endpoint (or extend the leaderboard response to embed each row's trajectory server-side to avoid N calls). Until wired, either hide the Trend column or label it clearly as a placeholder. Then delete the stubRankTrajectory import.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

## 🔵 LOW findings

### 🔵 LOW — flags.ts (243 lines) is a dead legacy module superseded by teamCodes.ts + flagSvgs.ts

- **Ref:** `clean-dead:DEAD-2`  ·  **Effort:** trivial  ·  **Confidence:** 0.95
- **Location:** `frontend/src/lib/utils/flags.ts:219-241`

**Problem.** flags.ts exports getFlagUrl(), getCountryCode(), hasFlag() and a ~200-line countryCodeMap, but has zero importers across the whole frontend (grep for any import of utils/flags returned nothing; the only hits for 'flags' point to the live flagSvgs.ts). The flag rendering pipeline now goes through teamCodes.ts (FIFA code → ISO) + flagSvgs.ts (Vite glob of flag-icons SVGs) + PnFlag.svelte. flags.ts is a stale earlier approach left behind. Dead, but tree-shaken so no prod-bundle impact.

**Recommendation.** Delete frontend/src/lib/utils/flags.ts.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🔵 LOW — DwPredictionNudge.svelte (277 lines) is an orphaned widget — superseded by DwAlert

- **Ref:** `clean-dead:DEAD-4`  ·  **Effort:** trivial  ·  **Confidence:** 0.93
- **Location:** `frontend/src/lib/components/panini/dashboard/widgets/DwPredictionNudge.svelte:1-13`

**Problem.** DwPredictionNudge is a fully-built, documented urgency-nudge widget whose own docstring claims it is 'Used at the top of DashboardPre (phase_1_open), DashboardBetween (phase_2_bracket), and conditionally inside DashboardKO'. In reality it has zero importers — those dashboards use DwAlert instead (DashboardPre.svelte:19 imports DwAlert, not the nudge). The docstring is aspirational; the widget was written, then replaced by DwAlert and never wired in. Dead, tree-shaken from prod, but a maintenance trap because its docstring lies about being in use.

**Recommendation.** Delete DwPredictionNudge.svelte, or if it is intentionally shelved for later, move it out of the active widgets dir and correct the misleading 'Used at...' docstring.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🔵 LOW — svelte-motion is a declared runtime dependency with zero usage

- **Ref:** `clean-dead:DEP-1`  ·  **Effort:** trivial  ·  **Confidence:** 0.92
- **Location:** `frontend/package.json (dependencies)`

**Problem.** package.json lists "svelte-motion": "^0.12.0" as a production dependency, but grep across the entire frontend src for svelte-motion / svelte/motion / 'motion' (including dynamic imports) returns nothing. CLAUDE.md describes it as 'planned'. It is unused weight in node_modules and the dependency tree. Low impact (private app), but it is dead and should not be advertised as a runtime dep.

**Recommendation.** Remove svelte-motion from package.json dependencies (re-add when animations are actually built).

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🔵 LOW — psycopg2-binary is a declared dependency but the app uses asyncpg exclusively

- **Ref:** `clean-dead:DEP-2`  ·  **Effort:** trivial  ·  **Confidence:** 0.82
- **Location:** `backend/pyproject.toml (dependencies)`

**Problem.** pyproject.toml lists psycopg2-binary>=2.9.9, but both the runtime engine (database.py:36 rewrites the URL to postgresql+asyncpg://) and Alembic (alembic/env.py:40 does the same) use asyncpg. A repo-wide grep for psycopg2 finds only one hit — a comment in scripts/test_match_detail.py noting the sync driver 'doesn't work'. The sync driver is genuinely unused, adding a C-extension build dependency to the backend image for nothing.

**Recommendation.** Drop psycopg2-binary from pyproject.toml dependencies unless a sync code path is planned. (python-multipart is also worth a glance — no Form()/UploadFile/OAuth2PasswordRequestForm usage was found — but it is commonly kept defensively; verify before removing.)

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

## ⚪ INFO findings

### ⚪ INFO — Stale TODOs leave a dead alert branch in DashboardBetween

- **Ref:** `clean-dead:CLEAN-1`  ·  **Effort:** small  ·  **Confidence:** 0.9
- **Location:** `frontend/src/lib/components/panini/dashboard/DashboardBetween.svelte:171`

**Problem.** DashboardBetween hardcodes `$: bracketFilled = 0; // TODO: wire to bracket store`. Because bracketFilled is permanently 0, the guarded block `{#if bracketFilled > 0 && bracketFilled < TOTAL_P2_BRACKET_SLOTS}` (line 183) that renders a 'Bracket has unsaved changes' DwAlert can never fire — it is dead UI. A second related TODO sits in DashboardPre.svelte:7. Not a correctness/security bug, but the unsaved-bracket nudge silently never shows on the Between dashboard.

**Recommendation.** Either wire bracketFilled to the unsavedPersistence/phase2 bracket store as the TODO says, or remove the dead {#if} branch so the code doesn't imply a feature that never triggers.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### ⚪ INFO — Commented-out console.warn in bracketResolver swallows invalid-winner cases silently

- **Ref:** `clean-dead:CLEAN-2`  ·  **Effort:** trivial  ·  **Confidence:** 0.85
- **Location:** `frontend/src/lib/utils/bracketResolver.ts:255`

**Problem.** In the bracket advancement validator, an invalid winner (not one of the two teams in the match) returns state unchanged with a commented-out warning: `// console.warn(\`Invalid winner ${winner} for match ${matchNumber}\`)`. This is minor leftover, but it means an invalid bracket input is silently no-op'd with no diagnostic, which could mask a data issue during bracket resolution. Either delete the dead comment or restore a dev-gated warning.

**Recommendation.** Delete the commented-out line (it's dead), or replace with a dev-only `if (dev) console.warn(...)` if silent failures during bracket resolution are worth surfacing.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### ⚪ INFO — Dev/test scripts include a destructive kickoff-shifting fixture (test_match_detail.py) — keep out of prod

- **Ref:** `clean-dead:CLEAN-3`  ·  **Effort:** small  ·  **Confidence:** 0.8
- **Location:** `backend/scripts/test_match_detail.py:1-5; backend/scripts/seed_*.py`

**Problem.** The backend/scripts dir holds calibration/seed tools that are correctly NOT wired into any runtime path (not in docker-compose command, Makefile, or Dockerfile CMD — they are mounted as a volume for manual use). However test_match_detail.py self-describes as 'Temporary test fixture setup' that 'force-locks fixtures by shifting their kickoffs into the recent past' — running it against a populated DB would mutate kickoff times, which directly violates the lock-timing data-integrity invariant. seed_scatter_test.py / seed_test_predictions.py create test users and predictions. None auto-run, so the threat is operator-error, not a shipped bug.

**Recommendation.** Before launch, ensure these scripts are excluded from the production image (they are dev tooling) and add a guard (e.g. refuse to run unless DEBUG/ENV=dev) to test_match_detail.py and the seed scripts so a stray prod invocation can't shift kickoffs or inject fake users into the real pool.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### ⚪ INFO — Shared docker-compose runs the backend with --reload (dev flag)

- **Ref:** `clean-dead:CLEAN-4`  ·  **Effort:** trivial  ·  **Confidence:** 0.7
- **Location:** `docker-compose.yml:63`

**Problem.** The backend service command is `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload` and mounts source as volumes — a development configuration. Per the deployment plan, production fronts the app with nginx/Cloudflare Tunnel and presumably a separate compose/run, so this is likely the dev compose. Flagging only so the launch checklist confirms prod does NOT use --reload (it watches the filesystem and adds overhead/restart-on-write behavior unsuited to prod).

**Recommendation.** Confirm the production deployment uses a non-reload command (the Dockerfile CMD at backend/Dockerfile:22 already omits --reload, which is good). If this single compose file is reused in prod, parameterize the command so --reload is dev-only.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### ⚪ INFO — Seven stub functions are fully dead — kept alive only by their own unit tests

- **Ref:** `clean-dead:DEAD-1`  ·  **Effort:** small  ·  **Confidence:** 0.97
- **Location:** `frontend/src/lib/stubs/panini.ts:105-295`

**Problem.** Of the 9 exports in the stub module, only stubRankTrajectory (used by the leaderboard, see STUB-1) and sparklinePath (used by PnSparkline) have real callers. The other seven — stubSocialSignal, stubHotPick, stubBracketExposure, stubUnderdogStats, stubSteepestClimb, stubBonusHaul, stubLiveScore — have zero non-test, non-comment importers; the migration comments in api/predictions.ts and api/leaderboard.ts confirm they were superseded by real endpoints. They are only referenced by panini.test.ts, which tests all 8 stub data-generators. This is dead code plus its scaffolding tests. Risk is low (dev-only, tree-shaken from prod bundle since nothing imports them), but it is misleading cruft that suggests features are still stubbed when they are wired.

**Recommendation.** Delete the 7 unused stub functions and their interfaces (SocialSignal, HotPick, BracketExposure, UnderdogStats, SteepestClimb, BonusHaul, LiveScore) plus their describe() blocks in panini.test.ts. Keep stubRankTrajectory (or remove it once STUB-1 is fixed) and sparklinePath.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### ⚪ INFO — predictionResult.ts util is dead — profile page reimplements the logic locally

- **Ref:** `clean-dead:DEAD-3`  ·  **Effort:** trivial  ·  **Confidence:** 0.9
- **Location:** `frontend/src/lib/utils/predictionResult.ts:7,27`

**Problem.** predictionResult.ts exports getPredictionResult() and the PredictionResult type, but nothing imports it (importers=0). The one place the concept is used — profile/[userId]/+page.svelte:61 — defines its OWN local predictionResult() function rather than importing the util. This is both dead code and a duplicated-logic smell: the same 'exact|outcome|wrong|pending' classification exists in two places and could drift.

**Recommendation.** Either import getPredictionResult() in the profile page and delete the local copy, or delete predictionResult.ts entirely if the local version is canonical. Don't leave two implementations of the same classification.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### ⚪ INFO — Two purpose-built backend leaderboard endpoints have no frontend callers

- **Ref:** `clean-dead:DEAD-5`  ·  **Effort:** small  ·  **Confidence:** 0.85
- **Location:** `backend/app/api/leaderboard.py:208,221`

**Problem.** GET /leaderboard/snapshots/{user_id} (per-user rank trajectory) and GET /leaderboard/climbers (steepest climbers) are fully implemented and registered, with matching frontend API wrappers getRankTrajectory()/getSteepestClimbers() in api/leaderboard.ts:55,62 — but neither wrapper is called anywhere. The /snapshots/{user_id} endpoint is exactly what STUB-1's leaderboard column should use. The /climbers endpoint comment (lines 226-228) confirms the dashboard 'previously' called it but no longer does. These are authenticated read-only endpoints (no security risk), just unused surface area.

**Recommendation.** Wire /snapshots/{user_id} into the leaderboard (fixes STUB-1). Either restore /climbers in a dashboard 'steepest climb' footer or remove the endpoint + its getSteepestClimbers wrapper if the feature was cut.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---
