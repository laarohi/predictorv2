<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { isAuthenticated, user } from '$stores/auth';
	import {
		fetchAllFixtures,
		liveFixtures,
		upcomingFixtures,
		formatKickoff,
		getTimeUntilKickoff
	} from '$stores/fixtures';
	import { fetchLeaderboard, currentUserPosition, topThree } from '$stores/leaderboard';

	$: if (!$isAuthenticated) {
		goto('/login');
	}

	onMount(() => {
		if ($isAuthenticated) {
			fetchAllFixtures();
			fetchLeaderboard();
		}
	});
</script>

<svelte:head>
	<title>Dashboard - Predictor v2</title>
</svelte:head>

{#if $isAuthenticated}
	<div class="container mx-auto mobile-padding py-6 space-y-6">
		<!-- Hero Welcome Section -->
		<div class="stadium-card p-6 sm:p-8 relative overflow-hidden animate-slide-up">
			<div class="relative z-10">
				<p class="text-sm text-primary font-medium mb-1">World Cup 2026</p>
				<h1 class="text-3xl sm:text-4xl font-display tracking-wide mb-2">
					Welcome back, {$user?.name?.split(' ')[0] || 'Player'}!
				</h1>
				<p class="text-base-content/50 text-sm">
					Track your predictions and climb the leaderboard.
				</p>
			</div>
			<!-- Decorative element -->
			<div class="absolute -right-8 -top-8 w-32 h-32 rounded-full bg-primary/5 blur-2xl"></div>
			<div class="absolute -right-4 -bottom-4 w-24 h-24 rounded-full bg-accent/5 blur-xl"></div>
		</div>

		<!-- Quick Stats -->
		<div class="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
			<div class="stat-card animate-slide-up stagger-1" style="animation-fill-mode: both;">
				<div class="stat-title">Position</div>
				<div class="stat-value text-gradient">
					#{$currentUserPosition?.position || '-'}
				</div>
			</div>
			<div class="stat-card animate-slide-up stagger-2" style="animation-fill-mode: both;">
				<div class="stat-title">Points</div>
				<div class="stat-value">{$currentUserPosition?.total_points || 0}</div>
			</div>
			<div class="stat-card animate-slide-up stagger-3" style="animation-fill-mode: both;">
				<div class="stat-title">Exact Scores</div>
				<div class="stat-value text-success">{$currentUserPosition?.exact_scores || 0}</div>
			</div>
			<div class="stat-card animate-slide-up stagger-4" style="animation-fill-mode: both;">
				<div class="stat-title">Correct Results</div>
				<div class="stat-value">{$currentUserPosition?.correct_outcomes || 0}</div>
			</div>
		</div>

		<div class="grid lg:grid-cols-2 gap-6">
			<!-- Live Matches -->
			<div class="stadium-card animate-slide-up stagger-5" style="animation-fill-mode: both;">
				<div class="p-5 sm:p-6">
					<div class="flex items-center gap-2 mb-5">
						<span class="relative flex h-3 w-3">
							<span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-error opacity-75"></span>
							<span class="relative inline-flex rounded-full h-3 w-3 bg-error"></span>
						</span>
						<h2 class="text-lg font-display tracking-wide">Live Matches</h2>
					</div>
					{#if $liveFixtures.length === 0}
						<div class="text-center py-8">
							<div class="w-12 h-12 mx-auto mb-3 rounded-xl bg-base-300/50 flex items-center justify-center">
								<svg class="w-6 h-6 text-base-content/30" fill="none" viewBox="0 0 24 24" stroke="currentColor">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
								</svg>
							</div>
							<p class="text-base-content/50 text-sm">No live matches right now</p>
						</div>
					{:else}
						<div class="space-y-3">
							{#each $liveFixtures as fixture}
								<div class="flex items-center justify-between p-4 bg-base-300/50 rounded-xl border border-base-300/30">
									<div class="flex-1">
										<span class="font-semibold">{fixture.home_team}</span>
									</div>
									<div class="px-4 text-center">
										<span class="text-2xl font-display tracking-wide">? - ?</span>
										<div class="text-xs text-error font-medium">{fixture.minute}'</div>
									</div>
									<div class="flex-1 text-right">
										<span class="font-semibold">{fixture.away_team}</span>
									</div>
								</div>
							{/each}
						</div>
					{/if}
				</div>
			</div>

			<!-- Top Leaderboard -->
			<div class="stadium-card animate-slide-up stagger-6" style="animation-fill-mode: both;">
				<div class="p-5 sm:p-6">
					<div class="flex items-center justify-between mb-5">
						<h2 class="text-lg font-display tracking-wide">Leaderboard</h2>
						<a href="/leaderboard" class="text-xs text-primary hover:text-primary/80 transition-colors font-medium">
							View All
						</a>
					</div>
					{#if $topThree.length === 0}
						<div class="text-center py-8">
							<div class="w-12 h-12 mx-auto mb-3 rounded-xl bg-base-300/50 flex items-center justify-center">
								<svg class="w-6 h-6 text-base-content/30" fill="none" viewBox="0 0 24 24" stroke="currentColor">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z" />
								</svg>
							</div>
							<p class="text-base-content/50 text-sm">No standings yet</p>
						</div>
					{:else}
						<div class="space-y-2">
							{#each $topThree as entry, i}
								<div
									class="leaderboard-row"
									class:current-user={entry.user_id === $user?.id}
								>
									<div
										class="position-badge"
										class:gold={i === 0}
										class:silver={i === 1}
										class:bronze={i === 2}
									>
										{entry.position}
									</div>
									<div class="flex-1 min-w-0">
										<div class="font-semibold truncate">{entry.user_name}</div>
									</div>
									<div class="text-xl font-display tracking-wide">{entry.total_points}</div>
								</div>
							{/each}
						</div>
					{/if}
				</div>
			</div>
		</div>

		<!-- Upcoming Matches -->
		<div class="stadium-card animate-slide-up stagger-7" style="animation-fill-mode: both;">
			<div class="p-5 sm:p-6">
				<div class="flex items-center justify-between mb-5">
					<h2 class="text-lg font-display tracking-wide">Upcoming Matches</h2>
					<a href="/predictions" class="text-xs text-primary hover:text-primary/80 transition-colors font-medium">
						Make Predictions
					</a>
				</div>
				{#if $upcomingFixtures.length === 0}
					<div class="text-center py-8">
						<div class="w-12 h-12 mx-auto mb-3 rounded-xl bg-base-300/50 flex items-center justify-center">
							<svg class="w-6 h-6 text-base-content/30" fill="none" viewBox="0 0 24 24" stroke="currentColor">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
							</svg>
						</div>
						<p class="text-base-content/50 text-sm">No upcoming matches</p>
					</div>
				{:else}
					<div class="space-y-2">
						{#each $upcomingFixtures.slice(0, 5) as fixture, i}
							<div class="flex items-center gap-4 p-3 rounded-lg hover:bg-base-300/30 transition-colors">
								<div class="flex-1 min-w-0">
									<div class="flex items-center gap-2 text-sm">
										<span class="font-semibold truncate">{fixture.home_team}</span>
										<span class="vs-badge text-[10px]">VS</span>
										<span class="font-semibold truncate">{fixture.away_team}</span>
									</div>
									<div class="text-xs text-base-content/50 mt-1">
										{formatKickoff(fixture.kickoff)}
									</div>
								</div>
								<div>
									{#if fixture.is_locked}
										<span class="inline-flex items-center gap-1 text-xs px-2 py-1 bg-error/10 text-error rounded-md border border-error/20">
											<svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
												<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
											</svg>
											Locked
										</span>
									{:else}
										<span class="countdown-timer">
											{getTimeUntilKickoff(fixture.kickoff)}
										</span>
									{/if}
								</div>
							</div>
						{/each}
					</div>
					{#if $upcomingFixtures.length > 5}
						<div class="mt-4 pt-4 border-t border-base-300/30 text-center">
							<a href="/predictions" class="btn btn-ghost btn-sm gap-2">
								View all {$upcomingFixtures.length} matches
								<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 8l4 4m0 0l-4 4m4-4H3" />
								</svg>
							</a>
						</div>
					{/if}
				{/if}
			</div>
		</div>
	</div>
{/if}
