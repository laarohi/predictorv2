<script context="module" lang="ts">
	/** One bucket of a stage row. `pts` is the points the bucket is worth
	 *  (earned = banked, available = in play, missed = 0). `teams` are full
	 *  names — run through teamCode() before display. */
	export type JourneyCell = {
		n: number;
		pts: number;
		teams?: string[];
	};
	export type JourneyStageRow = {
		earned?: JourneyCell; // reached (banked) — green
		available?: JourneyCell; // still alive (in play) — gold
		missed?: JourneyCell; // eliminated — muted red
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
	 * Scoring Journey — bracket ADVANCEMENT points, both phases at once.
	 *
	 * Grouped paired bars: one row per KO achievement round (R16 → Winner),
	 * Phase 1 over Phase 2. Each bar is split into three segments —
	 * green = reached (banked), gold-hatch = still alive (in play),
	 * muted-red = eliminated — sized by share of that phase's picks at the
	 * stage (a fair 0..N scale across phases). The points value rides as a
	 * label; the ×N per-pick multiplier in the round header explains why
	 * Phase 1 banks more despite a lower pick-rate. Tap any segment for its
	 * teams. The live round (some picks settled, some still alive) is tagged
	 * "deciding now". Match-SCORE points live in the sibling KO-matches strip.
	 */
	import { teamCode } from '$lib/utils/teamCodes';

	export let p1: JourneyPhase = {};
	export let p2: JourneyPhase = {};
	export let footHref: string = '/leaderboard';

	// Per-pick advancement values, mirroring config/worldcup2026.yml
	// (advancement.* / advancement.phase_2.*). Display only — every bar's
	// points come from the backend, so the numbers always reconcile even if
	// these labels drift.
	const STAGES = [
		{ key: 'r16', label: 'R16', p1m: 15, p2m: 5 },
		{ key: 'qf', label: 'QF', p1m: 25, p2m: 15 },
		{ key: 'sf', label: 'SF', p1m: 55, p2m: 40 },
		{ key: 'f', label: 'Final', p1m: 85, p2m: 60 },
		{ key: 'w', label: 'Winner', p1m: 150, p2m: 100 }
	] as const;
	type StageKey = (typeof STAGES)[number]['key'];

	function cell(row: JourneyStageRow | undefined, which: 'earned' | 'available' | 'missed') {
		const c = row?.[which];
		return { n: c?.n ?? 0, pts: c?.pts ?? 0, teams: c?.teams ?? [] };
	}

	function totals(phase: JourneyPhase) {
		let banked = 0;
		let inplay = 0;
		for (const s of STAGES) {
			const row = phase[s.key as StageKey];
			banked += cell(row, 'earned').pts;
			inplay += cell(row, 'available').pts;
		}
		return { banked, inplay, grand: banked + inplay };
	}
	$: t1 = totals(p1);
	$: t2 = totals(p2);

	// A round is "deciding now" when, in either phase, some picks have resolved
	// (reached or eliminated) AND some are still alive — i.e. the bar carries a
	// green/gold split. Flags the live frontier without needing fixture status.
	function isNow(key: StageKey): boolean {
		for (const ph of [p1, p2]) {
			const row = ph[key];
			const e = cell(row, 'earned').n;
			const a = cell(row, 'available').n;
			const m = cell(row, 'missed').n;
			if (a > 0 && (e > 0 || m > 0)) return true;
		}
		return false;
	}
	$: liveStage = STAGES.find((s) => isNow(s.key as StageKey))?.label ?? null;

	function codes(teams: string[]): string[] {
		return teams.map((t) => teamCode(t));
	}

	// Tap-to-open tooltip state (one at a time). Hover/focus also reveal via
	// CSS; this drives touch.
	let openTip: string | null = null;
	function toggle(id: string) {
		openTip = openTip === id ? null : id;
	}
</script>

<svelte:window on:click={() => (openTip = null)} />

<div class="pn-sec-h">
	<span class="ttl"><span class="pip"></span> Your scoring <em>journey</em></span>
	<span class="meta"><a href={footHref}>See full breakdown →</a></span>
</div>

<div class="pn-sjg">
	<!-- phase running totals -->
	<div class="sjg-totals">
		{#each [{ lab: 'P1', kind: 'Original', t: t1, pc: 'p1' }, { lab: 'P2', kind: 'Re-pick', t: t2, pc: 'p2' }] as B}
			<div class="sjg-ph {B.pc}">
				<div class="tag"><span class="chip">{B.lab}</span>{B.kind}</div>
				<div class="nums">
					<span class="grand">{B.t.grand}</span>
					<span class="split"><b class="g">{B.t.banked} banked</b><br /><b class="y">{B.t.inplay} in play</b></span>
				</div>
			</div>
		{/each}
	</div>

	<!-- legend -->
	<div class="sjg-legend">
		<span class="it"><span class="sw g"></span>Banked</span>
		<span class="it"><span class="sw y"></span>In play</span>
		<span class="it"><span class="sw m"></span>Missed</span>
		{#if liveStage}<span class="it note">{liveStage} deciding now</span>{/if}
	</div>

	<!-- chart -->
	<div class="sjg-chart">
		{#each STAGES as s, i (s.key)}
			{@const now = isNow(s.key)}
			<div class="sjg-rnd" class:now>
				<div class="sjg-rhead">
					<span class="rname">{s.label}</span>
					<span class="pot">P1 ×{s.p1m} · P2 ×{s.p2m}</span>
					{#if now}<span class="nowtag">deciding now</span>{/if}
				</div>
				{#each [{ ph: p1, lab: 'P1', pc: 'p1' }, { ph: p2, lab: 'P2', pc: 'p2' }] as B}
					{@const row = B.ph[s.key]}
					{@const e = cell(row, 'earned')}
					{@const a = cell(row, 'available')}
					{@const m = cell(row, 'missed')}
					{@const N = e.n + a.n + m.n}
					{@const kept = e.n + a.n}
					<div class="sjg-bar {B.pc}" class:down={i === 0}>
						<span class="sjg-pchip">{B.lab}</span>
						<div class="sjg-track">
							{#if e.n > 0}
								{@const id = `${B.lab}-${s.key}-b`}
								<button
									type="button"
									class="sjg-seg bank clampL"
									class:open={openTip === id}
									style="width:{(e.n / N) * 100}%"
									aria-label={`${s.label} ${B.lab} reached: ${e.pts} points, ${e.n} teams`}
									on:click|stopPropagation={() => toggle(id)}
								>
									<span class="sjg-tip">
										<span class="th"><span>{s.label} · {B.lab} reached</span><b class="g">{e.pts}</b></span>
										<span class="chips">{#each codes(e.teams) as c}<span class="fc al">{c}</span>{/each}</span>
									</span>
								</button>
							{/if}
							{#if a.n > 0}
								{@const id = `${B.lab}-${s.key}-a`}
								<button
									type="button"
									class="sjg-seg play"
									class:open={openTip === id}
									style="width:{(a.n / N) * 100}%"
									aria-label={`${s.label} ${B.lab} still alive: ${a.pts} points, ${a.n} teams`}
									on:click|stopPropagation={() => toggle(id)}
								>
									<span class="sjg-tip">
										<span class="th"><span>{s.label} · {B.lab} in play</span><b class="y">{a.pts}</b></span>
										<span class="chips">{#each codes(a.teams) as c}<span class="fc live">{c}</span>{/each}</span>
									</span>
								</button>
							{/if}
							{#if m.n > 0}
								{@const id = `${B.lab}-${s.key}-m`}
								<button
									type="button"
									class="sjg-seg miss clampR"
									class:open={openTip === id}
									style="width:{(m.n / N) * 100}%"
									aria-label={`${s.label} ${B.lab} missed: ${m.n} teams`}
									on:click|stopPropagation={() => toggle(id)}
								>
									<span class="sjg-tip">
										<span class="th"><span>{s.label} · {B.lab} missed</span><b class="r">0</b></span>
										<span class="chips">{#each codes(m.teams) as c}<span class="fc out">{c}</span>{/each}</span>
									</span>
								</button>
							{/if}
						</div>
						<div class="sjg-end">
							<span class="pts">
								{#if e.pts > 0}<span class="g">{e.pts}</span>{/if}{#if a.pts > 0}<span class="y">{a.pts}</span>{/if}{#if e.pts === 0 && a.pts === 0}<span class="z">—</span>{/if}
							</span>
							<span class="nn" class:full={N > 0 && kept === N}>{N > 0 ? `${kept}/${N}` : '—'}</span>
						</div>
					</div>
				{/each}
			</div>
		{/each}
	</div>

	<div class="sjg-foot">
		Bar = <b>picks kept / made</b> (same scale both phases). <b>Points</b> labelled carry each
		round&rsquo;s value (see ×N). Tap a segment for its teams.
	</div>
</div>
