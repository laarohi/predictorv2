# Pre-Launch Audit — The Predictor v2

_Conducted May 2026, on the `worktree-ultra` branch, ahead of the private friend-group launch for World Cup 2026._

This is a four-part audit — **security**, **performance/caching**, **dead-code/cleanliness**, and **user-flow** — plus a separate **[design audit](./design.md)** done by driving the live site in a browser. Every fix lives in its own commit so you can cherry-pick exactly what you want into `main`; the [Implementation Map](./IMPLEMENTATION.md) ties each finding to its commit.

## How this was run

- **Code audits**: a 9-dimension parallel agent sweep (5 security sub-areas, backend + frontend performance, dead-code, and UX-flow). Each dimension produced findings cited to `file:line`, and **every finding was then handed to an independent adversarial verifier** instructed to *refute* it against the real code. 79 agents, ~3.1M tokens. The verifier knocked out 12 findings as false positives or over-severe (see [below](#what-was-considered-and-dismissed)) — including a `/agreements`-is-safe claim that turned out to be *wrong* (the endpoint does leak), which is why two finders disagreed and a human read settled it.
- **Design audit**: the running app was driven page-by-page in Chrome (desktop + 375 px mobile) using minted JWTs against the seeded dataset (25 users, 1,590 predictions). See [design.md](./design.md).
- **Threat model**: the realistic adversary is a *curious, technically-capable friend* — someone who might tamper with their score, peek at rivals' predictions before lock, or pollute the pool. Severities are calibrated to that, **not** to a public high-value target. Recommendations are deliberately proportionate (no WAF/SSO/SOC2 theatre).

## Verdict

**The app is in good shape and close to launch-ready.** The architecture is sound: prediction *writes* are correctly scoped to the current user (no IDOR on mutations), admin endpoints uniformly enforce a server-side `is_admin` check, the magic-link flow is textbook, there is no SQL injection surface, and Svelte's auto-escaping closes XSS. There are **no findings that require a redesign**.

What does need attention before you hand the URL to tech-savvy friends clusters into a small number of themes:

1. **Secret hygiene at deploy time** — the JWT signing key has a weak, *committed* default and no startup guard. If it ships unset, tokens (including admin) are forgeable. This is the single highest-impact item and it's a 10-minute fix.
2. **The blind pool has two server-side holes** — bracket picks and the `/agreements` endpoint leak opponents' predictions *before lock*, defeating the core fairness guarantee for the most strategic picks.
3. **Data-integrity hardening** — the prediction tables have no real DB-level uniqueness (a `Config.unique_together` that SQLModel silently ignores), so a double-tapped save can duplicate rows.
4. **Launch gating & operability** — open self-registration with no admin-bootstrap path, and a shared compose file that runs the dev `--reload` server in prod.

Everything else is polish, proportionate hardening, and cleanup.

## Severity dashboard

58 confirmed findings:

| Area | 🔴 Critical | 🟠 High | 🟡 Medium | 🔵 Low | ⚪ Info | Total |
|------|:--:|:--:|:--:|:--:|:--:|:--:|
| [Security](./security.md) | 4 | 1 | 7 | 11 | 2 | **25** |
| [Performance](./performance.md) | 0 | 0 | 2 | 8 | 2 | **12** |
| [Dead code](./dead-code.md) | 0 | 0 | 1 | 4 | 7 | **12** |
| [Flow / UX](./flow.md) | 0 | 0 | 1 | 7 | 1 | **9** |
| **Total** | **4** | **1** | **11** | **30** | **12** | **58** |

## Must-fix before launch (the short list)

| # | Finding | Why it matters | Effort |
|---|---------|----------------|:--:|
| 1 | **Weak committed JWT secret + no startup validation** (`sec-auth:AUTH-1`, `sec-infra:SEC-1`) | A forgeable signing key = full impersonation, including admin. | small |
| 2 | **Bracket blind-pool leak** (`sec-authz:AUTH-1` / `sec-logic:BLI-2`) | Any friend can read everyone's full bracket + champion pick pre-lock. | small |
| 3 | **`/agreements` blind-pool leak** (`sec-input:BLI-1`) | Pick distribution reconstructable by probing before a match locks. | small |
| 4 | **No DB uniqueness on predictions** (`sec-authz:AUTH-2`) | Concurrent/double-tap saves can duplicate → double-counted scores. | small |
| 5 | **Open registration + no admin bootstrap** (`sec-auth:AUTH-2`, `AUTH-3`) | Anyone reaching `/register` joins the live pool; a clean deploy has zero admins. | medium |
| 6 | **Prod runs `--reload` + source bind-mounts** (`sec-infra:SEC-2`) | Prod executes mutable host source on the dev reloader. | small |
| 7 | **Unauthenticated `POST /leaderboard/invalidate`** (`sec-infra:AUTH-3`) | Anyone can force cache rebuilds during a live match. | trivial |
| 8 | **No global 401 handler** (`flow:FLOW-2`) | An expired token leaves users on a half-broken screen; a save can silently fail. | small |

## What was considered and dismissed

The adversarial pass refuted 12 candidate findings. They're worth recording so the decisions are auditable:

- **Score *breakdowns* are exposed for any user** (`BLI-3`, `AUTH-4`) — **not a leak**: point breakdowns are inherently public in a leaderboard competition; it's *predictions* that must stay blind, and those are gated.
- **bcrypt 72-byte truncation** (`AUTH-9`) — not exploitable at this scale; passwords are `>=8` and human-chosen.
- **Server goal cap (20) looser than UI cap (15)** (`INJ-4`, `BLI-5`) — cosmetic, not a vulnerability.
- **`DATABASE_PASSWORD` defaults to `predictor`** (`SEC-7`) — DB is bound to `127.0.0.1` and not internet-exposed; covered by the same prod-env checklist as the JWT secret.
- **Several "N+1" claims** (`PERF-4`, `PERF-5`, `PERF-10`, the 1 s wizard ticker) — verified as either not fanning out as claimed, or on trivially small tables, or already cheap.
- **`ssr=false` slows first paint** (`PERF-7`) — true but a deliberate SPA choice; addressed instead by adding a splash (`FLOW-5`).

Full reasoning for every confirmed and refuted finding is preserved in [`_raw-findings.json`](./_raw-findings.json).

## Documents

- **[security.md](./security.md)** — 25 findings across auth, authorization/blind-pool, input validation, infra/config, and business-logic integrity.
- **[performance.md](./performance.md)** — 12 findings on leaderboard caching/recompute, indexes, and frontend fetch/poll behaviour.
- **[dead-code.md](./dead-code.md)** — 12 findings: unused modules, deps, stubs, and dev→prod cleanliness.
- **[flow.md](./flow.md)** — 9 findings on the user journey, navigation, error/empty states.
- **[design.md](./design.md)** — page-by-page visual audit (desktop + mobile).
- **[IMPLEMENTATION.md](./IMPLEMENTATION.md)** — every finding → status (Fixed / Documented / Deferred) → commit.
