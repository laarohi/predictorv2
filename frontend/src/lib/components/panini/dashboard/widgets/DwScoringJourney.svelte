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
	 * Phase 4 + Phase 5 widget — combines what used to be `points by source`
	 * and `bracket alive` into one. Two stacked phase cards (Phase 1, Phase 2),
	 * each rendered as a 5-row × 2-col table.
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

	function flatten(phase: JourneyPhase): JourneyCell[] {
		const out: JourneyCell[] = [];
		for (const s of STAGES) {
			const row = phase[s.key];
			if (row?.earned) out.push(row.earned);
			if (row?.available) out.push(row.available);
		}
		return out;
	}

	$: maxPts = Math.max(1, ...flatten(p1).map((c) => c.pts || 0), ...flatten(p2).map((c) => c.pts || 0));

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

	function teamsList(arr: string[] | undefined): string {
		return arr && arr.length ? arr.join(' · ') : '—';
	}

	$: p1Totals = totals(p1);
	$: p2Totals = totals(p2);
</script>

<div class="pn-sj2">
	<div class="sj2-h">
		<div class="ttl">Your scoring <em>journey</em></div>
		<a class="breakdown" href={footHref}>See full breakdown →</a>
	</div>

	{#each [{ phase: p1, label: 'PHASE 1', kind: 'ORIGINAL', t: p1Totals }, { phase: p2, label: 'PHASE 2', kind: 'RE-PICK', t: p2Totals }] as block}
		<div class="sj2-phase">
			<div class="sj2-phase-h">
				<div class="ttl">
					<b>{block.label}</b>
					<span class="kind">· {block.kind}</span>
				</div>
				<div class="totals">
					<span>earned <b class="g">{block.t.earned} pts</b></span>
					<span>available <b class="y">{block.t.available} pts</b></span>
				</div>
			</div>
			<div class="sj2-grid">
				<div class="sj2-col-hd empty"></div>
				<div class="sj2-col-hd">Earned</div>
				<div class="sj2-col-hd">Available</div>
				{#each STAGES as s (s.key)}
					{@const row = block.phase[s.key] ?? {}}
					{@const earned = row.earned}
					{@const available = row.available}
					{@const eW = earned?.pts ? (earned.pts / maxPts) * 100 : 0}
					{@const aW = available?.pts ? (available.pts / maxPts) * 100 : 0}
					<div class="sj2-row-lbl">{s.label}</div>

					<div class="sj2-cell earned">
						<div class="sj2-bar">
							{#if earned && earned.pts > 0}
								<div class="fill" style="width: {eW}%">
									<span class="lbl">{earned.pts} pts <span class="frac">({earned.n}/{earned.of})</span></span>
								</div>
							{:else}
								<span class="empty">—</span>
							{/if}
						</div>
						{#if earned && earned.pts > 0}
							<div class="sj2-tip">
								<b>EARNED · {s.label}</b><br />
								{teamsList(earned.teams)}<br />
								<em>earned {earned.pts} pts</em>
							</div>
						{/if}
					</div>

					<div class="sj2-cell available">
						<div class="sj2-bar">
							{#if available && available.pts > 0}
								<div class="fill" style="width: {aW}%">
									<span class="lbl">{available.pts} pts <span class="frac">({available.n}/{available.of})</span></span>
								</div>
							{:else}
								<span class="empty">—</span>
							{/if}
						</div>
						{#if available && available.pts > 0}
							<div class="sj2-tip">
								<b>AVAILABLE · {s.label}</b><br />
								{teamsList(available.teams)}<br />
								<em>potential {available.pts} pts</em>
							</div>
						{/if}
					</div>
				{/each}
			</div>
		</div>
	{/each}
</div>
