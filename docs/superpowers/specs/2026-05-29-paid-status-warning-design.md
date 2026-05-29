# Paid-status warning & roster name-and-shame — design

**Date:** 2026-05-29
**Status:** Approved (pending user spec review)

## Problem

Players who haven't paid the €25 entry fee currently get no visible cue inside
the app. The only place paid status surfaces is the admin panel, which is
hidden from regular players. As Phase 1 lock approaches, the admin has no
in-app lever to nudge unpaid players, and players themselves cannot tell from
the dashboard whether they still owe money.

## Goals

1. **Banner.** While the user is on the pre-tournament dashboard and has not
   paid, show a red alert at the top with a one-click "Pay €X now" button
   that opens Revolut in a new tab, pre-filled with amount and note.
2. **Roster name-and-shame.** In the players roster on the same dashboard,
   show an `UNPAID` pill next to any active player who hasn't paid,
   regardless of prediction progress. Paid players get no badge.
3. **Phase scoping.** Both indicators disappear automatically once the
   tournament starts (i.e. once the dashboard transitions out of
   `pre_tournament`). This is to keep the dashboard clean once payment can no
   longer materially change the user's standing.
4. **Configurable amount.** The €25 figure lives in
   `config/worldcup2026.yml` so a future tournament can change it without a
   code edit. Currency is always EUR.

## Non-goals

- No automated payment confirmation. Admin keeps toggling `paid` manually
  after funds land in their Revolut account (existing workflow).
- No PAID badge in the roster. The signal is "you owe money" — a positive
  badge for paying players adds visual noise without solving a problem.
- No payment reminder emails, pushes, or in-app notifications. The banner is
  the only nudge.
- Revolut handle (`laarohi`), phone number, and note text remain hard-coded.
  Only the amount is YAML-driven. The handle is tied to the admin's personal
  Revolut account, not a per-tournament concern.

## Architecture & data flow

### Existing state we're building on

- `User.paid: bool` (default false) already exists at
  `backend/app/models/user.py:39`.
- Admin toggle endpoint `PATCH /admin/users/{user_id}/paid` already exists at
  `backend/app/api/admin.py:244`.
- `Competition.entry_fee` already exists as a Decimal DB column at
  `backend/app/models/competition.py:25` (default `0.00`). Currently
  populated only when admin updates competition settings; not driven from
  YAML.
- `/competition/info` already returns `entry_fee` and `paid_players` at
  `backend/app/api/competition.py:21`, and the rules page already reads it.
- The pre-tournament dashboard is `DashboardPre.svelte` at
  `frontend/src/lib/components/panini/dashboard/DashboardPre.svelte`. The
  routing in `frontend/src/routes/+page.svelte:33-39` only mounts it when
  `$uxPhase === 'pre_tournament'`.
- `DwAlert.svelte` already supports red/gold variants with title + meta +
  CTA. It currently renders the CTA as a same-tab `<a href>`.
- `DwRoster.svelte` already renders 3 columns: position, name+handle,
  progress (`filled/total` + pip).
- The current user's profile is fetched via `GET /auth/me` returning
  `UserRead` from `backend/app/schemas/auth.py:27`. `UserRead` does **not**
  currently include `paid`.
- `RosterEntry` at `backend/app/api/users.py:78` deliberately omits `paid`
  with a comment: "no email, no paid status, no auth_provider. Anything in
  here is visible to every authenticated user". This privacy posture is the
  one we're consciously reversing for a 30-friend competition.

### Changes

#### Backend

1. **`config/worldcup2026.yml`** — add to the `tournament:` section:
   ```yaml
   tournament:
     name: "FIFA World Cup 2026"
     year: 2026
     teams: 48
     groups: 12
     teams_per_group: 4
     entry_fee: 25      # EUR, used by the dashboard payment banner and rules page
   ```

2. **`backend/app/api/competition.py`** — `get_competition_info()` reads
   `entry_fee` from YAML when present, falls back to `competition.entry_fee`
   (the DB row) otherwise:
   ```python
   from app.config import get_tournament_config

   yaml_fee = (
       get_tournament_config().get("tournament", {}).get("entry_fee")
   )
   fee = float(yaml_fee) if yaml_fee is not None else float(competition.entry_fee)
   ```
   YAML wins because it's the new source of truth. The DB column stays as a
   fallback so existing test fixtures and the admin "update competition"
   path keep working without a migration.

3. **`backend/app/schemas/auth.py`** — add `paid: bool` to `UserRead`. No
   migration needed (the column already exists on `User`).

4. **`backend/app/api/users.py`**:
   - Add `paid: bool` to `RosterEntry`.
   - Populate it from `u.paid` in the list comprehension building `entries`.
   - Update the "no paid status" comment to: "paid status intentionally
     surfaced — small private competition; the admin's paid-toggle decisions
     are visible to all participants".

5. **Tests**:
   - `backend/tests/test_users_api.py` — there is no existing roster test.
     Add a new test that creates one paid + one unpaid active user, hits
     `GET /users/roster`, and asserts `paid` flows through correctly for
     both rows.
   - If there's an existing test for `/competition/info`, extend it to
     assert YAML overrides DB. Otherwise skip — the YAML override is a
     one-line read with a fallback and not worth a new test file.

#### Frontend

6. **`frontend/src/lib/types/index.ts`** — add `paid: boolean` to `User`.

7. **`frontend/src/lib/api/users.ts`** — add `paid: boolean` to
   `RosterEntry`.

8. **`frontend/src/lib/components/panini/dashboard/widgets/DwAlert.svelte`**
   — add `export let ctaExternal: boolean = false`. When true and `ctaHref`
   is set, render the anchor with `target="_blank" rel="noopener noreferrer"`.

9. **`frontend/src/lib/components/panini/dashboard/widgets/DwRoster.svelte`**:
   - Add `paid?: boolean` to the exported `RosterRow` type.
   - In the row template, after `{r.name}<span class="h">{r.handle}</span>`,
     render the pill **only when `r.paid === false`**:
     ```svelte
     {#if r.paid === false}
       <span class="paid-pill unpaid">UNPAID</span>
     {/if}
     ```
     PAID users get no pill (per name-and-shame rule). `paid === undefined`
     also skips the pill — defensive against an old token paired with a
     pre-deploy backend.

10. **`frontend/src/lib/components/panini/dashboard/DashboardPre.svelte`**:
    - Import `getCompetitionInfo` from `$api/competition` (or pull from an
      existing store if one already memoises it).
    - On mount, fetch competition info alongside the existing roster fetch.
    - Compute `entryFee = info?.entry_fee ?? 25` (fallback so the banner
      renders sensibly before the fetch resolves).
    - Compute `revolutUrl = `https://revolut.me/laarohi?currency=EUR&amount=${Math.round(entryFee * 100)}&note=World%20Cup%20Predictor``.
    - When `$user?.paid === false`, render a `<DwAlert>` *above* the
      existing gold "predictions still to fill" alert:
      ```svelte
      <DwAlert
        variant="red"
        icon="€"
        title="Entry fee unpaid"
        meta={`Send <b>€${entryFee}</b> to <b>+356 9929 0197</b> on Revolut before the competition starts.`}
        ctaLabel={`Pay €${entryFee} now`}
        ctaHref={revolutUrl}
        ctaExternal
      />
      ```
    - Pass `paid: e.paid` through into each `RosterRow` in the existing
      `rosterRows` reactive block.

11. **`frontend/src/lib/styles/panini-dashboard-v4.css`** — add styles under
    `.pn-roster`:
    ```css
    .pn-roster .paid-pill.unpaid {
      display: inline-block;
      margin-left: 8px;
      padding: 1px 6px;
      font: 600 9px/1.4 var(--mono);
      letter-spacing: 0.08em;
      color: var(--red-deep);
      background: var(--paper-3);
      border: 1.5px solid var(--red-deep);
      border-radius: 2px;
      vertical-align: middle;
      text-transform: uppercase;
    }
    ```
    Match the existing roster's typography rhythm; small enough not to
    crowd the name column.

### Phase scoping

Both the banner and the roster pill render only inside `DashboardPre`. The
dispatcher in `frontend/src/routes/+page.svelte:33-39` only mounts
`DashboardPre` when `$uxPhase === 'pre_tournament'`. The instant `uxPhase`
transitions to `group_stage` (i.e. tournament starts), the dashboard swaps
to `DashGroupStage`, and both the banner and the pill disappear by
construction. No explicit phase check is needed at the component level.

## Error handling

- If `/competition/info` fails: fall back to `entryFee = 25` so the banner
  still renders meaningfully. Better to show a slightly-stale amount than
  hide the payment nudge.
- If `/auth/me` is missing `paid` (e.g. an old token paired with a
  pre-deploy backend): treat as `undefined`, do not render the banner.
  Defensive: `$user?.paid === false`, not `!$user?.paid`.
- Revolut URL opening: standard browser behaviour. The hard-coded URL has
  no user-controlled segments (note is fixed; amount is from YAML), so no
  encoding concerns beyond the existing `%20`.

## Testing strategy

- **Backend pytest**:
  - Roster endpoint test: create one paid + one unpaid active user, assert
    both `paid` values flow through into `RosterResponse.entries`.
  - `/auth/me` test (if existing): assert `paid` is in the response shape.
- **Manual frontend smoke**:
  - Sign in as an unpaid user → banner renders, UNPAID pill appears next
    to their own name in the roster (independent of prediction progress).
  - Sign in as a paid user → no banner, no pill anywhere in the roster.
  - Roster shows the right mix of UNPAID pills for the unpaid players in
    the group, and no pills for paid players.
  - Click "Pay €25 now" → opens Revolut in new tab with prefilled amount.
  - Force `uxPhase = 'group_stage'` (admin advance) → both banner and
    pill gone (the whole `DashboardPre` is gone).
- **Vitest**: not strictly required — `DwAlert` and `DwRoster` are simple
  templating; a unit test would mostly assert markup.

## Risks & open questions

- **Privacy reversal.** The existing comment at `backend/app/api/users.py:81`
  is explicit that the roster is public-safe-only. Reversing that for paid
  status is fine in a 30-friend group but does mean every authenticated user
  can see who's a deadbeat. Owner has signed off; recording here so future
  maintainers see the trade-off.
- **DB row entry_fee drift.** With YAML as the new source of truth, the
  `Competition.entry_fee` DB column can drift from YAML. Acceptable: only
  the rules page and the new banner read it, both go through
  `/competition/info`, which now reads YAML-first. The admin "update
  competition" form still writes to the DB row, but the displayed amount
  comes from YAML — a future cleanup could remove the DB column or hide the
  admin field. Out of scope for this change.
- **Pill scope.** UNPAID pill shows for every unpaid player regardless of
  prediction progress — even players who registered and haven't picked
  anything yet get the pill. Per spec — name-and-shame applies to anyone
  on the roster who hasn't paid.

## File touch list

Backend:
- `config/worldcup2026.yml`
- `backend/app/api/competition.py`
- `backend/app/schemas/auth.py`
- `backend/app/api/users.py`
- `backend/tests/test_users_api.py` (new roster test)

Frontend:
- `frontend/src/lib/types/index.ts`
- `frontend/src/lib/api/users.ts`
- `frontend/src/lib/components/panini/dashboard/widgets/DwAlert.svelte`
- `frontend/src/lib/components/panini/dashboard/widgets/DwRoster.svelte`
- `frontend/src/lib/components/panini/dashboard/DashboardPre.svelte`
- `frontend/src/lib/styles/panini-dashboard-v4.css`

No DB migration; no new dependencies.
