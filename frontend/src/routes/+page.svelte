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
		<!-- Welcome Section -->
		<div class="card bg-base-200">
			<div class="card-body">
				<h1 class="text-2xl font-bold">Welcome back, {$user?.name || 'Player'}!</h1>
				<p class="text-base-content/70">World Cup 2026 Predictions</p>
			</div>
		</div>

		<!-- Quick Stats -->
		<div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
			<div class="stat bg-base-200 rounded-lg">
				<div class="stat-title">Your Position</div>
				<div class="stat-value text-primary">
					{$currentUserPosition?.position || '-'}
				</div>
			</div>
			<div class="stat bg-base-200 rounded-lg">
				<div class="stat-title">Total Points</div>
				<div class="stat-value">{$currentUserPosition?.total_points || 0}</div>
			</div>
			<div class="stat bg-base-200 rounded-lg">
				<div class="stat-title">Exact Scores</div>
				<div class="stat-value text-success">{$currentUserPosition?.exact_scores || 0}</div>
			</div>
			<div class="stat bg-base-200 rounded-lg">
				<div class="stat-title">Correct Results</div>
				<div class="stat-value">{$currentUserPosition?.correct_outcomes || 0}</div>
			</div>
		</div>

		<div class="grid lg:grid-cols-2 gap-6">
			<!-- Live Matches -->
			<div class="card bg-base-200">
				<div class="card-body">
					<h2 class="card-title">
						<span class="text-error animate-pulse">●</span>
						Live Matches
					</h2>
					{#if $liveFixtures.length === 0}
						<p class="text-base-content/50 text-center py-8">No live matches right now</p>
					{:else}
						<div class="space-y-3">
							{#each $liveFixtures as fixture}
								<div class="flex items-center justify-between p-3 bg-base-300 rounded-lg">
									<div class="flex-1">
										<span class="team-name">{fixture.home_team}</span>
									</div>
									<div class="px-4 text-center">
										<span class="text-2xl font-bold">? - ?</span>
										<div class="text-xs text-error">{fixture.minute}'</div>
									</div>
									<div class="flex-1 text-right">
										<span class="team-name">{fixture.away_team}</span>
									</div>
								</div>
							{/each}
						</div>
					{/if}
				</div>
			</div>

			<!-- Top Leaderboard -->
			<div class="card bg-base-200">
				<div class="card-body">
					<h2 class="card-title">Leaderboard</h2>
					{#if $topThree.length === 0}
						<p class="text-base-content/50 text-center py-8">No standings yet</p>
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
									<div class="flex-1">
										<div class="font-semibold">{entry.user_name}</div>
									</div>
									<div class="text-xl font-bold">{entry.total_points}</div>
								</div>
							{/each}
						</div>
						<div class="card-actions justify-end mt-4">
							<a href="/leaderboard" class="btn btn-ghost btn-sm">View Full Leaderboard</a>
						</div>
					{/if}
				</div>
			</div>
		</div>

		<!-- Upcoming Matches -->
		<div class="card bg-base-200">
			<div class="card-body">
				<h2 class="card-title">Upcoming Matches</h2>
				{#if $upcomingFixtures.length === 0}
					<p class="text-base-content/50 text-center py-8">No upcoming matches</p>
				{:else}
					<div class="overflow-x-auto">
						<table class="table">
							<thead>
								<tr>
									<th>Match</th>
									<th>Kickoff</th>
									<th>Status</th>
									<th></th>
								</tr>
							</thead>
							<tbody>
								{#each $upcomingFixtures as fixture}
									<tr class="hover">
										<td>
											<span class="font-semibold">{fixture.home_team}</span>
											<span class="text-base-content/50 mx-2">vs</span>
											<span class="font-semibold">{fixture.away_team}</span>
										</td>
										<td class="text-sm">{formatKickoff(fixture.kickoff)}</td>
										<td>
											{#if fixture.is_locked}
												<span class="badge badge-error badge-sm">Locked</span>
											{:else}
												<span class="countdown-timer">
													{getTimeUntilKickoff(fixture.kickoff)}
												</span>
											{/if}
										</td>
										<td>
											<a href="/predictions" class="btn btn-ghost btn-xs">Predict</a>
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			</div>
		</div>
	</div>
{/if}
