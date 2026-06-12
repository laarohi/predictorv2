<script lang="ts">
	/**
	 * Scoreline heatmap — every player's pick for one fixture. 5×5 (goals
	 * 0–4 per side) by default, expanding per axis when a pick or the
	 * actual result goes beyond 4 goals.
	 *
	 * Successor to PnBubbleGrid (same props, same call sites): cell colour
	 * intensity scales with how many predictors picked that score, the
	 * number in the cell is that count, and hue keeps the original
	 * semantics — W/D/L pre-match, exact/outcome/miss once a result
	 * exists. Layout ported from the prediction-model's Heatmap.svelte
	 * (plain CSS grid instead of SVG), tooltips carried over verbatim
	 * from the bubble grid.
	 */
	import PnFlag from './PnFlag.svelte';
	import type { BubbleCell, GridPlayer } from '$lib/utils/matchDetail';
	import { classifyPick, heatColor, outcomeOf } from '$lib/utils/matchDetail';
	import { logarithmicRarityBonus } from '$lib/utils/matchBreakdown';

	export let mode: 'pre' | 'post';
	export let homeCode: string;
	export let awayCode: string;
	export let actual: { home_score: number; away_score: number } | null = null;
	export let cells: Record<string, BubbleCell>;
	export let youPlayer: GridPlayer | null = null;
	export let compact: boolean = false;
	/** Scoring values used to label hover tooltip points. */
	export let pointsExact: number = 15;
	export let pointsOutcome: number = 5;
	export let rarityCap: number = 10;
	/** Highest goal count per axis (from `gridAxes`). 4 is the floor; the
	 *  grid grows row/column-wise for high-scoring picks or results. Must
	 *  match what the caller passed to `buildCells`. */
	export let homeMax: number = 4;
	export let awayMax: number = 4;

	$: homeGoals = Array.from({ length: homeMax + 1 }, (_, i) => i);
	$: awayGoals = Array.from({ length: awayMax + 1 }, (_, i) => i);

	$: maxCount = Math.max(1, ...Object.values(cells).map((c) => c.players.length));

	// Rarity bonus paid to everyone who called the actual outcome — same
	// computation as PnMatchLeaderboard (shared logarithmic mirror of the
	// backend), so the tooltip points match the rows below the grid.
	$: totalPicks = Object.values(cells).reduce((n, c) => n + c.players.length, 0);
	$: actualOutcome =
		mode === 'post' && actual ? outcomeOf(actual.home_score, actual.away_score) : null;
	$: correctCt = actualOutcome
		? Object.values(cells)
				.filter((c) => outcomeOf(c.h, c.a) === actualOutcome)
				.reduce((n, c) => n + c.players.length, 0)
		: 0;
	$: rarBonus = actualOutcome ? logarithmicRarityBonus(totalPicks, correctCt, rarityCap) : 0;
	// Clamp mirrors buildCells — a no-op when the axes came from gridAxes.
	$: youH = youPlayer ? Math.min(homeMax, Math.max(0, youPlayer.home)) : -1;
	$: youA = youPlayer ? Math.min(awayMax, Math.max(0, youPlayer.away)) : -1;

	function kindOf(h: number, a: number): string {
		if (mode === 'pre') return 'pre-' + outcomeOf(h, a);
		return classifyPick({ home_score: h, away_score: a }, actual);
	}

	interface Tip {
		cell: BubbleCell;
		kind: string;
		left: number;
		top: number;
	}
	let tip: Tip | null = null;
	let wrapEl: HTMLDivElement;

	function showTip(c: BubbleCell, e: Event) {
		const cellRect = (e.currentTarget as HTMLElement).getBoundingClientRect();
		const wrapRect = wrapEl.getBoundingClientRect();
		const x = cellRect.left - wrapRect.left + cellRect.width / 2;
		const y = cellRect.top - wrapRect.top;
		// Same clamp as the bubble grid: keep the ~200px box inside the wrapper.
		const tooltipWidth = 200;
		tip = {
			cell: c,
			kind: kindOf(c.h, c.a),
			left: Math.min(wrapRect.width - tooltipWidth, Math.max(0, x - tooltipWidth / 2)),
			top: Math.max(0, y - 16 - 18 * c.players.length - 30)
		};
	}
	function hideTip() {
		tip = null;
	}

	function pointsFor(kind: string, bonus: number): number {
		if (kind === 'exact') return pointsExact + pointsOutcome + bonus;
		if (kind === 'outcome') return pointsOutcome + bonus;
		return 0;
	}
</script>

<div class="pn-hm-wrap" class:compact bind:this={wrapEl}>
	<!-- Top axis — away team, columns are away goals. -->
	<div class="pn-hm-axis top">
		<PnFlag code={awayCode} w={compact ? 20 : 24} h={compact ? 13 : 16} />
		<b>{awayCode}</b>
		<span class="sub">GOALS →</span>
	</div>

	<div class="pn-hm-body">
		<!-- Left axis — home team, rows are home goals (rotated strip). -->
		<div class="pn-hm-axis left">
			<span class="rot">
				<PnFlag code={homeCode} w={compact ? 20 : 24} h={compact ? 13 : 16} />
				<b>{homeCode}</b>
				<span class="sub">GOALS →</span>
			</span>
		</div>

		<div
			class="pn-hm"
			style="--hm-cols: {awayGoals.length}; --hm-ratio: {awayGoals.length + 1} / {homeGoals.length + 1};"
		>
			<div class="corner" />
			{#each awayGoals as a (`h-${a}`)}
				<div class="hdr">{a}</div>
			{/each}
			{#each homeGoals as h (`r-${h}`)}
				<div class="hdr side">{h}</div>
				{#each awayGoals as a (`c-${h}-${a}`)}
					{@const c = cells[`${h},${a}`]}
					{@const n = c ? c.players.length : 0}
					{@const kind = kindOf(h, a)}
					{@const col = n > 0 ? heatColor(kind, n, maxCount) : null}
					{@const isResult =
						mode === 'post' && actual && actual.home_score === h && actual.away_score === a}
					{@const isYou = h === youH && a === youA}
					<div
						class={'cell ' + kind}
						class:filled={n > 0}
						class:you={isYou}
						class:result={isResult}
						role="button"
						aria-label={`${n} pick${n === 1 ? '' : 's'} of ${h}-${a}`}
						tabindex={n > 0 ? 0 : -1}
						style={col ? `background:${col.bg};color:${col.fg};` : ''}
						on:mouseenter={(e) => n > 0 && c && showTip(c, e)}
						on:mouseleave={hideTip}
						on:focus={(e) => n > 0 && c && showTip(c, e)}
						on:blur={hideTip}
						on:keydown={(e) => {
							if ((e.key === 'Enter' || e.key === ' ') && n > 0 && c) showTip(c, e);
							if (e.key === 'Escape') hideTip();
						}}
					>
						{#if n > 0}
							<span class="num">{#if isResult}<span class="star">★</span>{/if}{n}</span>
						{:else}
							<span class="nil">·</span>
						{/if}
						{#if isYou}
							<span class="you-tag">YOU</span>
						{/if}
					</div>
				{/each}
			{/each}
		</div>
	</div>

	{#if tip && tip.cell.players.length > 0}
		<div class="pn-md-tip" style="left: {tip.left}px; top: {tip.top}px;">
			<div class="tip-h">
				<span>{tip.cell.h}–{tip.cell.a}</span>
				<span>
					{#if mode === 'post'}
						<span class={'tag ' + tip.kind}>
							{tip.kind === 'exact' ? '★ Exact' : tip.kind === 'outcome' ? 'Outcome' : 'No pts'}
						</span>
					{:else}
						<span class="tag">
							{tip.cell.players.length} pick{tip.cell.players.length > 1 ? 's' : ''}
						</span>
					{/if}
				</span>
			</div>
			<ul>
				{#each tip.cell.players as p (p.name)}
					{@const pts = mode === 'post' ? pointsFor(tip.kind, rarBonus) : null}
					<li class={p.you ? 'you' : ''}>
						<span>{p.you ? '◉ ' + p.name : p.name}</span>
						{#if mode === 'post' && pts != null}
							<span class={'pts ' + (pts > 0 ? 'points' : 'zero')}>
								{pts > 0 ? '+' + pts : '0'}
							</span>
						{:else if p.totalPts != null}
							<span class="pts zero">{p.totalPts}</span>
						{:else}
							<span class="pts zero">—</span>
						{/if}
					</li>
				{/each}
			</ul>
		</div>
	{/if}
</div>
