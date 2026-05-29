# User-Flow & UX Audit

> Part of the pre-launch audit. See [README](./README.md) for methodology and the [Implementation Map](./IMPLEMENTATION.md) for fix status.

**9 findings:** 1 medium · 7 low · 1 info

## What this area does well

- Blind pool holds server-side: /matches/{id}/community returns nothing unless the fixture is locked or finished (backend/app/api/predictions.py:585-586), and the write path re-checks lock with server time (predictions.py:219-222) — the UI gating on the Results page is defense-in-depth, not the only guard.
- Lock state is server-authoritative: matchState() keys off fixture.is_locked / fixture.status from the API (matchBreakdown.ts:100-105) rather than the client clock, so a tampered local time can't unlock a card.
- Save feedback is honest: the wizard's save button only shows the success/✓ state after Promise.all over the real API calls resolves (predictions/+page.svelte:582-585), matching the 'feedback only after backend confirms' rule.
- Strong draft-safety UX: localStorage draft mirror + restoration banner + beforeNavigate/beforeunload guards mean a friend who refreshes mid-entry doesn't silently lose picks (predictions/+page.svelte:533-542, 753-778).
- Empty/loading states are present almost everywhere a list can be empty: 'No standings yet' (leaderboard), 'No matches for the current filter', 'No knockout fixtures yet' (predictions), 'Loading stats…' with a Retry button (profile), and a real 'blind until lock' placeholder on the match-detail page.
- Auth dead-ends are handled thoughtfully: magic-link with no token redirects to the request form instead of erroring (auth/magic/+page.svelte:15-20), and the OAuth callback shows an explicit failure card with a 'Back to Sign In' button.
- Phase taxonomy is well-modelled: deriveUxPhase() composes lock signals into five distinct dashboards with phase-appropriate copy and CTAs, so the landing page is never generic regardless of where the tournament is.

## Assessment by sub-dimension

### User Flow & UX Journey (from the code)

The core journey (landing -> login/register/magic-link/Google -> phase-aware dashboard -> predictions wizard -> save/lock feedback -> leaderboard -> results -> rules) is genuinely well-built and unusually polished for a hobby app: blind-pool is enforced server-side (not just hidden in UI), lock state comes from a server-authoritative is_locked flag, drafts persist to localStorage with a restoration banner, the save state-machine gives proper post-confirmation feedback, empty/loading states exist on nearly every list, and there are dedicated phase-specific dashboards with real countdowns. The most serious UX defect is mobile-only: the bottom nav has no Profile or Logout entry, and the only place those live (the desktop masthead avatar menu) is display:none below 700px, so a mobile user (the primary audience) is stranded with no way to sign out, change password, or see their stats. The second-tier issues are flow robustness: there is no global 401 handler, so an expired/invalidated token never bounces the user to login and instead surfaces raw error strings while leaving the dead token in localStorage; and several user-facing copy/number mismatches (48 vs 72 group matches, the documented 5-minute lock vs the actual 15-minute config) will confuse careful readers. None of these let a friend cheat or snoop — the integrity-critical invariants hold — but the mobile dead-end and the 401 handling are real launch-blockers for UX.

## Findings

## 🟡 MEDIUM findings

### 🟡 MEDIUM — No global 401 handler — expired/invalid token never bounces to login and leaves a dead token in localStorage

- **Ref:** `flow-ux:FLOW-2`  ·  **Effort:** small  ·  **Confidence:** 0.9
- **Location:** `frontend/src/lib/api/client.ts:34-39; frontend/src/lib/stores/auth.ts:81-102`

**Problem.** ApiClient.request() throws a generic `new Error(error.detail)` for every non-OK response with no special case for 401/403 (client.ts:34-39). There is no interceptor that, on a 401, clears the token and redirects to /login (a repo-wide grep finds zero references to status 401). The only place a bad token is cleared is fetchUser() on initial app load (auth.ts:92-101). So once the app is running, if the JWT expires or is revoked mid-session, every page's onMount fetch (leaderboard polling, predictions save, results) rejects with a raw backend string like 'Could not validate credentials' rendered into the page's error slot, the user stays on a half-broken authenticated-looking screen, and the stale token remains in localStorage (so a refresh re-attempts with the same dead token). For a prediction app this is also a data-integrity footgun: a user could type picks into the wizard, hit Save, get an opaque error, and not realise their session died and nothing was saved. The audit explicitly asks 'expired token -> does a 401 cleanly bounce to login?' — currently it does not.

**Recommendation.** In ApiClient.request(), detect `response.status === 401` (and arguably 403 for revoked accounts), clear the token via the auth store and `goto('/login')` before throwing. Easiest decoupled approach: pass an onUnauthorized callback into the ApiClient from auth.ts (the store already imports goto and owns logout()). Show a brief 'Your session expired, please sign in again' message on the login page.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

## 🔵 LOW findings

### 🔵 LOW — Mobile users cannot reach Profile or Log out — no account access in the bottom nav

- **Ref:** `flow-ux:FLOW-1`  ·  **Effort:** small  ·  **Confidence:** 0.95
- **Location:** `frontend/src/lib/components/panini/PnBottomNav.svelte:12-39; frontend/src/lib/components/panini/PnPageShell.svelte:50-55; frontend/src/lib/components/panini/PnMast.svelte:96-114`

**Problem.** The only access points for 'My Profile' and 'Logout' live in the avatar dropdown inside PnMast (PnMast.svelte:96-114). PnMast is rendered inside the `.desktop-only` wrapper in PnPageShell (PnPageShell.svelte:50), which is `display:none` below 700px (panini-base.css). Below 700px only PnBottomNav renders, and its items are Home/Predict/Results/Standings/Rules (+Admin) — there is no Profile and no Logout. The leaderboard mobile 'you' self-card (leaderboard/+page.svelte:282-296) is a plain div with no href, so a phone user cannot even reach their own public profile, let alone the private profile page (stats, password change) or sign out. Given the app is explicitly mobile-first for ~30 friends, most of whom will use it on a phone, this is a hard dead-end: a logged-in friend on mobile has no way to view their detailed stats, change their password, or switch accounts.

**Recommendation.** Add a 6th bottom-nav slot (or replace Rules with an account/avatar entry that opens a small sheet) giving mobile users 'My Profile' and 'Sign out'. Simplest: add `{ href: '/profile', label: 'You', icon: 'user' }` to the items array and make the profile page's existing 'Sign out' button the logout path on mobile. Verify on a 375px viewport that both Profile and Logout are reachable.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🔵 LOW — Pre-tournament dashboard says '48 group match scores' but there are 72 group matches

- **Ref:** `flow-ux:FLOW-3`  ·  **Effort:** trivial  ·  **Confidence:** 0.95
- **Location:** `frontend/src/lib/components/panini/dashboard/DashboardPre.svelte:266; cf. DashboardPre.svelte:78-81 (totalGroupMatches falls back to 72)`

**Problem.** The 'Tournament structure' peek on the first screen a new user sees describes Phase I as 'All 48 group match scores, your knockout bracket, and 9 bonus picks.' But FIFA 2026 has 12 groups x 6 matches = 72 group matches — the same component computes `totalGroupMatches = groupFixtures.length || 72` two lines of code earlier (DashboardPre.svelte:81), and the rules page and funnel-hero teaser both use the live count. '48' is the team count, not the match count, conflated here. A new, somewhat-technical user reading the onboarding copy will see the dashboard promise 48 matches, then open the wizard and find 72 — undermining trust in the numbers right at the top of the funnel. (The same block also hardcodes '9 bonus picks' while the live bonus count is dynamic and elsewhere defaults to 10.)

**Recommendation.** Change the copy to '72 group match scores' (or interpolate `totalGroupMatches`), and either interpolate the bonus count (`totalBonusQuestions`) or use the same wording as the rules page. Quick string fix; consider deriving from the live values already in scope so it can't drift again.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🔵 LOW — Lock-window copy is internally consistent at 15 min but contradicts the documented 5-minute invariant

- **Ref:** `flow-ux:FLOW-4`  ·  **Effort:** trivial  ·  **Confidence:** 0.85
- **Location:** `config/worldcup2026.yml:20; frontend/src/routes/rules/+page.svelte:368; frontend/src/lib/utils/matchBreakdown.ts:97-98; multiple dashboard strings`

**Problem.** Every user-facing string says predictions lock '15 minutes before kickoff' (rules fine-print line 368; DashboardPre/Between structure peek; the Results blocked-card title), and the backend config agrees (`match_lock_before_kickoff: 15`). However the project's stated system invariant (CLAUDE.md and the audit brief) is that predictions lock '5 minutes before kickoff', and matchBreakdown.ts's own doc comment still says 'inside-the-5-min-window' (matchBreakdown.ts:97-98). So the copy is consistent with the code, but the code/copy disagree with the documented spec. For a prediction app where lock timing is the whole game, this ambiguity matters: friends will reasonably believe they have until T-5 if they read the spec, but the system will actually lock them out at T-15. Whichever number is correct, the spec, the config comment, and the stale matchBreakdown comment should be reconciled so nobody argues about a missed entry after kickoff.

**Recommendation.** Decide the canonical lock window with the organiser. If 15 is intended, update CLAUDE.md / the spec and fix the stale '5-min-window' comment in matchBreakdown.ts. If 5 is intended, change the YAML value and all the '15 minutes' copy. Either way make one number the source of truth.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🔵 LOW — ssr=false means a blank white screen on first load / refresh before the SPA boots and the auth gate runs

- **Ref:** `flow-ux:FLOW-5`  ·  **Effort:** small  ·  **Confidence:** 0.8
- **Location:** `frontend/src/routes/+layout.ts:3; frontend/src/routes/+page.svelte:43-50; all route auth gates use client-side goto()`

**Problem.** Layout sets `export const ssr = false`, so the server returns an empty shell and all rendering — including the `$: if (!$isAuthenticated) goto('/login')` gates — happens only after the JS bundle loads and initAuth() runs. On a cold load (or a hard refresh on, say, /predictions) the user sees a blank cream page, then a flash, then either the page or a redirect to /login. On a slow phone connection this reads as 'the app is broken / stuck loading'. Because every route gate is client-side and the landing dispatcher only renders `{#if $isAuthenticated && ActiveDashboard}` (root +page.svelte:48), an unauthenticated deep-link shows nothing at all until the redirect fires. It's not a security hole (the API still enforces auth), but it's a perceptible first-load UX rough edge for the target audience.

**Recommendation.** Add a lightweight loading/splash state (a centered crest + spinner) that renders before auth resolves, so cold loads show branding instead of a blank page. Keep ssr=false (it's a deliberate choice per the comments) but mask the gap. Verify the deep-link-while-logged-out path shows the splash then a clean login redirect, not a flash of empty content.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🔵 LOW — Leaderboard 'Available' points and per-match-detail 'available' are a hardcoded placeholder (288)

- **Ref:** `flow-ux:FLOW-6`  ·  **Effort:** small  ·  **Confidence:** 0.85
- **Location:** `frontend/src/routes/leaderboard/+page.svelte:132-135`

**Problem.** The leaderboard self-summary shows an 'Available' stat that is hardcoded `availablePts = 288` with a comment 'use a fixed-ish number; this slot exists in the design.' Once scoring starts, this number will be the same for every user at every point in the tournament regardless of how many matches remain, which is misleading in a competition where 'how many points are still in play' is a real strategic question friends will ask. It reads as authoritative (sits next to real values like Total and To #1) but is fiction.

**Recommendation.** Either compute remaining available points from unfinished fixtures + remaining bracket stages, or hide the 'Available' stat until the backend can supply it (consistent with how other backend-pending widgets are stubbed and labeled). Don't present a constant as a live figure.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🔵 LOW — Phase tabs/save copy can show 'Save Phase II' with a Phase-1-only badge count, and the wizard auto-jumps to Phase II

- **Ref:** `flow-ux:FLOW-7`  ·  **Effort:** medium  ·  **Confidence:** 0.7
- **Location:** `frontend/src/routes/predictions/+page.svelte:69-72, 824-859`

**Problem.** When Phase 2 is active, the wizard initialises activePhase to 'phase2' (predictions/+page.svelte:69-72), so a returning user who only ever touched Phase 1 group/bracket picks lands on the Phase II tab and may not realise their Phase I work is on the other tab. Separately, the unified save logic treats Phase 1 as three dirty sources (matches+bracket+bonus) but Phase 2's save button uses only `$hasUnsavedChanges` (match picks) — the Phase 2 bracket has its own separate 'Save bracket' button lower down (line 1328). The result is two different save affordances in one phase, which is easy to miss: a user can update the Phase II bracket, see no change in the hero save button, and think there's nothing to save. The transition between phases is functional but the dual-save model is a likely source of 'I thought I saved that' confusion.

**Recommendation.** Unify Phase II save the way Phase I is unified (single hero button covering match picks + Phase II bracket), or at minimum surface a dirty indicator on the hero save when the Phase II bracket has unsaved changes. Consider defaulting the landing tab to the phase the user has unsaved work in, or showing a one-time hint that Phase I picks live under the Phase I tab.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

### 🔵 LOW — Save errors in the wizard show only a transient '× Retry' button with no detail, and bonus-save swallows errors

- **Ref:** `flow-ux:FLOW-8`  ·  **Effort:** small  ·  **Confidence:** 0.75
- **Location:** `frontend/src/routes/predictions/+page.svelte:560-585, 844-849`

**Problem.** When handleSaveAll() fails, the only feedback is the save button flipping to '× Retry' (and unlike the success state it never auto-resets, which is fine), but the user is never told WHY — e.g. a single locked fixture rejected, or the session expired (see FLOW-2). The bonus-save branch additionally catches all errors and returns false with no message (`catch (_e) { return false; }`, lines 575-577), so a bonus-save failure is indistinguishable from a match-save failure. For a 100%-integrity prediction app, a save that silently 'didn't fully work' with only a generic Retry is risky — a user may assume Retry will fix it when the real cause (a now-locked match) won't resolve by retrying.

**Recommendation.** Capture the first failing task's error message and render it near the save button ('Couldn't save: 2 matches have already locked'). Distinguish 'session expired -> re-login' (FLOW-2) from 'some picks rejected because they locked' so Retry vs re-login is obvious.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---

## ⚪ INFO findings

### ⚪ INFO — DashboardBetween phase-2 bracket progress is hardcoded to 0 (TODO), so the 'Re-pick bracket' funnel always reads 0% updated

- **Ref:** `flow-ux:FLOW-9`  ·  **Effort:** small  ·  **Confidence:** 0.8
- **Location:** `frontend/src/lib/components/panini/dashboard/DashboardBetween.svelte:171, 183-209`

**Problem.** On the between-phases dashboard the funnel hero's progress and the 'Bracket has unsaved changes' alert are both driven by `bracketFilled = 0; // TODO: wire to bracket store`. So during the entire Phase 1->2 window the hero shows '0 / 32 updated' even after a user has re-picked and saved their Phase II bracket in the wizard, and the unsaved-bracket alert (gated on `bracketFilled > 0`) can never fire. The wizard itself works; only this dashboard's reflection of it is stubbed, which makes the between-phases screen feel like it isn't tracking the user's progress. Not a correctness/integrity issue, but it's the one phase whose dashboard understates the user's real state.

**Recommendation.** Wire bracketFilled to the Phase 2 bracket store (countBracketSlotsFilled on $phase2BracketPrediction, the same helper the wizard uses) so the between-phases funnel and alert reflect real progress, mirroring how DashboardPre composes its progress.

**Status:** _see [Implementation Map](./IMPLEMENTATION.md)_

---
