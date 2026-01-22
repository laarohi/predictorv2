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
			startPolling(60000); // Poll every 60 seconds
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
</script>
<svelte:head>
	<title>Leaderboard - Predictor v2</title>
</svelte:head>
{#if $isAuthenticated}
	<div class="container mx-auto mobile-padding py-6">
		<div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
			<div>
				<h1 class="text-2xl font-bold">Leaderboard</h1>
				<p class="text-sm text-base-content/50">
					{$totalParticipants} participants
					{#if $lastCalculated}
						· Updated {formatLastUpdated($lastCalculated)}
					{/if}
				</p>
			</div>
			<button
				class="btn btn-ghost btn-sm"
				on:click={() => fetchLeaderboard()}
				disabled={$leaderboardLoading}
			>
				{#if $leaderboardLoading}
					<span class="loading loading-spinner loading-sm"></span>
				{:else}
					Refresh
				{/if}
			</button>
		</div>
		{#if $leaderboardLoading && $leaderboard.length === 0}
			<div class="flex justify-center py-12">
				<span class="loading loading-spinner loading-lg text-primary"></span>
			</div>
		{:else if $leaderboard.length === 0}
			<div class="card bg-base-200">
				<div class="card-body text-center py-12">
					<p class="text-base-content/50">No standings yet. Start predicting!</p>
				</div>
			</div>
		{:else}
			<!-- Mobile: Cards layout -->
			<div class="sm:hidden space-y-2">
				{#each $leaderboard as entry}
					{@const movement = getMovementIndicator(entry.movement)}
					<div
						class="card bg-base-200"
						class:ring-2={entry.user_id === $user?.id}
						class:ring-primary={entry.user_id === $user?.id}
					>
						<div class="card-body p-4 flex-row items-center gap-4">
							<div
								class="position-badge text-lg"
								class:gold={entry.position === 1}
								class:silver={entry.position === 2}
								class:bronze={entry.position === 3}
							>
								{entry.position}
							</div>
							<div class="flex-1 min-w-0">
								<div class="font-semibold truncate">
									{entry.user_name}
									{#if entry.user_id === $user?.id}
										<span class="badge badge-primary badge-sm ml-1">You</span>
									{/if}
								</div>
								<div class="text-xs text-base-content/50">
									{entry.correct_outcomes} results · {entry.exact_scores} exact
								</div>
							</div>
							<div class="text-right">
								<div class="text-xl font-bold">{entry.total_points}</div>
								<div class={movement.class}>
									{movement.icon}
									{Math.abs(entry.movement) || ''}
								</div>
							</div>
						</div>
					</div>
				{/each}
			</div>
			<!-- Desktop: Table layout -->
			<div class="hidden sm:block card bg-base-200 overflow-hidden">
				<div class="overflow-x-auto">
					<table class="table">
						<thead>
							<tr>
								<th class="w-16">#</th>
								<th>Player</th>
								<th class="text-center">Results</th>
								<th class="text-center">Exact</th>
								<th class="text-right">Points</th>
								<th class="w-16"></th>
							</tr>
						</thead>
						<tbody>
							{#each $leaderboard as entry}
								{@const movement = getMovementIndicator(entry.movement)}
								<tr
									class="hover {entry.user_id === $user?.id ? 'bg-primary bg-opacity-10' : ''}"
								>
									<td>
										<div
											class="position-badge"
											class:gold={entry.position === 1}
											class:silver={entry.position === 2}
											class:bronze={entry.position === 3}
										>
											{entry.position}
										</div>
									</td>
									<td>
										<div class="font-semibold">
											{entry.user_name}
											{#if entry.user_id === $user?.id}
												<span class="badge badge-primary badge-sm ml-1">You</span>
											{/if}
										</div>
									</td>
									<td class="text-center">{entry.correct_outcomes}</td>
									<td class="text-center text-success">{entry.exact_scores}</td>
									<td class="text-right text-xl font-bold">{entry.total_points}</td>
									<td class={movement.class}>
										{movement.icon}
										{Math.abs(entry.movement) || ''}
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
