<script lang="ts">
	// Small inline SVG sparkline used by Dashboard (rank trajectory) and
	// Leaderboard (per-player trend column). Renders a filled area + a line
	// + circle markers. Pure visualization — accepts pre-computed paths and
	// points so the caller controls scale and seeding.
	import { sparklinePath } from '$lib/stubs/panini';

	/** Rank values, oldest at [0], newest at [end]. Smaller = better. */
	export let ranks: number[];
	/** Max rank (e.g. total players) for normalising the y-axis. */
	export let maxRank: number;
	export let width: number = 240;
	export let height: number = 56;
	export let strokeColor: string = 'var(--red)';
	export let fillColor: string = 'rgba(200,40,31,0.10)';
	export let markerColor: string = 'var(--gold)';
	/** Print the rank value above each marker. Needs extra head-room
	 *  (padTop) and side-room (padX), so geometry shifts when enabled. */
	export let showLabels: boolean = false;

	// padX keeps the end markers (and labels) inside the viewBox — without
	// it the first/last circles render as half-moons at the edges.
	$: ({ linePath, fillPath, points } = sparklinePath(ranks, maxRank, {
		width,
		height,
		padTop: showLabels ? 0.28 : 0.08,
		padBottom: 0.08,
		padX: showLabels ? 13 : 6
	}));
</script>

<svg class="pn-spark" viewBox="0 0 {width} {height}" preserveAspectRatio="none" aria-hidden="true">
	{#each [0.25, 0.5, 0.75] as p}
		<line
			class="grid"
			x1="0"
			y1={height * p}
			x2={width}
			y2={height * p}
			stroke="rgba(0,0,0,0.06)"
			stroke-width="0.6"
		/>
	{/each}
	<path d={fillPath} fill={fillColor} />
	<path d={linePath} fill="none" stroke={strokeColor} stroke-width="2" />
	{#each points as [x, y], i}
		<circle
			cx={x}
			cy={y}
			r={i === points.length - 1 ? 4 : 2.5}
			fill={markerColor}
			stroke="var(--ink)"
			stroke-width="1.5"
		/>
		{#if showLabels}
			<text
				class="lab"
				class:now={i === points.length - 1}
				x={x}
				y={y - 8}
				text-anchor="middle"
			>{ranks[i]}</text>
		{/if}
	{/each}
</svg>

<style>
	.pn-spark {
		width: 100%;
		display: block;
	}
	.pn-spark .lab {
		font-family: var(--mono);
		font-size: 9.5px;
		font-weight: 600;
		fill: var(--ink-2);
	}
	.pn-spark .lab.now {
		font-weight: 700;
		fill: var(--ink);
	}
</style>
