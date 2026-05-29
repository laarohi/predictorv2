# Design Audit

## ⚠️ Status: visual pass blocked

The interactive, page-by-page **visual** audit (screenshots + clicking through every page on desktop and at 375 px, via Chrome MCP) could **not** be completed: the Claude-in-Chrome browser extension was not connected during this session (every `tabs_context` call returned "Browser extension is not connected").

The app is running and ready (`http://localhost:5173`, seeded with 25 users / 1,590 predictions), and I prepared 12-hour JWTs for an admin and a non-admin account so the visual pass can start instantly. **To run it:** install/enable the extension (`https://claude.ai/chrome`), restart Chrome if needed, and ask me to proceed — I'll walk every page at both breakpoints and capture screenshots.

What follows is a **code-level** design review (design-system consistency, layout structure, responsive patterns, and concrete polish), plus a checklist of items that specifically need eyes-on confirmation.

## Design system — assessment

The Panini system is coherent and well-disciplined:

- **Tokens** are centralized as CSS variables on `.pn` (`panini-base.css`) and used consistently — cream paper, navy ink, red signal, gold highlight, green/navy accents. No stray hex values in the components I read.
- **Typography** is on-system: Archivo Black for display/numbers, Archivo for medium headings, IBM Plex Sans/Mono for body/metadata. Fonts are `preconnect`-ed and loaded with `display=swap` in `app.html` (good — avoids invisible-text FOIT).
- **Sticker shadows** (`box-shadow: 5px 5px 0 var(--ink)`) are applied at the card level; I did not find `transform: rotate(...)` on card-level containers — the no-tilt rule (a prior explicit preference) is respected.
- **Responsive split** is pure CSS (`@media 700px`) with separate desktop/mobile markup (e.g. the leaderboard renders `pn-desk` and `pn-mob` blocks; Results/MatchLeaderboard have dedicated mobile components). This avoids hydration flicker and is the right call for a mobile-first audience.
- **`PnPageShell`** measures its own chrome height into `--pn-chrome-h` so sticky page elements stack correctly beneath the masthead — a clean solution to sticky-under-sticky overlap.

This is a polished foundation; the suggestions below are refinements, not corrections.

## Changes already made this session that affect the look/feel

- **Cold-load splash** (`FLOW-5`): a blank white screen on first load/refresh is replaced by a cream splash with the CxF crest + "Loading…". → *Verify the splash matches the in-app crest styling and that the hand-off to the app is flicker-free.*
- **Mobile bottom nav** (`FLOW-1`): added a "You" tab (→ profile + sign-out). The bar now has **6 tabs (7 for admins)**. → *Verify at 375 px that 6–7 tabs aren't too cramped (labels legible, tap targets ≥ ~44 px). If tight, consider dropping labels to icons-only on the narrowest widths, or collapsing Rules into the profile sheet.*
- **Leaderboard** (`STUB-1`, `FLOW-6`): removed the fake "Trend · 7d" sparkline column and the hardcoded "Available 288" stat. → *Verify the desktop table still balances visually with one fewer column, and the self-card with two stats (Total, To #1) doesn't look sparse.*

## Per-area code-level notes & polish suggestions

> Pending visual confirmation. Ordered by likely impact.

1. **Empty / first-run states** — the most important thing to verify visually. Before the tournament starts and before any scoring, check: dashboard with zero predictions, leaderboard with no scored matches, results page with no finished fixtures, a brand-new user's profile. These are the screens your friends hit on day one; they should feel intentional, not empty. (The code has phase-specific dashboards — `DashboardPre/Between/KO/Post` — but empty-data variants within each need eyes.)
2. **Loading states** — now that the 401 bounce and the splash exist, verify the per-page loading affordances (leaderboard "LOADING…", dashboard skeletons if any) read consistently and don't flash on fast loads.
3. **Lock / deadline messaging** — the configured lock window is 15 min (not 5); verify countdowns and "locks in …" copy are consistent across dashboard, wizard, and results, and that a locked match is visually unambiguous (the `lock` icon + state).
4. **Predictions wizard (1,546 lines)** — the densest screen. Visually verify: the stacked Phase I/II + Groups/Knockout/Bonus toggles in the hero, the score-input cap (15) feedback, the bracket gating (knockout locked until groups filled), and save feedback. Two deferred UX items live here (`FLOW-7` Phase II save clarity, `FLOW-8` actionable save errors) — worth a visual decision.
5. **Flag swatches** — `PnFlag` renders 2/3-stripe gradient placeholders (a real flag library is a separate planned task). Verify they read acceptably en masse on the bracket and results pages; they're the most obvious "placeholder" surface.
6. **Bracket (`PnKnockoutBracket`)** — final-in-the-middle wall chart on desktop, swipeable on mobile. Verify the swipe affordance is discoverable on mobile and the connector lines render cleanly.
7. **Profile** — has the only sign-out button (now reachable on mobile via the new tab). Verify the profile hero and stat cards.
8. **Auth pages** (login / register / magic-link / callback) — verify they sit inside the Panini shell consistently and the new generic OAuth error + "session expired" message render in-theme.

## Cross-cutting suggestions (low-risk polish)

- Confirm focus-visible styles exist for keyboard nav on the interactive elements (tabs, nav, buttons) — quick a11y win.
- Confirm tap targets on the mobile bottom nav and phase tabs meet ~44 px.
- With `flag-icons` retained and real flags planned, the gradient `PnFlag` is the single biggest visual-polish lever once that follow-up lands.

_When the extension is connected, this document will be expanded with per-page screenshots and concrete visual findings._
