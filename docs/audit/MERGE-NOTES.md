# Merge Notes — `worktree-ultra` → `main`

_Round-2 MCP audit (2026-05-31). **The awards-feature merge hazard described in
the original version of this file is RESOLVED** — `worktree-ultra` was rebased
onto `main` on 2026-05-31._

## ✅ Resolved: rebased onto `main`

The worktree had branched one commit before `main`'s `9316ce6`
("feat(bonus): searchable player dropdowns for award questions"), so it lacked
`PnCombobox` + the `/bonus/players` endpoint + the `players` table, and five
audit commits touched the same three files `9316ce6` changed.

`worktree-ultra` has now been **rebased onto current `main`**. Result:

- `main` is an **ancestor** of `worktree-ultra` → history is linear (`main` +
  the audit commits on top). **Merging is a clean fast-forward:**
  `git checkout main && git merge worktree-ultra`.
- `PnCombobox.svelte`, `/api/predictions/bonus/players`, the admin bonus search,
  `players` model + migration + `sync_squads.py` are all **present** (inherited
  from `main`).
- The three former conflict files now carry **both** feature sets — git's 3-way
  merge auto-resolved them because the audit changes (auth guards, the admin
  cold-load fix, input-size caps, the agreements gate) live in different regions
  than `9316ce6`'s additions. Verified by hand + by the suites:
  - `frontend/src/routes/admin/+page.svelte` — PnCombobox award pickers **and**
    the `authResolved` guards + reactive cold-load fix.
  - `frontend/src/routes/predictions/+page.svelte` — PnCombobox awards **and**
    the unified Phase II save / save-error surfacing.
  - `backend/app/api/predictions.py` — `/bonus/players` **and** the input-size
    caps + the `/agreements` blind-pool gate.

## Verification after rebase

- `svelte-check` — **0 errors**, 2 baseline warnings.
- `vitest` — **122 passed**.
- `pytest` — **323 passed, 6 skipped, 0 failed** (run with `config/` + `docs/`
  mounted into the transient backend container).

## Note: commit hashes were rewritten

The rebase gave every audit commit a new SHA. References elsewhere in these audit
docs were written against the pre-rebase hashes; **match commits by their message,
not their SHA.** A safety copy of the pre-rebase tip is at branch
`backup/worktree-ultra-prerebase` (delete once the merge is landed).

## Still to do on `main` after merge (can't be done from a worktree)

- `CLAUDE.md`: "predictions lock **5 minutes** before kickoff" → it's **15**
  (`config/worldcup2026.yml`).
- `CLAUDE.md`: "Flag swatches are **2/3-stripe gradient placeholders**" → they're
  real `flag-icons` SVGs now.
