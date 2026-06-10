<script context="module" lang="ts">
	export type Source = {
		key: 'match' | 'p1' | 'p2' | 'bonus';
		name: string;
		points: number;
		/** Optional inline hint rendered after the name. */
		suffix?: string;
	};
</script>

<script lang="ts">
	/**
	 * Post-competition / KO summary card splitting the user's total points by
	 * source:
	 *   match scores · P1 bracket · P2 bracket · bonus questions
	 *
	 * Each row gets a coloured horizontal bar where the fill width is
	 * proportional to the source's points relative to the largest source —
	 * makes the "which lane carried me" question visually obvious.
	 */
	export let sources: Source[] = [];
	export let total: number = 0;
	export let title: string = 'Points · by';
	export let titleEm: string = 'source';
	export let meta: string = 'final';
	export let footLabel: string = 'See full breakdown →';
	export let footHref: string = '/leaderboard';

	$: maxPts = Math.max(1, ...sources.map((s) => s.points));
	$: totalSum = total > 0 ? total : sources.reduce((acc, s) => acc + s.points, 0);
</script>

<div class="pn-source">
	<div class="pn-sec-h" style="margin-bottom: 14px;">
		<span class="ttl"><span class="pip"></span> {title} <em>{titleEm}</em></span>
		<span class="meta">{meta}</span>
	</div>

	{#each sources as s (s.key)}
		{@const pct = (s.points / maxPts) * 100}
		{@const share = totalSum > 0 ? Math.round((s.points / totalSum) * 100) : 0}
		<div class="src-row">
			<div class="lbl">
				<span class="nm">
					{s.name}
					{#if s.suffix}<span style="font-size: 10px; color: var(--ink-3);">{s.suffix}</span>{/if}
				</span>
				<span class="v"><b>{s.points}</b> · {share}%</span>
			</div>
			<div class="bar"><div class="fill {s.key}" style="width: {pct}%"></div></div>
		</div>
	{/each}

	<!-- Total + breakdown link share one closing line — a stacked total
	     row plus a separate foot pushed the post dashboard past 900px. -->
	<div class="total">
		<span>Total <span class="v">{totalSum} pts</span></span>
		<a class="foot-link" href={footHref}>{footLabel}</a>
	</div>
</div>
