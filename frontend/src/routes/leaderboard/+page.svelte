<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import { isAuthenticated, user } from '$stores/auth';
	import {
		fetchLeaderboard,
		startPolling,
		stopPolling,
		leaderboard,
		leaderboardLoading,
		lastCalculated,
		totalParticipants,
		getMovementIndicator
	} from '$stores/leaderboard';

	$: if (!$isAuthenticated) {
		goto('/login');
	}

	onMount(() => {
		if ($isAuthenticated) {
			startPolling(60000);
		}
	});

	onDestroy(() => {
		stopPolling();
	});

	function formatLastUpdated(date: string | null): string {
		if (!date) return '';
		return new Date(date).toLocaleTimeString('en-GB', {
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	// Get stagger class for animation
	function getStaggerClass(index: number): string {
		const staggerIndex = Math.min(index + 1, 8);
		return `stagger-${staggerIndex}`;
	}
</script>

<svelte:head>
	<title>Leaderboard - Predictor v2</title>
</svelte:head>

{#if $isAuthenticated}
	<div class="container mx-auto mobile-padding py-6">
		<!-- Header -->
		<div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
			<div>
				<h1 class="text-3xl sm:text-4xl font-display tracking-wide">Leaderboard</h1>
				<p class="text-sm text-base-content/50 mt-1">
					{$totalParticipants} participants
					{#if $lastCalculated}
						<span class="text-base-content/30 mx-2">·</span>
						Updated {formatLastUpdated($lastCalculated)}
					{/if}
				</p>
			</div>
			<button
				class="btn btn-ghost btn-sm gap-2"
				on:click={() => fetchLeaderboard()}
				disabled={$leaderboardLoading}
			>
				{#if $leaderboardLoading}
					<span class="loading loading-spinner loading-sm"></span>
				{:else}
					<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
					</svg>
					Refresh
				{/if}
			</button>
		</div>

		{#if $leaderboardLoading && $leaderboard.length === 0}
			<div class="flex justify-center py-16">
				<span class="loading loading-spinner loading-lg text-primary"></span>
			</div>
		{:else if $leaderboard.length === 0}
			<div class="stadium-card p-8 text-center">
				<div class="text-6xl mb-4 opacity-30">🏆</div>
				<p class="text-base-content/50">No standings yet. Start predicting!</p>
			</div>
		{:else}
			<!-- Mobile: Cards layout -->
			<div class="sm:hidden space-y-3">
				{#each $leaderboard as entry, i}
					{@const movement = getMovementIndicator(entry.movement)}
					{@const isCurrentUser = entry.user_id === $user?.id}
					<div
						class="stadium-card p-4 animate-slide-up {getStaggerClass(i)} {isCurrentUser ? 'ring-2 ring-primary shadow-glow-green' : ''}"
						style="animation-fill-mode: both;"
					>
						<div class="flex items-center gap-4">
							<div
								class="position-badge"
								class:gold={entry.position === 1}
								class:silver={entry.position === 2}
								class:bronze={entry.position === 3}
							>
								{entry.position}
							</div>
							<div class="flex-1 min-w-0">
								<div class="font-semibold truncate flex items-center gap-2">
									{entry.user_name}
									{#if isCurrentUser}
										<span class="text-[10px] uppercase tracking-wider px-2 py-0.5 bg-primary/20 text-primary rounded-full">
											You
										</span>
									{/if}
								</div>
								<div class="text-xs text-base-content/50 mt-0.5">
									{entry.correct_outcomes} results · {entry.exact_scores} exact
								</div>
							</div>
							<div class="text-right">
								<div class="text-2xl font-display tracking-wide">{entry.total_points}</div>
								{#if entry.movement !== 0}
									<div class="text-xs {movement.class} flex items-center justify-end gap-1">
										{movement.icon}
										{Math.abs(entry.movement)}
									</div>
								{/if}
							</div>
						</div>
					</div>
				{/each}
			</div>

			<!-- Desktop: Enhanced table layout -->
			<div class="hidden sm:block stadium-card overflow-hidden">
				<div class="overflow-x-auto">
					<table class="w-full">
						<thead>
							<tr class="border-b border-base-300/50">
								<th class="text-left py-4 px-6 text-xs uppercase tracking-wider text-base-content/50 font-normal w-20">Rank</th>
								<th class="text-left py-4 px-6 text-xs uppercase tracking-wider text-base-content/50 font-normal">Player</th>
								<th class="text-center py-4 px-6 text-xs uppercase tracking-wider text-base-content/50 font-normal">Results</th>
								<th class="text-center py-4 px-6 text-xs uppercase tracking-wider text-base-content/50 font-normal">Exact</th>
								<th class="text-right py-4 px-6 text-xs uppercase tracking-wider text-base-content/50 font-normal">Points</th>
								<th class="py-4 px-4 w-16"></th>
							</tr>
						</thead>
						<tbody>
							{#each $leaderboard as entry, i}
								{@const movement = getMovementIndicator(entry.movement)}
								{@const isCurrentUser = entry.user_id === $user?.id}
								<tr
									class="border-b border-base-300/30 animate-slide-up transition-colors {getStaggerClass(i)} {isCurrentUser ? 'bg-primary/10' : 'hover:bg-base-300/30'}"
									style="animation-fill-mode: both;"
								>
									<td class="py-4 px-6">
										<div
											class="position-badge"
											class:gold={entry.position === 1}
											class:silver={entry.position === 2}
											class:bronze={entry.position === 3}
										>
											{entry.position}
										</div>
									</td>
									<td class="py-4 px-6">
										<div class="flex items-center gap-3">
											<span class="font-semibold">{entry.user_name}</span>
											{#if isCurrentUser}
												<span class="text-[10px] uppercase tracking-wider px-2 py-0.5 bg-primary/20 text-primary rounded-full">
													You
												</span>
											{/if}
										</div>
									</td>
									<td class="py-4 px-6 text-center text-base-content/70">{entry.correct_outcomes}</td>
									<td class="py-4 px-6 text-center text-success font-medium">{entry.exact_scores}</td>
									<td class="py-4 px-6 text-right">
										<span class="text-2xl font-display tracking-wide">{entry.total_points}</span>
									</td>
									<td class="py-4 px-4">
										{#if entry.movement !== 0}
											<div class="text-sm {movement.class} flex items-center gap-1">
												{movement.icon}
												{Math.abs(entry.movement)}
											</div>
										{/if}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</div>
		{/if}
	</div>
{/if}
