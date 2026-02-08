<script lang="ts">
	import { createEventDispatcher } from 'svelte';

	export let status: 'idle' | 'saving' | 'saved' | 'error' = 'idle';
	export let count: number = 0;

	const dispatch = createEventDispatcher<{ save: void }>();

	function handleClick() {
		if (status === 'saving') return;
		dispatch('save');
	}
</script>

<button
	class="save-btn"
	class:saving={status === 'saving'}
	class:saved={status === 'saved'}
	class:error={status === 'error'}
	on:click={handleClick}
	disabled={status === 'saving'}
>
	<span class="save-btn-content">
		{#if status === 'saving'}
			<svg class="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
				<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
				<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
			</svg>
			<span>Saving...</span>
		{:else if status === 'saved'}
			<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
				<path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
			</svg>
			<span>Saved!</span>
		{:else if status === 'error'}
			<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
			</svg>
			<span>Error</span>
		{:else}
			<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
			</svg>
			<span>Save {count} {count === 1 ? 'change' : 'changes'}</span>
		{/if}
	</span>
</button>

<style>
	.save-btn {
		@apply flex items-center gap-2 px-5 py-3 rounded-xl font-semibold text-sm;
		@apply bg-primary text-primary-content;
		@apply shadow-lg shadow-primary/30;
		@apply transition-all duration-200 ease-out;
		@apply hover:shadow-xl hover:shadow-primary/40 hover:scale-105;
		@apply active:scale-95;
		@apply disabled:opacity-70 disabled:cursor-not-allowed disabled:hover:scale-100;
		animation: slide-up 0.3s ease-out;
	}

	.save-btn.saving {
		@apply bg-primary/80;
	}

	.save-btn.saved {
		@apply bg-success shadow-success/30;
		@apply hover:shadow-success/40;
	}

	.save-btn.error {
		@apply bg-error shadow-error/30;
		@apply hover:shadow-error/40;
	}

	.save-btn-content {
		@apply flex items-center gap-2;
	}
</style>
