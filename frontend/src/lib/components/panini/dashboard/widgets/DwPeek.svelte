<script context="module" lang="ts">
	export type Rule = {
		pts: string;
		ptsTone?: 'red' | 'gold' | 'navy' | 'green';
		ptsUnit?: string;
		name: string;
		desc?: string;
	};
	export type Item = {
		ix: string;
		name: string;
		desc?: string;
		value?: string;
	};
</script>

<script lang="ts">
	/**
	 * "Peek" card — content depends on `mode`:
	 *
	 *   mode="rules"   — `rules` prop: list of { pts, ptsTone, ptsUnit,
	 *                    name, desc }
	 *   mode="items"   — `items` prop: list of { ix, name, desc, value }
	 *                    (used for "Tournament structure" rundown)
	 *
	 * Pure presentational; both renderings share the .pn-peek chrome.
	 */
	export let mode: 'rules' | 'items' = 'rules';
	export let title: string = '';
	export let titleEm: string = '';
	export let meta: string = '';
	export let rules: Rule[] = [];
	export let items: Item[] = [];
	export let footLabel: string = 'Read full rules →';
	export let footHref: string = '/rules';
</script>

<div class="pn-peek">
	<div class="hd">
		<span class="ttl">{title}{#if titleEm} <em>{titleEm}</em>{/if}</span>
		{#if meta}<span class="meta">{meta}</span>{/if}
	</div>

	{#if mode === 'rules'}
		<div class="rules-list">
			{#each rules as r, i (i)}
				<div class="rule">
					<div
						class="pts"
						class:gold={r.ptsTone === 'gold'}
						class:navy={r.ptsTone === 'navy'}
						class:green={r.ptsTone === 'green'}
					>
						{r.pts}{#if r.ptsUnit}<span class="pl">{r.ptsUnit}</span>{/if}
					</div>
					<div class="nm">
						{r.name}
						{#if r.desc}<span class="desc">{r.desc}</span>{/if}
					</div>
				</div>
			{/each}
		</div>
	{:else}
		<div class="item-list">
			{#each items as it, i (i)}
				<div class="item">
					<span class="ix">{it.ix}</span>
					<div class="nm">
						{it.name}
						{#if it.desc}<span class="desc">{it.desc}</span>{/if}
					</div>
					{#if it.value}<span class="v">{it.value}</span>{/if}
				</div>
			{/each}
		</div>
	{/if}

	<div class="foot"><a href={footHref}>{footLabel}</a></div>
</div>
