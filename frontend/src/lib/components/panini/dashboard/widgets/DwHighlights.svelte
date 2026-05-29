<script context="module" lang="ts">
	export type Highlight = {
		label: string;
		valueHtml: string;
		valueTone?: 'gold' | 'red';
		desc: string;
		tag?: { label: string; tone?: 'gold' | 'red' | 'green' };
	};
</script>

<script lang="ts">
	/**
	 * Post-competition retrospective. 2×2 grid of "highlight" cards — each
	 * showing one notable user stat: best exact streak, biggest single-day
	 * climb, most contrarian win, best phase, etc.
	 *
	 * Cards are presentational only; the parent assembles them from the
	 * /me/highlights endpoint.
	 */
	export let title: string = 'Your highlights';
	export let highlights: Highlight[] = [];
</script>

<div class="pn-hlights">
	<div class="label"><span class="pip"></span> {title}</div>
	<div class="h-grid">
		{#each highlights as h, i (i)}
			<div class="h-card">
				<div class="h-l">{h.label}</div>
				<div class="h-v" class:gold={h.valueTone === 'gold'}>{@html h.valueHtml}</div>
				<div class="h-d">{@html h.desc}</div>
				{#if h.tag}
					<span class="tag" class:red={h.tag.tone === 'red'} class:green={h.tag.tone === 'green'}>
						{h.tag.label}
					</span>
				{/if}
			</div>
		{/each}
	</div>
</div>
