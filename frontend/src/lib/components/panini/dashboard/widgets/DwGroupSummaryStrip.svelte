<script lang="ts">
	/**
	 * Skinny 12-cell horizontal strip showing the user's points-by-group for
	 * the in-progress group stage (Phase 2 dashboard).
	 *
	 * Pure presentational atom — caller passes the array of `{group, points}`
	 * already computed (typically by combining `predictionsByFixture` with
	 * the user's `breakdown` per-fixture data once the score sync has run).
	 *
	 * Cell colour scales with relative point density:
	 *   ratio > 0.75 → gold (.hi)
	 *   ratio < 0.20 → faded (.lo)
	 *   else        → default ink
	 */
	export let groups: Array<{ group: string; points: number }> = [];
	export let liveLabel: string = '12 grps · live';
	export let title: string = 'Groups';
	export let titleEm: string = 'so far';

	$: max = groups.length > 0 ? Math.max(...groups.map((g) => g.points), 1) : 1;

	function tone(points: number): '' | 'hi' | 'lo' {
		const ratio = max > 0 ? points / max : 0;
		if (ratio > 0.75) return 'hi';
		if (ratio < 0.2) return 'lo';
		return '';
	}
</script>

<div class="pn-gss">
	<div class="gss-lbl">
		<div class="ttl">{title} <em>{titleEm}</em></div>
		<div class="sub">{liveLabel}</div>
	</div>
	<div class="gss-cells">
		{#each groups as g (g.group)}
			{@const ratio = max > 0 ? g.points / max : 0}
			<div class="gss-cell {tone(g.points)}" title="Group {g.group} · {g.points} pts">
				<div class="g">Grp {g.group}</div>
				<div class="v">{g.points}</div>
				<div class="mini">
					<div class="fill" style="width: {Math.max(8, ratio * 100)}%"></div>
				</div>
			</div>
		{/each}
	</div>
</div>
