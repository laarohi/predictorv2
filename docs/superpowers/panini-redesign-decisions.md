# Panini Redesign — Decisions Log

Decisions made during execution of the goal "implement the redesign purely in the frontend, keep working till it builds with no bugs and test where possible." Each entry has the date, the decision, the rationale, and what to revisit if you want to push back.

The user can review/override any item here; they're judgment calls I made to keep moving, not commitments. Listed newest first.

---

## 2026-05-15 — Build / test verification strategy

- **`npm run check` baseline**: the project memory notes ~58 pre-existing warnings (CSS `@apply`, a11y) with 0 errors. I treat "builds clean" as **0 net-new errors and not adding more than a handful of warnings** rather than zero-warning. If a Panini port introduces warnings beyond a couple, I will fix them.
- **`npm run build`**: must succeed end-to-end inside the dev container. Reported as the build acceptance gate.
- **Unit tests**: I'll add `vitest` tests for pure data/utility functions (e.g. sparkline path generation, stub data shapers). I will **not** add tests for purely-visual components — Playwright isn't set up and writing snapshot tests for chrome is high-noise, low-value.

## 2026-05-15 — Stubbing backend-dependent features

Several Panini features (sparklines, social signals, hot-pick yield, bracket exposure, underdog hits, steepest climb, live match in progress) need backend data we don't have yet. Stubbing strategy:

- All stubs live in `frontend/src/lib/stubs/panini.ts`. Every export is named `stub<Thing>()` so they're greppable.
- Stubs return **plausible but deterministic** data (no `Math.random()` in render paths — flaky tests). Seeded by route/user where possible.
- Every consuming component logs `console.debug('[panini:stub] using stub <name>')` in dev so we can find them when the backend lands.
- Once the backend supports a feature, we swap the stub for a real fetch and delete the stub fn.

Push back if you'd rather see the components ship without these widgets entirely (then we delete the stub and the widget together).

## 2026-05-15 — Page migration order

Migrating in this order, one commit per surface:

1. Dashboard — most visible, highest design surface area
2. Leaderboard — self-contained table reskin + self-card
3. Predictions Wizard — biggest rewrite, includes Phase 1/2 toggle + bonus questions tab + integrated bracket
4. Bracket — handled inside Predictions (interactive when open, display when locked), per earlier decision
5. Results — new Panini design (using frontend-design skill where it helps)
6. Admin — new Panini design
7. Profile / Login / Register / Auth callback — Panini treatment

Each page wraps in `<PnPageShell>`. Until a page is migrated, it keeps the legacy dark theme — both coexist because Panini is `.pn`-scoped.

## 2026-05-15 — Layout root chrome

The existing root `+layout.svelte` renders the legacy dark navbar above any child page. When `/panini-sandbox` shows both, that's expected sandbox behaviour. **For migrated pages**, I will switch the root layout to detect Panini pages and hide its own nav for those routes. Implementation idea: a `usesPanini` flag derived from the route, gated by a small map in `+layout.svelte`. Push back if you'd rather move every page in one shot and delete the legacy nav entirely.

## 2026-05-15 — Bottom nav exposure

`PnBottomNav` is mobile-only (hidden ≥ 700px). It's currently fixed-positioned, so on Panini pages it floats over content. I'll keep the existing root layout's legacy mobile nav suppressed on Panini routes to avoid two bottom nav bars stacking.

## 2026-05-15 — CSS module strategy per page

Each migrated page gets a dedicated stylesheet under `frontend/src/lib/styles/`:
- `panini-dashboard.css`
- `panini-leaderboard.css`
- `panini-wizard.css`
- `panini-bracket.css`
- `panini-results.css`
- `panini-admin.css`

These are imported by `app.css` (top of file, before `@tailwind` — same rule as `panini-base.css`). All rules scoped under `.pn`. This keeps the bundle modular and makes it easy to drop a page if you want it reverted.

Alternative I rejected: inline `<style>` in each page. Reason: shared rules across desktop/mobile would duplicate, and the JSX source already had these as page-level stylesheets — keeping the same shape eases comparison with the design.

## 2026-05-15 — Use existing stores, don't rewrite

The current `$stores/fixtures`, `$stores/predictions`, `$stores/leaderboard`, `$stores/phase`, `$stores/auth` work. Panini pages **read from the same stores** — no new state plumbing. Where Panini needs different aggregations (e.g. "top 5"), the page computes those from existing store data. Push back if you'd rather refactor the stores.

## 2026-05-15 — TypeScript prop typing

Every Svelte component prop gets an explicit TypeScript type. No `any`. Per project CLAUDE.md and the existing convention. Shared types live in `frontend/src/lib/types/panini.ts` (already created in Foundation).

## 2026-05-15 — Tilts & flags (carry-over)

From the Foundation review:
- **No `transform: rotate(...)` on cards/stickers/KPIs anywhere.** This applies to every Panini stylesheet I write.
- **`PnFlag` stays as the 2/3-stripe placeholder** for this push. Swapping for real flag SVGs is deferred to a follow-up plan after Dashboard.

## 2026-05-15 — CLAUDE.md update deferred

Originally Task 11 of the Foundation plan. Held until the whole worktree is ready to merge. Will batch-apply at merge time.

---

## Decisions still to make (will land here as I hit them)

### 2026-05-15 — Drop expandable per-row breakdown on Leaderboard

The current Leaderboard supports clicking any row to expand and see a per-phase breakdown (match outcome / exact / bonus, groups / R32 / R16 / QF+). The Panini design does **not** include this expand affordance. Two options:

- **A (chose this)** — drop the expander. Per-player breakdowns remain reachable via `/profile/[userId]` which shows the same data.
- B — keep the expander; needs custom plumbing to fit the Panini row design.

**Why A:** the Panini table is the design we signed off on; expandable rows would change its skim-ability. `/profile/[userId]` already exposes the breakdown so no data is lost. Easy to revert by re-adding the row click + a state machine.

### 2026-05-15 — Wizard reuses KnockoutBracket and Phase2Content unchanged

The new Panini wizard rewrites the **outer** chrome and per-group view in Panini styling, but the **inner** components stay as-is:

- `KnockoutBracket.svelte` — used inside the new "Knockout" pill of Phase 1, unchanged.
- `Phase2Content.svelte` — used when the user toggles to Phase 2, unchanged.

**Why:** these components contain hundreds of lines of interaction logic (drag-drop / click-select, persistence, derived bracket state). Rewriting them in Panini would be a multi-day project on its own and risks breaking the prediction save flow. Visually they will look "off-brand" inside the cream Panini chrome — they still use the dark-theme Tailwind utilities (`bg-base-300/50` etc.) that point to DaisyUI tokens — but they remain fully functional.

**Follow-up:** write a separate plan to restyle these components to match Panini, OR rebuild them on top of Panini primitives. Until then, the wizard is fully usable.

### 2026-05-15 — Bonus questions are UI stubs with no persistence

The new Panini wizard adds a "Bonus" pill with 6 example bonus questions (Who wins the tournament, Top scorer, Most cards, etc.). These currently:

- Render with Panini styling
- Allow no real interaction (no select widgets are wired up)
- Have **no backend save path** — the schema for bonus_questions doesn't exist yet

**Why a stub:** the user wants bonus questions in Phase 1 (see earlier decisions). Adding the UI now lets us iterate the design. The full feature requires (a) a `bonus_questions` table on the backend, (b) admin entry of correct answers, (c) scoring rules, (d) prediction persistence. Each of those belongs in a follow-up plan.

### 2026-05-15 — Bracket exposure value is currently a fixed stub

`stubBracketExposure` returns the same `{ pointsAvailable: 235, picksLocked: 22, picksTotal: 22, finalPick: ARG over FRA }` regardless of user. This is intentional: real bracket-exposure math needs to know (a) which knockout-stage points are still in play given the current bracket state, (b) which of the user's picks are still alive. Push back if you want me to compute a less misleading value from the existing bracket prediction data, even without backend support.
