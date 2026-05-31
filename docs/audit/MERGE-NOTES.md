# Merge Notes — READ BEFORE MERGING `worktree-ultra` INTO `main`

_From the round-2 MCP walkthrough audit (2026-05-31). This is a **pre-merge**
concern, not a post-launch one — see [deferred.md](./deferred.md) for the
post-launch backlog._

## 🔴 The worktree is one commit behind `main` on the awards feature

`worktree-ultra` branched from `main` at **`bfb5657`** ("feat(dashboard-pre):
payment banner…"). The **very next** commit on `main`, **`9316ce6`**
("feat(bonus): searchable player dropdowns for award questions"), is **not in
the worktree**. That commit added:

- `frontend/src/lib/components/panini/PnCombobox.svelte` (the searchable player picker)
- `GET /api/predictions/bonus/players` consumption + `frontend/src/lib/api/bonus.ts` additions
- the searchable picker in the **admin** bonus-answer UI
- `backend/app/models/player.py`, `backend/scripts/sync_squads.py`, the `players` table migration

**Consequence:** on the worktree, the awards questions (Golden Ball/Boot/Boy/
Glove) and the admin answer-key still use a **plain free-text `<input>`**.
`main` already has the good searchable dropdown. **Production is fine** — this
is purely a worktree artifact. Do **not** let a wholesale merge revert `main`'s
`9316ce6`.

## Conflict hotspots

Exactly **three files** were changed by *both* the audit and `9316ce6`. Cherry-
picking the audit commits below onto `main` will conflict on these; resolve by
**keeping `main`'s `PnCombobox` / players-endpoint / admin-search code** and
layering the audit change on top.

| File | Audit commit(s) that touch it | What the audit change is | Resolve by |
|---|---|---|---|
| `frontend/src/routes/predictions/+page.svelte` | `e3ea3e3` | FLOW-7/8: unify Phase II save + surface save errors | keep main's `PnCombobox` awards block; re-apply the save-error handling |
| `frontend/src/routes/admin/+page.svelte` | `c2f62b7` (DESIGN-1 guard), **`812bceb`** (round-2 cold-load fix) | auth-resolved guards + reactive admin data load | keep main's admin bonus search; re-apply the `authResolved`/reactive-load logic |
| `backend/app/api/predictions.py` | `9f0afaf` (INJ caps), `84107c8` (agreements gate) | input-size caps + blind-pool gate | keep main's `/bonus/players` endpoint; re-apply both security changes |

The other ~50 audit commits touch files `main` did not change since `bfb5657`
→ they cherry-pick cleanly.

## Recommended approach

**Option A (cleanest): rebase `worktree-ultra` onto current `main`** before
cherry-picking. Git replays the audit commits on top of `9316ce6`; you resolve
the 3-file conflicts once, in context, and everything downstream is clean. After
the rebase, re-run `npm run check`, `vitest`, and `pytest`.

**Option B: cherry-pick individually** (the original plan). The ~50 clean
commits apply with no fuss; the 4 commits in the table will stop with a
conflict — resolve each keeping main's PnCombobox-related lines.

Either way, after merging, **spot-check the awards questions and the admin
answer-key still render the searchable `PnCombobox`**, not a bare text box.
