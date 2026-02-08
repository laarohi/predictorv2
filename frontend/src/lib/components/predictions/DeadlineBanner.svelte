<script lang="ts">
	import Icon from '$components/Icon.svelte';

	export let countdown: string;
	export let isLocked: boolean;
	export let phase: 'phase1' | 'phase2';

	$: showCountdown = !isLocked && countdown !== 'Not set' && countdown !== 'Locked';
</script>

{#if showCountdown}
	<div class="flex items-center gap-3 px-4 py-3 rounded-xl
		{phase === 'phase1' ? 'bg-primary/10 border border-primary/20' : 'bg-accent/10 border border-accent/20'}">
		<Icon name="clock" class="w-5 h-5 flex-shrink-0 {phase === 'phase1' ? 'text-primary' : 'text-accent'}" />
		<div class="flex-1 min-w-0">
			<p class="text-sm font-medium {phase === 'phase1' ? 'text-primary' : 'text-accent'}">
				{#if phase === 'phase1'}
					Predictions lock in <span class="font-mono">{countdown}</span>
				{:else}
					Bracket predictions lock in <span class="font-mono">{countdown}</span>
				{/if}
			</p>
			<p class="text-xs text-base-content/50">
				{#if phase === 'phase1'}
					Complete your group stage and bracket predictions
				{:else}
					Submit your knockout bracket before the deadline
				{/if}
			</p>
		</div>
	</div>
{/if}

{#if isLocked}
	<div class="flex items-center gap-3 px-4 py-3 bg-base-300/50 border border-base-300 rounded-xl">
		<Icon name="lock" class="w-5 h-5 text-base-content/50 flex-shrink-0" />
		<div class="flex-1">
			<p class="text-sm font-medium text-base-content/70">
				{#if phase === 'phase1'}
					Phase 1 predictions are locked
				{:else}
					Bracket predictions are locked
				{/if}
			</p>
			<p class="text-xs text-base-content/50">
				{#if phase === 'phase1'}
					Group stage and bracket predictions can no longer be changed
				{:else}
					Match score predictions lock 5 minutes before each kickoff
				{/if}
			</p>
		</div>
	</div>
{/if}
