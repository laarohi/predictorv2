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
		syncScores,
		type AdminStats,
		type CompetitionAdminView,
		type UserAdminView,
		type SyncScoresResponse
	} from '$lib/api/admin';

	// Redirect non-admins
	$: if ($isAuthenticated && !$user?.is_admin) {
		goto('/');
	}

	$: if (!$isAuthenticated) {
		goto('/login');
	}

	let stats: AdminStats | null = null;
	let competitions: CompetitionAdminView[] = [];
	let users: UserAdminView[] = [];
	let loading = true;
	let error: string | null = null;

	// Phase 1 deadline form
	let phase1DeadlineDate = '';
	let phase1DeadlineTime = '12:00';
	let settingPhase1 = false;
	let phase1Error: string | null = null;
	let phase1Success: string | null = null;

	// Phase 2 activation form
	let bracketDeadlineDate = '';
	let bracketDeadlineTime = '12:00';
	let activating = false;
	let activationError: string | null = null;
	let activationSuccess: string | null = null;

	// Manual score sync
	let syncing = false;
	let syncResult: SyncScoresResponse | null = null;
	let syncedAt: Date | null = null;
	let syncError: string | null = null;

	// User management
	let userSearch = '';
	let togglingUserId: string | null = null;
	let userActionError: string | null = null;

	onMount(async () => {
		if ($user?.is_admin) {
			await loadData();
		}
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
			// Refresh stats so live_fixtures count updates
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

	// Get the active competition
	$: activeCompetition = competitions.find((c) => c.is_active);
</script>

<svelte:head>
	<title>Admin Dashboard - Predictor v2</title>
</svelte:head>

{#if $isAuthenticated && $user?.is_admin}
	<div class="container mx-auto mobile-padding py-6">
		<!-- Header -->
		<div class="mb-8">
			<h1 class="text-3xl sm:text-4xl font-display tracking-wide">Admin Dashboard</h1>
			<p class="text-sm text-base-content/50 mt-1">Manage competition and view statistics</p>
		</div>

		{#if loading}
			<div class="flex justify-center py-16">
				<span class="loading loading-spinner loading-lg text-primary"></span>
			</div>
		{:else if error}
			<div class="alert alert-error">
				<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
				</svg>
				<span>{error}</span>
				<button class="btn btn-sm btn-ghost" on:click={loadData}>Retry</button>
			</div>
		{:else}
			<div class="space-y-8">
				<!-- Stats Grid -->
				{#if stats}
					<div class="grid grid-cols-2 sm:grid-cols-4 gap-4">
						<div class="stadium-card no-glow p-4">
							<p class="text-xs text-base-content/50 uppercase tracking-wider">Users</p>
							<p class="text-2xl font-display mt-1">{stats.total_users}</p>
							<p class="text-xs text-base-content/40">{stats.active_users} active</p>
						</div>
						<div class="stadium-card no-glow p-4">
							<p class="text-xs text-base-content/50 uppercase tracking-wider">Fixtures</p>
							<p class="text-2xl font-display mt-1">{stats.total_fixtures}</p>
							<p class="text-xs text-base-content/40">{stats.completed_fixtures} completed</p>
						</div>
						<div class="stadium-card no-glow p-4">
							<p class="text-xs text-base-content/50 uppercase tracking-wider">Predictions</p>
							<p class="text-2xl font-display mt-1">{stats.total_predictions}</p>
						</div>
						<div class="stadium-card no-glow p-4">
							<p class="text-xs text-base-content/50 uppercase tracking-wider">Live</p>
							<p class="text-2xl font-display mt-1 text-success">{stats.live_fixtures}</p>
							<p class="text-xs text-base-content/40">matches</p>
						</div>
					</div>
				{/if}

				<!-- Manual Score Sync -->
				<div class="stadium-card no-glow p-4 sm:p-6">
					<div class="flex items-center gap-3 mb-4">
						<div class="w-10 h-10 rounded-xl bg-success/10 flex items-center justify-center">
							<svg class="w-5 h-5 text-success" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
							</svg>
						</div>
						<div class="flex-1">
							<h2 class="text-lg font-display tracking-wide">Score Sync</h2>
							<p class="text-xs text-base-content/50">
								Manually trigger a Football-Data.org sync. The background scheduler runs every 60s during match windows; this is the manual escape hatch.
							</p>
						</div>
					</div>

					{#if syncError}
						<div class="alert alert-error mb-4">
							<span>{syncError}</span>
						</div>
					{/if}

					{#if syncResult}
						<div class="mb-4 p-4 rounded-xl bg-base-200/50">
							<div class="flex items-center gap-2 mb-2">
								<span class="text-sm font-medium">Last sync:</span>
								<span class="text-sm text-base-content/70">{syncedAt?.toLocaleTimeString() ?? ''}</span>
							</div>
							<div class="flex flex-wrap gap-3 text-sm">
								<span class="badge badge-success gap-1">
									<span class="font-mono">{syncResult.synced}</span> created
								</span>
								<span class="badge badge-info gap-1">
									<span class="font-mono">{syncResult.updated}</span> updated
								</span>
								{#if syncResult.errors.length > 0}
									<span class="badge badge-error gap-1">
										<span class="font-mono">{syncResult.errors.length}</span> errors
									</span>
								{/if}
							</div>
							{#if syncResult.errors.length > 0}
								<div class="mt-3 space-y-1 text-xs text-error/80">
									{#each syncResult.errors as err}
										<div>• {err}</div>
									{/each}
								</div>
							{/if}
						</div>
					{/if}

					<button class="btn btn-success" on:click={handleSyncScores} disabled={syncing}>
						{#if syncing}
							<span class="loading loading-spinner loading-sm"></span>
						{/if}
						Sync scores now
					</button>
				</div>

				<!-- Phase 1 Deadline Control -->
				<div class="stadium-card no-glow p-4 sm:p-6">
					<div class="flex items-center gap-3 mb-6">
						<div class="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
							<svg class="w-5 h-5 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
							</svg>
						</div>
						<div>
							<h2 class="text-lg font-display tracking-wide">Phase 1 Deadline</h2>
							<p class="text-xs text-base-content/50">Group stage predictions deadline</p>
						</div>
					</div>

					<!-- Current Status -->
					<div class="mb-6 p-4 rounded-xl bg-base-200/50">
						<div class="flex items-center justify-between">
							<span class="text-sm text-base-content/70">Deadline:</span>
							{#if $phase1Deadline}
								<span class="text-sm font-medium">{new Date($phase1Deadline).toLocaleString()}</span>
							{:else}
								<span class="badge badge-ghost">Not set</span>
							{/if}
						</div>
						{#if $phase1Deadline}
							<div class="flex items-center justify-between mt-2">
								<span class="text-sm text-base-content/70">Time remaining:</span>
								<span class="text-sm font-mono font-medium {$phase1Countdown === 'Locked' ? 'text-error' : 'text-success'}">{$phase1Countdown}</span>
							</div>
						{/if}
					</div>

					{#if phase1Error}
						<div class="alert alert-error mb-4">
							<span>{phase1Error}</span>
						</div>
					{/if}

					{#if phase1Success}
						<div class="alert alert-success mb-4">
							<span>{phase1Success}</span>
						</div>
					{/if}

					<div class="space-y-4">
						<div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
							<div class="form-control">
								<label class="label" for="phase1-deadline-date">
									<span class="label-text">Deadline Date</span>
								</label>
								<input
									id="phase1-deadline-date"
									type="date"
									class="input input-bordered"
									bind:value={phase1DeadlineDate}
								/>
							</div>
							<div class="form-control">
								<label class="label" for="phase1-deadline-time">
									<span class="label-text">Time</span>
								</label>
								<input
									id="phase1-deadline-time"
									type="time"
									class="input input-bordered"
									bind:value={phase1DeadlineTime}
								/>
							</div>
						</div>
						<button
							class="btn btn-primary w-full sm:w-auto"
							on:click={handleSetPhase1Deadline}
							disabled={settingPhase1}
						>
							{#if settingPhase1}
								<span class="loading loading-spinner loading-sm"></span>
							{/if}
							{$phase1Deadline ? 'Update Deadline' : 'Set Deadline'}
						</button>
					</div>
				</div>

				<!-- Phase 2 Control -->
				<div class="stadium-card no-glow p-4 sm:p-6">
					<div class="flex items-center gap-3 mb-6">
						<div class="w-10 h-10 rounded-xl bg-accent/10 flex items-center justify-center">
							<svg class="w-5 h-5 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
							</svg>
						</div>
						<div>
							<h2 class="text-lg font-display tracking-wide">Phase 2 Control</h2>
							<p class="text-xs text-base-content/50">Activate knockout predictions phase</p>
						</div>
					</div>

					<!-- Current Status -->
					<div class="mb-6 p-4 rounded-xl bg-base-200/50">
						<div class="flex items-center justify-between">
							<span class="text-sm text-base-content/70">Status:</span>
							{#if $isPhase2Active}
								<span class="badge badge-success gap-1">
									<span class="w-2 h-2 rounded-full bg-success animate-pulse"></span>
									Active
								</span>
							{:else}
								<span class="badge badge-ghost">Inactive</span>
							{/if}
						</div>
						{#if $phase2BracketDeadline}
							<div class="flex items-center justify-between mt-2">
								<span class="text-sm text-base-content/70">Bracket Deadline:</span>
								<span class="text-sm font-medium">{new Date($phase2BracketDeadline).toLocaleString()}</span>
							</div>
							<div class="flex items-center justify-between mt-2">
								<span class="text-sm text-base-content/70">Time remaining:</span>
								<span class="text-sm font-mono font-medium {$phase2Countdown === 'Locked' ? 'text-error' : 'text-success'}">{$phase2Countdown}</span>
							</div>
						{/if}
					</div>

					<!-- Activation/Deactivation -->
					{#if activationError}
						<div class="alert alert-error mb-4">
							<span>{activationError}</span>
						</div>
					{/if}

					{#if activationSuccess}
						<div class="alert alert-success mb-4">
							<span>{activationSuccess}</span>
						</div>
					{/if}

					{#if !$isPhase2Active}
						<div class="space-y-4">
							<div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
								<div class="form-control">
									<label class="label" for="deadline-date">
										<span class="label-text">Bracket Deadline Date</span>
									</label>
									<input
										id="deadline-date"
										type="date"
										class="input input-bordered"
										bind:value={bracketDeadlineDate}
									/>
								</div>
								<div class="form-control">
									<label class="label" for="deadline-time">
										<span class="label-text">Time</span>
									</label>
									<input
										id="deadline-time"
										type="time"
										class="input input-bordered"
										bind:value={bracketDeadlineTime}
									/>
								</div>
							</div>
							<button
								class="btn btn-accent w-full sm:w-auto"
								on:click={handleActivatePhase2}
								disabled={activating}
							>
								{#if activating}
									<span class="loading loading-spinner loading-sm"></span>
								{/if}
								Activate Phase 2
							</button>
						</div>
					{:else}
						<button
							class="btn btn-outline btn-error"
							on:click={handleDeactivatePhase2}
							disabled={activating}
						>
							{#if activating}
								<span class="loading loading-spinner loading-sm"></span>
							{/if}
							Deactivate Phase 2
						</button>
					{/if}
				</div>

				<!-- User Management -->
				<div class="stadium-card no-glow p-4 sm:p-6">
					<div class="flex items-center gap-3 mb-4">
						<div class="w-10 h-10 rounded-xl bg-info/10 flex items-center justify-center">
							<svg class="w-5 h-5 text-info" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
							</svg>
						</div>
						<div class="flex-1">
							<h2 class="text-lg font-display tracking-wide">Users</h2>
							<p class="text-xs text-base-content/50">
								{users.length} registered. Toggle admin or active state.
							</p>
						</div>
					</div>

					{#if userActionError}
						<div class="alert alert-error mb-4">
							<span>{userActionError}</span>
						</div>
					{/if}

					<div class="form-control mb-4">
						<input
							type="text"
							placeholder="Search by name or email..."
							class="input input-bordered input-sm"
							bind:value={userSearch}
						/>
					</div>

					<div class="overflow-x-auto -mx-4 sm:mx-0">
						<table class="table table-sm">
							<thead>
								<tr>
									<th>Name</th>
									<th class="hidden sm:table-cell">Email</th>
									<th class="text-right">Predictions</th>
									<th class="text-center">Admin</th>
									<th class="text-center">Active</th>
								</tr>
							</thead>
							<tbody>
								{#each filteredUsers as u (u.id)}
									{@const busy = togglingUserId === u.id}
									<tr class:opacity-50={!u.is_active}>
										<td>
											<div class="font-medium">{u.name}</div>
											<div class="text-[10px] text-base-content/40 sm:hidden">{u.email}</div>
											<div class="text-[10px] text-base-content/40">{u.auth_provider}</div>
										</td>
										<td class="hidden sm:table-cell text-xs text-base-content/70">{u.email}</td>
										<td class="text-right font-mono text-sm">{u.prediction_count}</td>
										<td class="text-center">
											<input
												type="checkbox"
												class="toggle toggle-sm toggle-primary"
												checked={u.is_admin}
												disabled={busy}
												on:change={() => handleToggleAdmin(u)}
											/>
										</td>
										<td class="text-center">
											<input
												type="checkbox"
												class="toggle toggle-sm toggle-success"
												checked={u.is_active}
												disabled={busy}
												on:change={() => handleToggleActive(u)}
											/>
										</td>
									</tr>
								{/each}
								{#if filteredUsers.length === 0}
									<tr>
										<td colspan="5" class="text-center py-6 text-base-content/40 text-sm">
											{userSearch ? 'No users match your search.' : 'No users yet.'}
										</td>
									</tr>
								{/if}
							</tbody>
						</table>
					</div>
				</div>

				<!-- Active Competition -->
				{#if activeCompetition}
					<div class="stadium-card no-glow p-4 sm:p-6">
						<div class="flex items-center gap-3 mb-4">
							<div class="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
								<svg class="w-5 h-5 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
								</svg>
							</div>
							<div>
								<h2 class="text-lg font-display tracking-wide">{activeCompetition.name}</h2>
								<p class="text-xs text-base-content/50">Active Competition</p>
							</div>
						</div>

						<div class="grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm">
							<div>
								<p class="text-base-content/50">Fixtures</p>
								<p class="font-medium">{activeCompetition.fixture_count}</p>
							</div>
							<div>
								<p class="text-base-content/50">Participants</p>
								<p class="font-medium">{activeCompetition.user_count}</p>
							</div>
							<div>
								<p class="text-base-content/50">Entry Fee</p>
								<p class="font-medium">${activeCompetition.entry_fee}</p>
							</div>
						</div>
					</div>
				{/if}
			</div>
		{/if}
	</div>
{/if}
