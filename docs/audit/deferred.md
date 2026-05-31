# Deferred — Post-Launch Backlog

Things worth doing **after** launch. None blocks the friend-group launch. The
urgent **pre-merge** item lives separately in [MERGE-NOTES.md](./MERGE-NOTES.md).

Status legend: 🆕 found in round-2 MCP walkthrough · ↩ carried over from round 1 ·
✅ resolved since first logged · ⛔ now moot.

## Correctness / data (verify before the tournament progresses)

- 🆕 **Leaderboard per-row expander omits the bonus-question bucket.** The main
  table now reconciles (fixed: `34674b1`), but the expandable per-row detail
  still breaks points down only by Phase I / Phase II and never shows the
  cross-phase `bonus_question_points`. So an expanded row's two phase subtotals
  sum to less than its headline total once award answers are revealed.
  *Incomplete, not contradictory.* Fix: add a "Bonus questions" line/strip to
  the expander (desktop `pn-lb-detail`, mobile `pn-m-lb-detail`), e.g.
  full-width below the two phase blocks.
- 🆕 **Bracket-unlock gate vs. locked-before-prediction matches.** The Phase-1
  knockout bracket unlocks only when *every* group match is predicted. A user
  who registers after some group matches have kicked off sees those as
  "LOCKED · NO EDITS" and can never fill them → the bracket could stay locked
  forever. Unlikely in practice (everyone predicts pre-tournament), but verify
  the gate counts a locked/unpredictable match as "satisfied" rather than
  "outstanding." (Surfaced with a fresh user against the seed's mid-schedule
  "today".)
- 🆕 **Confirm `group_position_points` timing.** A brand-new user with a single
  group prediction received `group_position_points: 5` before the group had
  resolved (consistent across seeded users, so likely interim-standings scoring
  by design). Confirm this is intended — i.e. that group-position points are
  meant to accrue against current standings rather than only final ones.

## UX / polish

- 🆕 **Leaderboard "Total" is overall in every phase tab.** In the Phase I /
  Phase II tabs the category columns switch to that phase, but the Total column
  always shows the overall `total_points`. The position ranking is overall too,
  so it's internally consistent, but a phase tab where columns don't sum to the
  shown Total can read oddly. Decide: per-phase total in phase tabs, or a label
  clarifying "overall".
- ↩ **Results page scroll length.** ~104 fixtures in one scroll (mobile page is
  very tall). The page *does* now have Date/Group sort + All/Played/Live/Locked/
  Open filter chips (good mitigation). Still worth a "jump to today" / matchday
  collapse for the full-tournament view.
- ↩ **Mobile bottom-nav density.** 6 tabs for players, **7 for admins**
  (Home/Predict/Results/Standings/Rules/You/Admin). Fits at 375px and is legible,
  but the admin row is edge-to-edge tight — confirm tap targets on a real handset.

## Resolved / moot since first logged

- ✅ **Empty / first-run states** (was: "couldn't test with seeded data"). Audited
  this round with a brand-new account: dashboard `0/145`, empty progress bars,
  unpaid banner, and the leaderboard zero-state all render cleanly. **Closed.**
- ⛔ **Flag-swatch replacement** (memory + `docs/panini-flag-style-options.md`).
  Moot: the app already renders **real `flag-icons` SVGs** with a Panini filter
  (`PnFlag`/`PnAxisFlag`); the 2/3-stripe gradient placeholder was removed in
  `f35c3e9`. The only fallback is a neutral grey box during async chunk load.
  Drop this from the backlog (and the stale CLAUDE.md "flag swatches are …
  placeholders" line — fix on `main`).

## Fixed during round 2 (for reference, already committed)

_Hashes below are post-rebase (the branch was rebased onto `main` on 2026-05-31,
which rewrote SHAs — match by message if these drift again)._

- `2b8850a` — leaderboard Bonus column now includes `bonus_question_points`
  (Overall view reconciles).
- `00d20f4` — admin console loads on cold load / refresh (data-load auth race;
  the data-load twin of DESIGN-1).
- `d399fe2` — match-detail header navy gap (from the prior design pass).
