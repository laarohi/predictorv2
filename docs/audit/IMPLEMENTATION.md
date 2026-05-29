# Implementation Map

Every confirmed finding → status → commit. **Status legend:** ✅ Fixed · 📝 Documented (no code change — judgment call, recorded with rationale) · ⏭️ Deferred (intentionally not pre-launch).

Each fix is an isolated commit so you can cherry-pick into `main`. **24 fix commits**; the remainder are documented/deferred with rationale below.

All commits keep the suites green: **backend pytest** (325 passing, +20 new) · **svelte-check** (0 errors) · **vitest** (122 passing).

## ✅ Fixed

| Finding(s) | Severity | What changed | Commit |
|---|---|---|---|
| `sec-auth:AUTH-1`, `sec-infra:SEC-1`, `SEC-8` | critical | JWT secret strength validator (fail-closed in prod) + required compose var + `.env.example` | `3c6534f` |
| `sec-authz:AUTH-1` / `sec-logic:BLI-2` | critical/high | Blind-pool gate on bracket picks in `GET /users/{id}/predictions` | `6124552` |
| `sec-input:BLI-1` | critical | Gate `/predictions/agreements` behind match lock | `84107c8` |
| `sec-infra:AUTH-3`, `perf-backend:PERF-2`, `PERF-9` | medium | Admin-only invalidate/refresh + single-flight cache rebuild + per-process cache note | `3ddc581` |
| `sec-logic:BLI-4` | low | Live trajectory point dated in UTC | `f897439` |
| `sec-authz:AUTH-2` | medium | DB-level `UNIQUE` constraints on prediction tables (+ migration) | `83626a0` |
| `sec-auth:AUTH-5`, `sec-infra:SEC-4`, `SEC-6` | medium/low | OAuth token in URL fragment (not query) + generic errors + canonical redirect base | `80e1140` |
| `sec-auth:AUTH-6` | low | No account enumeration on magic-link request | `10ad772` |
| `sec-input:INJ-1` (partial), `INJ-2`, `INJ-3` | low | Schema-level length/batch caps on predictions & bonus | `9f0afaf` |
| `sec-auth:AUTH-2`, `AUTH-3` | medium | Admin bootstrap (`ADMIN_EMAILS`) + registration toggle + `make_admin` script | `9fe51c1` |
| `perf-backend:PERF-8` | low | Scheduler reuses the shared DB engine | `0d6ac40` |
| `clean-dead:DEP-2` | low | Drop unused `psycopg2-binary` | `19755e6` |
| `sec-infra:SEC-5` | low | nginx Referrer-Policy + CSP/HSTS guidance | `1ba3247` |
| `sec-infra:SEC-2`, `clean-dead:CLEAN-4` | medium/info | Prod compose override (no `--reload`) + Makefile wiring | `c0d7d26` |
| `sec-infra:SEC-3` | medium | Per-account login brute-force throttle | `11f8b14` |
| `flow:FLOW-2` | medium | 401 → clear session + bounce to `/login` | `986b948` |
| `clean-dead:DEAD-2`, `DEAD-4`, `DEP-1` | low | Remove dead `flags.ts`, `DwPredictionNudge`, `svelte-motion` | `f35c3e9` |
| `STUB-1`, `flow:FLOW-6` | medium/low | Remove fabricated trend sparkline + hardcoded "available" stat | `4c9d4c3` |
| `flow:FLOW-3` | low | Correct pre-tournament match/bonus counts (interpolated) | `b0af8dc` |
| `flow:FLOW-1` | low | Account/logout access in the mobile bottom nav (`user` icon) | `6a7d948` |
| `perf-frontend:PERF-2` | low | Leaderboard poll no longer resets phase tab / flashes loading | `802a99c` |
| `clean-dead:CLEAN-2`, `flow:FLOW-4` | info/low | Drop dead comment; correct stale lock-window comment | `45aefb6` |
| `clean-dead:DEAD-1` | info | Remove dead Panini stub generators (+ their tests) | `129e0f8` |
| `flow:FLOW-5` | low | Branded splash on cold load instead of blank screen | `f718449` |

## 📝 Documented (judgment call, no code change)

- **`sec-auth:AUTH-7`** (Google linking flips an email user to GOOGLE provider) — acceptable at hobby scale per the finding; an edge case requiring a user to both have a password and later sign in with Google on the same email.
- **`sec-auth:AUTH-8`** (stateless 7-day JWT, no server-side revocation) — the finding itself rates this acceptable. `is_active` deactivation is already checked on every request (a working revocation lever). Shortening the lifetime is a UX/security tradeoff left to you.
- **`sec-infra:SEC-9`** (no backend lockfile) — recommend committing a resolved lockfile + periodic `pip-audit`; cheap insurance, not launch-blocking.
- **`perf-backend:PERF-7`** (composite indexes) — negligible at this scale (104 fixtures / ~1,590 rows → microsecond seq scans), and the hot `(user_id, fixture_id)` pair is **already indexed** by the unique constraint added in `83626a0`. Revisit if the dataset grows.
- **`clean-dead:DEAD-5`** (two unused leaderboard endpoints) — `/snapshots/{user_id}` is the intended wiring target for the real trend sparkline (STUB-1 follow-up), so kept. Removing backend endpoints is riskier than leaving unused ones; no action taken.
- **`clean-dead:CLEAN-3`** (dev scripts shipped in the image) — scripts require explicit invocation. Recommended mitigation: drop the `./backend/scripts` bind-mount in `docker-compose.prod.yml` (noted in that file). `FLOW-4` also notes **CLAUDE.md still says "5 minutes"** for the lock window (configured value is 15) — update on merge (worktree policy: no CLAUDE.md edits here).

## ⏭️ Deferred (intentionally not pre-launch — "nothing experimental")

- **`perf-backend:PERF-1`** (leaderboard cold-rebuild N+1) — the highest-value perf item, but the fix refactors `calculate_user_points` (the scoring core) and carries correctness risk. The acute concern — a cache stampede / abuse during a live match — is already removed by the single-flight lock + admin-only refresh (`3ddc581`). At 30 users with a 30s cache, a single cold rebuild is tolerable. Best done post-launch with golden parity tests (see `feedback_frontend_backend_logic_parity`).
- **`perf-backend:PERF-3`** (redundant standings recompute in the group-position bonus) — same hot path as PERF-1; defer together.
- **`perf-backend:PERF-6`** (receipt batch runs inline in the scheduler tick) — works serially for 30 users; decoupling is robustness polish. Note: a slow Resend could delay a match-day score tick — acceptable at this scale.
- **`perf-frontend:PERF-1`** (≈260 flag SVGs eagerly inlined) — real bundle weight, but acceptable for 30 users on normal connections. Converting to lazy `import()` makes flag rendering async (regression risk); do it as a tested follow-up.
- **`perf-frontend:PERF-3`** (per-navigation refetch) — loading flash on nav; a store freshness-guard is follow-up polish.
- **`perf-frontend:PERF-4`** (full bracket mounts all flags) — low priority; mostly addressed by PERF-1-fe; the bracket is small and fixed.
- **`perf-frontend:PERF-6`** (poll runs on hidden tabs) — optional micro-optimization.
- **`flow:FLOW-7`** (Phase II save copy/dirty state) and **`flow:FLOW-8`** (actionable wizard save errors) — real UX refinements inside the 1,546-line predictions wizard; both need visual verification (see the design-audit blocker) before changing.
- **`flow:FLOW-9` / `clean-dead:CLEAN-1`** (between-phases bracket progress hardcoded to 0) — info-level, on the transient between-phases dashboard. Wiring it requires the Phase 2 bracket store loaded in that view; implementing it blind (no browser) risks showing **wrong** progress, which is worse than the current honest TODO.
- **`clean-dead:DEAD-3`** (`predictionResult.ts` duplicated by the profile page) — info; cosmetic dedupe, no prod impact.
- **`sec-auth:AUTH-4`** (Google OAuth has no CSRF `state`) — low impact for a private friend pool (login-CSRF worst case is minor here). Enabling `fastapi-sso` state needs `SessionMiddleware` and can't be verified end-to-end without Google credentials; the risk of breaking login at launch outweighs the benefit. Revisit post-launch.

## Design audit

⚠️ The **visual** design pass (page-by-page screenshots + interaction via Chrome MCP) is **blocked** — the Claude-in-Chrome extension was not connected during this session. A code-level design review is in [design.md](./design.md); the visual pass is ready to run the moment the extension connects.
