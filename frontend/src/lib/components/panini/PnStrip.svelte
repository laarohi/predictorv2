<script lang="ts">
	// Red sub-strip below the masthead — signals: live match, next lock, your rank.
	// IMPORTANT: prop labels are rendered via {@html} so the design's inline <b>
	// tags work. All call sites MUST produce labels from trusted server-derived
	// values (team names, scores, your rank). NEVER pipe user input through these
	// props — XSS risk.
	export let liveLabel: string | null = null;
	export let lockLabel: string | null = null;
	export let youLabel: string | null = null;
</script>

{#if liveLabel || lockLabel || youLabel}
	<div class="pn-strip">
		{#if liveLabel}
			<span class="live">{@html liveLabel}</span>
		{/if}
		{#if lockLabel}
			<span>{@html lockLabel}</span>
		{/if}
		{#if youLabel}
			<span class="ml">{@html youLabel}</span>
		{/if}
	</div>
{/if}
