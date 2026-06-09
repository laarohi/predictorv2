<script context="module" lang="ts">
	// no module-level exports
</script>

<script lang="ts">
	/**
	 * v4 KPI row — 6 stickers in two rows of three:
	 *
	 *   Row 1  ·  Rank · Total · Trajectory
	 *   Row 2  ·  Outcomes · Exact · Rarity bonus
	 *
	 * Rank / Total / Outcomes / Exact carry an arrow-delta chip on the value
	 * line; Trajectory uses a sparkline and its own caption; Rarity bonus
	 * surfaces what share of the user's total points came from the rarity
	 * bonus pool.
	 *
	 * Layout per panini-dashboard-v4.css `.pn-kpi-row-v4` (3-col grid).
	 */
	import PnSparkline from '$components/panini/PnSparkline.svelte';

	export let rank: number | null = null;
	export let rankOf: number = 0;
	export let rankDelta: number = 0;

	export let total: number = 0;
	export let totalDelta: number = 0;
	/** Optional contextual sub for the Total cell. Between/Post dashboards
	 *  use it for things like "X pts behind champion". In-tournament
	 *  dashboards omit it — the delta chip already conveys recency. */
	export let totalSub: string = '';

	export let exact: number = 0;
	export let exactOf: number = 0;
	export let exactDelta: number = 0;

	export let outcomes: number = 0;
	export let outcomesOf: number = 0;
	export let outcomesDelta: number = 0;

	/** Rarity bonus pts the user has accumulated (from
	 *  PointBreakdown.hybrid_bonus_points). */
	export let rarity: number = 0;
	/** Denominator for the rarity-share sub ("X% of total"). Pass the user's
	 *  total points so the sub shows what share of their score came from
	 *  rarity. 0 hides the share. */
	export let rarityShareOf: number = 0;

	/** Last N daily rank positions (newest last). 7-day default. */
	export let trajectory: number[] = [];
	export let trajectoryMaxRank: number = 30;
	export let trajectoryTodayPts: number = 0;
	/** Caption for the recent-pts stat next to the sparkline. Defaults to
	 * "Today" — pre-v4 the value WAS today's gain. With the shift to a
	 * count-based window (last N matches), dashboards pass e.g. "Last 4"
	 * so the caption matches the metric. */
	export let trajectoryNowLabel: string = 'Today';

	/** Optional foot link (e.g. "See full breakdown"). null hides the foot. */
	export let footHref: string | null = null;
	export let footLabel: string = 'See full breakdown →';

	/** Compact cells (106px instead of 140px) for the dashboards that
	 *  carry more sections than the group stage and must still fit one
	 *  900px desktop screen. */
	export let compact: boolean = false;

	$: outcomeRate = outcomesOf > 0 ? Math.round((outcomes / outcomesOf) * 100) : 0;
	$: exactRate = exactOf > 0 ? Math.round((exact / exactOf) * 100) : 0;
	$: rarityShare = rarityShareOf > 0 ? Math.round((rarity / rarityShareOf) * 100) : 0;

	function delta(d: number): { cls: 'up' | 'dn' | 'zero'; label: string } {
		if (!d) return { cls: 'zero', label: '±0' };
		const up = d > 0;
		return { cls: up ? 'up' : 'dn', label: `${up ? '↑' : '↓'}${Math.abs(d)}` };
	}

	$: rd = delta(rankDelta);
	$: td = delta(totalDelta);
	$: ed = delta(exactDelta);
	$: od = delta(outcomesDelta);

	// Sparkline endpoint trend label (▲N places · 7d). Positive = climbed.
	$: trajPlaces = trajectory.length >= 2 ? trajectory[0] - trajectory[trajectory.length - 1] : 0;
</script>

<section class="pn-kpi-row-v4" class:compact>
	<!-- Row 1 -->
	<div class="pn-kpi-v4">
		<div class="l"><span class="pip red"></span>Rank</div>
		<div class="topline">
			<div class="v">
				<span class="red">{rank ?? '—'}</span><span class="sm">/{rankOf || '—'}</span>
			</div>
			<span class="delta {rd.cls}">{rd.label}</span>
		</div>
	</div>

	<div class="pn-kpi-v4">
		<div class="l"><span class="pip"></span>Total</div>
		<div class="topline">
			<div class="v">{total}<span class="sm unit">pts</span></div>
			<span class="delta {td.cls}">{td.label}</span>
		</div>
		{#if totalSub}
			<div class="sub">{@html totalSub}</div>
		{/if}
	</div>

	<div class="pn-kpi-v4 trajectory">
		<div class="l"><span class="pip"></span>Trajectory · {trajectory.length}d</div>
		<div class="spark-wrap">
			{#if trajectory.length >= 2}
				<PnSparkline ranks={trajectory} maxRank={trajectoryMaxRank} width={240} height={56} />
			{:else}
				<div style="display: grid; place-items: center; height: 56px; font-family: var(--mono); font-size: 10px; color: var(--ink-3);">
					awaiting history
				</div>
			{/if}
		</div>
		<div class="trj-sub">
			{#if trajPlaces > 0}▲{trajPlaces} pl
			{:else if trajPlaces < 0}▼{Math.abs(trajPlaces)} pl
			{:else}— pl{/if}
			· {trajectory.length}d · {trajectoryNowLabel}: <em class="now">+{trajectoryTodayPts}</em>
		</div>
	</div>

	<!-- Row 2 -->
	<div class="pn-kpi-v4">
		<div class="l"><span class="pip"></span>Outcomes</div>
		<div class="topline">
			<div class="v">{outcomes}<span class="sm">/{outcomesOf || '—'}</span></div>
			<span class="delta {od.cls}">{od.label}</span>
		</div>
		<div class="sub"><b>{outcomeRate}%</b> hit rate</div>
	</div>

	<div class="pn-kpi-v4">
		<div class="l"><span class="pip green"></span>Exact</div>
		<div class="topline">
			<div class="v">
				<span class="green">{exact}</span><span class="sm">/{exactOf || '—'}</span>
			</div>
			<span class="delta {ed.cls}">{ed.label}</span>
		</div>
		<div class="sub"><b>{exactRate}%</b> hit rate</div>
	</div>

	<div class="pn-kpi-v4">
		<div class="l"><span class="pip"></span>Rarity bonus</div>
		<div class="topline">
			<div class="v">{rarity}<span class="sm unit">pts</span></div>
		</div>
		{#if rarityShareOf > 0}
			<div class="sub"><b>{rarityShare}%</b> of total</div>
		{/if}
	</div>
</section>

{#if footHref !== null}
	<div class="pn-kpi-foot"><a href={footHref}>{footLabel}</a></div>
{/if}
