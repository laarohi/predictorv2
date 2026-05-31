# Implementation Map

> **Note (2026-05-31):** `worktree-ultra` was rebased onto `main`, which
> **rewrote every commit SHA below.** The commit *messages* are unchanged —
> match by message, not hash. The branch now fast-forwards into `main`
> (see [MERGE-NOTES.md](./MERGE-NOTES.md)).

Every confirmed finding → status → commit. **Status legend:** ✅ Fixed · 📝 Documented (judgment call, recorded with rationale).

Each fix is an isolated commit so you can cherry-pick into `main`. **40 fix commits — all 58 confirmed findings fixed, plus `DESIGN-1` from the visual design audit.** All four audits are complete (including the visual design pass — see bottom).

All commits keep the suites green: **backend pytest 329** (+24 new) · **svelte-check 0 errors** · **vitest 122**.

## ✅ Fixed

### Security (criticals first)

| Finding(s) | Sev | What changed | Commit |
|---|---|---|---|
| `sec-auth:AUTH-1`, `sec-infra:SEC-1`, `SEC-8` | critical | JWT secret strength validator (fail-closed in prod) + required compose var | `3c6534f` |
| `sec-authz:AUTH-1` / `sec-logic:BLI-2` | crit/high | Blind-pool gate on bracket picks in `GET /users/{id}/predictions` | `6124552` |
| `sec-input:BLI-1` | critical | Gate `/predictions/agreements` behind match lock | `84107c8` |
| `sec-authz:AUTH-2` | medium | DB-level `UNIQUE` constraints on prediction tables (+ migration) | `83626a0` |
| `sec-auth:AUTH-2`, `AUTH-3` | medium | Admin bootstrap (`ADMIN_EMAILS`) + registration toggle + `make_admin` | `9fe51c1` |
| `sec-auth:AUTH-5`, `SEC-4`, `SEC-6` | med/low | OAuth token in URL fragment + generic errors + canonical redirect base | `80e1140` |
| `sec-auth:AUTH-6` | low | No account enumeration on magic-link request | `10ad772` |
| `sec-input:INJ-1/2/3` | low | Schema-level length/batch caps on predictions & bonus | `9f0afaf` |
| `sec-infra:SEC-3` | medium | Per-account login brute-force throttle | `11f8b14` |
| `sec-infra:SEC-2`, `CLEAN-4` | med/info | Prod compose override (no `--reload`) + Makefile wiring | `c0d7d26` |
| `sec-infra:SEC-5` | low | nginx Referrer-Policy + CSP/HSTS guidance | `1ba3247` |
| `sec-auth:AUTH-4` | low | CSRF `state` on the Google OAuth flow | `a0e36a8` |
| `sec-auth:AUTH-7` | low | Linking no longer downgrades a password user to Google-only | `b67feab` |
| `sec-auth:AUTH-8` | low | JWT `token_version` revocation + `/me/logout-all` (+ migration) | `a918592` |
| `sec-infra:SEC-9` | info | Pinned backend lockfile + build from it (verified) | `e6ca660` |

### Leaderboard / performance

| Finding(s) | Sev | What changed | Commit |
|---|---|---|---|
| `sec-infra:AUTH-3`, `perf:PERF-2`, `PERF-9` | medium | Admin-only invalidate/refresh + single-flight cache rebuild | `3ddc581` |
| `sec-logic:BLI-4` | low | Live trajectory point dated in UTC | `f897439` |
| `perf-backend:PERF-1`, `PERF-3` | med/low | Precompute leaderboard globals once per build (no per-user N+1) + parity test | `563741b` |
| `perf-backend:PERF-7` | low | Index `fixtures.status` + `fixtures.stage` (+ migration) | `6e18cd7` |
| `perf-backend:PERF-8` | low | Scheduler reuses the shared DB engine | `0d6ac40` |
| `perf-backend:PERF-6` | low | Score sync runs before the receipt batch in the tick | `6827acd` |
| `perf-frontend:PERF-2` | low | Leaderboard poll keeps phase tab / no loading flash | `802a99c` |
| `perf-frontend:PERF-3` | low | Cache fixtures across navigations (freshness guard) | `6cb2772` |
| `perf-frontend:PERF-6` | info | Pause leaderboard poll on hidden tabs | `0e47f32` |

### Flow / UX

| Finding(s) | Sev | What changed | Commit |
|---|---|---|---|
| `flow:FLOW-2` | medium | 401 → clear session + bounce to `/login` | `986b948` |
| `STUB-1`, `flow:FLOW-6` | med/low | Remove fabricated trend sparkline + hardcoded "available" stat | `4c9d4c3` |
| `flow:FLOW-3` | low | Correct pre-tournament match/bonus counts (interpolated) | `b0af8dc` |
| `flow:FLOW-1` | low | Account/logout access in the mobile bottom nav | `6a7d948` |
| `flow:FLOW-4`, `clean:CLEAN-2` | low/info | Correct stale lock-window comment; drop dead comment | `45aefb6` |
| `flow:FLOW-5` | low | Branded splash on cold load instead of blank screen | `f718449` |
| `flow:FLOW-9`, `clean:CLEAN-1` | info | Wire between-phases bracket progress to real data | `08bacea` |
| `flow:FLOW-7`, `FLOW-8` | low | Unify Phase II save + surface save-error detail | `e3ea3e3` |
| `DESIGN-1` (visual audit) | high* | Admins no longer bounced off `/admin` on cold load (auth-guard race) | `c2f62b7` |

<sub>*high-impact for admins — surfaced only by loading the page; see design.md.</sub>

### Dead code / cleanliness

| Finding(s) | Sev | What changed | Commit |
|---|---|---|---|
| `clean-dead:DEAD-2/4`, `DEP-1` | low | Remove dead `flags.ts`, `DwPredictionNudge`, `svelte-motion` | `f35c3e9` |
| `clean-dead:DEAD-1` | info | Remove dead Panini stub generators (+ tests) | `129e0f8` |
| `clean-dead:DEP-2` | low | Drop unused `psycopg2-binary` | `19755e6` |
| `clean-dead:DEAD-3` | info | Remove dead `predictionResult.ts` util | `f6004a2` |
| `clean-dead:DEAD-5` | info | Remove unused trajectory/climbers endpoints + wrappers | `7eee194` |
| `clean-dead:CLEAN-3` | info | Guard the kickoff-shifting dev script behind DEBUG | `edd7712` |
| `perf-frontend:PERF-1`, `PERF-4` | low | Lazy-load flag SVGs (code-split) instead of inlining all ~270 | `0c43c8e` |

_All 58 confirmed findings are now fixed in code — nothing deferred. The flag-bundle fix (`PERF-1/4-fe`) became safe once it was clear both flag consumers degrade gracefully to a placeholder while a flag's chunk loads; verified with a production build._

## Design audit — complete

✅ The visual pass is **done**. With the Claude-in-Chrome extension unavailable, every page was captured at desktop + mobile via headless Chrome (Playwright `channel: 'chrome'`) with a real admin session, and reviewed. Findings + per-page notes are in [design.md](./design.md). The verdict: the Panini design is polished and launch-ready; the pass found one real bug (`DESIGN-1`, fixed above) and a short list of low-priority polish (chiefly the 104-fixture results scroll).

One note for merge: `CLAUDE.md` still says predictions lock "5 minutes" before kickoff, but the configured/enforced value is **15** (`config/worldcup2026.yml` → `get_lock_minutes` default 15) — correct it on `main` (left untouched here per worktree policy).
