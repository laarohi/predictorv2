# Paid-status warning banner & roster name-and-shame — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface entry-fee payment status on the pre-tournament dashboard via a red DwAlert banner (with a Revolut deep-link CTA) for the signed-in user, plus an inline `UNPAID` pill in the players roster for every unpaid player. Both indicators auto-disappear once the tournament starts. Entry fee amount sourced from `config/worldcup2026.yml`.

**Architecture:** YAML becomes the source of truth for `entry_fee`; `/competition/info` reads YAML-first with the existing `Competition.entry_fee` DB column as a fallback. `User.paid` (already exists, admin-managed) starts flowing through `/auth/me` (`UserRead`) and `/users/roster` (`RosterEntry`). `DwAlert` gains a `ctaExternal` flag for the new-tab Revolut link. `DwRoster` learns to render an UNPAID pill. `DashboardPre` glues it all together — fetches `/competition/info` for the amount, fetches the existing roster, renders the banner when the current user has `paid === false`, and passes `paid` through to each roster row. Phase scoping is automatic because both indicators live inside `DashboardPre`, which the page-level dispatcher only mounts during `pre_tournament`.

**Tech Stack:** FastAPI + SQLModel + Pydantic (backend); SvelteKit + TypeScript + Panini CSS modules (frontend); YAML config; pytest unit tests.

**Reference spec:** `docs/superpowers/specs/2026-05-29-paid-status-warning-design.md`

---

## File Structure

### Backend
- `config/worldcup2026.yml` — add `entry_fee: 25` under `tournament:`.
- `backend/app/api/competition.py` — `get_competition_info()` reads YAML-first.
- `backend/app/schemas/auth.py` — `UserRead` gains `paid: bool`.
- `backend/app/api/users.py` — `RosterEntry` gains `paid: bool`, populated from `User.paid`.
- `backend/tests/test_users_api.py` — new test class asserting `RosterEntry.paid` flows through.

### Frontend
- `frontend/src/lib/types/index.ts` — `User` interface gains `paid: boolean`.
- `frontend/src/lib/api/users.ts` — `RosterEntry` interface gains `paid: boolean`.
- `frontend/src/lib/components/panini/dashboard/widgets/DwAlert.svelte` — new `ctaExternal` prop.
- `frontend/src/lib/components/panini/dashboard/widgets/DwRoster.svelte` — `RosterRow` gains `paid?: boolean`; render UNPAID pill.
- `frontend/src/lib/styles/panini-dashboard-v4.css` — UNPAID pill styles inside `.pn-roster`.
- `frontend/src/lib/components/panini/dashboard/DashboardPre.svelte` — fetch `/competition/info`, render the red banner conditionally, pass `paid` through to each `RosterRow`.

No DB migration. No new dependencies.

---

### Task 1: Add `entry_fee` to YAML config

**Files:**
- Modify: `config/worldcup2026.yml` (lines 4-9)

- [ ] **Step 1: Add the YAML key**

Open `config/worldcup2026.yml` and locate the `tournament:` block (top of file, around line 4). Add a single `entry_fee` line under it.

Before:
```yaml
tournament:
  name: "FIFA World Cup 2026"
  year: 2026
  teams: 48
  groups: 12
  teams_per_group: 4
```

After:
```yaml
tournament:
  name: "FIFA World Cup 2026"
  year: 2026
  teams: 48
  groups: 12
  teams_per_group: 4
  entry_fee: 25      # EUR. Drives the pre-tournament payment banner and the rules-page entry-fee display via /competition/info.
```

- [ ] **Step 2: Sanity-check YAML still parses**

Run:
```bash
docker-compose exec backend python -c "from app.config import get_tournament_config; print(get_tournament_config()['tournament']['entry_fee'])"
```
Expected output: `25`

- [ ] **Step 3: Commit**

```bash
git add config/worldcup2026.yml
git commit -m "config(wc2026): expose entry_fee in YAML for payment banner"
```

---

### Task 2: Backend — YAML override for `entry_fee` in `/competition/info`

**Files:**
- Modify: `backend/app/api/competition.py:1-15` (imports), `:62-70` (return value)

- [ ] **Step 1: Add the YAML import at the top of the file**

Open `backend/app/api/competition.py` and add `get_tournament_config` to the imports. The existing import line for `services.scoring` already imports `get_scoring_config` from a different module, so we add a separate line from `app.config`.

Before (line 15):
```python
from app.services.scoring import get_scoring_config
```

After:
```python
from app.config import get_tournament_config
from app.services.scoring import get_scoring_config
```

- [ ] **Step 2: Replace the entry_fee read in `get_competition_info`**

Locate the `return CompetitionInfo(...)` block at the bottom of `get_competition_info` (lines 62-70). Replace the `entry_fee=float(competition.entry_fee)` line with a YAML-first read.

Before:
```python
    return CompetitionInfo(
        name=competition.name,
        entry_fee=float(competition.entry_fee),
        is_phase2_active=competition.is_phase2_active,
        phase1_deadline=competition.phase1_deadline,
        phase2_bracket_deadline=competition.phase2_bracket_deadline,
        total_players=total or 0,
        paid_players=paid or 0,
    )
```

After:
```python
    # YAML is the source of truth for entry_fee — the dashboard payment
    # banner reads this value to render copy AND to build the Revolut URL.
    # The DB column stays as a fallback so the admin's "update competition"
    # form keeps working without a migration.
    yaml_fee = get_tournament_config().get("tournament", {}).get("entry_fee")
    entry_fee = float(yaml_fee) if yaml_fee is not None else float(competition.entry_fee)

    return CompetitionInfo(
        name=competition.name,
        entry_fee=entry_fee,
        is_phase2_active=competition.is_phase2_active,
        phase1_deadline=competition.phase1_deadline,
        phase2_bracket_deadline=competition.phase2_bracket_deadline,
        total_players=total or 0,
        paid_players=paid or 0,
    )
```

- [ ] **Step 3: Restart backend so the YAML reload picks up**

Run:
```bash
docker-compose restart backend
```

Wait for the line `Application startup complete.` in:
```bash
docker-compose logs --tail=20 backend
```

- [ ] **Step 4: Smoke-test `/competition/info`**

Run:
```bash
curl -s http://localhost:8000/api/competition/info | python -m json.tool
```

Expected: response includes `"entry_fee": 25.0` (or `25` depending on JSON formatter). The value should be `25` regardless of whatever is in the `Competition.entry_fee` DB row.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/competition.py
git commit -m "feat(competition): prefer YAML entry_fee over DB column"
```

---

### Task 3: Backend — Add `paid` to `UserRead` (TDD)

**Files:**
- Modify: `backend/app/schemas/auth.py:27-42` (UserRead class)
- Test: `backend/tests/test_users_api.py` (new test class at end of file)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_users_api.py`:

```python
class TestUserReadPaid:
    """UserRead must surface `paid` so the frontend can render the
    pre-tournament payment banner without an extra request."""

    def test_paid_true_flows_through(self):
        from app.schemas.auth import UserRead
        from app.models.user import User, AuthProvider

        user = User(
            email="alice@example.com",
            name="Alice",
            auth_provider=AuthProvider.EMAIL,
            paid=True,
        )
        read = UserRead.model_validate(user)
        assert read.paid is True

    def test_paid_false_flows_through(self):
        from app.schemas.auth import UserRead
        from app.models.user import User, AuthProvider

        user = User(
            email="bob@example.com",
            name="Bob",
            auth_provider=AuthProvider.EMAIL,
            paid=False,
        )
        read = UserRead.model_validate(user)
        assert read.paid is False
```

- [ ] **Step 2: Run the failing test**

Run:
```bash
docker-compose exec backend sh -c "pip install -q pytest pytest-asyncio && pytest tests/test_users_api.py::TestUserReadPaid -v"
```

Expected: FAIL with a Pydantic `ValidationError` or `AttributeError` complaining about the missing `paid` field on `UserRead` (or `paid` being absent from the model).

- [ ] **Step 3: Add `paid` to `UserRead`**

Open `backend/app/schemas/auth.py` and modify the `UserRead` class.

Before (lines 27-42):
```python
class UserRead(BaseModel):
    """Schema for reading user data."""

    id: uuid.UUID
    email: str
    name: str
    auth_provider: AuthProvider
    is_admin: bool
    is_active: bool
    competition_id: uuid.UUID | None
    created_at: datetime

    class Config:
        """Pydantic config."""

        from_attributes = True
```

After:
```python
class UserRead(BaseModel):
    """Schema for reading user data."""

    id: uuid.UUID
    email: str
    name: str
    auth_provider: AuthProvider
    is_admin: bool
    is_active: bool
    paid: bool
    competition_id: uuid.UUID | None
    created_at: datetime

    class Config:
        """Pydantic config."""

        from_attributes = True
```

- [ ] **Step 4: Run the test, confirm it passes**

Run:
```bash
docker-compose exec backend pytest tests/test_users_api.py::TestUserReadPaid -v
```

Expected: 2 passing tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/auth.py backend/tests/test_users_api.py
git commit -m "feat(auth): expose user.paid via /auth/me"
```

---

### Task 4: Backend — Add `paid` to `RosterEntry` (TDD)

**Files:**
- Modify: `backend/app/api/users.py:78-95` (RosterEntry schema)
- Modify: `backend/app/api/users.py:140-149` (population in `get_roster`)
- Test: `backend/tests/test_users_api.py` (new test class)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_users_api.py`:

```python
class TestRosterEntryPaid:
    """RosterEntry exposes `paid` so the dashboard roster can render an
    UNPAID pill next to every unpaid player. Privacy reversal of the
    previous public-safe-only posture is deliberate — see spec for
    rationale."""

    def test_paid_field_required(self):
        """RosterEntry without `paid` must fail validation — guarantees
        future contributors can't accidentally drop the field."""
        import pytest
        from pydantic import ValidationError
        from app.api.users import RosterEntry
        import uuid

        with pytest.raises(ValidationError):
            RosterEntry(
                user_id=uuid.uuid4(),
                name="Alice",
                match_predictions_filled=0,
                bracket_picks_filled=0,
                is_current_user=False,
            )

    def test_paid_true_serializes(self):
        from app.api.users import RosterEntry
        import uuid

        entry = RosterEntry(
            user_id=uuid.uuid4(),
            name="Alice",
            match_predictions_filled=3,
            bracket_picks_filled=2,
            is_current_user=False,
            paid=True,
        )
        assert entry.paid is True

    def test_paid_false_serializes(self):
        from app.api.users import RosterEntry
        import uuid

        entry = RosterEntry(
            user_id=uuid.uuid4(),
            name="Bob",
            match_predictions_filled=0,
            bracket_picks_filled=0,
            is_current_user=False,
            paid=False,
        )
        assert entry.paid is False
```

- [ ] **Step 2: Run the failing test**

Run:
```bash
docker-compose exec backend pytest tests/test_users_api.py::TestRosterEntryPaid -v
```

Expected: 3 failures — the `paid` field doesn't exist yet, so `RosterEntry(paid=True)` raises and `test_paid_field_required` does NOT raise.

- [ ] **Step 3: Add `paid` to `RosterEntry` and populate it in `get_roster`**

Open `backend/app/api/users.py`. First, modify the `RosterEntry` class.

Before (lines 78-91):
```python
class RosterEntry(BaseModel):
    """One row of the pre-tournament registered-users roster.

    Fields are deliberately narrow — no email, no paid status, no
    auth_provider. Anything in here is visible to every authenticated
    user; treat it the same way as the public leaderboard.
    """

    user_id: uuid.UUID
    name: str
    match_predictions_filled: int
    bracket_picks_filled: int
    is_current_user: bool
```

After:
```python
class RosterEntry(BaseModel):
    """One row of the pre-tournament registered-users roster.

    Paid status is intentionally surfaced — small private competition
    where the admin's paid-toggle decisions are visible to all
    participants. The dashboard roster renders an UNPAID pill next
    to every unpaid player. Email, auth_provider, and other private
    fields are still excluded.
    """

    user_id: uuid.UUID
    name: str
    match_predictions_filled: int
    bracket_picks_filled: int
    is_current_user: bool
    paid: bool
```

Then modify the list comprehension that builds `entries` inside `get_roster`.

Before (lines 140-149):
```python
    entries = [
        RosterEntry(
            user_id=u.id,
            name=u.name,
            match_predictions_filled=match_counts.get(u.id, 0),
            bracket_picks_filled=bracket_counts.get(u.id, 0),
            is_current_user=(u.id == current_user.id),
        )
        for u in users
    ]
```

After:
```python
    entries = [
        RosterEntry(
            user_id=u.id,
            name=u.name,
            match_predictions_filled=match_counts.get(u.id, 0),
            bracket_picks_filled=bracket_counts.get(u.id, 0),
            is_current_user=(u.id == current_user.id),
            paid=u.paid,
        )
        for u in users
    ]
```

- [ ] **Step 4: Run the tests, confirm they pass**

Run:
```bash
docker-compose exec backend pytest tests/test_users_api.py::TestRosterEntryPaid -v
```

Expected: 3 passing tests.

- [ ] **Step 5: Restart backend and smoke-test `/users/roster`**

Run:
```bash
docker-compose restart backend
```

Wait for startup, then hit the endpoint via a logged-in browser session OR via curl with a token. Quick browser check: open the dashboard in dev mode, open DevTools → Network, refresh, find the `/api/users/roster` response, and confirm each entry has a `paid` boolean.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/users.py backend/tests/test_users_api.py
git commit -m "feat(users): expose paid status in /users/roster"
```

---

### Task 5: Frontend — Add `paid` to `User` TS type

**Files:**
- Modify: `frontend/src/lib/types/index.ts:7-16` (User interface)

- [ ] **Step 1: Modify the `User` interface**

Open `frontend/src/lib/types/index.ts`.

Before (lines 7-16):
```typescript
export interface User {
	id: string;
	email: string;
	name: string;
	auth_provider: 'email' | 'google';
	is_admin: boolean;
	is_active: boolean;
	competition_id: string | null;
	created_at: string;
}
```

After:
```typescript
export interface User {
	id: string;
	email: string;
	name: string;
	auth_provider: 'email' | 'google';
	is_admin: boolean;
	is_active: boolean;
	paid: boolean;
	competition_id: string | null;
	created_at: string;
}
```

- [ ] **Step 2: Run svelte-check to confirm no regressions**

Run:
```bash
docker-compose exec frontend-dev npm run check
```

Expected: 0 errors. Pre-existing warning count (~59) may rise by 0 since this is a new optional-feeling field on an existing interface, no consumer asserts the absence of `paid`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/types/index.ts
git commit -m "feat(types): add paid to User interface"
```

---

### Task 6: Frontend — Add `paid` to `RosterEntry` TS interface

**Files:**
- Modify: `frontend/src/lib/api/users.ts:17-23` (RosterEntry interface)

- [ ] **Step 1: Modify the `RosterEntry` interface**

Open `frontend/src/lib/api/users.ts`.

Before (lines 17-23):
```typescript
export interface RosterEntry {
	user_id: string;
	name: string;
	match_predictions_filled: number;
	bracket_picks_filled: number;
	is_current_user: boolean;
}
```

After:
```typescript
export interface RosterEntry {
	user_id: string;
	name: string;
	match_predictions_filled: number;
	bracket_picks_filled: number;
	is_current_user: boolean;
	paid: boolean;
}
```

- [ ] **Step 2: Run svelte-check**

Run:
```bash
docker-compose exec frontend-dev npm run check
```

Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/api/users.ts
git commit -m "feat(api): mirror RosterEntry.paid in TS interface"
```

---

### Task 7: Frontend — Extend `DwAlert` with `ctaExternal`

**Files:**
- Modify: `frontend/src/lib/components/panini/dashboard/widgets/DwAlert.svelte`

- [ ] **Step 1: Add `ctaExternal` prop and wire it into the anchor**

Open `frontend/src/lib/components/panini/dashboard/widgets/DwAlert.svelte`.

Before:
```svelte
<script lang="ts">
	/**
	 * Banner alert at the top of phase dashboards.
	 *
	 *   variant="gold" — informational, non-urgent (unsaved predictions,
	 *                    bracket has unsaved changes)
	 *   variant="red"  — urgent (KO matches missing predictions; next lock
	 *                    is soon)
	 *
	 * Slot the CTA via the `cta` snippet — the alert lays it out on the
	 * right edge.
	 */
	export let variant: 'gold' | 'red' = 'gold';
	/** Title rendered next to the icon. */
	export let title: string = '';
	/** Meta line below the title (raw HTML allowed for inline <b>). */
	export let meta: string = '';
	/** Icon glyph in the tilted box. Default "!" for either variant. */
	export let icon: string = '!';
	/** CTA button label. Empty string hides the button. */
	export let ctaLabel: string = '';
	export let ctaHref: string | null = null;
	export let onCta: (() => void) | null = null;
</script>

<div class="pn-alert-v4" class:red={variant === 'red'}>
	<div class="ico">{icon}</div>
	<div class="copy">
		<div class="ttl">{title}</div>
		<div class="meta">{@html meta}</div>
	</div>

	{#if ctaLabel}
		{#if ctaHref}
			<a class="pn-btn" class:gold={variant === 'gold'} href={ctaHref}>{ctaLabel}</a>
		{:else}
			<button class="pn-btn" class:gold={variant === 'gold'} on:click={() => onCta?.()}>
				{ctaLabel}
			</button>
		{/if}
	{/if}
</div>
```

After:
```svelte
<script lang="ts">
	/**
	 * Banner alert at the top of phase dashboards.
	 *
	 *   variant="gold" — informational, non-urgent (unsaved predictions,
	 *                    bracket has unsaved changes)
	 *   variant="red"  — urgent (KO matches missing predictions; next lock
	 *                    is soon)
	 *
	 * Slot the CTA via the `cta` snippet — the alert lays it out on the
	 * right edge. Set ctaExternal=true to open the CTA href in a new tab
	 * (used for off-site links like the Revolut payment URL).
	 */
	export let variant: 'gold' | 'red' = 'gold';
	/** Title rendered next to the icon. */
	export let title: string = '';
	/** Meta line below the title (raw HTML allowed for inline <b>). */
	export let meta: string = '';
	/** Icon glyph in the tilted box. Default "!" for either variant. */
	export let icon: string = '!';
	/** CTA button label. Empty string hides the button. */
	export let ctaLabel: string = '';
	export let ctaHref: string | null = null;
	/** When true and ctaHref is set, opens the link in a new tab. */
	export let ctaExternal: boolean = false;
	export let onCta: (() => void) | null = null;
</script>

<div class="pn-alert-v4" class:red={variant === 'red'}>
	<div class="ico">{icon}</div>
	<div class="copy">
		<div class="ttl">{title}</div>
		<div class="meta">{@html meta}</div>
	</div>

	{#if ctaLabel}
		{#if ctaHref}
			<a
				class="pn-btn"
				class:gold={variant === 'gold'}
				href={ctaHref}
				target={ctaExternal ? '_blank' : undefined}
				rel={ctaExternal ? 'noopener noreferrer' : undefined}
			>
				{ctaLabel}
			</a>
		{:else}
			<button class="pn-btn" class:gold={variant === 'gold'} on:click={() => onCta?.()}>
				{ctaLabel}
			</button>
		{/if}
	{/if}
</div>
```

- [ ] **Step 2: Run svelte-check**

Run:
```bash
docker-compose exec frontend-dev npm run check
```

Expected: 0 errors. Existing callers of `DwAlert` don't pass `ctaExternal`, so they get the `false` default and behaviour is unchanged.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/components/panini/dashboard/widgets/DwAlert.svelte
git commit -m "feat(dw-alert): add ctaExternal prop for off-site CTAs"
```

---

### Task 8: Frontend — Add UNPAID pill to `DwRoster` + CSS

**Files:**
- Modify: `frontend/src/lib/components/panini/dashboard/widgets/DwRoster.svelte`
- Modify: `frontend/src/lib/styles/panini-dashboard-v4.css` (insert after line 1326)

- [ ] **Step 1: Add `paid` to `RosterRow` type and render the pill inside `td.nm`**

Open `frontend/src/lib/components/panini/dashboard/widgets/DwRoster.svelte`.

Before:
```svelte
<script context="module" lang="ts">
	export type RosterRow = {
		position: string;
		name: string;
		handle: string;
		filled: number;
		total: number;
		isCurrentUser?: boolean;
	};
</script>

<script lang="ts">
	/**
	 * Pre-tournament players roster. Three columns:
	 *   #  |  Player + handle  |  Progress (filled/total) + pip
	 *
	 * The "you" row gets red name colour. A solid pip means the player has
	 * fully completed predictions; faded pip means partial.
	 */
	export let title: string = '';
	export let meta: string = '';
	export let rows: RosterRow[] = [];

	function isFull(r: RosterRow): boolean {
		return r.total > 0 && r.filled >= r.total;
	}
</script>

<div class="pn-roster">
	<div class="hd">
		<span>{title}</span>
		<span class="right">{meta}</span>
	</div>
	<div class="roster-scroll">
		<table>
			<thead>
				<tr>
					<th>#</th>
					<th>Player</th>
					<th class="r">Progress</th>
				</tr>
			</thead>
			<tbody>
				{#each rows as r (r.position)}
					<tr>
						<td class="pos">{r.position}</td>
						<td class="nm" class:you={r.isCurrentUser}>
							{r.name}<span class="h">{r.handle}</span>
						</td>
						<td class="r prog">
							<span class="pip" class:empty={!isFull(r)}></span>
							{r.filled} / {r.total}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</div>
```

After:
```svelte
<script context="module" lang="ts">
	export type RosterRow = {
		position: string;
		name: string;
		handle: string;
		filled: number;
		total: number;
		isCurrentUser?: boolean;
		/** Undefined while data is loading; explicit false means show UNPAID. */
		paid?: boolean;
	};
</script>

<script lang="ts">
	/**
	 * Pre-tournament players roster. Three columns:
	 *   #  |  Player + handle (+ UNPAID pill if unpaid)  |  Progress
	 *
	 * The "you" row gets red name colour. A solid pip means the player has
	 * fully completed predictions; faded pip means partial. Players with
	 * paid === false get a small UNPAID pill inline with their name —
	 * name-and-shame for the pre-tournament dashboard. Paid players get
	 * no pill (no positive-badge noise).
	 */
	export let title: string = '';
	export let meta: string = '';
	export let rows: RosterRow[] = [];

	function isFull(r: RosterRow): boolean {
		return r.total > 0 && r.filled >= r.total;
	}
</script>

<div class="pn-roster">
	<div class="hd">
		<span>{title}</span>
		<span class="right">{meta}</span>
	</div>
	<div class="roster-scroll">
		<table>
			<thead>
				<tr>
					<th>#</th>
					<th>Player</th>
					<th class="r">Progress</th>
				</tr>
			</thead>
			<tbody>
				{#each rows as r (r.position)}
					<tr>
						<td class="pos">{r.position}</td>
						<td class="nm" class:you={r.isCurrentUser}>
							{r.name}{#if r.paid === false}<span class="paid-pill unpaid">UNPAID</span>{/if}<span class="h">{r.handle}</span>
						</td>
						<td class="r prog">
							<span class="pip" class:empty={!isFull(r)}></span>
							{r.filled} / {r.total}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</div>
```

- [ ] **Step 2: Add the UNPAID pill CSS**

Open `frontend/src/lib/styles/panini-dashboard-v4.css` and locate the line:
```css
.pn .pn-roster tr:nth-child(even) td { background: rgba(0, 0, 0, 0.02); }
```

Immediately after that line (around line 1326), insert the UNPAID pill block (BEFORE the `/* GROUP-STAGE SKINNY STRIP (Phase 2) */` comment block):

```css
.pn .pn-roster td.nm .paid-pill {
	display: inline-block;
	margin-left: 6px;
	padding: 1px 5px;
	font-family: var(--mono);
	font-size: 9px;
	font-weight: 600;
	letter-spacing: 0.08em;
	text-transform: uppercase;
	vertical-align: middle;
	border-radius: 2px;
}
.pn .pn-roster td.nm .paid-pill.unpaid {
	color: var(--red-deep);
	background: var(--paper-3);
	border: 1.5px solid var(--red-deep);
}
```

- [ ] **Step 3: Run svelte-check**

Run:
```bash
docker-compose exec frontend-dev npm run check
```

Expected: 0 errors. (One or two new CSS warnings from the unused-class checker may appear if the Svelte template hasn't yet wired the conditional render — verify that the warning count hasn't risen by more than 1-2.)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/components/panini/dashboard/widgets/DwRoster.svelte frontend/src/lib/styles/panini-dashboard-v4.css
git commit -m "feat(dw-roster): UNPAID name-and-shame pill"
```

---

### Task 9: Frontend — Wire banner + `paid` into `DashboardPre`

**Files:**
- Modify: `frontend/src/lib/components/panini/dashboard/DashboardPre.svelte`

- [ ] **Step 1: Add imports for competition info**

Open `frontend/src/lib/components/panini/dashboard/DashboardPre.svelte` and add the competition info import next to the existing user/roster imports.

Locate the existing import group (around line 36):
```typescript
	import { getRoster, type RosterResponse } from '$api/users';
	import { getBonusQuestions, getMyBonusPredictions } from '$api/bonus';
```

Replace with:
```typescript
	import { getRoster, type RosterResponse } from '$api/users';
	import { getBonusQuestions, getMyBonusPredictions } from '$api/bonus';
	import { getCompetitionInfo, type CompetitionInfo } from '$api/competition';
```

- [ ] **Step 2: Add the `info` state variable**

Locate the `let rosterResp: RosterResponse | null = null;` declaration (around line 40) and add a sibling `info` variable directly below it.

Before:
```typescript
	let rosterResp: RosterResponse | null = null;
```

After:
```typescript
	let rosterResp: RosterResponse | null = null;
	let info: CompetitionInfo | null = null;
```

- [ ] **Step 3: Fetch competition info inside `onMount`**

Locate the existing roster-fetch try/catch inside `onMount` (around lines 52-56):
```typescript
		try {
			rosterResp = await getRoster();
		} catch {
			rosterResp = null;
		}
```

Replace with a parallel fetch of both roster and competition info:
```typescript
		// Roster + competition info fetched in parallel — they're independent
		// requests and the banner can render without the roster.
		const [rosterResult, infoResult] = await Promise.allSettled([
			getRoster(),
			getCompetitionInfo(),
		]);
		rosterResp = rosterResult.status === 'fulfilled' ? rosterResult.value : null;
		info = infoResult.status === 'fulfilled' ? infoResult.value : null;
```

- [ ] **Step 4: Derive `entryFee` and `revolutUrl` from `info`**

Locate the `$: countdown = (() => {` block (around line 93) and add the payment-related reactive declarations directly above it.

Before:
```typescript
	$: countdown = (() => {
```

After:
```typescript
	// Entry fee comes from /competition/info (YAML-backed). Fall back to 25
	// before the fetch resolves so the banner copy and the Revolut URL stay
	// sensible during the first render. EUR is the only supported currency.
	$: entryFee = info?.entry_fee ?? 25;
	$: revolutUrl = `https://revolut.me/laarohi?currency=EUR&amount=${Math.round(entryFee * 100)}&note=World%20Cup%20Predictor`;

	$: countdown = (() => {
```

- [ ] **Step 5: Pass `paid` into `RosterRow`**

Locate the roster rows builder (around lines 108-134):
```typescript
	$: rosterRows = (() => {
		if (rosterResp) {
			return rosterResp.entries.map((e, i) => ({
				position: String(i + 1).padStart(2, '0'),
				name: e.name,
				handle: e.is_current_user
					? 'YOU'
					: `@${e.name.split(' ')[0].toLowerCase()}`,
				filled: e.match_predictions_filled + e.bracket_picks_filled,
				total: overallTotal,
				isCurrentUser: e.is_current_user
			}));
		}
		if ($user) {
			return [
				{
					position: '01',
					name: $user.name ?? 'You',
					handle: 'YOU',
					filled: overallFilled,
					total: overallTotal,
					isCurrentUser: true
				}
			];
		}
		return [];
	})();
```

Replace with the same logic plus `paid` propagation:
```typescript
	$: rosterRows = (() => {
		if (rosterResp) {
			return rosterResp.entries.map((e, i) => ({
				position: String(i + 1).padStart(2, '0'),
				name: e.name,
				handle: e.is_current_user
					? 'YOU'
					: `@${e.name.split(' ')[0].toLowerCase()}`,
				filled: e.match_predictions_filled + e.bracket_picks_filled,
				total: overallTotal,
				isCurrentUser: e.is_current_user,
				paid: e.paid
			}));
		}
		if ($user) {
			return [
				{
					position: '01',
					name: $user.name ?? 'You',
					handle: 'YOU',
					filled: overallFilled,
					total: overallTotal,
					isCurrentUser: true,
					paid: $user.paid
				}
			];
		}
		return [];
	})();
```

- [ ] **Step 6: Render the payment banner above the existing gold alert**

Locate the existing DwAlert call inside the template (around lines 148-156):
```svelte
	<div class="pn-dash-v4">
		{#if overallFilled < overallTotal && overallFilled > 0}
			<DwAlert
				variant="gold"
				title={`${overallTotal - overallFilled} predictions still to fill`}
				meta="Lock in before the whistle · <b>switch devices &amp; partial drafts are gone</b>"
				ctaLabel="Open predictions →"
				ctaHref="/predictions"
			/>
		{/if}
```

Replace with the same alert preceded by the payment banner:
```svelte
	<div class="pn-dash-v4">
		{#if $user && $user.paid === false}
			<DwAlert
				variant="red"
				icon="€"
				title="Entry fee unpaid"
				meta={`Send <b>€${entryFee}</b> to <b>+356 9929 0197</b> on Revolut before the competition starts.`}
				ctaLabel={`Pay €${entryFee} now`}
				ctaHref={revolutUrl}
				ctaExternal
			/>
		{/if}

		{#if overallFilled < overallTotal && overallFilled > 0}
			<DwAlert
				variant="gold"
				title={`${overallTotal - overallFilled} predictions still to fill`}
				meta="Lock in before the whistle · <b>switch devices &amp; partial drafts are gone</b>"
				ctaLabel="Open predictions →"
				ctaHref="/predictions"
			/>
		{/if}
```

- [ ] **Step 7: Run svelte-check**

Run:
```bash
docker-compose exec frontend-dev npm run check
```

Expected: 0 errors. Warning count should not rise by more than ~2.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/lib/components/panini/dashboard/DashboardPre.svelte
git commit -m "feat(dashboard-pre): payment banner + paid status in roster"
```

---

### Task 10: Manual smoke verification

**Files:** none modified

- [ ] **Step 1: Ensure dev environment is up**

Run:
```bash
docker-compose up -d
docker-compose --profile dev up -d frontend-dev
```

Wait until `docker-compose logs --tail=10 backend` shows `Application startup complete.` and `docker-compose logs --tail=10 frontend-dev` shows a Vite-ready line.

- [ ] **Step 2: Set up two test users (one paid, one unpaid)**

Via the admin panel at `http://localhost:5173/admin`, ensure there are at least two registered active users. Mark one as paid, leave one (your test user) as unpaid. Alternatively, set the values directly with SQL:

```bash
docker-compose exec backend python -c "
import asyncio
from sqlmodel import select
from app.database import get_session_factory
from app.models.user import User

async def main():
    async with get_session_factory()() as s:
        users = (await s.execute(select(User).where(User.is_active == True))).scalars().all()
        for u in users[:1]:
            u.paid = True
        for u in users[1:2]:
            u.paid = False
        await s.commit()
        for u in users[:2]:
            print(u.name, 'paid=', u.paid)

asyncio.run(main())
"
```

- [ ] **Step 3: Sign in as the UNPAID test user**

Open `http://localhost:5173` in a browser. Sign in as the unpaid user. Land on the dashboard. Verify:

1. **Red banner is visible at the top**, with:
   - icon `€`
   - title "Entry fee unpaid"
   - meta "Send €25 to +356 9929 0197 on Revolut before the competition starts."
   - button "Pay €25 now"
2. **UNPAID pill** appears next to the unpaid test user's name in the roster.
3. **No UNPAID pill** appears next to the paid test user's name.
4. **No PAID pill** appears anywhere.

- [ ] **Step 4: Click "Pay €25 now"**

Click the CTA. Verify it opens a new tab to `https://revolut.me/laarohi?currency=EUR&amount=2500&note=World%20Cup%20Predictor`. (You don't need to actually pay — just confirm the URL.)

- [ ] **Step 5: Sign in as the PAID test user**

Sign out, sign in as the user you marked paid. Verify:

1. **No red banner** at the top of the dashboard.
2. **No UNPAID pill** next to their own name.
3. The unpaid user(s) in the roster still show UNPAID pills.

- [ ] **Step 6: Verify phase scoping (optional but recommended)**

If you can advance the phase (admin → "Advance to group stage" or similar), do so and reload as the unpaid user. The `DashboardPre` should no longer be the active dashboard at all — `DashGroupStage` (or whichever phase replaced pre_tournament) renders instead, and neither the banner nor the UNPAID pill is visible (because they live exclusively inside `DashboardPre`).

If you don't want to mutate phase state for this verification, the same outcome can be confirmed by inspecting `frontend/src/routes/+page.svelte:33-39` and noting that `DashboardPre` is only mounted when `$uxPhase === 'pre_tournament'`.

- [ ] **Step 7: Reset test users if needed**

If you toggled paid state for verification, restore it to what production should look like. (For dev, leaving the test users mixed is fine.)

---

## Self-Review Notes

- **Spec coverage:**
  - Banner on unpaid users → Task 9 step 6.
  - Revolut deep-link new-tab CTA → Tasks 7 + 9.
  - Roster name-and-shame for every unpaid player regardless of progress → Task 8 (renders when `r.paid === false`, no progress check).
  - Phase scoping (auto via `DashboardPre` routing) → covered by architecture, verified in Task 10 step 6.
  - YAML-configurable amount → Tasks 1 + 2.
  - Backend `paid` exposure on `UserRead` and `RosterEntry` → Tasks 3 + 4.
  - Frontend type mirroring → Tasks 5 + 6.
- **Placeholder scan:** no TBDs, all code blocks contain real content, all commands are concrete.
- **Type consistency:** `paid: bool` (Python) / `paid: boolean` (TS) used consistently. `entryFee` (camelCase) is a frontend-only derived value, never sent to backend. `revolutUrl` derived from `entryFee`. `ctaExternal` matches between `DwAlert` prop and `DashboardPre` call site.
