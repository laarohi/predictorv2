<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { isAuthenticated, user } from '$stores/auth';
	import {
		fetchPhaseStatus,
		isPhase2Active,
		phase1Deadline,
		phase2BracketDeadline,
		phase1Countdown,
		phase2Countdown
	} from '$stores/phase';
	import {
		getAdminStats,
		getCompetitions,
		setPhase1Deadline,
		activatePhase2,
		deactivatePhase2,
		getAllUsers,
		toggleUserAdmin,
		toggleUserActive,
		toggleUserPaid,
		getPaidLocal,
		syncScores,
		type AdminStats,
		type CompetitionAdminView,
		type UserAdminView,
		type SyncScoresResponse
	} from '$lib/api/admin';
	import PnPageShell from '$components/panini/PnPageShell.svelte';

	$: if ($isAuthenticated && !$user?.is_admin) goto('/');
	$: if (!$isAuthenticated) goto('/login');

	let stats: AdminStats | null = null;
	let competitions: CompetitionAdminView[] = [];
	let users: UserAdminView[] = [];
	let loading = true;
	let error: string | null = null;

	let phase1DeadlineDate = '';
	let phase1DeadlineTime = '12:00';
	let settingPhase1 = false;
	let phase1Error: string | null = null;
	let phase1Success: string | null = null;

	let bracketDeadlineDate = '';
	let bracketDeadlineTime = '12:00';
	let activating = false;
	let activationError: string | null = null;
	let activationSuccess: string | null = null;

	let syncing = false;
	let syncResult: SyncScoresResponse | null = null;
	let syncedAt: Date | null = null;
	let syncError: string | null = null;

	let userSearch = '';
	let togglingUserId: string | null = null;
	let userActionError: string | null = null;

	onMount(async () => {
		if ($user?.is_admin) await loadData();
	});

	async function loadData() {
		loading = true;
		error = null;
		try {
			[stats, competitions, users] = await Promise.all([
				getAdminStats(),
				getCompetitions(),
				getAllUsers()
			]);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load admin data';
		} finally {
			loading = false;
		}
	}

	async function handleSyncScores() {
		syncing = true;
		syncResult = null;
		syncError = null;
		try {
			syncResult = await syncScores();
			syncedAt = new Date();
			await loadData();
		} catch (e) {
			syncError = e instanceof Error ? e.message : 'Failed to sync scores';
		} finally {
			syncing = false;
		}
	}

	async function handleToggleAdmin(u: UserAdminView) {
		const action = u.is_admin ? 'remove admin from' : 'grant admin to';
		if (!confirm(`Are you sure you want to ${action} ${u.name}?`)) return;
		togglingUserId = u.id;
		userActionError = null;
		try {
			const updated = await toggleUserAdmin(u.id);
			users = users.map((x) => (x.id === updated.id ? updated : x));
		} catch (e) {
			userActionError = e instanceof Error ? e.message : 'Failed to update admin status';
		} finally {
			togglingUserId = null;
		}
	}

	async function handleTogglePaid(u: UserAdminView) {
		togglingUserId = u.id;
		userActionError = null;
		try {
			const next = await toggleUserPaid(u.id);
			users = users.map((x) => (x.id === u.id ? { ...x, paid: next } : x));
		} catch (e) {
			userActionError = e instanceof Error ? e.message : 'Failed to update paid status';
		} finally {
			togglingUserId = null;
		}
	}

	/** Effective paid state for a user — backend value if present, else localStorage. */
	function paidOf(u: UserAdminView): boolean {
		return u.paid ?? getPaidLocal(u.id);
	}

	async function handleToggleActive(u: UserAdminView) {
		const action = u.is_active ? 'deactivate' : 'reactivate';
		if (!confirm(`Are you sure you want to ${action} ${u.name}?`)) return;
		togglingUserId = u.id;
		userActionError = null;
		try {
			const updated = await toggleUserActive(u.id);
			users = users.map((x) => (x.id === updated.id ? updated : x));
		} catch (e) {
			userActionError = e instanceof Error ? e.message : 'Failed to update active status';
		} finally {
			togglingUserId = null;
		}
	}

	$: filteredUsers = userSearch.trim()
		? users.filter((u) => {
				const q = userSearch.toLowerCase();
				return u.name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q);
			})
		: users;

	async function handleSetPhase1Deadline() {
		if (!phase1DeadlineDate) {
			phase1Error = 'Please select a deadline date';
			return;
		}
		settingPhase1 = true;
		phase1Error = null;
		phase1Success = null;
		try {
			const deadline = `${phase1DeadlineDate}T${phase1DeadlineTime}:00`;
			const result = await setPhase1Deadline(deadline);
			phase1Success = `Phase 1 deadline set: ${new Date(result.deadline).toLocaleString()}`;
			await Promise.all([loadData(), fetchPhaseStatus()]);
		} catch (e) {
			phase1Error = e instanceof Error ? e.message : 'Failed to set Phase 1 deadline';
		} finally {
			settingPhase1 = false;
		}
	}

	async function handleActivatePhase2() {
		if (!bracketDeadlineDate) {
			activationError = 'Please select a deadline date';
			return;
		}
		activating = true;
		activationError = null;
		activationSuccess = null;
		try {
			const deadline = `${bracketDeadlineDate}T${bracketDeadlineTime}:00`;
			const result = await activatePhase2(deadline);
			activationSuccess = `Phase 2 activated! Bracket deadline: ${new Date(result.bracket_deadline).toLocaleString()}`;
			await Promise.all([loadData(), fetchPhaseStatus()]);
		} catch (e) {
			activationError = e instanceof Error ? e.message : 'Failed to activate Phase 2';
		} finally {
			activating = false;
		}
	}

	async function handleDeactivatePhase2() {
		if (!confirm('Are you sure you want to deactivate Phase 2?')) return;
		activating = true;
		activationError = null;
		activationSuccess = null;
		try {
			await deactivatePhase2();
			activationSuccess = 'Phase 2 deactivated';
			await Promise.all([loadData(), fetchPhaseStatus()]);
		} catch (e) {
			activationError = e instanceof Error ? e.message : 'Failed to deactivate Phase 2';
		} finally {
			activating = false;
		}
	}

	$: activeCompetition = competitions.find((c) => c.is_active);
</script>

<svelte:head>
	<title>Admin — Predictor</title>
</svelte:head>

{#if $isAuthenticated && $user?.is_admin}
	<PnPageShell>
		<section class="pn-pf-hero">
			<div class="av" style="background: var(--gold); color: var(--ink);">★</div>
			<div class="nm-block">
				<div class="nm">Admin <em>console</em></div>
				<div class="sub">Manage competition, phases, scores, and users</div>
			</div>
			<div class="rank-block">
				<div class="l">Phase</div>
				<div class="v" style="color: var(--gold);">{$isPhase2Active ? 'II' : 'I'}</div>
				<div class="of">{activeCompetition?.name ?? 'no competition active'}</div>
			</div>
		</section>

		{#if loading}
			<p style="font-family: var(--mono); font-size: 11px; color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.08em;">Loading admin data…</p>
		{:else if error}
			<div class="pn-pf-alert error">{error} · <button class="pn-btn ghost" style="padding: 4px 10px; font-size: 11px;" on:click={loadData}>Retry</button></div>
		{:else}
			<!-- Stats -->
			{#if stats}
				<section class="pn-pf-stats">
					<div class="pn-pf-stat">
						<div class="l">Users</div>
						<div class="v">{stats.total_users}</div>
						<div class="sub">{stats.active_users} active</div>
					</div>
					<div class="pn-pf-stat">
						<div class="l">Fixtures</div>
						<div class="v">{stats.total_fixtures}</div>
						<div class="sub">{stats.completed_fixtures} completed</div>
					</div>
					<div class="pn-pf-stat">
						<div class="l">Predictions</div>
						<div class="v">{stats.total_predictions}</div>
					</div>
					<div class="pn-pf-stat">
						<div class="l">Live</div>
						<div class="v exact">{stats.live_fixtures}</div>
						<div class="sub">matches</div>
					</div>
				</section>
			{/if}

			<!-- Score Sync -->
			<section class="pn-pf-section">
				<div class="h"><span>Score Sync</span><span class="right">Football-Data.org</span></div>
				<div class="body">
					{#if syncError}<div class="pn-pf-alert error" style="margin-bottom: 12px;">{syncError}</div>{/if}
					{#if syncResult}
						<div class="pn-ad-syncresult">
							<div>Last sync: <b>{syncedAt?.toLocaleTimeString() ?? ''}</b></div>
							<div class="pills">
								<span class="pn-tag got">{syncResult.synced} created</span>
								<span class="pn-tag">{syncResult.updated} updated</span>
								{#if syncResult.errors.length > 0}
									<span class="pn-tag red">{syncResult.errors.length} errors</span>
								{/if}
							</div>
							{#if syncResult.errors.length > 0}
								<div style="margin-top: 8px;">
									{#each syncResult.errors as err}
										<div style="color: var(--red); font-size: 10.5px;">• {err}</div>
									{/each}
								</div>
							{/if}
						</div>
					{/if}
					<p style="font-family: var(--mono); font-size: 11px; color: var(--ink-3); letter-spacing: 0.06em; margin-bottom: 12px;">
						The background scheduler runs every 60s during match windows; this is the manual escape hatch.
					</p>
					<button class="pn-btn gold" type="button" on:click={handleSyncScores} disabled={syncing}>
						{syncing ? 'Syncing…' : 'Sync scores now'}
					</button>
				</div>
			</section>

			<!-- Phase 1 Deadline -->
			<section class="pn-pf-section">
				<div class="h"><span>Phase I Deadline</span><span class="right">Group stage lock</span></div>
				<div class="body">
					<div class="pn-ad-status">
						<span>
							<b>DEADLINE</b>
							{#if $phase1Deadline}
								· {new Date($phase1Deadline).toLocaleString()}
							{:else}
								· <span class="warn">NOT SET</span>
							{/if}
						</span>
						{#if $phase1Deadline}
							<span class="{$phase1Countdown === 'Locked' ? 'warn' : 'ok'}">{$phase1Countdown}</span>
						{/if}
					</div>

					{#if phase1Error}<div class="pn-pf-alert error" style="margin-bottom: 12px;">{phase1Error}</div>{/if}
					{#if phase1Success}<div class="pn-pf-alert success" style="margin-bottom: 12px;">{phase1Success}</div>{/if}

					<div class="pn-pf-form row2">
						<div>
							<label for="p1-date">Date</label>
							<input id="p1-date" type="date" bind:value={phase1DeadlineDate} />
						</div>
						<div>
							<label for="p1-time">Time</label>
							<input id="p1-time" type="time" bind:value={phase1DeadlineTime} />
						</div>
						<div class="full">
							<button class="pn-btn" type="button" on:click={handleSetPhase1Deadline} disabled={settingPhase1}>
								{settingPhase1 ? 'Setting…' : 'Set Phase I deadline'}
							</button>
						</div>
					</div>
				</div>
			</section>

			<!-- Phase 2 Activation -->
			<section class="pn-pf-section">
				<div class="h"><span>Phase II Activation</span><span class="right">Knockout stage</span></div>
				<div class="body">
					<div class="pn-ad-status">
						<span>
							<b>STATUS</b> ·
							{#if $isPhase2Active}
								<span class="ok">ACTIVE</span>
								{#if $phase2BracketDeadline}
									· Bracket locks {new Date($phase2BracketDeadline).toLocaleString()}
								{/if}
							{:else}
								<span class="warn">NOT ACTIVE</span>
							{/if}
						</span>
						{#if $phase2BracketDeadline}
							<span class="{$phase2Countdown === 'Locked' ? 'warn' : 'ok'}">{$phase2Countdown}</span>
						{/if}
					</div>

					{#if activationError}<div class="pn-pf-alert error" style="margin-bottom: 12px;">{activationError}</div>{/if}
					{#if activationSuccess}<div class="pn-pf-alert success" style="margin-bottom: 12px;">{activationSuccess}</div>{/if}

					<div class="pn-pf-form row2">
						<div>
							<label for="p2-date">Bracket lock date</label>
							<input id="p2-date" type="date" bind:value={bracketDeadlineDate} />
						</div>
						<div>
							<label for="p2-time">Time</label>
							<input id="p2-time" type="time" bind:value={bracketDeadlineTime} />
						</div>
						<div class="full" style="display: flex; gap: 10px; flex-wrap: wrap;">
							<button class="pn-btn gold" type="button" on:click={handleActivatePhase2} disabled={activating}>
								{activating ? 'Working…' : ($isPhase2Active ? 'Update Phase II deadline' : 'Activate Phase II')}
							</button>
							{#if $isPhase2Active}
								<button class="pn-btn navy" type="button" on:click={handleDeactivatePhase2} disabled={activating}>
									Deactivate Phase II
								</button>
							{/if}
						</div>
					</div>
				</div>
			</section>

			<!-- User Management -->
			<section class="pn-pf-section">
				<div class="h"><span>User Management</span><span class="right">{filteredUsers.length} of {users.length}</span></div>
				<div class="body">
					{#if userActionError}<div class="pn-pf-alert error" style="margin-bottom: 12px;">{userActionError}</div>{/if}
					<input
						class="pn-ad-search"
						placeholder="Search by name or email…"
						bind:value={userSearch}
						type="search"
					/>
					<div class="pn-ad-users">
						{#each filteredUsers as u (u.id)}
							{@const isPaid = paidOf(u)}
							<div class="pn-ad-user" class:admin={u.is_admin} class:inactive={!u.is_active} class:paid={isPaid}>
								<label class="paid-toggle" title={isPaid ? 'Mark as unpaid' : 'Mark as paid'}>
									<input
										type="checkbox"
										checked={isPaid}
										disabled={togglingUserId === u.id}
										on:change={() => handleTogglePaid(u)}
									/>
									<span class="box" aria-hidden="true">{isPaid ? '✓' : ''}</span>
									<span class="lbl">{isPaid ? 'Paid' : 'Unpaid'}</span>
								</label>
								<div class="who">
									<div class="nm">{u.name}</div>
									<div class="em">{u.email} · {u.auth_provider === 'google' ? 'GOOGLE' : 'EMAIL'}</div>
								</div>
								<div class="badges">
									{#if u.is_admin}<span class="pn-tag gold">Admin</span>{/if}
									<span class="pn-tag {u.is_active ? 'got' : 'red'}">{u.is_active ? 'Active' : 'Inactive'}</span>
								</div>
								<div class="actions">
									<button class="pn-btn ghost" type="button" on:click={() => handleToggleAdmin(u)} disabled={togglingUserId === u.id}>
										{u.is_admin ? '− Admin' : '+ Admin'}
									</button>
									<button class="pn-btn navy" type="button" on:click={() => handleToggleActive(u)} disabled={togglingUserId === u.id}>
										{u.is_active ? 'Deactivate' : 'Reactivate'}
									</button>
								</div>
							</div>
						{:else}
							<p style="font-family: var(--mono); font-size: 11px; color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.08em;">No users match search</p>
						{/each}
					</div>
				</div>
			</section>
		{/if}
	</PnPageShell>
{/if}
