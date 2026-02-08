<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { isAuthenticated, user, logout } from '$stores/auth';
	import { getUserStats, changePassword } from '$api/auth';
	import type { UserStats } from '$types';

	$: if (!$isAuthenticated) {
		goto('/login');
	}

	let stats: UserStats | null = null;
	let statsLoading = true;
	let statsError: string | null = null;

	// Password form state
	let currentPassword = '';
	let newPassword = '';
	let confirmPassword = '';
	let passwordChanging = false;
	let passwordError: string | null = null;
	let passwordSuccess: string | null = null;

	onMount(async () => {
		if ($isAuthenticated) {
			await loadStats();
		}
	});

	async function loadStats() {
		statsLoading = true;
		statsError = null;
		try {
			stats = await getUserStats();
		} catch (e) {
			statsError = e instanceof Error ? e.message : 'Failed to load stats';
		} finally {
			statsLoading = false;
		}
	}

	async function handleChangePassword() {
		passwordError = null;
		passwordSuccess = null;

		if (!currentPassword || !newPassword || !confirmPassword) {
			passwordError = 'All fields are required';
			return;
		}

		if (newPassword.length < 8) {
			passwordError = 'New password must be at least 8 characters';
			return;
		}

		if (newPassword !== confirmPassword) {
			passwordError = 'New passwords do not match';
			return;
		}

		passwordChanging = true;

		try {
			const result = await changePassword({
				current_password: currentPassword,
				new_password: newPassword
			});
			passwordSuccess = result.message;
			currentPassword = '';
			newPassword = '';
			confirmPassword = '';
		} catch (e) {
			passwordError = e instanceof Error ? e.message : 'Failed to change password';
		} finally {
			passwordChanging = false;
		}
	}

	function formatDate(dateStr: string): string {
		return new Date(dateStr).toLocaleDateString('en-GB', {
			day: 'numeric',
			month: 'long',
			year: 'numeric'
		});
	}
</script>

<svelte:head>
	<title>Profile - Predictor v2</title>
</svelte:head>

{#if $isAuthenticated && $user}
	<div class="container mx-auto mobile-padding py-6">
		<!-- Header -->
		<div class="mb-8">
			<h1 class="text-3xl sm:text-4xl font-display tracking-wide">Profile</h1>
			<p class="text-sm text-base-content/50 mt-1">Your account and prediction stats</p>
		</div>

		<div class="space-y-8">
			<!-- Section 1: Account Information -->
			<div class="stadium-card no-glow p-6">
				<div class="flex items-center gap-3 mb-6">
					<div class="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
						<svg
							class="w-5 h-5 text-primary"
							fill="none"
							viewBox="0 0 24 24"
							stroke="currentColor"
							stroke-width="2"
						>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
							/>
						</svg>
					</div>
					<div>
						<h2 class="text-lg font-display tracking-wide">Account Information</h2>
						<p class="text-xs text-base-content/50">Your account details</p>
					</div>
				</div>

				<div class="space-y-4">
					<!-- Name and Email -->
					<div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
						<div>
							<p class="text-xs text-base-content/50 uppercase tracking-wider mb-1">Name</p>
							<p class="font-medium">{$user.name}</p>
						</div>
						<div>
							<p class="text-xs text-base-content/50 uppercase tracking-wider mb-1">Email</p>
							<p class="font-medium">{$user.email}</p>
						</div>
					</div>

					<!-- Metadata grid -->
					<div class="grid grid-cols-2 sm:grid-cols-4 gap-4 pt-4 border-t border-base-300/50">
						<div>
							<p class="text-xs text-base-content/50 uppercase tracking-wider mb-1">Auth</p>
							<span class="badge badge-sm {$user.auth_provider === 'google' ? 'badge-info' : 'badge-ghost'}">
								{$user.auth_provider === 'google' ? 'Google' : 'Email'}
							</span>
						</div>
						<div>
							<p class="text-xs text-base-content/50 uppercase tracking-wider mb-1">Member Since</p>
							<p class="text-sm">{formatDate($user.created_at)}</p>
						</div>
						{#if $user.is_admin}
							<div>
								<p class="text-xs text-base-content/50 uppercase tracking-wider mb-1">Role</p>
								<span class="badge badge-sm badge-primary">Admin</span>
							</div>
						{/if}
						<div>
							<p class="text-xs text-base-content/50 uppercase tracking-wider mb-1">Status</p>
							<span class="badge badge-sm {$user.is_active ? 'badge-success' : 'badge-error'}">
								{$user.is_active ? 'Active' : 'Inactive'}
							</span>
						</div>
					</div>
				</div>
			</div>

			<!-- Section 2: Prediction Stats -->
			<div class="stadium-card no-glow p-6">
				<div class="flex items-center gap-3 mb-6">
					<div class="w-10 h-10 rounded-xl bg-accent/10 flex items-center justify-center">
						<svg
							class="w-5 h-5 text-accent"
							fill="none"
							viewBox="0 0 24 24"
							stroke="currentColor"
							stroke-width="2"
						>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
							/>
						</svg>
					</div>
					<div>
						<h2 class="text-lg font-display tracking-wide">Prediction Stats</h2>
						<p class="text-xs text-base-content/50">Your performance overview</p>
					</div>
				</div>

				{#if statsLoading}
					<div class="flex justify-center py-8">
						<span class="loading loading-spinner loading-lg text-primary"></span>
					</div>
				{:else if statsError}
					<div class="alert alert-error">
						<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
							/>
						</svg>
						<span>{statsError}</span>
						<button class="btn btn-sm btn-ghost" on:click={loadStats}>Retry</button>
					</div>
				{:else if stats}
					<div class="grid grid-cols-2 sm:grid-cols-3 gap-4">
						<div class="stat-card">
							<p class="stat-title">Leaderboard</p>
							<p class="stat-value {stats.leaderboard_position && stats.leaderboard_position <= 3 ? 'text-primary' : ''}">
								{#if stats.leaderboard_position}
									#{stats.leaderboard_position}
								{:else}
									-
								{/if}
							</p>
							<p class="text-xs text-base-content/40 mt-1">of {stats.total_participants}</p>
						</div>
						<div class="stat-card">
							<p class="stat-title">Total Points</p>
							<p class="stat-value">{stats.total_points}</p>
						</div>
						<div class="stat-card">
							<p class="stat-title">Predictions</p>
							<p class="stat-value">{stats.total_predictions}</p>
							<p class="text-xs text-base-content/40 mt-1">
								{stats.total_match_predictions} match, {stats.total_team_predictions} team
							</p>
						</div>
						<div class="stat-card">
							<p class="stat-title">Accuracy</p>
							<p class="stat-value">{stats.accuracy_pct}%</p>
						</div>
						<div class="stat-card">
							<p class="stat-title">Correct Outcomes</p>
							<p class="stat-value text-success">{stats.correct_outcomes}</p>
						</div>
						<div class="stat-card">
							<p class="stat-title">Exact Scores</p>
							<p class="stat-value text-primary">{stats.exact_scores}</p>
						</div>
					</div>
				{/if}
			</div>

			<!-- Section 3: Change Password -->
			<div class="stadium-card no-glow p-6">
				<div class="flex items-center gap-3 mb-6">
					<div class="w-10 h-10 rounded-xl bg-warning/10 flex items-center justify-center">
						<svg
							class="w-5 h-5 text-warning"
							fill="none"
							viewBox="0 0 24 24"
							stroke="currentColor"
							stroke-width="2"
						>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
							/>
						</svg>
					</div>
					<div>
						<h2 class="text-lg font-display tracking-wide">Password</h2>
						<p class="text-xs text-base-content/50">Manage your account security</p>
					</div>
				</div>

				{#if $user.auth_provider === 'google'}
					<div class="p-4 rounded-xl bg-info/10 border border-info/20">
						<div class="flex items-start gap-3">
							<svg class="w-5 h-5 text-info mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
							</svg>
							<div>
								<p class="text-sm font-medium text-info">Google Account</p>
								<p class="text-xs text-base-content/60 mt-1">
									Your password is managed by Google. To change it, visit your Google Account settings.
								</p>
							</div>
						</div>
					</div>
				{:else}
					{#if passwordError}
						<div class="alert alert-error mb-4">
							<span>{passwordError}</span>
						</div>
					{/if}

					{#if passwordSuccess}
						<div class="alert alert-success mb-4">
							<span>{passwordSuccess}</span>
						</div>
					{/if}

					<div class="space-y-4">
						<div class="form-control">
							<label class="label" for="current-password">
								<span class="label-text">Current Password</span>
							</label>
							<input
								id="current-password"
								type="password"
								class="input input-bordered w-full max-w-md"
								bind:value={currentPassword}
								autocomplete="current-password"
							/>
						</div>
						<div class="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-md sm:max-w-none">
							<div class="form-control">
								<label class="label" for="new-password">
									<span class="label-text">New Password</span>
								</label>
								<input
									id="new-password"
									type="password"
									class="input input-bordered w-full"
									bind:value={newPassword}
									autocomplete="new-password"
									minlength={8}
								/>
							</div>
							<div class="form-control">
								<label class="label" for="confirm-password">
									<span class="label-text">Confirm New Password</span>
								</label>
								<input
									id="confirm-password"
									type="password"
									class="input input-bordered w-full"
									bind:value={confirmPassword}
									autocomplete="new-password"
								/>
							</div>
						</div>
						<button
							class="btn btn-primary w-full sm:w-auto"
							on:click={handleChangePassword}
							disabled={passwordChanging}
						>
							{#if passwordChanging}
								<span class="loading loading-spinner loading-sm"></span>
							{/if}
							Update Password
						</button>
					</div>
				{/if}
			</div>

			<!-- Logout -->
			<div class="flex justify-center pt-4">
				<button class="btn btn-outline btn-error" on:click={logout}>
					<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"
						/>
					</svg>
					Sign Out
				</button>
			</div>
		</div>
	</div>
{/if}
