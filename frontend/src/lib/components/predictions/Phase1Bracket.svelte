<script lang="ts">
	import { KnockoutBracket } from '$components/bracket';
	import SaveButton from '$components/SaveButton.svelte';
	import Icon from '$components/Icon.svelte';
	import type { BracketPrediction } from '$types';
	import type { TeamStanding } from '$lib/utils/standings';

	export let bracketLoading: boolean;
	export let bracketError: string | null;
	export let bracketPrediction: BracketPrediction | null;
	export let displayBracket: BracketPrediction | null;
	export let groupStandings: Record<string, TeamStanding[]>;
	export let hasBracketChanges: boolean;
	export let hasBracketSelections: boolean;
	export let bracketSaveStatus: 'idle' | 'saving' | 'saved' | 'error';
	export let bracketComponent: KnockoutBracket | undefined = undefined;
	export let lastLocalSave: Date | null = null;

	export let onRetry: () => void;
	export let onClear: () => void;
	export let onSave: () => void;
	export let onUpdate: (event: CustomEvent<BracketPrediction>) => void;

	function formatLocalTime(d: Date): string {
		return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
	}
</script>

{#if bracketLoading && !bracketPrediction}
	<div class="flex justify-center py-16">
		<span class="loading loading-spinner loading-lg text-primary"></span>
	</div>
{:else if bracketError}
	<div class="stadium-card no-glow p-8 text-center">
		<div class="text-error mb-4">
			<svg class="w-12 h-12 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
			</svg>
		</div>
		<p class="text-base-content/70">{bracketError}</p>
		<button class="btn btn-primary btn-sm mt-4" on:click={onRetry}>
			Try Again
		</button>
	</div>
{:else}
	<div class="stadium-card no-glow px-0 py-4 sm:px-6 sm:py-6 -mx-4 sm:mx-0 rounded-none sm:rounded-2xl border-0 sm:border">
		<div class="flex items-center justify-between mb-6 px-4 sm:px-0">
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
						on:click={onClear}
					>
						<Icon name="trash" class="w-3.5 h-3.5" />
						Clear All
					</button>
				{/if}
			</div>
		</div>

		<KnockoutBracket
			bind:this={bracketComponent}
			prediction={displayBracket}
			groupStandings={groupStandings}
			locked={false}
			phase="phase_1"
			on:update={onUpdate}
		/>
	</div>

	<!-- Bracket Save Button -->
	{#if hasBracketChanges}
		<div class="fixed bottom-24 sm:bottom-6 right-4 sm:right-6 z-40 flex flex-col items-end gap-1">
			<SaveButton
				status={bracketSaveStatus}
				count={1}
				on:save={onSave}
			/>
			{#if lastLocalSave}
				<p class="text-xs text-base-content/50 text-right">
					Saved locally · {formatLocalTime(lastLocalSave)}
				</p>
			{/if}
		</div>
	{/if}
{/if}
