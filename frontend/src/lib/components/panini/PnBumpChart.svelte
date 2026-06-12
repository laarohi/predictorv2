<script lang="ts">
	/**
	 * Bump chart — every player's rank over the tournament, one line each.
	 *
	 * Rank 1 sits at the top. With ~30 players a full spaghetti plot is
	 * unreadable, so by default only YOU + the current top 3 are drawn in
	 * colour; everyone else is a thin grey line. Tapping a name chip in the
	 * legend toggles that player into the highlight set (replacing the
	 * default once anything is selected).
	 *
	 * Pure SVG, no chart library — same approach as PnSparkline. The chart
	 * widens with the number of days (min 56px/day) and the parent wrapper
	 * scrolls horizontally on mobile.
	 */
	import type { ProgressionSeries } from '$lib/api/leaderboard';

	export let users: ProgressionSeries[] = []; // ordered by current position
	export let youId: string | null = null;

	// Start scrolled to the newest day — the interesting end of the chart.
	// An action (not `$:` + bind:this): assigning scrollLeft to a bound
	// component variable invalidates it and re-runs the block forever.
	function scrollToEnd(node: HTMLElement) {
		node.scrollLeft = node.scrollWidth;
	}

	const ROW_H = 26; // vertical px per rank
	const DAY_W = 56; // horizontal px per day
	const PAD_L = 30; // left gutter: start-rank labels
	const PAD_R = 44; // right gutter: end-rank labels
	const PAD_T = 18;
	const PAD_B = 26; // bottom gutter: date labels

	// Selected user ids; empty set = default highlight (you + top 3).
	let selected = new Set<string>();
	function toggleUser(id: string) {
		if (selected.has(id)) selected.delete(id);
		else selected.add(id);
		selected = selected;
	}

	$: defaultIds = new Set(
		[...users.slice(0, 3).map((u) => u.user_id), ...(youId ? [youId] : [])]
	);
	$: activeIds = selected.size > 0 ? selected : defaultIds;

	// X domain — union of every series' dates, sorted ascending.
	$: dates = [...new Set(users.flatMap((u) => u.points.map((p) => p.captured_date)))].sort();
	$: maxRank = Math.max(1, ...users.flatMap((u) => u.points.map((p) => p.position)));

	$: chartW = PAD_L + PAD_R + Math.max(1, dates.length - 1) * DAY_W;
	$: chartH = PAD_T + PAD_B + (maxRank - 1) * ROW_H;

	function x(date: string): number {
		const i = dates.indexOf(date);
		return PAD_L + (dates.length > 1 ? i * DAY_W : 0);
	}
	function y(rank: number): number {
		return PAD_T + (rank - 1) * ROW_H;
	}

	function linePath(s: ProgressionSeries): string {
		return s.points.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(p.captured_date)},${y(p.position)}`).join(' ');
	}

	// Highlight palette: YOU is always red; others cycle through inks.
	const PALETTE = ['#d49a2e', '#1a3168', '#1b6c3e', '#7b4ba0', '#b05c14', '#0e7c86'];
	function colorOf(s: ProgressionSeries, idx: number): string {
		if (s.user_id === youId) return 'var(--red)';
		return PALETTE[idx % PALETTE.length];
	}

	function shortDate(d: string): string {
		const dt = new Date(d + 'T00:00:00Z');
		return dt.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' });
	}

	// Stable highlight-colour index per user so a line keeps its colour as
	// others toggle on and off.
	$: colorIdx = new Map(users.map((u, i) => [u.user_id, i]));
</script>

<div class="pn-bump">
	<div class="pn-bump-scroll" use:scrollToEnd>
		<svg width={chartW} height={chartH} viewBox="0 0 {chartW} {chartH}">
			<!-- rank gridlines -->
			{#each Array.from({ length: maxRank }, (_, i) => i + 1) as r (r)}
				<line x1={PAD_L} y1={y(r)} x2={chartW - PAD_R} y2={y(r)} class="grid" />
			{/each}
			<!-- date ticks -->
			{#each dates as d (d)}
				<text x={x(d)} y={chartH - 8} class="tick">{shortDate(d)}</text>
			{/each}

			<!-- grey base lines first, highlighted on top -->
			{#each users.filter((u) => !activeIds.has(u.user_id)) as s (s.user_id)}
				<path d={linePath(s)} class="ln dim" />
			{/each}
			{#each users.filter((u) => activeIds.has(u.user_id)) as s (s.user_id)}
				{@const col = colorOf(s, colorIdx.get(s.user_id) ?? 0)}
				<path d={linePath(s)} class="ln hot" style="stroke: {col};" />
				{#each s.points as p (p.captured_date)}
					<circle cx={x(p.captured_date)} cy={y(p.position)} r="3.5" style="fill: {col};" />
				{/each}
				{@const last = s.points[s.points.length - 1]}
				{#if last}
					<text x={x(last.captured_date) + 8} y={y(last.position) + 4} class="endlab" style="fill: {col};">
						#{last.position}
					</text>
				{/if}
			{/each}
		</svg>
	</div>

	<div class="pn-bump-legend">
		{#each users as s, i (s.user_id)}
			{@const on = activeIds.has(s.user_id)}
			<button
				class="chip"
				class:on
				class:you={s.user_id === youId}
				style={on ? `--chip: ${s.user_id === youId ? 'var(--red)' : colorOf(s, i)};` : ''}
				on:click={() => toggleUser(s.user_id)}
			>
				{s.user_name}
			</button>
		{/each}
	</div>
</div>
