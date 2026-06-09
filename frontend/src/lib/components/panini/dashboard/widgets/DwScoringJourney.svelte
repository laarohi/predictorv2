<script context="module" lang="ts">
	export type JourneyCell = {
		n: number;
		of: number;
		pts: number;
		teams?: string[];
	};
	export type JourneyStageRow = {
		earned?: JourneyCell;
		available?: JourneyCell;
	};
	export type JourneyPhase = {
		r16?: JourneyStageRow;
		qf?: JourneyStageRow;
		sf?: JourneyStageRow;
		f?: JourneyStageRow;
		w?: JourneyStageRow;
	};
</script>

<script lang="ts">
	/**
	 * Phase 4 + Phase 5 widget. One horizontal strip per phase: five
	 * sticker cells (R16 → Winner), each leading with the GOLD points
	 * still in play at that stage, with alive-pick fraction and banked
	 * points as a mono subline. Replaces the old 5-row × 2-col bar
	 * table, which was ~3× taller, mostly empty early in the KO stage,
	 * and whose hover tooltips forced a 750px layout width on phones.
	 */
	export let p1: JourneyPhase = {};
	export let p2: JourneyPhase = {};
	export let footHref: string = '/leaderboard';

	const STAGES = [
		{ key: 'r16', label: 'R16' },
		{ key: 'qf', label: 'QF' },
		{ key: 'sf', label: 'SF' },
		{ key: 'f', label: 'Final' },
		{ key: 'w', label: 'Winner' }
	] as const;

	function totals(phase: JourneyPhase) {
		let earned = 0;
		let available = 0;
		for (const s of STAGES) {
			const row = phase[s.key];
			if (row?.earned) earned += row.earned.pts;
			if (row?.available) available += row.available.pts;
		}
		return { earned, available };
	}

	$: p1Totals = totals(p1);
	$: p2Totals = totals(p2);
</script>

<div class="pn-sj3">
	<div class="sj3-h">
		<div class="ttl">Your scoring <em>journey</em></div>
		<a class="breakdown" href={footHref}>See full breakdown →</a>
	</div>

	<div class="sj3-phases">
	{#each [{ phase: p1, label: 'PHASE 1', kind: 'ORIGINAL', t: p1Totals }, { phase: p2, label: 'PHASE 2', kind: 'RE-PICK', t: p2Totals }] as block}
		<div class="sj3-phase">
			<div class="sj3-phase-h">
				<div class="ttl">
					<b>{block.label}</b>
					<span class="kind">· {block.kind}</span>
				</div>
				<div class="totals">
					<span>banked <b class="g">{block.t.earned}</b></span>
					<span>in play <b class="y">{block.t.available}</b></span>
				</div>
			</div>
			<div class="sj3-cells">
				{#each STAGES as s (s.key)}
					{@const row = block.phase[s.key] ?? {}}
					{@const earnedPts = row.earned?.pts ?? 0}
					{@const avail = row.available}
					{@const availPts = avail?.pts ?? 0}
					{@const dead = availPts === 0 && earnedPts === 0}
					<div class="sj3-cell" class:dead>
						<div class="stage">{s.label}</div>
						{#if availPts > 0}
							<div class="hero">{availPts}<span class="unit">pts</span></div>
							<div class="sub">
								{avail?.n ?? 0}/{avail?.of ?? 0} alive{#if earnedPts > 0}&nbsp;· <span class="banked">+{earnedPts}</span>{/if}
							</div>
						{:else if earnedPts > 0}
							<div class="hero earned-only">+{earnedPts}<span class="unit">pts</span></div>
							<div class="sub">
								{row.earned?.n ?? 0}/{row.earned?.of ?? 0} hit · banked
							</div>
						{:else}
							<div class="hero">—</div>
							<div class="sub">out</div>
						{/if}
					</div>
				{/each}
			</div>
		</div>
	{/each}
	</div>
</div>
