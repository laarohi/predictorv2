<script lang="ts">
	export let progress: number;
	export let breakdown: { label: string; value: number }[] = [];
	export let phase: 'phase1' | 'phase2' = 'phase1';
</script>

<div class="sticky top-16 z-30 -mx-4 sm:-mx-0 px-4 sm:px-0 py-2 sm:py-3 bg-base-100/95 backdrop-blur-sm border-b border-base-300/30 -mt-2 mb-4">
	<div class="flex items-center gap-3">
		<div class="flex-1 h-1.5 sm:h-2 bg-base-300 rounded-full overflow-hidden">
			<div
				class="h-full transition-all duration-500 ease-out rounded-full
					{phase === 'phase1' ? 'bg-gradient-to-r from-primary to-accent' : 'bg-gradient-to-r from-accent to-primary'}"
				style="width: {progress}%"
			></div>
		</div>
		<span class="text-xs font-medium text-base-content/70 tabular-nums w-10 text-right">{progress}%</span>
		{#if breakdown.length > 0}
			<div class="hidden sm:flex items-center gap-2 text-xs text-base-content/40 border-l border-base-300/50 pl-3">
				{#each breakdown as item}
					<span>{item.label}: {item.value}%</span>
				{/each}
			</div>
		{/if}
	</div>
</div>
