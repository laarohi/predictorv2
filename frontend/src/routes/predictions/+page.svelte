<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { goto, beforeNavigate } from '$app/navigation';
	import { isAuthenticated, user } from '$stores/auth';
	import {
		fetchMatchPredictions,
		fetchBracketPredictions,
		fetchPhase2BracketPredictions,
		saveBracketPredictions,
		matchPredictions,
		unsavedChanges,
		unsavedChangesCount,
		hasUnsavedChanges,
		saveAllPredictions,
		matchPredictionsLoading,
		bracketPrediction,
		bracketLoading,
		bracketError,
		unsavedBracketPrediction,
		hasUnsavedBracketChanges,
		phase2BracketPrediction,
		unsavedPhase2BracketPrediction,
		hasUnsavedPhase2BracketChanges
	} from '$stores/predictions';
	import {
		initPersistence,
		hydrateFromStorage,
		lastLocalSave
	} from '$stores/unsavedPersistence';
	import {
		fetchGroupFixtures,
		groupFixtures,
		fetchActualKnockoutFixtures,
		fetchActualStandings,
		actualKnockoutFixtures,
		actualGroupStandingsMap,
		actualStandingsLoading
	} from '$stores/fixtures';
	import {
		isPhase2Active,
		isPhase2BracketLocked,
		isPhase1Locked,
		phase1Countdown,
		phase2Countdown
	} from '$stores/phase';
	import SaveButton from '$components/SaveButton.svelte';
	import { KnockoutBracket } from '$components/bracket';
	import type { MatchPrediction, BracketPrediction, TeamAdvancementPrediction, Fixture } from '$types';
	import { computeGroupStandingsMap } from '$lib/utils/standings';

	import DeadlineBanner from '$components/predictions/DeadlineBanner.svelte';
	import ProgressBar from '$components/predictions/ProgressBar.svelte';
	import Phase1Groups from '$components/predictions/Phase1Groups.svelte';
	import Phase1Bracket from '$components/predictions/Phase1Bracket.svelte';
	import Phase2Content from '$components/predictions/Phase2Content.svelte';

	$: if (!$isAuthenticated) {
		goto('/login');
	}

	let activePhase: 'phase1' | 'phase2' = $isPhase2Active ? 'phase2' : 'phase1';
	let activeTab: 'groups' | 'bracket' = 'groups';

	// Track if we've set the initial phase (to avoid overriding user selection)
	let initialPhaseSet = false;
	$: if (!initialPhaseSet && $isPhase2Active !== undefined) {
		activePhase = $isPhase2Active ? 'phase2' : 'phase1';
		initialPhaseSet = true;
	}
	let saveStatus: 'idle' | 'saving' | 'saved' | 'error' = 'idle';
	let bracketSaveStatus: 'idle' | 'saving' | 'saved' | 'error' = 'idle';
	let phase2BracketSaveStatus: 'idle' | 'saving' | 'saved' | 'error' = 'idle';
	let bracketComponent: KnockoutBracket;
	let phase2BracketComponent: KnockoutBracket;

	// Hydration / persistence lifecycle
	let fetchesDone = false;
	let phase2FetchesStarted = false;
	let hydrated = false;
	let restorationBanner: { matchCount: number; p1: boolean; p2: boolean } | null = null;
	let bannerTimeout: ReturnType<typeof setTimeout> | null = null;

	onMount(async () => {
		if ($isAuthenticated) {
			await Promise.all([
				fetchMatchPredictions(),
				fetchGroupFixtures(),
				fetchBracketPredictions()
			]);

			// Fetch Phase 2 data if active
			if ($isPhase2Active) {
				phase2FetchesStarted = true;
				await Promise.all([
					fetchActualKnockoutFixtures(),
					fetchActualStandings(),
					fetchPhase2BracketPredictions()
				]);
			}

			fetchesDone = true;
		}

		window.addEventListener('beforeunload', handleBeforeUnload);
	});

	onDestroy(() => {
		if (typeof window !== 'undefined') {
			window.removeEventListener('beforeunload', handleBeforeUnload);
		}
		if (bannerTimeout !== null) clearTimeout(bannerTimeout);
	});

	// Reactively fetch Phase 2 data when it becomes active (one-shot guard so
	// it doesn't re-fire on every dependency change).
	$: if ($isPhase2Active && $isAuthenticated && !phase2FetchesStarted) {
		phase2FetchesStarted = true;
		Promise.all([
			fetchActualKnockoutFixtures(),
			fetchActualStandings(),
			fetchPhase2BracketPredictions()
		]);
	}

	// Hydrate once both $user and the initial fetches are ready. The user
	// store is populated asynchronously by initAuth in +layout.svelte, so a
	// reactive guard handles whichever finishes last.
	$: if ($user && fetchesDone && !hydrated) {
		hydrated = true;
		initPersistence($user.id);
		const r = hydrateFromStorage(
			$user.id,
			$groupFixtures,
			$isPhase1Locked,
			$isPhase2BracketLocked
		);
		if (r) {
			restorationBanner = {
				matchCount: r.matchCount,
				p1: r.bracketPhase1Restored,
				p2: r.bracketPhase2Restored
			};
			bannerTimeout = setTimeout(() => {
				restorationBanner = null;
				bannerTimeout = null;
			}, 8000);
		}
	}

	// Exit-confirmation guards: prevent accidentally leaving with unsaved work.
	$: hasAnyUnsaved =
		$hasUnsavedChanges || $hasUnsavedBracketChanges || $hasUnsavedPhase2BracketChanges;

	beforeNavigate(({ cancel, type }) => {
		if (!hasAnyUnsaved) return;
		// Browser-level leaves (refresh, close, external link) are handled by
		// the beforeunload listener — let it through to avoid double-prompting.
		if (type === 'leave') return;
		const ok = confirm(
			"You have unsaved predictions. Leave anyway?\n\nYour drafts are saved on this device and will be restored when you return, but they won't be submitted until you click Save."
		);
		if (!ok) cancel();
	});

	function handleBeforeUnload(e: BeforeUnloadEvent) {
		if (!hasAnyUnsaved) return;
		e.preventDefault();
		// Required for Chrome / older browsers; modern browsers ignore the
		// returned string and show their own generic dialog.
		e.returnValue = '';
	}

	function dismissBanner() {
		restorationBanner = null;
		if (bannerTimeout !== null) {
			clearTimeout(bannerTimeout);
			bannerTimeout = null;
		}
	}

	function formatLocalTime(d: Date): string {
		return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
	}

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

	// Shared helper: Convert BracketPrediction to TeamAdvancementPrediction array
	function bracketToPredictions(bracket: BracketPrediction, includeR32: boolean = true): TeamAdvancementPrediction[] {
		const predictions: TeamAdvancementPrediction[] = [];

		if (includeR32) {
			bracket.round_of_32.forEach((team) => {
				if (team) predictions.push({ team, stage: 'round_of_32', group_position: null });
			});
		}

		bracket.round_of_16.forEach((team) => {
			if (team) predictions.push({ team, stage: 'round_of_16', group_position: null });
		});

		bracket.quarter_finals.forEach((team) => {
			if (team) predictions.push({ team, stage: 'quarter_finals', group_position: null });
		});

		bracket.semi_finals.forEach((team) => {
			if (team) predictions.push({ team, stage: 'semi_finals', group_position: null });
		});

		bracket.final.forEach((team) => {
			if (team) predictions.push({ team, stage: 'final', group_position: null });
		});

		if (bracket.winner) {
			predictions.push({ team: bracket.winner, stage: 'winner', group_position: null });
		}

		return predictions;
	}

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
			setTimeout(() => { saveStatus = 'idle'; }, 2000);
		}
	}

	function handleBracketUpdate(event: CustomEvent<BracketPrediction>) {
		unsavedBracketPrediction.set(event.detail);
	}

	async function handleSaveBracket() {
		const bracket = $unsavedBracketPrediction;
		if (!bracket) return;

		bracketSaveStatus = 'saving';
		const predictions = bracketToPredictions(bracket, true);
		const success = await saveBracketPredictions(predictions);
		bracketSaveStatus = success ? 'saved' : 'error';

		if (success) {
			unsavedBracketPrediction.set(null);
			setTimeout(() => { bracketSaveStatus = 'idle'; }, 2000);
		}
	}

	// Phase 2 bracket handlers
	function handlePhase2BracketUpdate(event: CustomEvent<BracketPrediction>) {
		unsavedPhase2BracketPrediction.set(event.detail);
	}

	function handleClearPhase2Bracket() {
		if (confirm('Are you sure you want to clear all knockout selections?')) {
			phase2BracketComponent?.clearAllSelections();
		}
	}

	async function handleSavePhase2Bracket() {
		const bracket = $unsavedPhase2BracketPrediction;
		if (!bracket) return;

		phase2BracketSaveStatus = 'saving';
		const predictions = bracketToPredictions(bracket, false);
		const success = await saveBracketPredictions(predictions);
		phase2BracketSaveStatus = success ? 'saved' : 'error';

		if (success) {
			unsavedPhase2BracketPrediction.set(null);
			setTimeout(() => { phase2BracketSaveStatus = 'idle'; }, 2000);
		}
	}

	// Phase 2 computed values
	$: hasPhase2BracketChanges = $hasUnsavedPhase2BracketChanges;
	$: phase2DisplayBracket = $unsavedPhase2BracketPrediction || $phase2BracketPrediction;
	$: hasPhase2BracketSelections = phase2DisplayBracket && (
		phase2DisplayBracket.round_of_16?.some(t => t) ||
		phase2DisplayBracket.quarter_finals?.some(t => t) ||
		phase2DisplayBracket.semi_finals?.some(t => t) ||
		phase2DisplayBracket.final?.some(t => t) ||
		phase2DisplayBracket.winner
	);

	// Organize knockout fixtures by round
	$: knockoutRounds = (() => {
		const rounds: { name: string; stage: string; fixtures: Fixture[] }[] = [
			{ name: 'Round of 32', stage: 'round_of_32', fixtures: [] },
			{ name: 'Round of 16', stage: 'round_of_16', fixtures: [] },
			{ name: 'Quarter-Finals', stage: 'quarter_final', fixtures: [] },
			{ name: 'Semi-Finals', stage: 'semi_final', fixtures: [] },
			{ name: 'Final', stage: 'final', fixtures: [] }
		];

		for (const fixture of $actualKnockoutFixtures) {
			const round = rounds.find(r => r.stage === fixture.stage);
			if (round) round.fixtures.push(fixture);
		}

		return rounds.filter(r => r.fixtures.length > 0);
	})();

	// Phase 2 progress calculation
	$: phase2TotalKnockoutPicks = 31;
	$: phase2PredictedKnockoutPicks = (() => {
		const bracket = $phase2BracketPrediction;
		if (!bracket) return 0;
		let count = 0;
		count += bracket.round_of_16?.filter(t => t).length ?? 0;
		count += bracket.quarter_finals?.filter(t => t).length ?? 0;
		count += bracket.semi_finals?.filter(t => t).length ?? 0;
		count += bracket.final?.filter(t => t).length ?? 0;
		count += bracket.winner ? 1 : 0;
		return count;
	})();
	$: phase2BracketProgressPercent = Math.round((phase2PredictedKnockoutPicks / phase2TotalKnockoutPicks) * 100);

	$: phase2TotalMatches = $actualKnockoutFixtures.length;
	$: phase2PredictedMatches = $matchPredictions.filter(p =>
		$actualKnockoutFixtures.some(f => f.id === p.fixture_id)
	).length;
	$: phase2MatchProgressPercent = phase2TotalMatches > 0
		? Math.round((phase2PredictedMatches / phase2TotalMatches) * 100)
		: 0;

	$: phase2TotalPredictions = phase2TotalKnockoutPicks + phase2TotalMatches;
	$: phase2CompletedPredictions = phase2PredictedKnockoutPicks + phase2PredictedMatches;
	$: phase2ProgressPercent = phase2TotalPredictions > 0
		? Math.round((phase2CompletedPredictions / phase2TotalPredictions) * 100)
		: 0;

	// Create a map of predictions by fixture ID
	$: predictionMap = new Map($matchPredictions.map((p) => [p.fixture_id, p]));

	// Create a merged prediction map that includes unsaved changes for live standings
	$: livePredictionMap = (() => {
		const map = new Map<string, MatchPrediction>();
		for (const pred of $matchPredictions) {
			map.set(pred.fixture_id, pred);
		}
		for (const [fixtureId, scores] of Object.entries($unsavedChanges)) {
			const existing = map.get(fixtureId);
			if (existing) {
				map.set(fixtureId, { ...existing, ...scores });
			} else {
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
		return thirdPlace.sort((a, b) => {
			if (b.points !== a.points) return b.points - a.points;
			if (b.goalDifference !== a.goalDifference) return b.goalDifference - a.goalDifference;
			return b.goalsFor - a.goalsFor;
		});
	})();

	// Get the current bracket prediction to display
	$: displayBracket = $unsavedBracketPrediction || $bracketPrediction;

	// Calculate prediction progress
	$: totalGroupMatches = $groupFixtures.reduce((sum, g) => sum + g.fixtures.length, 0);
	$: predictedGroupMatches = $matchPredictions.length;
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

	$: totalPredictions = totalGroupMatches + totalKnockoutPicks;
	$: completedPredictions = predictedGroupMatches + predictedKnockoutPicks;
	$: progressPercent = totalPredictions > 0 ? Math.round((completedPredictions / totalPredictions) * 100) : 0;
	$: groupProgressPercent = totalGroupMatches > 0 ? Math.round((predictedGroupMatches / totalGroupMatches) * 100) : 0;
	$: bracketProgressPercent = Math.round((predictedKnockoutPicks / totalKnockoutPicks) * 100);
</script>

<svelte:head>
	<title>Predictions - Predictor v2</title>
</svelte:head>

{#if $isAuthenticated}
	<div class="container mx-auto mobile-padding py-6">
		{#if restorationBanner}
			<div class="alert alert-info shadow-md mb-4">
				<span>
					Restored
					{#if restorationBanner.matchCount > 0}
						{restorationBanner.matchCount} unsaved match prediction{restorationBanner.matchCount === 1 ? '' : 's'}
					{/if}
					{#if restorationBanner.matchCount > 0 && (restorationBanner.p1 || restorationBanner.p2)} and {/if}
					{#if restorationBanner.p1 || restorationBanner.p2}your unsaved bracket{/if}
					from your last visit. Click Save when ready.
				</span>
				<button class="btn btn-sm btn-ghost" on:click={dismissBanner}>Dismiss</button>
			</div>
		{/if}

		<!-- Header -->
		<div class="flex flex-col gap-6 mb-8">
			<div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
				<div>
					<h1 class="text-3xl sm:text-4xl font-display tracking-wide">Predictions</h1>
					<p class="text-sm text-base-content/50 mt-1">
						{#if activePhase === 'phase1'}
							{completedPredictions} of {totalPredictions} predictions complete
						{:else}
							Phase 2 - Knockout Predictions
						{/if}
					</p>
				</div>

				<!-- Phase selector (only show if Phase 2 is active) -->
				{#if $isPhase2Active}
					<div class="flex bg-base-300/50 rounded-xl p-1 gap-1">
						<button
							class="px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200
								{activePhase === 'phase1'
									? 'bg-base-100 text-base-content shadow-sm'
									: 'text-base-content/50 hover:text-base-content'}"
							on:click={() => (activePhase = 'phase1')}
						>
							Phase 1
						</button>
						<button
							class="px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 flex items-center gap-2
								{activePhase === 'phase2'
									? 'bg-accent text-accent-content shadow-sm'
									: 'text-base-content/50 hover:text-base-content'}"
							on:click={() => (activePhase = 'phase2')}
						>
							Phase 2
							{#if !$isPhase2BracketLocked}
								<span class="w-2 h-2 rounded-full bg-success animate-pulse"></span>
							{/if}
						</button>
					</div>
				{/if}
			</div>

			<!-- Phase 1 sub-tabs (Groups / Knockout) -->
			{#if activePhase === 'phase1'}
				<div class="flex bg-base-200 rounded-xl p-1 gap-1 self-start">
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
			{/if}

			<!-- Deadline banners -->
			{#if activePhase === 'phase1'}
				<DeadlineBanner
					countdown={$phase1Countdown}
					isLocked={$isPhase1Locked}
					phase="phase1"
				/>
			{:else}
				<DeadlineBanner
					countdown={$phase2Countdown}
					isLocked={$isPhase2BracketLocked}
					phase="phase2"
				/>
			{/if}
		</div>

		<!-- Phase content with fade transition -->
		{#key activePhase}
			<div class="animate-fade-in" style="animation-duration: 150ms;">
				<!-- PHASE 1 CONTENT -->
				{#if activePhase === 'phase1'}
					<!-- Progress bar -->
					{#if totalPredictions > 0}
						<ProgressBar
							progress={progressPercent}
							breakdown={[
								{ label: 'G', value: groupProgressPercent },
								{ label: 'K', value: bracketProgressPercent }
							]}
							phase="phase1"
						/>
					{/if}

					<!-- Floating save button for groups -->
					{#if activeTab === 'groups' && $hasUnsavedChanges}
						<div class="fixed bottom-24 sm:bottom-6 right-4 sm:right-6 z-40 flex flex-col items-end gap-1">
							<SaveButton
								status={saveStatus}
								count={$unsavedChangesCount}
								on:save={handleSaveAll}
							/>
							{#if $lastLocalSave}
								<p class="text-xs text-base-content/50 text-right">
									Saved locally · {formatLocalTime($lastLocalSave)}
								</p>
							{/if}
						</div>
					{/if}

					<!-- Tab content with fade transition -->
					{#key activeTab}
						<div class="animate-fade-in" style="animation-duration: 150ms;">
							{#if activeTab === 'groups'}
								<Phase1Groups
									groupFixtures={$groupFixtures}
									loading={$matchPredictionsLoading}
									{predictionMap}
									{livePredictionMap}
									{thirdPlaceStandings}
								/>
							{/if}

							{#if activeTab === 'bracket'}
								<Phase1Bracket
									bracketLoading={$bracketLoading}
									bracketError={$bracketError}
									bracketPrediction={$bracketPrediction}
									{displayBracket}
									groupStandings={groupStandingsMap}
									{hasBracketChanges}
									hasBracketSelections={!!hasBracketSelections}
									{bracketSaveStatus}
									bind:bracketComponent
									lastLocalSave={$lastLocalSave}
									onRetry={fetchBracketPredictions}
									onClear={handleClearBracket}
									onSave={handleSaveBracket}
									onUpdate={handleBracketUpdate}
								/>
							{/if}
						</div>
					{/key}
				{/if}

				<!-- PHASE 2 CONTENT -->
				{#if activePhase === 'phase2'}
					<!-- Phase 2 Progress bar -->
					<ProgressBar
						progress={phase2ProgressPercent}
						breakdown={[
							{ label: 'B', value: phase2BracketProgressPercent },
							{ label: 'M', value: phase2MatchProgressPercent }
						]}
						phase="phase2"
					/>

					<Phase2Content
						isPhase2BracketLocked={$isPhase2BracketLocked}
						actualStandingsLoading={$actualStandingsLoading}
						actualGroupStandingsMap={$actualGroupStandingsMap}
						{phase2DisplayBracket}
						{hasPhase2BracketChanges}
						hasPhase2BracketSelections={!!hasPhase2BracketSelections}
						{phase2BracketSaveStatus}
						bind:phase2BracketComponent
						{knockoutRounds}
						{predictionMap}
						hasUnsavedChanges={$hasUnsavedChanges}
						{saveStatus}
						unsavedChangesCount={$unsavedChangesCount}
						lastLocalSave={$lastLocalSave}
						onClearBracket={handleClearPhase2Bracket}
						onSaveBracket={handleSavePhase2Bracket}
						onSaveAll={handleSaveAll}
						onBracketUpdate={handlePhase2BracketUpdate}
					/>
				{/if}
			</div>
		{/key}
	</div>
{/if}
