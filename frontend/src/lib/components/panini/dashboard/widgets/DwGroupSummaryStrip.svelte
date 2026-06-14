<script lang="ts">
	/**
	 * Skinny 12-cell horizontal strip showing the user's points-by-group for
	 * the in-progress group stage.
	 *
	 * Each cell's value is the FULL group total — match outcome + exact-score
	 * bonus + rarity (logarithmic) bonus — and a hover/focus tooltip breaks
	 * that total into those three buckets. The caller computes the per-group
	 * split (combining predictions, fixture scores, per-fixture predictor
	 * counts and the scoring config via the shared `computeMatchPoints`
	 * mirror); this atom stays purely presentational.
	 *
	 * Cell colour scales with relative point density:
	 *   ratio > 0.75 → gold (.hi)
	 *   ratio < 0.20 → faded (.lo)
	 *   else        → default ink
	 */
	interface GroupPoints {
		group: string;
		outcome: number;
		exact: number;
		bonus: number;
	}

	export let groups: GroupPoints[] = [];
	export let liveLabel: string = '12 grps · live';
	export let title: string = 'Groups';
	export let titleEm: string = 'so far';

	// The headline number is always the sum of the three buckets, so it can
	// never disagree with the tooltip breakdown rendered beneath it.
	$: totals = groups.map((g) => g.outcome + g.exact + g.bonus);
	$: max = totals.length > 0 ? Math.max(...totals, 1) : 1;

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
		{#each groups as g, i (g.group)}
			{@const total = totals[i]}
			{@const ratio = max > 0 ? total / max : 0}
			<div
				class="gss-cell {tone(total)}"
				role="button"
				tabindex="0"
				aria-label={`Group ${g.group}: ${total} points — ${g.outcome} outcome, ${g.exact} exact, ${g.bonus} bonus`}
			>
				<div class="g">Grp {g.group}</div>
				<div class="v">{total}</div>
				<div class="mini">
					<div class="fill" style="width: {Math.max(8, ratio * 100)}%"></div>
				</div>
				<div class="gss-tip" role="tooltip">
					<div class="tip-h"><span>Grp {g.group}</span><b>{total} pts</b></div>
					<ul>
						<li><span>Outcome</span><span>{g.outcome}</span></li>
						<li><span>Exact</span><span>{g.exact}</span></li>
						<li class="bonus"><span>Bonus</span><span>{g.bonus}</span></li>
					</ul>
				</div>
			</div>
		{/each}
	</div>
</div>
