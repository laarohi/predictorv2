# Implementation Map

Every confirmed finding → status → commit. **Status legend:** ✅ Fixed · 📝 Documented (no code change — judgment call, recorded with rationale) · ⏭️ Deferred (gated on the visual pass or deliberately out-of-scope for launch).

Each fix is an isolated commit so you can cherry-pick into `main`. **31 fix commits.**

All commits keep the suites green: **backend pytest 326** (+21 new) · **svelte-check 0 errors** · **vitest 122**.

## ✅ Fixed (31 commits)

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
| `perf-backend:PERF-7` | low | Index `fixtures.status` + `fixtures.stage` (+ migration) | `6e18cd7` |
| `clean-dead:DEAD-3` | info | Remove dead `predictionResult.ts` util | `f6004a2` |
| `perf-backend:PERF-1`, `PERF-3` | medium/low | Precompute leaderboard globals once per build (no per-user N+1) + parity test | `563741b` |
| `sec-auth:AUTH-7` | low | Don't downgrade a password user to Google-only on account linking | `b67feab` |
| `clean-dead:CLEAN-3` | info | Guard the kickoff-shifting dev script behind DEBUG | `edd7712` |
| `perf-frontend:PERF-6` | info | Pause leaderboard poll on hidden tabs | `0e47f32` |

## 📝 Documented (judgment call, no code change)

- **`sec-auth:AUTH-8`** (stateless 7-day JWT, no server-side revocation) — the finding rates this acceptable at scale. `is_active` deactivation is already checked on every request (a working revocation lever). Shortening the 7-day lifetime would *hurt* UX for friends checking scores daily, so it's left as an operator-tunable env value (`jwt_access_token_expire_minutes`).
- **`sec-infra:SEC-9`** (no backend lockfile) — recommend committing a resolved lockfile + periodic `pip-audit`; the finding itself marks this low-priority for 30 users. Changing the build to install from a lock is post-launch infra.
- **`clean-dead:DEAD-5`** (two unused leaderboard endpoints) — `/snapshots/{user_id}` is the intended wiring target for a real trend sparkline (the STUB-1 follow-up), so it's kept. Removing backend endpoints is riskier than leaving unused ones.

## ⏭️ Deferred — gated on the visual pass / out-of-scope for a safe launch

These split into two buckets, both of which respect your "nothing crazy experimental as we are about to launch" constraint:

**Need eyes-on (same blocker as the design audit — implement + verify together once the browser is connected):**
- **`flow:FLOW-7`** (Phase II save copy / dirty-state clarity) and **`flow:FLOW-8`** (actionable wizard save errors) — UX changes inside the 1,546-line predictions wizard; changing copy/layout blind risks regressions.
- **`flow:FLOW-9` / `clean-dead:CLEAN-1`** (between-phases bracket progress hardcoded to 0) — wiring it needs the Phase 2 bracket store loaded in that view; implementing blind risks showing *wrong* progress, worse than the honest TODO.
- **`perf-frontend:PERF-1`** (≈260 flag SVGs eagerly inlined) and **`perf-frontend:PERF-4`** (full bracket mounts all flags) — converting flags to async `import()` changes rendering across the app; needs visual verification. Acceptable bundle weight for 30 users on normal connections meanwhile.
- **`perf-frontend:PERF-3`** (per-navigation refetch flash) — a store freshness-guard could introduce staleness; needs visual confirmation of the "no flash, no stale data" outcome.

**Deliberate launch-stability calls:**
- **`sec-auth:AUTH-4`** (Google OAuth has no CSRF `state`) — enabling `fastapi-sso` state needs `SessionMiddleware` and can't be verified end-to-end without Google credentials. Low impact for a private friend pool (login-CSRF worst case is minor here); the risk of breaking Google login at launch outweighs the benefit. Revisit post-launch.
- **`perf-backend:PERF-6`** (receipt batch runs inline in the scheduler tick) — works serially for 30 users; decoupling is robustness polish, not launch-blocking.

## Design audit

⚠️ The **visual** design pass (page-by-page screenshots + interaction via Chrome MCP) is **blocked** — the Claude-in-Chrome extension was not connected during this session. A code-level design review is in [design.md](./design.md); the visual pass is ready to run the moment the extension connects, at which point the "need eyes-on" deferrals above can be implemented and verified in the same pass.
