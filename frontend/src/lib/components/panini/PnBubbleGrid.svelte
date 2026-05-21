<script lang="ts">
	/**
	 * 5×5 SVG bubble plot — Mexican standoff of every prediction for one
	 * fixture. Bubble area scales with how many predictors picked that score;
	 * colour encodes either pre-match outcome (W/D/L) or post-match
	 * classification (exact / outcome / miss).
	 *
	 * Ported from the design handoff (`PnBubbleGrid` in panini-match.jsx).
	 * Axis flags come from our existing flag-icons assets rendered as SVG
	 * `<image>` elements with `data:image/svg+xml` hrefs (see
	 * PnAxisFlag.svelte). That's a native SVG primitive so it scales with
	 * the parent — the earlier foreignObject + HTML PnFlag approach
	 * misbehaved on iOS Safari.
	 * Hover tooltip is positioned in HTML over the SVG (wrapper has
	 * position: relative), driven by hovered-cell state.
	 */
	import PnAxisFlag from './PnAxisFlag.svelte';
	import type { BubbleCell, GridPlayer } from '$lib/utils/matchDetail';
	import { classifyPick, outcomeOf } from '$lib/utils/matchDetail';

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

	const N = 5;
	$: cellSize = compact ? 58 : 96;
	// padLeft / padTop reserve room for an axis-flag + 3-letter code +
	// "GOALS →" caption. Tight on mobile, generous on desktop.
	$: padLeft = compact ? 50 : 80;
	$: padTop = compact ? 44 : 64;
	$: padRight = compact ? 12 : 18;
	$: padBottom = compact ? 16 : 26;
	$: W = padLeft + N * cellSize + padRight;
	$: H = padTop + N * cellSize + padBottom;
	$: flagW = compact ? 20 : 26;
	$: flagH = compact ? 13 : 17;

	$: cellValues = Object.values(cells);
	$: maxCount = Math.max(1, ...cellValues.map((c) => c.players.length));
	// Max bubble fills ~80% of cell → r = k * sqrt(count)
	$: k = (cellSize * 0.40) / Math.sqrt(maxCount);

	$: youCell = youPlayer ? cells[`${Math.min(4, youPlayer.home)},${Math.min(4, youPlayer.away)}`] : null;
	$: youCount = youCell ? youCell.players.length : 0;
	$: youR = Math.max(8, k * Math.sqrt(youCount || 1));

	function cellX(a: number): number { return padLeft + a * cellSize + cellSize / 2; }
	function cellY(h: number): number { return padTop + h * cellSize + cellSize / 2; }

	function cellKind(h: number, a: number): string {
		if (mode === 'pre') {
			return 'pre-' + outcomeOf(h, a);
		}
		return classifyPick({ home_score: h, away_score: a }, actual);
	}

	interface Tip {
		cell: BubbleCell;
		kind: string;
		x: number;
		y: number;
	}
	let tip: Tip | null = null;

	function handleEnter(c: BubbleCell, cx: number, cy: number, r: number) {
		tip = { cell: c, kind: cellKind(c.h, c.a), x: cx, y: cy - r - 6 };
	}
	function handleLeave() {
		tip = null;
	}

	function tipPos(t: Tip): { left: number; top: number } {
		// Mirror of the React version's clamp — keep tooltip inside the SVG box.
		const tooltipWidth = 200;
		const left = Math.min(W - tooltipWidth, Math.max(0, t.x - tooltipWidth / 2));
		const top = Math.max(0, t.y - 12 - 18 * t.cell.players.length - 30);
		return { left, top };
	}

	function pointsFor(kind: string): number {
		if (kind === 'exact') return pointsExact + pointsOutcome;
		if (kind === 'outcome') return pointsOutcome;
		return 0;
	}

	$: drawCount = cellValues.reduce(
		(acc, c) => (c.h === c.a ? acc + c.players.length : acc),
		0
	);
</script>

<div class="bubble-wrap">
	<svg class="pn-md-bubble" viewBox={`0 0 ${W} ${H}`} width="100%" style="max-width: {W}px;">
		<!-- Top axis title — away team flag + code, centred over the plot. -->
		<g transform={`translate(${padLeft + (N * cellSize) / 2}, ${compact ? 4 : 8})`}>
			<PnAxisFlag
				code={awayCode}
				x={compact ? -64 : -84}
				y={compact ? 2 : 4}
				w={flagW}
				h={flagH}
			/>
			<text class="axis-title" x={compact ? -40 : -54} y={compact ? 13 : 18} text-anchor="start" style="font-size: {compact ? 13 : 16}px;">
				{awayCode}
			</text>
			<text class="axis-title" x={compact ? 0 : 6} y={compact ? 13 : 18} text-anchor="start">
				<tspan class="sub" style="font-size: {compact ? 8.5 : 10}px;">GOALS →</tspan>
			</text>
		</g>

		<!-- Left axis title — home team flag + code (group rotated). -->
		<g transform={`translate(${compact ? 10 : 14}, ${padTop + (N * cellSize) / 2}) rotate(-90)`}>
			<PnAxisFlag
				code={homeCode}
				x={compact ? -64 : -84}
				y={compact ? -8 : -11}
				w={flagW}
				h={flagH}
			/>
			<text class="axis-title" x={compact ? -40 : -54} y={compact ? 4 : 5} text-anchor="start" style="font-size: {compact ? 13 : 16}px;">
				{homeCode}
			</text>
			<text class="axis-title" x={compact ? 0 : 6} y={compact ? 4 : 5} text-anchor="start">
				<tspan class="sub" style="font-size: {compact ? 8.5 : 10}px;">GOALS →</tspan>
			</text>
		</g>

		<!-- Axis numbers — away (top) -->
		{#each Array.from({ length: N }, (_, i) => i) as i (`ax-${i}`)}
			<text
				class="axis-num"
				x={cellX(i)}
				y={padTop - (compact ? 6 : 10)}
				text-anchor="middle"
				style="font-size: {compact ? 11 : 14}px;"
			>{i}</text>
		{/each}
		<!-- Axis numbers — home (left) -->
		{#each Array.from({ length: N }, (_, i) => i) as i (`ay-${i}`)}
			<text
				class="axis-num"
				x={padLeft - (compact ? 8 : 14)}
				y={cellY(i) + (compact ? 4 : 5)}
				text-anchor="end"
				style="font-size: {compact ? 11 : 14}px;"
			>{i}</text>
		{/each}

		<!-- Plot frame -->
		<rect class="plot-frame" x={padLeft} y={padTop} width={N * cellSize} height={N * cellSize} />

		<!-- Gridlines -->
		{#each Array.from({ length: N - 1 }, (_, i) => i) as i (`gv-${i}`)}
			<line
				class="gridline"
				x1={padLeft + (i + 1) * cellSize}
				x2={padLeft + (i + 1) * cellSize}
				y1={padTop}
				y2={padTop + N * cellSize}
			/>
		{/each}
		{#each Array.from({ length: N - 1 }, (_, i) => i) as i (`gh-${i}`)}
			<line
				class="gridline"
				y1={padTop + (i + 1) * cellSize}
				y2={padTop + (i + 1) * cellSize}
				x1={padLeft}
				x2={padLeft + N * cellSize}
			/>
		{/each}

		<!-- Diagonal -->
		<line
			class="diagonal"
			x1={padLeft}
			y1={padTop}
			x2={padLeft + N * cellSize}
			y2={padTop + N * cellSize}
		/>

		<!-- DRAW label rotated 45° along the diagonal -->
		{#if drawCount > 0}
			{@const t = 0.78}
			{@const lx = padLeft + t * N * cellSize}
			{@const ly = padTop + t * N * cellSize}
			{@const off = compact ? 9 : 11}
			{@const ox = lx + off * Math.cos(-Math.PI / 4)}
			{@const oy = ly + off * Math.sin(-Math.PI / 4)}
			<text
				class="draw-lbl"
				x={ox}
				y={oy}
				text-anchor="middle"
				style="font-size: {compact ? 8.5 : 9.5}px;"
				transform={`rotate(45, ${ox}, ${oy})`}
			>DRAW</text>
		{/if}

		<!-- Zone labels — corner badges -->
		<text class="zone-lbl" x={padLeft + N * cellSize - 8} y={padTop + 18} text-anchor="end">
			{awayCode} win →
		</text>
		<text class="zone-lbl" x={padLeft + 8} y={padTop + N * cellSize - 10}>
			← {homeCode} win
		</text>

		<!-- Bubbles -->
		{#each cellValues as c (c.h + '-' + c.a)}
			{@const r = k * Math.sqrt(c.players.length)}
			{@const kind = cellKind(c.h, c.a)}
			{@const cx = cellX(c.a)}
			{@const cy = cellY(c.h)}
			{@const isResult = mode === 'post' && actual && actual.home_score === c.h && actual.away_score === c.a}
			{@const showLabel = c.players.length >= 3}
			<g
				class={'bub ' + kind}
				role="button"
				aria-label={`${c.players.length} pick${c.players.length === 1 ? '' : 's'} of ${c.h}-${c.a}`}
				on:mouseenter={() => handleEnter(c, cx, cy, r)}
				on:mouseleave={handleLeave}
				on:focus={() => handleEnter(c, cx, cy, r)}
				on:blur={handleLeave}
				on:keydown={(e) => {
					if (e.key === 'Enter' || e.key === ' ') handleEnter(c, cx, cy, r);
					if (e.key === 'Escape') handleLeave();
				}}
				tabindex="0"
			>
				<circle class="fill" cx={cx} cy={cy} r={r} />
				{#if showLabel}
					<text class={isResult ? 'star' : ''} x={cx} y={cy + 5}>
						{isResult ? '★ ' + c.players.length : c.players.length}
					</text>
				{/if}
			</g>
		{/each}

		<!-- User-pick ring + YOU tag -->
		{#if youPlayer && youCell}
			<circle
				class="you-ring"
				cx={cellX(Math.min(4, youPlayer.away))}
				cy={cellY(Math.min(4, youPlayer.home))}
				r={youR + 5}
			/>
			<rect
				class="you-tag-bg"
				x={cellX(Math.min(4, youPlayer.away)) - 17}
				y={cellY(Math.min(4, youPlayer.home)) + youR + 8}
				width={34}
				height={15}
			/>
			<text
				class="you-tag"
				x={cellX(Math.min(4, youPlayer.away))}
				y={cellY(Math.min(4, youPlayer.home)) + youR + 18.5}
				text-anchor="middle"
			>YOU</text>
		{/if}
	</svg>

	{#if tip && tip.cell.players.length > 0}
		{@const pos = tipPos(tip)}
		<div class="pn-md-tip" style="left: {pos.left}px; top: {pos.top}px;">
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
					{@const pts = mode === 'post' ? pointsFor(tip.kind) : null}
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

<style>
	.bubble-wrap {
		position: relative;
		display: block;
	}
</style>
