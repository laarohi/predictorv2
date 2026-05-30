# Design Audit

Page-by-page visual review of every page at **desktop (1280px)** and **mobile (375px)**. Captured by driving headless Chrome (Playwright `channel: 'chrome'`) against the running app with a real admin session injected, then inspecting the screenshots — the Claude-in-Chrome extension never connected this session, so this headless route was used instead. 24 screenshots across login, register, the four dashboard phases, predictions, leaderboard, results, profile, rules, and admin.

## Verdict

**The Panini design system is polished, consistent, and launch-ready.** Cream paper + navy ink + red/gold accents are applied uniformly; the offset "sticker" shadows and Archivo-Black numerics give it a strong, distinctive identity that holds together across every page. Typographic hierarchy is clear, the desktop/mobile split is clean (dense data tables remain legible at 375px), and nothing looks broken or unfinished. The findings below are one real bug (fixed) plus polish.

## 🟠 Found & fixed during this pass

- **`DESIGN-1` — admins were bounced off `/admin` on cold load.** The screenshot of `/admin` came back showing the *dashboard*; with a 5s settle the URL had redirected to `/`. Root cause: the admin route guard ran `if ($isAuthenticated && !$user?.is_admin) goto('/')`, and on a cold load/refresh the localStorage token makes `$isAuthenticated` true *before* `/auth/me` populates `$user` — so every admin was redirected before their role loaded. Fixed by gating all three admin guards on a new `authResolved` flag (commit `c2f62b7`); re-screenshotting the worktree build confirmed `/admin` now renders the **Admin Console**. The code audit's flow dimension didn't catch this — it only surfaced by actually loading the page.

## Per-page notes

| Page | Assessment |
|---|---|
| **Login / Register** | Clean. Clear auth hierarchy: primary Sign in → "email me a login link" → "continue with Google". Centered card, good on mobile. |
| **Dashboard — pre-tournament** | Strong landing: live countdown, "how points work" legend, Phase I/II structure, and the registration roster with paid badges. Stacks well on mobile. |
| **Dashboard — group / between / post** | All four phase variants render correctly (checked via `?uxPhase=`). Between-phases funnel + KPI row read well; post-comp podium/highlights present. |
| **Predictions** | The densest screen, and it holds up: Phase/Groups/Knockout/Bonus toggles, a "145/145" progress bar with a clear saved state, predicted-standings table, and per-match score cards with flags + lock/saved badges. At 375px it linearizes cleanly (group nav arrows, stacked cards). |
| **Leaderboard** | Clean ranked table (rank, exact, outcome, bonus, bracket, total, move) with a prominent "you" self-card. _Note: this audit's fixes removed the fabricated Trend·7d column and the hardcoded "288 available" — confirmed gone in the worktree build._ |
| **Results** | Date-grouped fixture cards with flags + scores. **Polish opportunity:** all ~104 fixtures render in one continuous scroll (the mobile page is ~23,000px tall). Consider collapsing by matchday, a sticky date rail, or a "jump to today"/upcoming filter so users aren't scrolling the whole tournament. (Low priority; not a bug.) |
| **Profile** | Well-organized: identity + role badges, a 2×3 stat-card grid (points, predictions, accuracy, exact, outcomes, bonus), account info, and password/sign-out. Clean. |
| **Rules** | Comprehensive and nicely sectioned — phases, scoring breakdown, bracket-advancement points table, bonus questions, entry fee. |
| **Admin** | Renders the Admin Console (post-fix). Competition/phase/user/score management laid out in the same Panini chrome. |

## Polish suggestions (all low priority — the design is solid)

1. **Results scroll length** — the biggest UX opportunity: 104 fixtures in one scroll is a lot to traverse. Matchday collapse / sticky date headers / a date filter would help (also lightens the DOM, complementing the lazy-flag work).
2. **Empty / first-run states** — the seeded dataset meant I couldn't see a brand-new user's empty dashboard/leaderboard. Worth a manual look with a fresh account before launch (the one state these screenshots couldn't exercise).
3. **Mobile bottom nav density** — with the new "You" tab it's 6 tabs (7 for admins); it reads fine in the capture, but confirm tap targets feel comfortable on a real handset.
4. **Dev phase pill** — the `DEV · PRE TOURNAMENT` pill is dev-only (`import.meta.env.DEV`) and won't ship to prod; no action needed.

## Method note

Screenshots live under `/tmp/dq-shots/shots/` (not committed — transient artifacts). To reproduce or extend: the app runs at `localhost:5173`; inject a JWT into `localStorage['predictor_token']` and drive Playwright with `channel: 'chrome'` (no browser download needed). The worktree's own changes were verified by serving the worktree frontend on `:5174` (`VITE_API_TARGET=http://localhost:8000 npm run dev -- --port 5174`).
