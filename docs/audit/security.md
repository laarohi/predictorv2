# Security Audit

> Part of the pre-launch audit. See [README](./README.md) for methodology and the [Implementation Map](./IMPLEMENTATION.md) for fix status.

**25 findings:** 4 critical · 1 high · 7 medium · 11 low · 2 info

## What this area does well

- Magic-link service is textbook: secrets.token_urlsafe(32) entropy, sha256 hash at rest (raw token never stored or logged), single-use via used_at set in the same transaction as lookup (concurrent-verify safe), 15-min TTL, prior-unused-token revocation, and a 3-per-15-min rate limit (magic_link.py:88-329).
- JWT verification pins the algorithm allowlist to [settings.jwt_algorithm] (HS256) in jwt.decode (dependencies.py:69), closing the classic alg=none / RS256→HS256 confusion attacks.
- JWT expiry is set on every token (create_access_token, dependencies.py:49) and validated by python-jose's default exp check; get_current_user also re-checks is_active on every request (dependencies.py:82-83), so deactivated users are locked out immediately despite stateless tokens.
- Passwords are hashed with bcrypt + per-hash gensalt() (dependencies.py:33-38); login and password-change use constant-comparison checkpw and never echo password state.
- Login returns an identical generic 'Invalid email or password' for both unknown-user and wrong-password (auth.py:86-96), avoiding credential-stuffing enumeration on the password path.
- All /api/admin/* routes consistently depend on AdminUser (admin.py), and the UserCreate schema exposes only email/name/password — no mass-assignment of is_admin/is_active/paid on registration.
- Password change correctly returns 403 for non-EMAIL (Google) accounts and requires the current password (auth.py:206-218).
- All prediction mutations (predictions.py: PUT /matches/{id}, POST /matches/batch, PUT /bracket, POST /bonus) derive ownership from current_user.id and filter both reads and writes by it — a client cannot target another user's row by passing a foreign user_id; there is no IDOR on any write path.
- Request schemas are tight against mass assignment: MatchPredictionCreate/Update, BracketPredictionUpdate, BonusPredictionUpdate, ScoreUpdate and UserCreate contain only the safe fields — none accept paid, is_admin, is_active, points, score, or user_id, so a client cannot escalate privilege or set their own points via a request body (schemas/prediction.py, schemas/auth.py, schemas/score.py).
- Every admin endpoint (admin.py users list, toggle admin/active/paid, phase ops, scores/sync, bonus answers, audit history) and every admin mutation in fixtures.py and scores.py uses the AdminUser dependency, which enforces current_user.is_admin server-side (dependencies.py:102-111) — authorization is not merely hidden in the frontend nav.
- The audit-log endpoints (admin/users/{user_id}/history) are correctly behind AdminUser, so a non-admin friend cannot pull another player's prediction-change history for dispute snooping.
- The match-score blind pool is enforced on the server with the correct lock semantics: get_community_predictions (predictions.py:585) and the match-prediction loop in get_user_predictions (users.py:213-217) both 403/skip until get_fixture_lock_view reports locked or the fixture is finished, including the Phase-1-deadline rule for group fixtures.
- The /predictions/agreements endpoint is carefully designed to leak nothing pre-lock: it returns only aggregate counts computed relative to the caller's own pick, never another user's individual prediction (predictions.py:826-881).
- Phase separation is respected on the bracket write path: the destructive delete-then-insert in PUT /bracket is scoped to (user_id, current_phase), so a Phase 2 rewrite cannot wipe Phase 1 picks (predictions.py:527-531).
- No raw SQL anywhere: every query in services and api uses SQLModel select()/delete()/update() with bound parameters; grep for text(), .execute("..."), f"SELECT", .format(), and exec_driver_sql found zero query-building occurrences. SQL injection is not reachable.
- Blind pool is enforced server-side, not just in the UI: get_community_predictions (api/predictions.py:585) and get_user_predictions (api/users.py:213-217) both check get_fixture_lock_view / MatchStatus.FINISHED before returning any other user's picks.
- All {@html} Svelte sinks were traced to safe sources: DwHighlights/DwFunnelHero/DwMemorialStrip receive server-derived integers from the caller's own /me/highlights data (e.g. user_pick = f"{home}-{away}"), PnFlag renders a bundled static SVG keyed by team code, and DwChampionPodium renders user names via plain {name} (auto-escaped), not @html.
- Magic-link HTML email (services/magic_link.py:_esc) and the Phase 1 receipt email (services/receipts.py:_esc) HTML-escape every user-supplied field (user.name, team names, bonus answers) before interpolating into the HTML body.
- No open redirect: the Google OAuth callback redirects to settings.cors_origins[0] (server config) and the magic-link URL is built from settings.public_base_url — neither uses a user-supplied next/returnTo/redirect parameter.
- Email header injection is not possible: subjects are static server strings, recipients are validated EmailStr, and Resend is called with a JSON body (no SMTP header concatenation).
- Score write path is bounded server-side: MatchPredictionCreate/Update enforce Field(ge=0, le=20) and ScoreUpdate enforces ge=0, so negative and absurdly large goal counts are rejected at the schema layer regardless of the UI cap.
- JWT uses a fixed single-element algorithm list (algorithms=[settings.jwt_algorithm], HS256) so alg=none confusion is not possible, and jwt_secret_key is a required setting with no insecure default. yaml.safe_load is used for config; no eval/exec/pickle/template-injection patterns exist in the backend.
- No .env committed; only backend/.env.example is tracked. .gitignore correctly ignores .env, *.env, *.pem, *.key, credentials.json, *.db.
- DB and backend host ports bind to loopback only ("127.0.0.1:5432:5432", "127.0.0.1:8000:8000") in docker-compose.yml, so Postgres/backend aren't directly reachable from the network even before the Cloudflare Tunnel.
- FastAPI /api/docs and /api/redoc are gated behind settings.debug (main.py:36-37), so OpenAPI is not exposed when DEBUG is false.
- Every admin endpoint is uniformly protected with the AdminUser dependency (admin.py — _admin: AdminUser on all 15 routes); no admin operation is reachable without is_admin.
- Magic-link auth is well designed: secrets.token_urlsafe(32), sha256-hashed at rest, 15-min TTL, single-use with atomic used_at, prior-token revocation, and a 3-per-15min per-account send cap (magic_link.py).
- Passwords are bcrypt-hashed with per-hash salt (dependencies.py:33-38); registration enforces min_length=8 (schemas/auth.py).
- nginx sets X-Content-Type-Options: nosniff, X-Frame-Options: SAMEORIGIN, has per-real-IP rate limiting (limit_req_zone $binary_remote_addr 10r/s burst=20) and correctly recovers the real client IP from CF-Connecting-IP only from private ranges (nginx.conf:31-40).
- CORS allow_origins is an explicit env-driven allowlist (no "*"), which is the correct pairing with allow_credentials=True.
- Daily encrypted offsite DB backups to R2 with 14-day retention and fail-loud cron semantics (ops/backup-db.sh).
- Write-path lock is enforced server-side with utc_now() on every mutation endpoint (update_match_prediction, batch_update_predictions, update_bracket_predictions, save_bonus_predictions) — never trusts client time, and there is no backdating/replay vector because lock state is recomputed from fixture.kickoff each request (predictions.py:212-223, 311-327, 490-499, 694-698).
- The phase1_deadline-vs-per-match-T-lock gap is explicitly understood and closed: group fixtures lock en-masse at phase1_deadline so a user cannot edit a group score in the window between the Phase 1 deadline and that match's own kickoff (locking.py:86-120, predictions.py:208-216), with dedicated regression tests in test_predictions_lock_guards.py.
- Prediction phase is derived from the immutable fixture.stage, not the mutable global get_current_phase, preventing a Phase-1 group prediction from being mis-tagged Phase 2 (predictions.py:234-242) — and this is regression-tested (TestPredictionPhaseDerivation).
- Phase 1 and Phase 2 predictions are stored and queried separately throughout (bracket rewrite deletes/inserts scoped to one phase only — predictions.py:525-531; scoring sums into independent PhaseBreakdown buckets — scoring.py:636-666).
- Scoring is entirely server-side and deterministic: points come only from stored MatchPrediction/TeamPrediction/Score/BonusAnswer rows; the rarity/hybrid bonus is computed from per-fixture predictor counts the server tallies itself (scoring.py:618-622, 692-710); there is no endpoint that lets a user submit or influence their own point total.
- External score ingestion and all score/phase mutations are admin- or scheduler-only (AdminUser dependency on /scores/sync, /scores PUT, phase2 activate/deactivate, phase1 deadline; dependencies.py:102-111). A normal user cannot trigger sync or spoof a result.
- Score sync and snapshot writes are idempotent (sync_scores_once re-run yields zero new rows; take_daily_snapshots uses ON CONFLICT DO NOTHING on a per-user-per-day unique constraint — snapshots.py:64-72), so repeated scheduler ticks cannot corrupt or double-count.
- The UTC-aware-datetime invariant is respected on every business-logic path: utc_now() is used for all lock comparisons, token expiry, and timestamps; the only datetime.now()/date.today() occurrences are either equivalent (tz-aware UTC) or cosmetic.
- Score.outcome correctly resolves knockout results via penalties then extra-time then regular time (score.py:49-71), so KO advancement and outcome scoring honour the real winner.

## Assessment by sub-dimension

### Authentication & Session Security

The core JWT mechanics are sound for a 30-person hobby app: signing/verification is pinned to HS256 with an explicit algorithms allowlist (no "none"-alg risk), expiry is enforced, passwords use bcrypt, and the magic-link flow is genuinely well-built (crypto-random token, sha256-at-rest, single-use, 15-min TTL, prior-token revocation, rate limiting, no raw-token logging). Admin endpoints uniformly require AdminUser. The real exposures are concentrated in three areas. (1) Registration is fully open self-signup with no invite/approval gate and the active competition is resolved globally — so anyone who can reach /api/auth/register joins the live prediction pool; combined with there being no admin-bootstrap path in the repo, the launch posture and first-admin story are undefined. (2) The JWT secret has a weak, well-known committed default in both docker-compose and .env.example with zero startup validation — if it ships unset, every token (including is_admin) is forgeable, which is a direct cheat/takeover vector. (3) Google OAuth runs with no CSRF state parameter (fastapi-sso defaults to requires_state=False and the code never opts in), and the callback returns the JWT in a URL query string. Token storage in localStorage is the standard SvelteKit tradeoff and acceptable here, but worth noting. Severity is calibrated to the friend-group threat model: the open-registration + weak-secret combination is what could actually let a curious friend cheat or impersonate, so those lead.

### Authorization, IDOR & Blind-Pool Enforcement

Authorization is, with two notable exceptions, in good shape for a 30-person private app. Every prediction write path (match single/batch, bracket rewrite, bonus) is scoped server-side to current_user.id and never trusts a user_id from the body or path — there is no IDOR on mutations, and no mass-assignment surface (paid/is_admin/points/user_id are absent from every request schema). All admin operations in admin.py, plus admin mutations in fixtures.py and scores.py, are gated by a real AdminUser dependency that checks current_user.is_admin server-side, not just hidden from the nav. The match-score blind pool is enforced correctly on the server in two places (predictions /matches/{id}/community and users /{id}/predictions for match rows). HOWEVER, there is one genuine server-side blind-pool hole that lets a curious friend read every opponent's full bracket (group winners, knockout advancement, predicted champion) before Phase 1 locks: the bracket_summary half of GET /users/{user_id}/predictions returns ALL of the target user's TeamPredictions with no lock/visibility check, and the profile page renders them under a "Locked predictions" label. Secondary issues: an unauthenticated POST /leaderboard/invalidate, and the absence of any DB-level uniqueness on prediction rows (the model's Config.unique_together is a SQLModel no-op), which threatens the 100%-integrity invariant under concurrent batch writes.

### Input Validation, Injection & XSS

The backend is in good shape against injection and XSS for a 30-person hobby app. Every DB query uses SQLModel/SQLAlchemy expression builders with bound parameters — there is no raw SQL, no text(), no f-string/format-built queries anywhere, so SQL injection is not reachable. The frontend uses Svelte, which auto-escapes all {expression} interpolation; the dozen {@html} sinks I traced are all fed either static template strings, server-derived integers (the caller's own data), or a bundled static SVG map — none render another user's free-text (name, bonus answer). User-supplied strings that DO reach HTML email bodies are escaped via _esc. OAuth/magic-link redirect targets come from server config, not user-supplied next/returnTo params, so there's no open redirect. The real gaps are write-path validation completeness on the two free-text prediction surfaces: the bracket endpoint stores arbitrary unbounded team/stage strings with no allowlist and no list-size cap, and the bonus endpoint stores unbounded-length answers with no batch-size cap. These are data-integrity / storage-abuse issues, not cheats — advancement scoring gates on teams that actually progressed, so forged team/stage values earn zero points. Score inputs ARE bounded server-side (0-20), so negative/huge goal values are rejected; the only nit is the cap is 20 while the UI says 15.

### Infrastructure, Config, Headers & Secrets

For a 30-friend hobby app behind Cloudflare Tunnel, the infra/config posture is mostly reasonable: secrets come from env (no committed .env, sane .gitignore), DB and backend ports bind to 127.0.0.1 only, /docs is gated behind DEBUG, admin endpoints are uniformly AdminUser-gated, magic-link tokens are crypto-random/hashed/single-use/rate-limited, and nginx sets nosniff + X-Frame-Options + per-IP rate limiting with correct real-IP recovery. The most serious issues are operational/launch-time, not deep design flaws: the single docker-compose.yml runs the backend with `--reload` + source bind-mounts even under the `prod` profile (dev server in prod), and JWT_SECRET_KEY / DATABASE_PASSWORD silently fall back to well-known hardcoded defaults if the prod .env omits them — a JWT secret of "super-secret-dev-key-change-in-prod" lets any friend forge an admin token, which is the single highest-impact finding for this threat model. Secondary: the email/password /login and /magic-link/verify paths have no per-account brute-force throttle (only a coarse 10 r/s per-IP nginx limit and a 3-per-15min email-send cap), Google-OAuth exception text and magic-link error detail are reflected to the client, and there's no HSTS/CSP/Referrer-Policy. None of the gaps are enterprise-overkill flags; they map directly to cheat/takeover/snoop risks or launch reliability.

### Business-Logic Integrity (locking, phases, scoring, time)

The core write-path locking model is genuinely well built: every prediction-mutation endpoint (single match, batch, bracket rewrite, bonus) re-checks the lock server-side using utc_now() before writing, derives prediction phase from the immutable fixture.stage rather than mutable global state, and the phase1-deadline-vs-per-match-T-lock gap is explicitly closed and regression-tested (test_predictions_lock_guards.py). Phase 1/2 storage and queries are cleanly separated, Phase 2 activation and all score mutation are admin-gated, scoring is computed 100% server-side from DB rows with no user-influenceable input, and the rarity bonus uses per-fixture predictor counts derived from stored predictions. The UTC-datetime invariant holds across the hot paths. The serious gap is on the READ side of the blind pool: while the dedicated community/profile endpoints correctly gate on lock state, the /predictions/agreements endpoint exposes per-fixture agreement counts for ANY fixture with no lock check, which a technical friend can use to reconstruct other players' un-locked predictions; and the per-user predictions endpoint leaks bracket picks unconditionally even though it gates match predictions. These are the launch-blocking items.

## Findings

## 🔴 CRITICAL findings

### 🔴 CRITICAL — Weak, committed default JWT secret with no startup validation

- **Ref:** `sec-auth:AUTH-1`  ·  **Effort:** small  ·  **Confidence:** 0.95
- **Location:** `backend/app/config.py:28; docker-compose.yml (JWT_SECRET_KEY default); backend/.env.example`

**Problem.** jwt_secret_key is a plain required string with no minimum-length or non-default validation. docker-compose.yml ships `JWT_SECRET_KEY=${JWT_SECRET_KEY:-super-secret-dev-key-change-in-prod}` and .env.example ships `JWT_SECRET_KEY=your-super-secret-key-change-in-production`. If the operator deploys without overriding the env var (easy to forget for a self-hosted hobby app), the HS256 signing key is a publicly known string from this repo. Any tech-savvy friend who recognizes the stack can forge a token with `{"sub": <any user id>, "exp": <future>}` signed with that key and become any user — including minting an is_admin session by pointing sub at an admin user id. This directly enables impersonation, score/paid/admin tampering, and reading everyone's predictions. Because the app boots fine with the weak key, there is no signal that anything is wrong.

**Recommendation.** Add a pydantic field_validator on jwt_secret_key that rejects the known default strings and enforces a minimum length (e.g. >=32 chars / 256 bits), failing app startup if violated. Remove the convenient fallback default in docker-compose.yml (require the var to be set), and in .env.example replace the placeholder with an explicit `# generate: python -c "import secrets;print(secrets.token_urlsafe(48))"` instruction rather than a usable-looking value.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🔴 CRITICAL — Bracket blind pool not enforced: GET /users/{user_id}/predictions leaks every opponent's full bracket before lock

- **Ref:** `sec-authz:AUTH-1`  ·  **Effort:** small  ·  **Confidence:** 0.95
- **Location:** `backend/app/api/users.py:251-275`

**Problem.** get_user_predictions correctly gates each MATCH prediction behind get_fixture_lock_view (lines 213-217), but the bracket_summary it returns immediately afterward queries ALL of the target user's TeamPredictions with no lock or visibility check whatsoever — it selects every row for user_id and buckets them into stages/phase1_stages/phase2_stages. TeamPredictions are the user's bracket picks: group winners/positions, round-of-32 through final advancement, and the predicted tournament champion. Any authenticated friend can call GET /api/users/{any_user_id}/predictions and read a rival's entire bracket (and champion pick) BEFORE the Phase 1 deadline locks, defeating the blind pool for the highest-value, most-strategic predictions in the competition. The frontend profile/[userId] page renders these under a 'Locked predictions' header (profile/[userId]/+page.svelte:132-156), so the leak is directly user-facing, but the curl is just as easy. Endpoint takes OptionalUser, so it is reachable by any logged-in (or, given OptionalUser, even anonymous) caller. This is a direct violation of invariant #3 (blind pool must hold server-side).

**Recommendation.** Apply the same lock gate to bracket picks that the match rows get. The simplest correct rule for a friend pool: only return another user's TeamPredictions once the relevant bracket deadline has passed (Phase 1: is_phase1_locked; Phase 2: is_phase2_bracket_locked), and return the empty/own-only bracket otherwise. When user_id == current_user.id, return their own picks unconditionally. Filter the bracket query by phase + a server-computed 'bracket visible' boolean rather than dumping all rows. Also reconsider whether this endpoint should require CurrentUser instead of OptionalUser.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🔴 CRITICAL — JWT_SECRET_KEY falls back to a public hardcoded default — admin-token forgery if prod .env omits it

- **Ref:** `sec-infra:SEC-1`  ·  **Effort:** trivial  ·  **Confidence:** 0.92
- **Location:** `docker-compose.yml:28`

**Problem.** The backend service sets JWT_SECRET_KEY=${JWT_SECRET_KEY:-super-secret-dev-key-change-in-prod}. The prod stack is launched with this same docker-compose.yml (Makefile deploy: `docker compose --profile prod up -d --build`). If the prod .env beside docker-compose.yml is missing the JWT_SECRET_KEY line (or it's blank/typo'd), the app boots with the well-known literal committed to this public-ish repo. Tokens are HS256 signed with that key (dependencies.py:50). A technically-curious friend who knows or guesses this default can forge a JWT with any `sub` (user id) and is_active=true, then hit admin endpoints once they also know an admin's user id — or simply forge a token for themselves and, combined with SEC-? below, escalate. The signing key is the entire trust anchor for the blind pool, scoring, paid status, and admin ops. This is the single highest-impact misconfiguration for the stated threat model (cheating/tampering/takeover).

**Recommendation.** Remove the `:-super-secret-dev-key-change-in-prod` fallback so a missing JWT_SECRET_KEY fails the container at startup (config.py already declares jwt_secret_key with no default — let that hard-fail propagate). Generate a real secret (e.g. `openssl rand -hex 32`) into the prod .env. Optionally add a startup assertion that rejects any known weak/default value when DEBUG is false.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🔴 CRITICAL — /predictions/agreements leaks pre-lock predictions (blind-pool violation via iterative probing)

- **Ref:** `sec-logic:BLI-1`  ·  **Effort:** small  ·  **Confidence:** 0.92
- **Location:** `backend/app/api/predictions.py:826-881`

**Problem.** The /agreements endpoint returns agrees_exact, agrees_outcome and total for every fixture the caller has predicted, computed across ALL predictions for that fixture — with NO check that the fixture is locked or finished (unlike get_community_predictions and get_user_predictions, which both gate on get_fixture_lock_view). The docstring claims 'revealing them pre-lock cannot leak any other user's prediction', but that is false. The counts are relative to the CALLER's own pick, and the caller can change their own pick and re-query. By sweeping their own home/away score across the plausible range and observing how agrees_exact moves, a technical friend reconstructs the exact-score distribution of all other players before the match locks. Boundary cases leak immediately: if agrees_exact == total, every other player picked the caller's exact score; if agrees_outcome == total, everyone picked the same 1/X/2. With ~30 friends and a small score space this fully defeats the server-side blind pool — the hardest invariant in the threat model.

**Recommendation.** Gate /agreements the same way community/profile endpoints are: for each requested fixture, compute get_fixture_lock_view (and/or status == FINISHED) and only include fixtures that are locked or finished; drop unlocked fixtures from the response. The DwAgreement widget should only need agreement data for matches that have already locked anyway.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

## 🟠 HIGH findings

### 🟠 HIGH — get_user_predictions returns another user's full bracket picks with no lock gate

- **Ref:** `sec-logic:BLI-2`  ·  **Effort:** small  ·  **Confidence:** 0.88
- **Location:** `backend/app/api/users.py:250-275`

**Problem.** GET /users/{user_id}/predictions correctly enforces the blind pool for match predictions (skips fixtures that aren't locked or finished, users.py:213-217), but the bracket_summary block immediately below queries ALL of the target user's TeamPrediction rows and returns them unconditionally — no phase1/phase2 lock check, no finished check. A curious friend can call this for any user_id and read that user's entire Phase 1 advancement bracket (who they picked to win each group, reach each KO round, win the tournament) before the Phase 1 deadline locks. Bracket picks are exactly the kind of competitive intel the blind pool is meant to protect, and the asymmetry (match preds gated, bracket not) shows the gate was simply forgotten for the bracket path.

**Recommendation.** Before exposing another user's bracket, check is_phase1_locked(session) for the Phase 1 stages and is_phase2_bracket_locked(session) for the Phase 2 stages; only include each phase's bracket once that phase's deadline has passed. When user_id == current_user.id, the user may always see their own picks.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

## 🟡 MEDIUM findings

### 🟡 MEDIUM — Open self-registration auto-joins the live prediction pool (no invite/approval gate)

- **Ref:** `sec-auth:AUTH-2`  ·  **Effort:** medium  ·  **Confidence:** 0.85
- **Location:** `backend/app/api/auth.py:49-77; backend/app/api/predictions.py (user-scoped writes against the globally-active competition)`

**Problem.** POST /api/auth/register is unauthenticated and unrestricted: it creates a fully active user (is_active defaults True) and immediately returns a working JWT. Prediction writes are scoped only by current_user.id and resolve the competition via get_active_competition() (the single is_active competition), never by user.competition_id. The net effect: anyone who can reach the registration endpoint — the app is behind Cloudflare but not IP-allowlisted, and the register page is publicly linked — can create an account and start submitting predictions into the real 30-friends pool, appear on the leaderboard, and (once a match locks) view others' predictions as a legitimate participant. For a paid, invite-only friend competition this is a gatekeeping/integrity gap: there is no approval step, no invite token, and no link between a registered user and an intended competition. An outsider (or a friend creating sockpuppets) can pollute the leaderboard and the blind pool.

**Recommendation.** Gate participation. Cheapest options for this scale: (a) disable open registration entirely and onboard the ~30 friends via admin-created accounts + magic-link login (the magic-link flow already supports passwordless onboarding), or (b) require an invite token / shared registration secret on /register, or (c) keep registration open but mark new users is_active=False / unassigned and require admin activation before they can predict. At minimum, document the intended onboarding path; right now there is none.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🟡 MEDIUM — No admin-bootstrap path — first/admin user provisioning is undefined

- **Ref:** `sec-auth:AUTH-3`  ·  **Effort:** small  ·  **Confidence:** 0.8
- **Location:** `backend/app/api/auth.py:61-66 and 167-172 (all new users default is_admin=False); backend/scripts/* (no promote-admin script)`

**Problem.** Every account-creation path (register, Google callback) sets is_admin to its model default of False (user.py:35), and there is no migration, seed, env var, CLI/script, or first-user-becomes-admin rule anywhere in the repo that grants the initial admin. is_admin can only be toggled by an existing admin via PATCH /api/admin/users/{id}/admin (which itself requires AdminUser). This is a chicken-and-egg gap: a clean production deploy has zero admins, so admin-only operations (activate Phase 2, set Phase 1 deadline, sync scores, set bonus answers, manage paid status) are unreachable. The operator will be tempted to fix this at launch with an ad-hoc manual DB UPDATE, which is exactly the kind of out-of-band, unaudited change that risks mistakes on a 100%-integrity system.

**Recommendation.** Add a deliberate, auditable bootstrap: either an ADMIN_EMAILS env setting that auto-grants is_admin on user creation/login for listed addresses, or a small `python -m scripts.make_admin <email>` management command. Document it in CLAUDE.md alongside the migration workflow so the first-admin story isn't a manual SQL edit.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🟡 MEDIUM — OAuth callback returns the JWT in a URL query string

- **Ref:** `sec-auth:AUTH-5`  ·  **Effort:** medium  ·  **Confidence:** 0.8
- **Location:** `backend/app/api/auth.py:190-192`

**Problem.** After successful Google auth the backend issues a 7-day JWT and 302-redirects to `{frontend}/auth/callback?token={access_token}`. Putting a long-lived bearer token in a URL means it can land in browser history, be captured by any referrer leakage, and — most relevantly for self-hosting — be written verbatim into nginx/Cloudflare access logs as the request line. Anyone with log access (or shoulder-surfing the address bar) gets a token valid for 7 days. The frontend callback then immediately stores it in localStorage, so the URL exposure is pure downside.

**Recommendation.** Avoid the token-in-URL pattern: set the JWT in a short-lived httpOnly cookie on the redirect (or a one-time exchange code that the callback POSTs to swap for the token), or at minimum scrub the query string from logs and have the callback page replaceState to strip the token immediately. If keeping query delivery, shorten the OAuth-issued token lifetime.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🟡 MEDIUM — Prediction tables have no DB-level uniqueness; Config.unique_together is a SQLModel no-op (duplicate rows / integrity risk)

- **Ref:** `sec-authz:AUTH-2`  ·  **Effort:** medium  ·  **Confidence:** 0.9
- **Location:** `backend/app/models/prediction.py:46-49, 82-85 and backend/alembic/versions/f06b6a2077d3_initial_schema.py:95-96,127-128`

**Problem.** MatchPrediction declares `class Config: unique_together = [('user_id','fixture_id')]` and TeamPrediction declares `('user_id','team','stage')`, but SQLModel/SQLAlchemy does NOT honor a `unique_together` Config key — it is silently ignored. The initial migration confirms only NON-unique indexes were created on user_id and fixture_id (lines 95-96, 127-128); there is no UniqueConstraint. The write paths rely on a SELECT-then-INSERT upsert pattern (predictions.py:226-268 single, 336-368 batch). Two concurrent requests for the same (user, fixture) — e.g. the wizard firing /matches/batch twice on a double-tap, or a single + batch save racing — can both miss the existing row and INSERT two MatchPredictions for the same fixture. Duplicates then inflate roster/admin prediction counts and, more importantly, can be double-counted by scoring/leaderboard aggregation, threatening invariant #5 (100% prediction/score integrity). The bracket rewrite's delete-then-insert (predictions.py:527-556) is similarly unprotected against interleaving.

**Recommendation.** Add real DB unique constraints via a migration: UNIQUE(user_id, fixture_id) on match_predictions and UNIQUE(user_id, team, stage, phase) on team_predictions (include phase so Phase 1 and Phase 2 rows can coexist). Replace the Config.unique_together with `__table_args__ = (UniqueConstraint(...),)`. Then either use an INSERT ... ON CONFLICT upsert or catch IntegrityError and retry, so concurrent saves converge to one row instead of duplicating.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🟡 MEDIUM — POST /leaderboard/invalidate has no authentication dependency

- **Ref:** `sec-authz:AUTH-3`  ·  **Effort:** trivial  ·  **Confidence:** 0.97
- **Location:** `backend/app/api/leaderboard.py:120-127`

**Problem.** invalidate_leaderboard_cache takes no CurrentUser/AdminUser dependency at all — it is a state-changing POST callable by anyone, including fully unauthenticated callers (the only thing in front is Cloudflare and CORS, neither of which authenticates). The leaderboard uses a 30s cache (calculate_leaderboard); repeatedly hammering /api/leaderboard/invalidate forces full recomputation on every subsequent fetch, a cheap way for a curious friend to degrade performance during a live match when everyone is polling. It cannot corrupt data, but it is an unauthenticated mutation that bypasses the otherwise-consistent auth model and should not be exposed. (Note: admin score updates already invalidate the cache internally, so this public endpoint is redundant.)

**Recommendation.** Gate it behind AdminUser (consistent with the rest of admin ops), or remove it entirely since scores.py:update_score and admin bonus/answer writes already call invalidate_cache() internally. At minimum require CurrentUser.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🟡 MEDIUM — Backend runs uvicorn --reload with live source bind-mounts under the prod profile

- **Ref:** `sec-infra:SEC-2`  ·  **Effort:** small  ·  **Confidence:** 0.85
- **Location:** `docker-compose.yml:63`

**Problem.** The `backend` service has no `profiles:` key, so it is part of every profile including `prod`, and its command is `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`. Combined with the source bind-mounts (./backend/app:/app/app, etc., lines 45-57), the production deployment runs the development auto-reload server against host-mounted, mutable source. --reload spawns a file-watcher/reloader process unsuitable for production (higher memory, no graceful worker management, watchdog overhead), and the bind-mounts mean the running prod code is whatever is on the VPS disk rather than the immutable built image — defeating reproducible deploys and letting a host-side file change silently alter scoring/locking logic without a rebuild. For an app with a 100%-integrity requirement this is a real reliability/integrity risk at launch.

**Recommendation.** Split prod from dev: either a docker-compose.prod.yml override that drops --reload (the Dockerfile CMD already runs uvicorn without --reload — let prod use the image CMD) and removes the source bind-mounts, or move --reload + mounts into a dev-only service. Run multiple workers via `uvicorn --workers N` or gunicorn+uvicorn workers in prod.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🟡 MEDIUM — No per-account brute-force throttle on email/password login or magic-link verify

- **Ref:** `sec-infra:SEC-3`  ·  **Effort:** medium  ·  **Confidence:** 0.75
- **Location:** `backend/app/api/auth.py:80`

**Problem.** POST /api/auth/login (auth.py:80) does an unrate-limited bcrypt password check per request, and POST /api/auth/magic-link/verify (auth.py:293) does an unrate-limited token guess. The only throttles are nginx's coarse per-IP 10 r/s burst=20 (nginx.conf:40-61) and the 3-per-15min cap on *sending* magic-link emails (magic_link.py:52) — neither limits verify/login attempts per account. A determined friend can attempt thousands of password guesses against a known friend's email (or grind magic-link tokens) within the per-IP budget over time, especially since they share a NAT/Cloudflare path. The magic-link token space (256-bit) makes verify-grinding impractical, but weak human-chosen passwords on the /login path are the real exposure given the threat model is account takeover by a peer.

**Recommendation.** Add a lightweight per-account failed-attempt counter (e.g. exponential backoff / temporary lock after N failures within a window) on /login, reusing the DB pattern already built for magic-link rate limiting. This is proportionate (no infra needed) and directly closes the peer-takeover vector. Magic-link verify could similarly cap repeated invalid-token POSTs per IP.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

## 🔵 LOW findings

### 🔵 LOW — Google OAuth callback has no CSRF state parameter

- **Ref:** `sec-auth:AUTH-4`  ·  **Effort:** medium  ·  **Confidence:** 0.85
- **Location:** `backend/app/api/auth.py:38-46 (get_google_sso), 112-123 (login redirect), 126-144 (callback)`

**Problem.** GoogleSSO from fastapi-sso 0.19.0 defaults to requires_state=False, and the code never opts in (get_login_redirect() is called with no state= argument, and there is no SessionMiddleware/cookie to carry one). In verify_and_process (fastapi_sso/sso/base.py), state is only validated when both a state query param AND a matching `sso_state` cookie are present; with neither set, the OAuth callback accepts any well-formed Google authorization code with no cross-request binding. This removes the OAuth login-CSRF protection: an attacker could initiate a flow with their own Google account and trick a victim into completing it (login-CSRF), or more realistically it just means the flow has no replay/forgery binding. For a 30-person app this is lower impact than AUTH-1/2 but is a genuine missing control on the account-auth path. (Note: a fresh GoogleSSO instance is also constructed per request, so even PKCE/state state could not survive across the redirect→callback boundary without external storage.)

**Recommendation.** Enable state: add Starlette SessionMiddleware (or pass an explicit state and store it in a short-lived signed cookie), construct the SSO with state support, and pass/verify the state across get_login_redirect and verify_and_process. fastapi-sso documents the per-method `state=` argument for exactly this.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🔵 LOW — Magic-link request endpoint leaks account existence (enumeration); login path differs in shape

- **Ref:** `sec-auth:AUTH-6`  ·  **Effort:** trivial  ·  **Confidence:** 0.9
- **Location:** `backend/app/api/auth.py:256-290; backend/app/services/magic_link.py:79-82,239-240`

**Problem.** POST /api/auth/magic-link/request returns HTTP 404 'No account found for this email' for unknown addresses and 403 'Account is inactive' for deactivated ones, versus 200 for known-active accounts. The MagicLinkRequestResponse docstring claims 'same shape regardless of outcome' but the implementation contradicts it — the distinct status codes/messages are a clean account-enumeration oracle. The code comment explicitly waves this off ('enumeration risk is essentially zero' for a friend group), which is a defensible call, but it also reveals which of the ~30 friends have accounts and their active/inactive status to anyone who can hit the endpoint, and it's inconsistent with the intended generic behavior. The /login path correctly returns a uniform 401, so the two auth entry points disagree.

**Recommendation.** Make the request endpoint return a uniform 200 'if an account exists, a link has been sent' for unknown/inactive emails (still rate-limited), and only branch internally. If you deliberately keep the friendly 404 for UX, update the misleading docstring and accept the documented tradeoff explicitly. Low effort, removes the inconsistency.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🔵 LOW — Google account-linking silently flips an email user to GOOGLE provider, disabling password & lockout

- **Ref:** `sec-auth:AUTH-7`  ·  **Effort:** medium  ·  **Confidence:** 0.7
- **Location:** `backend/app/api/auth.py:156-176`

**Problem.** When a Google callback matches an existing email-based user (linking branch), the code sets user.google_id and overwrites user.auth_provider = AuthProvider.GOOGLE. After this, change_password returns 403 (auth.py:206) because the provider is GOOGLE, even though the user still has a password_hash. More subtly, linking is keyed purely on Google's verified email == stored email with no confirmation step; while Google emails are verified, this means whoever controls a Google account with a friend's email address can claim that friend's existing account (and inherit its predictions/points/admin flag). For this trusted friend-group it's low risk, but the silent provider flip is a correctness surprise and the auto-link removes the password as a recovery path.

**Recommendation.** Either keep auth_provider as a non-destructive set of capabilities (allow both password and Google once linked) or, at minimum, don't downgrade password access on link; and consider only auto-linking when the existing account has no password_hash, otherwise require an authenticated link step. At hobby scale, documenting the behavior is acceptable.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🔵 LOW — Stateless 7-day JWT with no server-side revocation; logout is client-only

- **Ref:** `sec-auth:AUTH-8`  ·  **Effort:** medium  ·  **Confidence:** 0.85
- **Location:** `backend/app/config.py:30; frontend/src/lib/stores/auth.ts:104-111`

**Problem.** Tokens live 7 days (jwt_access_token_expire_minutes = 60*24*7) and there is no token denylist or jti/version check — get_current_user only verifies signature+exp and re-loads the user. logout() merely clears localStorage client-side; a token already copied elsewhere (see AUTH-5 URL leak, or XSS reading localStorage) remains valid for up to a week with no way to revoke short of deactivating the account (is_active=False, which is the only effective kill switch and is admin-only). For a competitive friend pool, a leaked/stolen token is a full-week impersonation window.

**Recommendation.** Acceptable for the scale, but tighten: shorten the access-token lifetime (e.g. 24h) and/or add a per-user token_version claim checked in get_current_user so a 'sign out everywhere' / compromise response is possible. Document that admin deactivation is the only current revocation lever.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🔵 LOW — Google OAuth callback reflects raw exception text to the client

- **Ref:** `sec-infra:SEC-4`  ·  **Effort:** trivial  ·  **Confidence:** 0.8
- **Location:** `backend/app/api/auth.py:140`

**Problem.** The Google callback wraps verify_and_process in `except Exception as e: raise HTTPException(... detail=f"Failed to authenticate with Google: {e}")`. The underlying exception string (from fastapi-sso / httpx / token exchange) is returned verbatim to the caller, which can leak internal details — token-exchange URLs, partial config, library internals — and is an information-disclosure smell. Similarly the magic-link MagicLinkError handler returns `detail=str(e)` (auth.py:323), though those messages are author-controlled. Not catastrophic for a friend group, but it's needless leakage and can aid a curious user probing the auth flow.

**Recommendation.** Return a generic message to the client ("Google sign-in failed, please try again") and log the exception server-side via logger.exception. Avoid interpolating raw exception strings into HTTP detail.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🔵 LOW — No HSTS, Content-Security-Policy, or Referrer-Policy headers

- **Ref:** `sec-infra:SEC-5`  ·  **Effort:** small  ·  **Confidence:** 0.7
- **Location:** `nginx/nginx.conf:54`

**Problem.** nginx adds X-Frame-Options, X-Content-Type-Options, and a (deprecated, harmless) X-XSS-Protection, but no Strict-Transport-Security, Content-Security-Policy, or Referrer-Policy. The app is served over HTTPS via Cloudflare Tunnel, so HSTS would normally be set at the Cloudflare edge rather than this origin nginx (origin only sees HTTP from cloudflared) — verify HSTS is enabled in the Cloudflare dashboard. CSP matters more here: the magic-link JWT arrives via URL and is stored in localStorage (predictor_token), so any XSS would exfiltrate the token; a CSP would harden against that. Referrer-Policy matters because the OAuth callback redirects to /auth/callback?token=... — without a restrictive referrer policy the token-bearing URL can leak via Referer to any external resource the callback page loads.

**Recommendation.** Add `add_header Referrer-Policy "strict-origin-when-cross-origin" always;` and a starter Content-Security-Policy at the nginx server block, and confirm HSTS is enabled at the Cloudflare edge (or add it here if cloudflared forwards as https). Consider moving the OAuth token out of the query string (e.g. fragment or short-lived exchange code) as a follow-up to avoid token-in-URL leakage.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🔵 LOW — OAuth callback redirect target derived from cors_origins[0], coupling CORS list ordering to auth redirect

- **Ref:** `sec-infra:SEC-6`  ·  **Effort:** trivial  ·  **Confidence:** 0.8
- **Location:** `backend/app/api/auth.py:191`

**Problem.** After Google login the backend redirects the user (with their freshly-minted JWT in the URL) to `settings.cors_origins[0]`. cors_origins is parsed from CORS_ORIGINS_STR (config.py:65-79), whose compose default is "http://localhost:5173,http://localhost:3000". If prod CORS_ORIGINS_STR is left at default or lists localhost first, a real user's post-login redirect (carrying their access token) goes to localhost — at best a broken login, at worst the token is appended to a URL the user's browser may not control. The redirect destination should be the dedicated PUBLIC_BASE_URL setting (which exists and is used for email links, magic_link.py:100), not whatever happens to be first in the CORS allowlist.

**Recommendation.** Use settings.public_base_url (already the canonical public frontend URL) for the OAuth callback redirect instead of cors_origins[0], so the redirect target is independent of CORS list ordering and matches the value already used for email links.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🔵 LOW — Bracket prediction write accepts arbitrary unbounded team/stage strings with no allowlist or list-size cap

- **Ref:** `sec-input:INJ-1`  ·  **Effort:** small  ·  **Confidence:** 0.9
- **Location:** `backend/app/api/predictions.py:533-541; backend/app/schemas/prediction.py:57-80; backend/app/models/prediction.py:69-70`

**Problem.** update_bracket_predictions persists pred_data.team, pred_data.stage and pred_data.group_position verbatim into TeamPrediction. The TeamAdvancementPrediction schema declares team: str and stage: str with NO max_length and NO validation that team is a real competition team or that stage is one of the known stage values (round_of_32 ... winner). The model columns (TeamPrediction.team, .stage) are likewise unbounded TEXT. BracketPredictionUpdate.predictions is a plain list[...] with no max-items cap, so an authenticated friend can POST thousands of rows with megabyte-long team strings per request. Why it matters for this threat model: violates the 100% data-integrity requirement (the team_predictions table can be polluted with garbage that the roster bracket-pick counter and bracket_summary endpoints then read back and render), and is an easy authenticated DB-bloat/DoS lever. It is NOT a scoring cheat: calculate_advancement_points (scoring.py:359-383) only awards points when actual_advancement.get(team) exists for a team that genuinely reached the stage, and stage_points.get(predicted_stage, 0) yields 0 for unknown stages — so forged values score nothing.

**Recommendation.** Constrain TeamAdvancementPrediction.stage to a Literal/enum of the six valid stages plus 'group', add max_length (~64) to team, and reject teams not present in fetch_competition_teams(session). Cap BracketPredictionUpdate.predictions length (e.g. <= ~120, the realistic bracket size) and add a server-side max_length on the TeamPrediction.team/stage columns. Fail the whole request on any invalid entry rather than silently storing it.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🔵 LOW — Bonus answer stored as unbounded free text with no per-request batch cap

- **Ref:** `sec-input:INJ-2`  ·  **Effort:** trivial  ·  **Confidence:** 0.85
- **Location:** `backend/app/api/predictions.py:680-768; backend/app/models/bonus.py:46; (BonusPredictionUpdate at predictions.py:76-86)`

**Problem.** save_bonus_predictions accepts BonusPredictionBatch.predictions (an uncapped list) and for each entry stores update.answer.strip() into BonusPrediction.answer. The schema field answer: str has no max_length, and the model column answer: str (bonus.py:46) is unbounded TEXT (only question_id is capped at 64). question_id IS validated against valid_ids (good), but a single authenticated request can carry an arbitrarily large list of valid question_ids each with a multi-megabyte answer string, and there is no upper bound. Why it matters: data-integrity/storage abuse by a curious friend, and an unbounded field that later feeds the HTML receipt email (escaped, so not XSS, but still bloats the email). Lower-impact than INJ-1 because the unique constraint on (user_id, question_id) caps the row count to one-per-question after dedup within a single transaction, but a single oversized answer is still accepted and persisted.

**Recommendation.** Add max_length (e.g. 100) to BonusPredictionUpdate.answer and to the BonusPrediction.answer column, and cap BonusPredictionBatch.predictions to the number of defined questions (~12). Optionally validate team-typed answers against the question's eligible_teams set already computed by get_questions.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🔵 LOW — Match-prediction batch endpoint has no list-size cap

- **Ref:** `sec-input:INJ-3`  ·  **Effort:** trivial  ·  **Confidence:** 0.75
- **Location:** `backend/app/api/predictions.py:302-308`

**Problem.** batch_update_predictions takes predictions_data: list[MatchPredictionCreate] with no max-items constraint and loops issuing a SELECT (for the fixture) and a SELECT (for the existing prediction) per element, plus per-element flush/refresh and an audit-history insert. An authenticated user can submit an arbitrarily large list, each triggering multiple DB round-trips, as a cheap amplification/DoS lever. Each individual prediction is bounded (le=20) and unknown fixtures are skipped, so this is integrity-neutral but a resource-abuse concern. Proportionate severity for a 30-user app behind Cloudflare: low.

**Recommendation.** Cap the batch list to a sane upper bound (e.g. the total fixture count, ~104) via a Field(max_length=...) on a wrapper model or a length check at the top of the handler that 422s oversized payloads.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🔵 LOW — Live trajectory point dated with local date.today() instead of UTC date, mismatching snapshot dates

- **Ref:** `sec-logic:BLI-4`  ·  **Effort:** trivial  ·  **Confidence:** 0.8
- **Location:** `backend/app/api/leaderboard.py:173 (and import at :4)`

**Problem.** The trajectory endpoint appends a synthetic 'live now' point dated date.today(), which returns the server's LOCAL calendar date, whereas every stored snapshot's captured_date is computed from utc_now().date() (snapshots.py:50). The de-dup logic at leaderboard.py:177 compares points[-1].captured_date == live_point.captured_date to decide whether to overwrite today's snapshot vs append. Around the UTC midnight boundary (server in a non-UTC zone), date.today() and the UTC-derived snapshot date can disagree, producing either a duplicate same-day point or an overwrite of the wrong day on the chart. This is a cosmetic/correctness issue on a dashboard sparkline, not a scoring or lock issue, but it is a (mild) violation of the system-wide UTC-date convention used for snapshots.

**Recommendation.** Use utc_now().date() here to match the snapshot write path, so the live point's date is computed on the same (UTC) calendar the stored snapshots use.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

## ⚪ INFO findings

### ⚪ INFO — .env.example ships DEBUG=true and a weak placeholder secret

- **Ref:** `sec-infra:SEC-8`  ·  **Effort:** trivial  ·  **Confidence:** 0.85
- **Location:** `backend/.env.example:2`

**Problem.** The committed .env.example sets DEBUG=true and JWT_SECRET_KEY=your-super-secret-key-change-in-production. If an operator copies .env.example to .env on the VPS (a very common workflow) and forgets to flip DEBUG, prod runs with DEBUG=true — which exposes /api/docs and /api/redoc (main.py:36-37) and flips Google SSO into allow_insecure_http (auth.py:45). Compose defaults DEBUG to false (line 29), so this only bites if .env explicitly sets it — but the example actively encourages that.

**Recommendation.** Default .env.example to DEBUG=false, leave JWT_SECRET_KEY blank with a comment to generate one (`openssl rand -hex 32`), and add a short prod-env checklist to the deployment doc enumerating the must-set secrets (JWT_SECRET_KEY, DATABASE_PASSWORD, CORS_ORIGINS_STR, PUBLIC_BASE_URL, GOOGLE_*, RESEND_API_KEY, CF_TUNNEL_TOKEN, R2_*).

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### ⚪ INFO — Dependency versions pinned with lower bounds only (>=), no lockfile for backend

- **Ref:** `sec-infra:SEC-9`  ·  **Effort:** small  ·  **Confidence:** 0.6
- **Location:** `backend/pyproject.toml:6`

**Problem.** Backend deps use floor pins (fastapi>=0.109.0, uvicorn>=0.27.0, python-jose[cryptography]>=3.3.0, etc.) with no lockfile, so `pip install -e .` resolves to whatever is latest at build time. That's good for getting CVE fixes but bad for reproducibility/integrity — two deploys can ship different code. python-jose in particular has had algorithm-confusion advisories historically; the floor pin won't protect against a regression and the unpinned ceiling won't deterministically pull a fix either. For a 100%-integrity app, deploy reproducibility matters.

**Recommendation.** Commit a resolved lockfile (pip-tools requirements.txt, uv.lock, or poetry.lock) and build from it for reproducible images; periodically run a dependency-audit (pip-audit) to catch known CVEs. Low priority for 30 users but cheap insurance for integrity-critical code.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---
