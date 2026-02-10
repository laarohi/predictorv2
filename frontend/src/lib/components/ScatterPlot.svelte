<script lang="ts">
	import type { CommunityPrediction, FixtureScore } from '$types';

	export let predictions: CommunityPrediction[];
	export let actual: FixtureScore | null;
	export let homeTeam: string;
	export let awayTeam: string;

	// SVG dimensions
	const svgSize = 320;
	const pad = 44;
	const plotSize = svgSize - pad * 2; // 232

	// Compute grid max from data
	$: allScores = [
		...predictions.flatMap((p) => [p.home_score, p.away_score]),
		...(actual ? [actual.home_score, actual.away_score] : [])
	];
	$: maxScore = Math.max(4, Math.min(7, Math.max(...allScores, 0) + 1));

	// Scale helpers
	$: cellSize = plotSize / maxScore;
	function toX(awayScore: number): number {
		return pad + awayScore * cellSize + cellSize / 2;
	}
	function toY(homeScore: number): number {
		return pad + (maxScore - homeScore) * cellSize - cellSize / 2;
	}

	// Group predictions by coordinate
	interface GroupedPrediction {
		home: number;
		away: number;
		count: number;
		names: string[];
	}
	$: grouped = (() => {
		const map = new Map<string, GroupedPrediction>();
		for (const p of predictions) {
			const key = `${p.home_score},${p.away_score}`;
			const existing = map.get(key);
			if (existing) {
				existing.count++;
				existing.names.push(p.user_name);
			} else {
				map.set(key, { home: p.home_score, away: p.away_score, count: 1, names: [p.user_name] });
			}
		}
		return Array.from(map.values());
	})();

	// Determine which outcome region a point falls into
	function getPointOutcome(home: number, away: number): string {
		if (home > away) return '1';
		if (home < away) return '2';
		return 'X';
	}

	// Region paths for outcome zones
	$: regionPaths = (() => {
		const left = pad;
		const top = pad;
		const right = pad + plotSize;
		const bottom = pad + plotSize;

		// In our coordinate system:
		// X-axis = away score (left=0), Y-axis = home score (top=max, bottom=0)
		// Home win (home > away): above the diagonal
		// Away win (away > home): below the diagonal
		// Draw: along the diagonal band

		// Diagonal line goes from (left, bottom) to (right, top) in plot coords
		// Actually, we need to think in grid cells
		const diagPoints: string[] = [];
		const diagPointsReverse: string[] = [];

		// Draw zone: cells where home == away
		// Home win zone: cells where home > away (above diagonal)
		// Away win zone: cells where home < away (below diagonal)

		// Simple approach: the diagonal from bottom-left to top-right
		// Bottom-left corner = (away=0, home=0) = screen (pad, bottom)
		// Top-right corner = (away=max, home=max) = screen (right, top)

		return {
			homeWin: `M ${left} ${bottom} L ${left} ${top} L ${right} ${top} Z`,
			awayWin: `M ${left} ${bottom} L ${right} ${bottom} L ${right} ${top} Z`,
			// Draw zone is the thin band, but for simplicity we skip it
		};
	})();

	// Tooltip state
	let hoveredGroup: GroupedPrediction | null = null;
	let tooltipX = 0;
	let tooltipY = 0;

	function showTooltip(group: GroupedPrediction, event: MouseEvent | TouchEvent) {
		hoveredGroup = group;
		if (event instanceof MouseEvent) {
			tooltipX = event.offsetX;
			tooltipY = event.offsetY - 10;
		} else if (event.touches.length > 0) {
			const rect = (event.currentTarget as Element).closest('svg')?.getBoundingClientRect();
			if (rect) {
				tooltipX = event.touches[0].clientX - rect.left;
				tooltipY = event.touches[0].clientY - rect.top - 10;
			}
		}
	}

	function hideTooltip() {
		hoveredGroup = null;
	}

	// Star polygon points for the actual result marker
	function starPoints(cx: number, cy: number, outerR: number, innerR: number, points: number): string {
		const coords: string[] = [];
		for (let i = 0; i < points * 2; i++) {
			const angle = (Math.PI / points) * i - Math.PI / 2;
			const r = i % 2 === 0 ? outerR : innerR;
			coords.push(`${cx + r * Math.cos(angle)},${cy + r * Math.sin(angle)}`);
		}
		return coords.join(' ');
	}

	// Tick marks
	$: ticks = Array.from({ length: maxScore + 1 }, (_, i) => i);

	// Base radius for grouped dots
	const baseRadius = 6;
</script>

<div class="w-full max-w-sm mx-auto relative" on:click={hideTooltip} role="presentation">
	<svg viewBox="0 0 {svgSize} {svgSize}" class="w-full h-auto" xmlns="http://www.w3.org/2000/svg">
		<!-- Outcome region fills -->
		{#if actual}
			<path
				d={regionPaths.homeWin}
				fill={actual.outcome === '1' ? 'rgba(0, 200, 83, 0.06)' : 'rgba(255, 255, 255, 0.01)'}
			/>
			<path
				d={regionPaths.awayWin}
				fill={actual.outcome === '2' ? 'rgba(56, 189, 248, 0.06)' : 'rgba(255, 255, 255, 0.01)'}
			/>
		{/if}

		<!-- Grid lines -->
		{#each ticks as t}
			<!-- Vertical lines (away score) -->
			<line
				x1={pad + t * cellSize}
				y1={pad}
				x2={pad + t * cellSize}
				y2={pad + plotSize}
				class="stroke-base-content/10"
				stroke-width="0.5"
			/>
			<!-- Horizontal lines (home score) -->
			<line
				x1={pad}
				y1={pad + t * cellSize}
				x2={pad + plotSize}
				y2={pad + t * cellSize}
				class="stroke-base-content/10"
				stroke-width="0.5"
			/>
		{/each}

		<!-- Diagonal line (draw line) -->
		<line
			x1={toX(0)}
			y1={toY(0)}
			x2={toX(maxScore - 1)}
			y2={toY(maxScore - 1)}
			class="stroke-warning/20"
			stroke-width="1"
			stroke-dasharray="4 4"
		/>

		<!-- Axis labels: ticks -->
		{#each ticks.slice(0, maxScore) as t}
			<!-- X-axis (away score) -->
			<text
				x={toX(t)}
				y={pad + plotSize + 18}
				text-anchor="middle"
				class="fill-base-content/40"
				font-size="11"
				font-family="'Bebas Neue', monospace"
			>{t}</text>
			<!-- Y-axis (home score) -->
			<text
				x={pad - 14}
				y={toY(t) + 4}
				text-anchor="middle"
				class="fill-base-content/40"
				font-size="11"
				font-family="'Bebas Neue', monospace"
			>{t}</text>
		{/each}

		<!-- Axis labels: team names -->
		<text
			x={pad + plotSize / 2}
			y={svgSize - 4}
			text-anchor="middle"
			class="fill-base-content/50"
			font-size="11"
			font-weight="600"
		>{awayTeam}</text>
		<text
			x={10}
			y={pad + plotSize / 2}
			text-anchor="middle"
			class="fill-base-content/50"
			font-size="11"
			font-weight="600"
			transform="rotate(-90, 10, {pad + plotSize / 2})"
		>{homeTeam}</text>

		<!-- Prediction dots -->
		{#each grouped as group}
			{@const cx = toX(group.away)}
			{@const cy = toY(group.home)}
			{@const r = Math.sqrt(group.count) * baseRadius}
			{@const pointOutcome = getPointOutcome(group.home, group.away)}
			{@const isInCorrectRegion = actual && pointOutcome === actual.outcome}
			<!-- svelte-ignore a11y-no-static-element-interactions -->
			<circle
				{cx}
				{cy}
				{r}
				class={isInCorrectRegion ? 'fill-base-content/70' : 'fill-base-content/35'}
				on:mouseenter={(e) => showTooltip(group, e)}
				on:mouseleave={hideTooltip}
				on:touchstart|preventDefault={(e) => showTooltip(group, e)}
				style="cursor: pointer; transition: r 0.2s ease;"
			/>
			{#if group.count > 1}
				<text
					x={cx}
					y={cy + 3.5}
					text-anchor="middle"
					class="fill-base-100"
					font-size="10"
					font-weight="700"
					pointer-events="none"
				>{group.count}</text>
			{/if}
		{/each}

		<!-- Actual result star -->
		{#if actual}
			{@const sx = toX(actual.away_score)}
			{@const sy = toY(actual.home_score)}
			<polygon
				points={starPoints(sx, sy, 10, 4.5, 5)}
				class="fill-primary"
				stroke="rgba(0,0,0,0.3)"
				stroke-width="0.5"
			/>
		{/if}
	</svg>

	<!-- Tooltip -->
	{#if hoveredGroup}
		<div
			class="absolute z-10 px-3 py-2 bg-base-300 border border-base-content/20 rounded-lg shadow-lg text-xs pointer-events-none"
			style="left: {tooltipX}px; top: {tooltipY}px; transform: translate(-50%, -100%);"
		>
			<div class="font-semibold text-base-content/80 mb-1">
				{hoveredGroup.home} - {hoveredGroup.away}
			</div>
			{#each hoveredGroup.names as name}
				<div class="text-base-content/60">{name}</div>
			{/each}
		</div>
	{/if}
</div>
