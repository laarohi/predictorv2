<script lang="ts">
	import { updateLocalPrediction, unsavedChanges } from '$stores/predictions';
	import { formatKickoff, getTimeUntilKickoff } from '$stores/fixtures';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import type { Fixture, MatchPrediction } from '$types';

	export let fixture: Fixture;
	export let prediction: MatchPrediction | undefined = undefined;

	// Check for unsaved changes from store
	$: unsaved = $unsavedChanges[fixture.id];

	// Compute display values: unsaved takes priority, then saved prediction, then empty
	// This is derived state - single source of truth
	$: displayHomeScore = unsaved?.home_score ?? prediction?.home_score ?? '';
	$: displayAwayScore = unsaved?.away_score ?? prediction?.away_score ?? '';

	function handleInput(e: Event, type: 'home' | 'away') {
		if (fixture.is_locked) return;

		const input = e.target as HTMLInputElement;
		const value = input.value;

		// Parse the new value
		let newScore: number | null = null;
		if (value === '') {
			newScore = 0; // Treat empty as 0 for storage
		} else {
			const num = parseInt(value, 10);
			if (!isNaN(num) && num >= 0 && num <= 20) {
				newScore = num;
			}
		}

		// Only update store if we have a valid number
		if (newScore !== null) {
			const currentHome = unsaved?.home_score ?? prediction?.home_score ?? 0;
			const currentAway = unsaved?.away_score ?? prediction?.away_score ?? 0;

			if (type === 'home') {
				updateLocalPrediction(fixture.id, newScore, currentAway);
			} else {
				updateLocalPrediction(fixture.id, currentHome, newScore);
			}
		}
	}

	$: timeUntil = getTimeUntilKickoff(fixture.kickoff);
	$: isUrgent = !fixture.is_locked && timeUntil && timeUntil.includes('m') && !timeUntil.includes('h');
</script>

<div class="match-card" class:locked={fixture.is_locked}>
	<!-- Match header -->
	<div class="flex justify-between items-center mb-2 sm:mb-4">
		<div class="flex items-center gap-2">
			<span class="text-xs text-base-content/50 font-medium">
				{formatKickoff(fixture.kickoff)}
			</span>
			{#if fixture.group}
				<span class="text-[10px] uppercase tracking-wider px-2 py-0.5 bg-base-100 rounded-full text-base-content/40">
					Group {fixture.group}
				</span>
			{/if}
		</div>
		{#if fixture.is_locked}
			<span class="flex items-center gap-1.5 text-xs px-2 py-1 bg-error/20 text-error rounded-md border border-error/30">
				<svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
				</svg>
				Locked
			</span>
		{:else}
			<span class="countdown-timer" class:urgent={isUrgent}>
				{timeUntil}
			</span>
		{/if}
	</div>

	<!-- Teams and Score inputs -->
	<div class="match-content">
		<!-- Home Team -->
		<div class="team-section">
			{#if hasFlag(fixture.home_team)}
				<img
					src={getFlagUrl(fixture.home_team, 'md')}
					alt="{fixture.home_team} flag"
					class="team-flag"
					loading="lazy"
				/>
			{:else}
				<div class="team-flag-placeholder"></div>
			{/if}
			<span class="team-name-card">{fixture.home_team}</span>
		</div>

		<!-- Score inputs with VS -->
		<div class="score-section">
			<input
				type="number"
				inputmode="numeric"
				min="0"
				max="20"
				class="score-input"
				value={displayHomeScore}
				on:input={(e) => handleInput(e, 'home')}
				on:click={(e) => e.currentTarget.select()}
				disabled={fixture.is_locked}
				aria-label="{fixture.home_team} score"
			/>

			<div class="vs-badge">VS</div>

			<input
				type="number"
				inputmode="numeric"
				min="0"
				max="20"
				class="score-input"
				value={displayAwayScore}
				on:input={(e) => handleInput(e, 'away')}
				on:click={(e) => e.currentTarget.select()}
				disabled={fixture.is_locked}
				aria-label="{fixture.away_team} score"
			/>
		</div>

		<!-- Away Team -->
		<div class="team-section">
			{#if hasFlag(fixture.away_team)}
				<img
					src={getFlagUrl(fixture.away_team, 'md')}
					alt="{fixture.away_team} flag"
					class="team-flag"
					loading="lazy"
				/>
			{:else}
				<div class="team-flag-placeholder"></div>
			{/if}
			<span class="team-name-card">{fixture.away_team}</span>
		</div>
	</div>

	<!-- Unsaved indicator -->
	{#if unsaved}
		<div class="mt-2 sm:mt-3 flex items-center justify-center gap-1.5 text-[10px] sm:text-xs text-accent">
			<span class="w-1.5 h-1.5 rounded-full bg-accent animate-pulse"></span>
			Unsaved
		</div>
	{/if}
</div>

<style>
	.match-content {
		@apply flex items-start justify-between;
	}

	.team-section {
		@apply flex flex-col items-center gap-1 sm:gap-2 flex-1;
		min-width: 0;
	}

	.team-flag {
		@apply w-8 sm:w-10 h-auto rounded shadow-sm;
	}

	.team-flag-placeholder {
		@apply w-8 sm:w-10 h-5 sm:h-6 bg-base-300 rounded;
	}

	.team-name-card {
		@apply font-semibold text-xs sm:text-sm leading-tight text-center;
		/* Never break words - only wrap between words */
		word-break: normal;
		overflow-wrap: normal;
		hyphens: none;
		white-space: normal;
	}

	.score-section {
		@apply flex items-center gap-1 sm:gap-2 flex-shrink-0 mx-2 sm:mx-4;
		/* Add vertical padding to align with flag tops */
		padding-top: 2px;
	}

	/* Ensure inputs are clickable */
	.score-input {
		@apply relative z-10 cursor-text;
	}
</style>
