<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import { isAuthenticated, user } from '$stores/auth';
	import {
		fetchLeaderboard,
		setPhase,
		startPolling,
		stopPolling,
		leaderboard,
		leaderboardLoading,
		lastCalculated,
		totalParticipants,
		getMovementIndicator,
		currentUserPosition,
		leaderboardPhase,
		type LeaderboardPhase
	} from '$stores/leaderboard';
	import {
		getGroupTotal,
		getKnockoutTotal,
		type PhaseBreakdown,
		type PointBreakdown
	} from '$types';

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

	function getStaggerClass(index: number): string {
		const staggerIndex = Math.min(index + 1, 8);
		return `stagger-${staggerIndex}`;
	}

	let expandedRows: Set<string> = new Set();
	let expandedBreakdown = false;

	function toggleRow(userId: string) {
		if (expandedRows.has(userId)) {
			expandedRows.delete(userId);
		} else {
			expandedRows.add(userId);
		}
		expandedRows = expandedRows;
	}

	function getPositionSuffix(pos: number): string {
		if (pos === 1) return 'st';
		if (pos === 2) return 'nd';
		if (pos === 3) return 'rd';
		return 'th';
	}

	// Phase tab handling
	async function handlePhaseChange(phase: LeaderboardPhase) {
		await setPhase(phase);
	}

	// Get match total for a phase breakdown
	function getPhaseMatchTotal(p: PhaseBreakdown): number {
		return p.match_outcome_points + p.exact_score_points + p.hybrid_bonus_points;
	}

	// Get bracket total for a phase breakdown
	function getPhaseBracketTotal(p: PhaseBreakdown): number {
		return getGroupTotal(p) + getKnockoutTotal(p);
	}

	// Get the relevant phase breakdown based on current filter
	function getDisplayPhase(b: PointBreakdown, phase: LeaderboardPhase): PhaseBreakdown | null {
		if (phase === 'phase_1') return b.phase1;
		if (phase === 'phase_2') return b.phase2;
		return null; // Overall shows both
	}
</script>

<svelte:head>
	<title>Leaderboard - Predictor v2</title>
</svelte:head>

{#if $isAuthenticated}
	<div class="container mx-auto mobile-padding py-6">
		<!-- Header -->
		<div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
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

		<!-- Phase Tabs -->
		<div class="flex gap-1 p-1 bg-base-300/30 rounded-xl mb-6 w-fit">
			<button
				class="px-4 py-2 rounded-lg text-sm font-medium transition-all {$leaderboardPhase === 'overall'
					? 'bg-primary text-primary-content shadow-md'
					: 'hover:bg-base-300/50 text-base-content/70'}"
				on:click={() => handlePhaseChange('overall')}
			>
				Overall
			</button>
			<button
				class="px-4 py-2 rounded-lg text-sm font-medium transition-all {$leaderboardPhase === 'phase_1'
					? 'bg-primary text-primary-content shadow-md'
					: 'hover:bg-base-300/50 text-base-content/70'}"
				on:click={() => handlePhaseChange('phase_1')}
			>
				Phase 1
			</button>
			<button
				class="px-4 py-2 rounded-lg text-sm font-medium transition-all {$leaderboardPhase === 'phase_2'
					? 'bg-primary text-primary-content shadow-md'
					: 'hover:bg-base-300/50 text-base-content/70'}"
				on:click={() => handlePhaseChange('phase_2')}
			>
				Phase 2
			</button>
		</div>

		{#if $leaderboardLoading && $leaderboard.length === 0}
			<div class="flex justify-center py-16">
				<span class="loading loading-spinner loading-lg text-primary"></span>
			</div>
		{:else if $leaderboard.length === 0}
			<div class="stadium-card p-8 text-center">
				<svg class="w-16 h-16 mx-auto mb-4 text-base-content/20" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
					<path stroke-linecap="round" stroke-linejoin="round" d="M16.5 18.75h-9m9 0a3 3 0 013 3h-15a3 3 0 013-3m9 0v-3.375c0-.621-.503-1.125-1.125-1.125h-.871M7.5 18.75v-3.375c0-.621.504-1.125 1.125-1.125h.872m5.007 0H9.497m5.007 0a7.454 7.454 0 01-.982-3.172M9.497 14.25a7.454 7.454 0 00.981-3.172M5.25 4.236c-.982.143-1.954.317-2.916.52A6.003 6.003 0 007.73 9.728M5.25 4.236V4.5c0 2.108.966 3.99 2.48 5.228M5.25 4.236V2.721C7.456 2.41 9.71 2.25 12 2.25c2.291 0 4.545.16 6.75.47v1.516M18.75 4.236c.982.143 1.954.317 2.916.52A6.003 6.003 0 0016.27 9.728M18.75 4.236V4.5c0 2.108-.966 3.99-2.48 5.228m0 0a6.003 6.003 0 01-4.52-1.978 6.003 6.003 0 01-4.52 1.978" />
				</svg>
				<p class="text-base-content/50">No standings yet. Start predicting!</p>
			</div>
		{:else}
			<!-- Your Score Card (Always visible) -->
			{#if $currentUserPosition}
				{@const entry = $currentUserPosition}
				{@const b = entry.breakdown}
				{@const movement = getMovementIndicator(entry.movement)}
				<div class="stadium-card p-5 mb-6 ring-2 ring-primary/50 shadow-glow-green">
					<!-- Header -->
					<div class="flex items-start justify-between mb-4">
						<div>
							<div class="text-xs uppercase tracking-wider text-base-content/50 mb-1">Your Score</div>
							<div class="flex items-baseline gap-2">
								<span class="text-4xl font-display tracking-wide">{entry.total_points}</span>
								<span class="text-base-content/50">pts</span>
								{#if entry.movement !== 0}
									<span class="text-sm {movement.class} flex items-center gap-1 ml-2">
										{movement.icon} {Math.abs(entry.movement)}
									</span>
								{/if}
							</div>
						</div>
						<div class="text-right">
							<div
								class="position-badge text-xl w-12 h-12"
								class:gold={entry.position === 1}
								class:silver={entry.position === 2}
								class:bronze={entry.position === 3}
							>
								{entry.position}
							</div>
							<div class="text-xs text-base-content/50 mt-1">
								{entry.position}{getPositionSuffix(entry.position)} place
							</div>
						</div>
					</div>

					<!-- Phase Comparison (Side by side) -->
					<div class="grid grid-cols-1 md:grid-cols-2 gap-4 pt-4 border-t border-base-300/30">
						<!-- Phase 1 -->
						<div class="bg-base-300/20 rounded-xl p-4">
							<div class="flex items-center justify-between mb-3">
								<div class="text-sm font-medium text-base-content/70">Phase 1</div>
								<div class="text-xl font-display">{b.phase1.total}</div>
							</div>
							<div class="grid grid-cols-2 gap-3">
								<div class="bg-base-300/40 rounded-lg p-2 text-center">
									<div class="text-xs text-base-content/50">Match</div>
									<div class="font-semibold">{getPhaseMatchTotal(b.phase1)}</div>
								</div>
								<div class="bg-base-300/40 rounded-lg p-2 text-center">
									<div class="text-xs text-base-content/50">Bracket</div>
									<div class="font-semibold text-info">{getPhaseBracketTotal(b.phase1)}</div>
								</div>
							</div>
						</div>

						<!-- Phase 2 -->
						<div class="bg-base-300/20 rounded-xl p-4">
							<div class="flex items-center justify-between mb-3">
								<div class="text-sm font-medium text-base-content/70">Phase 2</div>
								<div class="text-xl font-display">{b.phase2.total}</div>
							</div>
							<div class="grid grid-cols-2 gap-3">
								<div class="bg-base-300/40 rounded-lg p-2 text-center">
									<div class="text-xs text-base-content/50">Match</div>
									<div class="font-semibold">{getPhaseMatchTotal(b.phase2)}</div>
								</div>
								<div class="bg-base-300/40 rounded-lg p-2 text-center">
									<div class="text-xs text-base-content/50">Bracket</div>
									<div class="font-semibold text-info">{getPhaseBracketTotal(b.phase2)}</div>
								</div>
							</div>
						</div>
					</div>

					<!-- Expandable Full Breakdown -->
					<button
						class="w-full mt-4 pt-3 border-t border-base-300/30 flex items-center justify-center gap-2 text-sm text-base-content/50 hover:text-base-content transition-colors"
						on:click={() => (expandedBreakdown = !expandedBreakdown)}
					>
						{expandedBreakdown ? 'Hide' : 'Show'} full breakdown
						<svg
							class="w-4 h-4 transition-transform {expandedBreakdown ? 'rotate-180' : ''}"
							fill="none"
							viewBox="0 0 24 24"
							stroke="currentColor"
						>
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
						</svg>
					</button>

					{#if expandedBreakdown}
						<div class="mt-4 space-y-4">
							<!-- Phase 1 Breakdown -->
							<div class="bg-base-300/10 rounded-xl p-4">
								<div class="text-xs uppercase tracking-wider text-base-content/50 mb-3">Phase 1 Breakdown</div>
								<div class="grid grid-cols-2 gap-4">
									<!-- Match -->
									<div>
										<div class="text-[10px] uppercase tracking-wider text-base-content/40 mb-2">Match</div>
										<div class="grid grid-cols-3 gap-1 text-center text-xs">
											<div>
												<div class="text-base-content/40">Out</div>
												<div class="font-medium">{b.phase1.match_outcome_points}</div>
											</div>
											<div>
												<div class="text-base-content/40">Exact</div>
												<div class="font-medium text-success">{b.phase1.exact_score_points}</div>
											</div>
											<div>
												<div class="text-base-content/40">Bonus</div>
												<div class="font-medium text-warning">{b.phase1.hybrid_bonus_points}</div>
											</div>
										</div>
									</div>
									<!-- Bracket -->
									<div>
										<div class="text-[10px] uppercase tracking-wider text-base-content/40 mb-2">Bracket</div>
										<div class="grid grid-cols-4 gap-1 text-center text-xs">
											<div>
												<div class="text-base-content/40">Grp</div>
												<div class="font-medium text-info">{getGroupTotal(b.phase1)}</div>
											</div>
											<div>
												<div class="text-base-content/40">R32</div>
												<div class="font-medium text-info">{b.phase1.round_of_32_points}</div>
											</div>
											<div>
												<div class="text-base-content/40">R16</div>
												<div class="font-medium text-info">{b.phase1.round_of_16_points}</div>
											</div>
											<div>
												<div class="text-base-content/40">QF+</div>
												<div class="font-medium text-info">{b.phase1.quarter_final_points + b.phase1.semi_final_points + b.phase1.final_points + b.phase1.winner_points}</div>
											</div>
										</div>
									</div>
								</div>
							</div>

							<!-- Phase 2 Breakdown -->
							<div class="bg-base-300/10 rounded-xl p-4">
								<div class="text-xs uppercase tracking-wider text-base-content/50 mb-3">Phase 2 Breakdown</div>
								<div class="grid grid-cols-2 gap-4">
									<!-- Match -->
									<div>
										<div class="text-[10px] uppercase tracking-wider text-base-content/40 mb-2">Match</div>
										<div class="grid grid-cols-3 gap-1 text-center text-xs">
											<div>
												<div class="text-base-content/40">Out</div>
												<div class="font-medium">{b.phase2.match_outcome_points}</div>
											</div>
											<div>
												<div class="text-base-content/40">Exact</div>
												<div class="font-medium text-success">{b.phase2.exact_score_points}</div>
											</div>
											<div>
												<div class="text-base-content/40">Bonus</div>
												<div class="font-medium text-warning">{b.phase2.hybrid_bonus_points}</div>
											</div>
										</div>
									</div>
									<!-- Bracket -->
									<div>
										<div class="text-[10px] uppercase tracking-wider text-base-content/40 mb-2">Bracket</div>
										<div class="grid grid-cols-4 gap-1 text-center text-xs">
											<div>
												<div class="text-base-content/40">Grp</div>
												<div class="font-medium text-info">{getGroupTotal(b.phase2)}</div>
											</div>
											<div>
												<div class="text-base-content/40">R32</div>
												<div class="font-medium text-info">{b.phase2.round_of_32_points}</div>
											</div>
											<div>
												<div class="text-base-content/40">R16</div>
												<div class="font-medium text-info">{b.phase2.round_of_16_points}</div>
											</div>
											<div>
												<div class="text-base-content/40">QF+</div>
												<div class="font-medium text-info">{b.phase2.quarter_final_points + b.phase2.semi_final_points + b.phase2.final_points + b.phase2.winner_points}</div>
											</div>
										</div>
									</div>
								</div>
							</div>
						</div>
					{/if}
				</div>
			{/if}

			<!-- Mobile/Tablet: Tabular Cards -->
			<div class="xl:hidden">
				<!-- Table header -->
				<div class="flex items-center px-4 py-2 text-[10px] uppercase tracking-wider text-base-content/50 border-b border-base-300/30">
					<div class="w-10"></div>
					<div class="flex-1">Player</div>
					<div class="w-14 text-center">Match</div>
					<div class="w-14 text-center">Bracket</div>
					<div class="w-16 text-right">Total</div>
					<div class="w-6"></div>
				</div>

				<!-- Entries -->
				<div class="space-y-1 mt-1">
					{#each $leaderboard as entry, i}
						{@const movement = getMovementIndicator(entry.movement)}
						{@const isCurrentUser = entry.user_id === $user?.id}
						{@const isExpanded = expandedRows.has(entry.user_id)}
						{@const b = entry.breakdown}
						{@const displayPhase = getDisplayPhase(b, $leaderboardPhase)}
						{@const matchTotal = displayPhase ? getPhaseMatchTotal(displayPhase) : b.match_total}
						{@const bracketTotal = displayPhase ? getPhaseBracketTotal(displayPhase) : b.bracket_total}
						<div
							class="stadium-card animate-slide-up {getStaggerClass(i)} {isCurrentUser ? 'ring-2 ring-primary shadow-glow-green' : ''}"
							style="animation-fill-mode: both;"
						>
							<!-- Main row -->
							<button
								class="w-full px-3 py-3 flex items-center text-left"
								on:click={() => toggleRow(entry.user_id)}
							>
								<div
									class="position-badge w-8 h-8 text-sm"
									class:gold={entry.position === 1}
									class:silver={entry.position === 2}
									class:bronze={entry.position === 3}
								>
									{entry.position}
								</div>
								<div class="flex-1 min-w-0 ml-2">
									<div class="font-semibold truncate text-sm flex items-center gap-1">
										<a
											href="/profile/{entry.user_id}"
											class="hover:text-primary transition-colors"
											on:click|stopPropagation
										>{entry.user_name}</a>
										{#if isCurrentUser}
											<span class="text-[8px] uppercase tracking-wider px-1.5 py-0.5 bg-primary/20 text-primary rounded-full">
												You
											</span>
										{/if}
									</div>
									{#if entry.movement !== 0}
										<div class="text-[10px] {movement.class} flex items-center gap-0.5">
											{movement.icon}{Math.abs(entry.movement)}
										</div>
									{/if}
								</div>
								<div class="w-14 text-center text-sm font-medium">{matchTotal}</div>
								<div class="w-14 text-center text-sm font-medium text-info">{bracketTotal}</div>
								<div class="w-16 text-right">
									<span class="text-lg font-display">{entry.total_points}</span>
								</div>
								<div class="w-6 flex justify-center">
									<svg
										class="w-4 h-4 text-base-content/30 transition-transform {isExpanded ? 'rotate-180' : ''}"
										fill="none"
										viewBox="0 0 24 24"
										stroke="currentColor"
									>
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
									</svg>
								</div>
							</button>

							<!-- Expanded: Tabular breakdown -->
							{#if isExpanded}
								<div class="border-t border-base-300/30 bg-base-300/10 px-3 py-3">
									{#if $leaderboardPhase === 'overall'}
										<!-- Show both phases -->
										{#each [{ name: 'Phase 1', data: b.phase1 }, { name: 'Phase 2', data: b.phase2 }] as phase}
											<div class="mb-3 last:mb-0">
												<div class="text-[10px] uppercase tracking-wider text-base-content/50 mb-2">{phase.name}</div>
												<div class="grid grid-cols-2 gap-3">
													<!-- Match -->
													<div class="grid grid-cols-3 gap-2 text-center">
														<div>
															<div class="text-[10px] text-base-content/40">Out</div>
															<div class="font-medium text-sm">{phase.data.match_outcome_points}</div>
														</div>
														<div>
															<div class="text-[10px] text-base-content/40">Exact</div>
															<div class="font-medium text-sm text-success">{phase.data.exact_score_points}</div>
														</div>
														<div>
															<div class="text-[10px] text-base-content/40">Bonus</div>
															<div class="font-medium text-sm text-warning">{phase.data.hybrid_bonus_points}</div>
														</div>
													</div>
													<!-- Bracket -->
													<div class="grid grid-cols-4 gap-1 text-center">
														<div>
															<div class="text-[10px] text-base-content/40">Grp</div>
															<div class="font-medium text-sm text-info">{getGroupTotal(phase.data)}</div>
														</div>
														<div>
															<div class="text-[10px] text-base-content/40">R32</div>
															<div class="font-medium text-sm text-info">{phase.data.round_of_32_points}</div>
														</div>
														<div>
															<div class="text-[10px] text-base-content/40">R16</div>
															<div class="font-medium text-sm text-info">{phase.data.round_of_16_points}</div>
														</div>
														<div>
															<div class="text-[10px] text-base-content/40">QF+</div>
															<div class="font-medium text-sm text-info">{phase.data.quarter_final_points + phase.data.semi_final_points + phase.data.final_points + phase.data.winner_points}</div>
														</div>
													</div>
												</div>
											</div>
										{/each}
									{:else if displayPhase}
										<!-- Show single phase breakdown -->
										<div class="grid grid-cols-2 gap-3">
											<!-- Match -->
											<div>
												<div class="text-[10px] uppercase tracking-wider text-base-content/50 mb-2">Match</div>
												<div class="grid grid-cols-3 gap-2 text-center">
													<div>
														<div class="text-[10px] text-base-content/40">Out</div>
														<div class="font-medium text-sm">{displayPhase.match_outcome_points}</div>
													</div>
													<div>
														<div class="text-[10px] text-base-content/40">Exact</div>
														<div class="font-medium text-sm text-success">{displayPhase.exact_score_points}</div>
													</div>
													<div>
														<div class="text-[10px] text-base-content/40">Bonus</div>
														<div class="font-medium text-sm text-warning">{displayPhase.hybrid_bonus_points}</div>
													</div>
												</div>
											</div>
											<!-- Bracket -->
											<div>
												<div class="text-[10px] uppercase tracking-wider text-base-content/50 mb-2">Bracket</div>
												<div class="grid grid-cols-4 gap-1 text-center">
													<div>
														<div class="text-[10px] text-base-content/40">Grp</div>
														<div class="font-medium text-sm text-info">{getGroupTotal(displayPhase)}</div>
													</div>
													<div>
														<div class="text-[10px] text-base-content/40">R32</div>
														<div class="font-medium text-sm text-info">{displayPhase.round_of_32_points}</div>
													</div>
													<div>
														<div class="text-[10px] text-base-content/40">R16</div>
														<div class="font-medium text-sm text-info">{displayPhase.round_of_16_points}</div>
													</div>
													<div>
														<div class="text-[10px] text-base-content/40">QF+</div>
														<div class="font-medium text-sm text-info">{displayPhase.quarter_final_points + displayPhase.semi_final_points + displayPhase.final_points + displayPhase.winner_points}</div>
													</div>
												</div>
											</div>
										</div>
									{/if}
								</div>
							{/if}
						</div>
					{/each}
				</div>
			</div>

			<!-- Desktop: Full breakdown table -->
			<div class="hidden xl:block stadium-card overflow-hidden">
				<div class="overflow-x-auto">
					<table class="w-full">
						<thead>
							<tr class="border-b border-base-300/50">
								<th class="text-left py-4 px-4 text-xs uppercase tracking-wider text-base-content/50 font-normal w-16">Rank</th>
								<th class="text-left py-4 px-4 text-xs uppercase tracking-wider text-base-content/50 font-normal">Player</th>
								<th colspan="3" class="text-center py-2 px-2 text-xs uppercase tracking-wider text-base-content/50 font-normal border-l border-base-300/30">Match Predictions</th>
								<th colspan="5" class="text-center py-2 px-2 text-xs uppercase tracking-wider text-base-content/50 font-normal border-l border-base-300/30">Bracket Predictions</th>
								<th class="text-right py-4 px-4 text-xs uppercase tracking-wider text-base-content/50 font-normal border-l border-base-300/30">Total</th>
								<th class="py-4 px-3 w-12"></th>
							</tr>
							<tr class="border-b border-base-300/50 text-[10px]">
								<th></th>
								<th></th>
								<!-- Match sub-headers -->
								<th class="text-center py-2 px-2 text-base-content/40 font-normal border-l border-base-300/30">Out</th>
								<th class="text-center py-2 px-2 text-base-content/40 font-normal">Exact</th>
								<th class="text-center py-2 px-2 text-base-content/40 font-normal">Bonus</th>
								<!-- Bracket sub-headers -->
								<th class="text-center py-2 px-2 text-base-content/40 font-normal border-l border-base-300/30">Groups</th>
								<th class="text-center py-2 px-2 text-base-content/40 font-normal">R32</th>
								<th class="text-center py-2 px-2 text-base-content/40 font-normal">R16</th>
								<th class="text-center py-2 px-2 text-base-content/40 font-normal">QF</th>
								<th class="text-center py-2 px-2 text-base-content/40 font-normal">SF+</th>
								<th class="border-l border-base-300/30"></th>
								<th></th>
							</tr>
						</thead>
						<tbody>
							{#each $leaderboard as entry, i}
								{@const movement = getMovementIndicator(entry.movement)}
								{@const isCurrentUser = entry.user_id === $user?.id}
								{@const b = entry.breakdown}
								{@const displayPhase = getDisplayPhase(b, $leaderboardPhase)}
								<tr
									class="border-b border-base-300/30 animate-slide-up transition-colors {getStaggerClass(i)} {isCurrentUser ? 'bg-primary/10' : 'hover:bg-base-300/30'}"
									style="animation-fill-mode: both;"
								>
									<td class="py-3 px-4">
										<div
											class="position-badge"
											class:gold={entry.position === 1}
											class:silver={entry.position === 2}
											class:bronze={entry.position === 3}
										>
											{entry.position}
										</div>
									</td>
									<td class="py-3 px-4">
										<div class="flex items-center gap-3">
											<a href="/profile/{entry.user_id}" class="font-semibold hover:text-primary transition-colors">{entry.user_name}</a>
											{#if isCurrentUser}
												<span class="text-[10px] uppercase tracking-wider px-2 py-0.5 bg-primary/20 text-primary rounded-full">
													You
												</span>
											{/if}
										</div>
									</td>
									<!-- Match columns - use phase-specific or aggregated values -->
									<td class="py-3 px-2 text-center border-l border-base-300/30">
										<span class="font-medium">{displayPhase ? displayPhase.match_outcome_points : b.match_outcome_points}</span>
									</td>
									<td class="py-3 px-2 text-center">
										<span class="font-medium text-success">{displayPhase ? displayPhase.exact_score_points : b.exact_score_points}</span>
									</td>
									<td class="py-3 px-2 text-center">
										<span class="font-medium text-warning">{displayPhase ? displayPhase.hybrid_bonus_points : b.hybrid_bonus_points}</span>
									</td>
									<!-- Bracket columns - use phase-specific or aggregated values -->
									<td class="py-3 px-2 text-center border-l border-base-300/30">
										<span class="font-medium text-info">{displayPhase ? getGroupTotal(displayPhase) : b.group_advance_points + b.group_position_points}</span>
									</td>
									<td class="py-3 px-2 text-center">
										<span class="font-medium text-info">{displayPhase ? displayPhase.round_of_32_points : b.round_of_32_points}</span>
									</td>
									<td class="py-3 px-2 text-center">
										<span class="font-medium text-info">{displayPhase ? displayPhase.round_of_16_points : b.round_of_16_points}</span>
									</td>
									<td class="py-3 px-2 text-center">
										<span class="font-medium text-info">{displayPhase ? displayPhase.quarter_final_points : b.quarter_final_points}</span>
									</td>
									<td class="py-3 px-2 text-center">
										<span class="font-medium text-info">{displayPhase ? (displayPhase.semi_final_points + displayPhase.final_points + displayPhase.winner_points) : (b.semi_final_points + b.final_points + b.winner_points)}</span>
									</td>
									<td class="py-3 px-4 text-right border-l border-base-300/30">
										<span class="text-xl font-display tracking-wide">{entry.total_points}</span>
									</td>
									<td class="py-3 px-3">
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
