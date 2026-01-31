<script lang="ts">
	export let message: string | null = null;
</script>

{#if message}
	<div class="mb-6 p-4 bg-error/10 border border-error/30 rounded-lg text-error text-sm flex items-center gap-3">
		<svg class="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
		</svg>
		<span>{message}</span>
	</div>
{/if}
