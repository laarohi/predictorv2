<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { isAuthenticated } from '$stores/auth';
	import {
		fetchMatchPredictions,
		fetchBracketPredictions,
		saveBracketPredictions,
		matchPredictions,
		unsavedChanges,
		hasUnsavedChanges,
		saveAllPredictions,
		matchPredictionsLoading,
		bracketPrediction,
		bracketLoading,
		bracketError,
		unsavedBracketPrediction,
		hasUnsavedBracketChanges,
		workingBracketPrediction
	} from '$stores/predictions';
	import { fetchGroupFixtures, groupFixtures } from '$stores/fixtures';
	import MatchCard from '$components/MatchCard.svelte';
	import SaveButton from '$components/SaveButton.svelte';
	import GroupTable from '$components/GroupTable.svelte';
	import ThirdPlaceTable from '$components/ThirdPlaceTable.svelte';
	import { KnockoutBracket } from '$components/bracket';
	import type { MatchPrediction, BracketPrediction, TeamAdvancementPrediction } from '$types';
	import { getAllTeamsFromGroups, computeGroupStandingsMap } from '$lib/utils/standings';
	import { getQualifyingThirdPlaceTeams } from '$lib/utils/bracketResolver';

	$: if (!$isAuthenticated) {
		goto('/login');
	}

	let activeTab: 'groups' | 'bracket' = 'groups';
	let saveStatus: 'idle' | 'saving' | 'saved' | 'error' = 'idle';
	let bracketSaveStatus: 'idle' | 'saving' | 'saved' | 'error' = 'idle';
	let bracketComponent: KnockoutBracket;

	onMount(async () => {
		if ($isAuthenticated) {
			await Promise.all([
				fetchMatchPredictions(),
				fetchGroupFixtures(),
				fetchBracketPredictions()
			]);
		}
	});

	// Check if bracket has unsaved changes (from store)
	$: hasBracketChanges = $hasUnsavedBracketChanges;

	// Check if bracket has any selections (to show clear button)
	$: hasBracketSelections = displayBracket && (
		displayBracket.round_of_16?.some(t => t) ||
		displayBracket.quarter_finals?.some(t => t) ||
		displayBracket.semi_finals?.some(t => t) ||
		displayBracket.final?.some(t => t) ||
		displayBracket.winner
	);

	function handleClearBracket() {
		if (confirm('Are you sure you want to clear all knockout selections?')) {
			bracketComponent?.clearAllSelections();
		}
	}

	async function handleSaveAll() {
		saveStatus = 'saving';
		const success = await saveAllPredictions();
		saveStatus = success ? 'saved' : 'error';

		if (success) {
			setTimeout(() => {
				saveStatus = 'idle';
			}, 2000);
		}
	}

	function handleBracketUpdate(event: CustomEvent<BracketPrediction>) {
		unsavedBracketPrediction.set(event.detail);
	}

	async function handleSaveBracket() {
		const bracket = $unsavedBracketPrediction;
		if (!bracket) return;

		bracketSaveStatus = 'saving';

		// Convert BracketPrediction to TeamAdvancementPrediction array
		const predictions: TeamAdvancementPrediction[] = [];

		// Add round of 32 teams
		bracket.round_of_32.forEach((team, i) => {
			if (team) {
				predictions.push({ team, stage: 'round_of_32', group_position: null });
			}
		});

		// Add round of 16 teams
		bracket.round_of_16.forEach((team) => {
			if (team) {
				predictions.push({ team, stage: 'round_of_16', group_position: null });
			}
		});

		// Add quarter-finals teams
		bracket.quarter_finals.forEach((team) => {
			if (team) {
				predictions.push({ team, stage: 'quarter_finals', group_position: null });
			}
		});

		// Add semi-finals teams
		bracket.semi_finals.forEach((team) => {
			if (team) {
				predictions.push({ team, stage: 'semi_finals', group_position: null });
			}
		});

		// Add final teams
		bracket.final.forEach((team) => {
			if (team) {
				predictions.push({ team, stage: 'final', group_position: null });
			}
		});

		// Add winner
		if (bracket.winner) {
			predictions.push({ team: bracket.winner, stage: 'winner', group_position: null });
		}

		const success = await saveBracketPredictions(predictions);
		bracketSaveStatus = success ? 'saved' : 'error';

		if (success) {
			unsavedBracketPrediction.set(null);
			setTimeout(() => {
				bracketSaveStatus = 'idle';
			}, 2000);
		}
	}

	// Create a map of predictions by fixture ID
	$: predictionMap = new Map($matchPredictions.map((p) => [p.fixture_id, p]));

	// Create a merged prediction map that includes unsaved changes for live standings
	$: livePredictionMap = (() => {
		const map = new Map<string, MatchPrediction>();
		// Start with saved predictions
		for (const pred of $matchPredictions) {
			map.set(pred.fixture_id, pred);
		}
		// Overlay unsaved changes
		for (const [fixtureId, scores] of $unsavedChanges) {
			const existing = map.get(fixtureId);
			if (existing) {
				map.set(fixtureId, { ...existing, ...scores });
			} else {
				// Create a temporary prediction object for new unsaved predictions
				map.set(fixtureId, {
					id: '',
					fixture_id: fixtureId,
					home_score: scores.home_score,
					away_score: scores.away_score,
					phase: 'phase_1',
					locked_at: null,
					created_at: '',
					updated_at: '',
					is_locked: false
				});
			}
		}
		return map;
	})();

	// Get all teams from group fixtures - this is the source of truth
	$: allGroupTeams = getAllTeamsFromGroups($groupFixtures);

	// Compute group standings map for the knockout bracket
	$: groupStandingsMap = computeGroupStandingsMap($groupFixtures, livePredictionMap);

	// Compute sorted third-place standings
	$: thirdPlaceStandings = (() => {
		const thirdPlace = [];
		for (const [group, standings] of Object.entries(groupStandingsMap)) {
			if (standings[2]) {
				thirdPlace.push(standings[2]);
			}
		}
		// Sort by points, GD, GF
		return thirdPlace.sort((a, b) => {
			if (b.points !== a.points) return b.points - a.points;
			if (b.goalDifference !== a.goalDifference) return b.goalDifference - a.goalDifference;
			return b.goalsFor - a.goalsFor;
		});
	})();

	// Get the current bracket prediction to display
	// Use unsavedBracket if we have local changes, otherwise use the backend data
	$: displayBracket = $unsavedBracketPrediction || $bracketPrediction;

	// Calculate prediction progress (combined group stage + knockout bracket)
	// Group stage: count matches predicted
	$: totalGroupMatches = $groupFixtures.reduce((sum, g) => sum + g.fixtures.length, 0);
	$: predictedGroupMatches = $matchPredictions.length;

	// Knockout bracket: count picks required
	// R32: 16 winners, R16: 8 winners, QF: 4 winners, SF: 2 winners, Final: 1 winner = 31 total
	$: totalKnockoutPicks = 31;
	$: predictedKnockoutPicks = (() => {
		const bracket = $bracketPrediction;
		if (!bracket) return 0;
		let count = 0;
		count += bracket.round_of_16?.filter(t => t).length ?? 0;
		count += bracket.quarter_finals?.filter(t => t).length ?? 0;
		count += bracket.semi_finals?.filter(t => t).length ?? 0;
		count += bracket.final?.filter(t => t).length ?? 0;
		count += bracket.winner ? 1 : 0;
		return count;
	})();

	// Combined progress
	$: totalPredictions = totalGroupMatches + totalKnockoutPicks;
	$: completedPredictions = predictedGroupMatches + predictedKnockoutPicks;
	$: progressPercent = totalPredictions > 0 ? Math.round((completedPredictions / totalPredictions) * 100) : 0;

	// Individual progress for display
	$: groupProgressPercent = totalGroupMatches > 0 ? Math.round((predictedGroupMatches / totalGroupMatches) * 100) : 0;
	$: bracketProgressPercent = Math.round((predictedKnockoutPicks / totalKnockoutPicks) * 100);
</script>

<svelte:head>
	<title>Predictions - Predictor v2</title>
</svelte:head>

{#if $isAuthenticated}
	<div class="container mx-auto mobile-padding py-6">
		<!-- Header -->
		<div class="flex flex-col gap-6 mb-8">
			<div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
				<div>
					<h1 class="text-3xl sm:text-4xl font-display tracking-wide">Predictions</h1>
					<p class="text-sm text-base-content/50 mt-1">
						{completedPredictions} of {totalPredictions} predictions complete
					</p>
				</div>

				<!-- Tab buttons -->
				<div class="flex bg-base-200 rounded-xl p-1 gap-1">
					<button
						class="px-5 py-2.5 rounded-lg text-sm font-medium transition-all duration-200
							{activeTab === 'groups'
								? 'bg-primary text-primary-content shadow-md'
								: 'text-base-content/70 hover:text-base-content hover:bg-base-300/50'}"
						on:click={() => (activeTab = 'groups')}
					>
						<span class="flex items-center gap-2">
							<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
							</svg>
							Groups
						</span>
					</button>
					<button
						class="px-5 py-2.5 rounded-lg text-sm font-medium transition-all duration-200
							{activeTab === 'bracket'
								? 'bg-primary text-primary-content shadow-md'
								: 'text-base-content/70 hover:text-base-content hover:bg-base-300/50'}"
						on:click={() => (activeTab = 'bracket')}
					>
						<span class="flex items-center gap-2">
							<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
							</svg>
							Knockout
						</span>
					</button>
				</div>
			</div>

		</div>

		<!-- Sticky Progress bar -->
		{#if totalPredictions > 0}
			<div class="sticky top-16 z-30 -mx-4 sm:-mx-0 px-4 sm:px-0 py-2 sm:py-3 bg-base-100/95 backdrop-blur-sm border-b border-base-300/30 -mt-2 mb-4">
				<div class="flex items-center gap-3">
					<div class="flex-1 h-1.5 sm:h-2 bg-base-300 rounded-full overflow-hidden">
						<div
							class="h-full bg-gradient-to-r from-primary to-accent transition-all duration-500 ease-out rounded-full"
							style="width: {progressPercent}%"
						></div>
					</div>
					<span class="text-xs font-medium text-base-content/70 tabular-nums w-10 text-right">{progressPercent}%</span>
					<!-- Breakdown on larger screens -->
					<div class="hidden sm:flex items-center gap-2 text-xs text-base-content/40 border-l border-base-300/50 pl-3">
						<span>G: {groupProgressPercent}%</span>
						<span>K: {bracketProgressPercent}%</span>
					</div>
				</div>
			</div>
		{/if}

		<!-- Floating save button for groups -->
		{#if activeTab === 'groups' && $hasUnsavedChanges}
			<div class="fixed bottom-24 sm:bottom-6 right-4 sm:right-6 z-40">
				<SaveButton
					status={saveStatus}
					count={$unsavedChanges.size}
					on:save={handleSaveAll}
				/>
			</div>
		{/if}

		<!-- Groups Tab -->
		{#if activeTab === 'groups'}
			{#if $matchPredictionsLoading && $groupFixtures.length === 0}
				<div class="flex justify-center py-16">
					<span class="loading loading-spinner loading-lg text-primary"></span>
				</div>
			{:else if $groupFixtures.length === 0}
				<div class="stadium-card p-8 text-center">
					<div class="text-6xl mb-4 opacity-30">
						<svg class="w-16 h-16 mx-auto text-base-content/20" fill="none" viewBox="0 0 24 24" stroke="currentColor">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
						</svg>
					</div>
					<p class="text-base-content/50">No group stage fixtures available yet.</p>
				</div>
			{:else}
				<div class="space-y-8">
					{#each $groupFixtures as group, groupIndex}
						<div class="stadium-card no-glow p-4 sm:p-6 animate-slide-up" style="animation-delay: {groupIndex * 50}ms; animation-fill-mode: both;">
							<!-- Group Header -->
							<div class="flex items-center gap-3 mb-5">
								<div class="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
									<span class="text-lg font-display text-primary">{group.group}</span>
								</div>
								<div>
									<h2 class="text-lg font-display tracking-wide">Group {group.group}</h2>
									<p class="text-xs text-base-content/50">{group.fixtures.length} matches</p>
								</div>
							</div>

							<!-- Predicted Standings Table -->
							<div class="mb-6">
								<div class="flex items-center gap-2 mb-3">
									<svg class="w-4 h-4 text-base-content/40" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
										<path stroke-linecap="round" stroke-linejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
									</svg>
									<h3 class="text-xs font-medium text-base-content/50 uppercase tracking-wider">Predicted Standings</h3>
								</div>
								<GroupTable
									group={group.group}
									fixtures={group.fixtures}
									predictions={livePredictionMap}
								/>
							</div>

							<!-- Match Predictions -->
							<div>
								<div class="flex items-center gap-2 mb-3">
									<svg class="w-4 h-4 text-base-content/40" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
										<path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
									</svg>
									<h3 class="text-xs font-medium text-base-content/50 uppercase tracking-wider">Match Predictions</h3>
								</div>
								<div class="match-grid">
									{#each group.fixtures as fixture}
										<MatchCard
											{fixture}
											prediction={predictionMap.get(fixture.id)}
										/>
									{/each}
								</div>
							</div>
						</div>
					{/each}

					<!-- Third Place Table -->
					<div class="stadium-card no-glow p-4 sm:p-6 animate-slide-up" style="animation-delay: 600ms; animation-fill-mode: both;">
						<div class="flex items-center gap-3 mb-5">
							<div class="w-10 h-10 rounded-xl bg-warning/10 flex items-center justify-center">
								<span class="text-lg font-display text-warning">3rd</span>
							</div>
							<div>
								<h2 class="text-lg font-display tracking-wide">Ranking of 3rd Place Teams</h2>
								<p class="text-xs text-base-content/50">Top 8 advance to Round of 32</p>
							</div>
						</div>
						<ThirdPlaceTable standings={thirdPlaceStandings} />
					</div>
				</div>
			{/if}
		{/if}

		<!-- Bracket Tab -->
		{#if activeTab === 'bracket'}
			{#if $bracketLoading && !$bracketPrediction}
				<div class="flex justify-center py-16">
					<span class="loading loading-spinner loading-lg text-primary"></span>
				</div>
			{:else if $bracketError}
				<div class="stadium-card no-glow p-8 text-center">
					<div class="text-error mb-4">
						<svg class="w-12 h-12 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
						</svg>
					</div>
					<p class="text-base-content/70">{$bracketError}</p>
					<button class="btn btn-primary btn-sm mt-4" on:click={fetchBracketPredictions}>
						Try Again
					</button>
				</div>
			{:else}
				<div class="stadium-card no-glow p-4 sm:p-6">
					<div class="flex items-center justify-between mb-6">
						<div>
							<h2 class="text-xl font-display tracking-wide">Knockout Bracket</h2>
							<p class="text-xs text-base-content/50 mt-1">
								Select winners to advance through each round
							</p>
						</div>
						<div class="flex items-center gap-4">
							{#if hasBracketChanges}
								<span class="flex items-center gap-2 text-xs text-accent">
									<span class="w-2 h-2 rounded-full bg-accent animate-pulse"></span>
									Unsaved changes
								</span>
							{/if}
							{#if hasBracketSelections}
								<button
									class="text-xs font-medium text-base-content/40 hover:text-error transition-all duration-200 flex items-center gap-1.5 px-3 py-1.5 rounded-lg hover:bg-error/10 border border-transparent hover:border-error/20"
									on:click={handleClearBracket}
								>
									<svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											stroke-width="2"
											d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
										/>
									</svg>
									Clear All
								</button>
							{/if}
						</div>
					</div>

					<KnockoutBracket
						bind:this={bracketComponent}
						prediction={displayBracket}
						groupStandings={groupStandingsMap}
						locked={false}
						phase="phase_1"
						on:update={handleBracketUpdate}
					/>
				</div>

				<!-- Bracket Save Button -->
				{#if hasBracketChanges}
					<div class="fixed bottom-24 sm:bottom-6 right-4 sm:right-6 z-40">
						<button
							class="save-button gap-2"
							class:saving={bracketSaveStatus === 'saving'}
							class:saved={bracketSaveStatus === 'saved'}
							disabled={bracketSaveStatus === 'saving'}
							on:click={handleSaveBracket}
						>
							{#if bracketSaveStatus === 'saving'}
								<span class="loading loading-spinner loading-sm"></span>
								Saving...
							{:else if bracketSaveStatus === 'saved'}
								<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
								</svg>
								Saved!
							{:else if bracketSaveStatus === 'error'}
								<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
								</svg>
								Error - Try Again
							{:else}
								<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
								</svg>
								Save Bracket
							{/if}
						</button>
					</div>
				{/if}
			{/if}
		{/if}
	</div>
{/if}
