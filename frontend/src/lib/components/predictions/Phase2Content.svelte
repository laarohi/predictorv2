<script lang="ts">
	import { KnockoutBracket } from '$components/bracket';
	import MatchCard from '$components/MatchCard.svelte';
	import SaveButton from '$components/SaveButton.svelte';
	import Icon from '$components/Icon.svelte';
	import type { BracketPrediction, Fixture, MatchPrediction } from '$types';
	import type { TeamStanding } from '$lib/utils/standings';

	export let isPhase2BracketLocked: boolean;
	export let actualStandingsLoading: boolean;
	export let actualGroupStandingsMap: Record<string, TeamStanding[]>;
	export let phase2DisplayBracket: BracketPrediction | null;
	export let hasPhase2BracketChanges: boolean;
	export let hasPhase2BracketSelections: boolean;
	export let phase2BracketSaveStatus: 'idle' | 'saving' | 'saved' | 'error';
	export let phase2BracketComponent: KnockoutBracket | undefined = undefined;
	export let knockoutRounds: { name: string; stage: string; fixtures: Fixture[] }[];
	export let predictionMap: Map<string, MatchPrediction>;
	export let hasUnsavedChanges: boolean;
	export let saveStatus: 'idle' | 'saving' | 'saved' | 'error';
	export let unsavedChangesCount: number;
	export let lastLocalSave: Date | null = null;

	export let onClearBracket: () => void;
	export let onSaveBracket: () => void;
	export let onSaveAll: () => void;
	export let onBracketUpdate: (event: CustomEvent<BracketPrediction>) => void;

	function formatLocalTime(d: Date): string {
		return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
	}
</script>

<!-- Floating save button for Phase 2 match predictions -->
{#if hasUnsavedChanges}
	<div class="fixed bottom-24 sm:bottom-6 right-4 sm:right-6 z-40 flex flex-col items-end gap-1">
		<SaveButton
			status={saveStatus}
			count={unsavedChangesCount}
			on:save={onSaveAll}
		/>
		{#if lastLocalSave}
			<p class="text-xs text-base-content/50 text-right">
				Saved locally · {formatLocalTime(lastLocalSave)}
			</p>
		{/if}
	</div>
{/if}

<div class="space-y-6">
	<!-- Phase 2 Bracket Section -->
	<div class="stadium-card no-glow p-4 sm:p-6">
		<div class="flex items-center justify-between mb-6">
			<div>
				<h2 class="text-xl font-display tracking-wide">Knockout Bracket</h2>
				<p class="text-xs text-base-content/50 mt-1">
					{#if isPhase2BracketLocked}
						Your bracket predictions are locked
					{:else}
						Predict the knockout stage outcomes
					{/if}
				</p>
			</div>
			<div class="flex items-center gap-4">
				{#if hasPhase2BracketChanges && !isPhase2BracketLocked}
					<span class="flex items-center gap-2 text-xs text-accent">
						<span class="w-2 h-2 rounded-full bg-accent animate-pulse"></span>
						Unsaved changes
					</span>
				{/if}
				{#if isPhase2BracketLocked}
					<div class="badge badge-ghost gap-1">
						<Icon name="lock" class="w-3 h-3" />
						Locked
					</div>
				{:else if hasPhase2BracketSelections}
					<button
						class="text-xs font-medium text-base-content/40 hover:text-error transition-all duration-200 flex items-center gap-1.5 px-3 py-1.5 rounded-lg hover:bg-error/10 border border-transparent hover:border-error/20"
						on:click={onClearBracket}
					>
						<Icon name="trash" class="w-3.5 h-3.5" />
						Clear All
					</button>
				{/if}
			</div>
		</div>

		{#if actualStandingsLoading}
			<div class="flex justify-center py-16">
				<span class="loading loading-spinner loading-lg text-accent"></span>
			</div>
		{:else if Object.keys(actualGroupStandingsMap).length === 0}
			<div class="flex flex-col items-center justify-center py-12 text-center">
				<svg class="w-16 h-16 text-base-content/20 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
					<path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
				</svg>
				<p class="text-base-content/50 text-sm">Group stage not yet complete</p>
				<p class="text-base-content/30 text-xs mt-1">Bracket will be available once group stage results are finalized</p>
			</div>
		{:else}
			<KnockoutBracket
				bind:this={phase2BracketComponent}
				prediction={phase2DisplayBracket}
				groupStandings={actualGroupStandingsMap}
				locked={isPhase2BracketLocked}
				phase="phase_2"
				on:update={onBracketUpdate}
			/>
		{/if}
	</div>

	<!-- Phase 2 Bracket Save Button -->
	{#if hasPhase2BracketChanges && !isPhase2BracketLocked}
		<div class="fixed bottom-24 sm:bottom-6 right-4 sm:right-6 z-40 flex flex-col items-end gap-1">
			<SaveButton
				status={phase2BracketSaveStatus}
				count={1}
				on:save={onSaveBracket}
			/>
			{#if lastLocalSave}
				<p class="text-xs text-base-content/50 text-right">
					Saved locally · {formatLocalTime(lastLocalSave)}
				</p>
			{/if}
		</div>
	{/if}

	<!-- Phase 2 Match Predictions Section -->
	{#if knockoutRounds.length === 0}
		<div class="stadium-card no-glow p-4 sm:p-6">
			<div class="flex items-center gap-3 mb-5">
				<div class="w-10 h-10 rounded-xl bg-accent/10 flex items-center justify-center">
					<svg class="w-5 h-5 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
					</svg>
				</div>
				<div>
					<h2 class="text-lg font-display tracking-wide">Knockout Match Predictions</h2>
					<p class="text-xs text-base-content/50">Predict exact scores for knockout matches</p>
				</div>
			</div>

			<div class="flex flex-col items-center justify-center py-12 text-center">
				<svg class="w-16 h-16 text-base-content/20 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
					<path stroke-linecap="round" stroke-linejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
				</svg>
				<p class="text-base-content/50 text-sm">No knockout fixtures available yet</p>
				<p class="text-base-content/30 text-xs mt-1">Fixtures will appear once the knockout stage begins</p>
			</div>
		</div>
	{:else}
		{#each knockoutRounds as round, roundIndex}
			<div class="stadium-card no-glow p-4 sm:p-6 animate-slide-up" style="animation-delay: {roundIndex * 50}ms; animation-fill-mode: both;">
				<div class="flex items-center gap-3 mb-5">
					<div class="w-10 h-10 rounded-xl bg-accent/10 flex items-center justify-center">
						<svg class="w-5 h-5 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
						</svg>
					</div>
					<div>
						<h2 class="text-lg font-display tracking-wide">{round.name}</h2>
						<p class="text-xs text-base-content/50">{round.fixtures.length} matches</p>
					</div>
				</div>

				<div class="match-grid">
					{#each round.fixtures as fixture}
						<MatchCard
							{fixture}
							prediction={predictionMap.get(fixture.id)}
						/>
					{/each}
				</div>
			</div>
		{/each}
	{/if}
</div>
