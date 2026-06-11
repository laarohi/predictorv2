<script lang="ts">
	/**
	 * Distribution bar with integrated rarity underbraces — sits below
	 * the bubble plot. Ported from `PnPointsBar` in panini-match.jsx.
	 *
	 * - Post-match: 3 segments (Exact / Outcome / No-pts). Exact+Outcome share
	 *   the same rarity underbrace (they're the same outcome bucket).
	 * - Pre-match: 3 segments (Home / Draw / Away). Each has its own brace.
	 *
	 * The rarity bonus per *outcome bucket* is the REAL number scoring will
	 * pay: `logarithmicRarityBonus` from matchBreakdown.ts, the shared
	 * mirror of the backend's `_logarithmic_rarity_bonus` (validated by the
	 * golden parity cases). The Solo/Rare/Uncommon/Common label is derived
	 * from that bonus. A bucket nobody picked gets no brace at all — there
	 * is no one to pay a bonus to.
	 */
	import { classifyPick, outcomeOf, type GridPlayer } from '$lib/utils/matchDetail';
	import { logarithmicRarityBonus } from '$lib/utils/matchBreakdown';

	export let mode: 'pre' | 'post';
	export let homeCode: string;
	export let awayCode: string;
	export let actual: { home_score: number; away_score: number } | null = null;
	export let players: GridPlayer[];
	export let pointsExact: number = 15;
	export let pointsOutcome: number = 5;
	export let rarityCap: number = 10;

	type RarTier = { lbl: string; bonus: number; cls: 'solo' | 'rare' | 'uncommon' | 'common' };
	type SegKind = 'green' | 'gold' | 'miss' | 'navy' | 'paper' | 'red';

	interface Seg {
		k: SegKind;
		lbl: string;
		count: number;
		sub: string;
		rar: RarTier | null;
		group: string;
		you: boolean;
	}

	function tierFor(count: number, totalPicks: number, cap: number): RarTier | null {
		if (count <= 0) return null;
		const bonus = logarithmicRarityBonus(totalPicks, count, cap);
		if (count === 1) return { lbl: 'Solo', bonus, cls: 'solo' };
		if (bonus >= 5) return { lbl: 'Rare', bonus, cls: 'rare' };
		if (bonus >= 2) return { lbl: 'Uncommon', bonus, cls: 'uncommon' };
		return { lbl: 'Common', bonus, cls: 'common' };
	}

	function pct(n: number, t: number): string {
		if (t <= 0) return '0%';
		return Math.round((n / t) * 100) + '%';
	}

	$: you = players.find((p) => p.you) ?? null;
	$: total = players.length;
	$: homeCt = players.filter((p) => p.home > p.away).length;
	$: drawCt = players.filter((p) => p.home === p.away).length;
	$: awayCt = players.filter((p) => p.home < p.away).length;
	$: rarHome = tierFor(homeCt, total, rarityCap);
	$: rarDraw = tierFor(drawCt, total, rarityCap);
	$: rarAway = tierFor(awayCt, total, rarityCap);

	$: youOutcome = you ? outcomeOf(you.home, you.away) : null;

	$: segs = (() => {
		if (mode === 'post' && actual) {
			const actualOutcome = outcomeOf(actual.home_score, actual.away_score);
			const exact = players.filter((p) => classifyPick({ home_score: p.home, away_score: p.away }, actual) === 'exact').length;
			const outcome = players.filter((p) => classifyPick({ home_score: p.home, away_score: p.away }, actual) === 'outcome').length;
			const miss = players.filter((p) => classifyPick({ home_score: p.home, away_score: p.away }, actual) === 'miss').length;
			const winRar = actualOutcome === 'home' ? rarHome : actualOutcome === 'away' ? rarAway : rarDraw;
			const youKind = you ? classifyPick({ home_score: you.home, away_score: you.away }, actual) : null;
			const arr: Seg[] = [
				{
					k: 'green',
					lbl: 'Exact',
					count: exact,
					sub: '+' + (pointsExact + pointsOutcome) + ' pts',
					rar: winRar,
					group: 'correct',
					you: youKind === 'exact'
				},
				{
					k: 'gold',
					lbl: 'Outcome',
					count: outcome,
					sub: '+' + pointsOutcome + ' pts',
					rar: winRar,
					group: 'correct',
					you: youKind === 'outcome'
				},
				{
					k: 'miss',
					lbl: 'No points',
					count: miss,
					sub: '0 pts',
					rar: null,
					group: 'miss',
					you: youKind === 'miss'
				}
			];
			return arr;
		}
		// Pre-match
		const arr: Seg[] = [
			{
				k: 'navy',
				lbl: `${homeCode} win`,
				count: homeCt,
				sub: pct(homeCt, total),
				rar: rarHome,
				group: 'home',
				you: youOutcome === 'home'
			},
			{
				k: 'paper',
				lbl: 'Draw',
				count: drawCt,
				sub: pct(drawCt, total),
				rar: rarDraw,
				group: 'draw',
				you: youOutcome === 'draw'
			},
			{
				k: 'red',
				lbl: `${awayCode} win`,
				count: awayCt,
				sub: pct(awayCt, total),
				rar: rarAway,
				group: 'away',
				you: youOutcome === 'away'
			}
		];
		return arr;
	})();

	// Group consecutive segs sharing the same outcome-bucket key for the brace row.
	$: groups = (() => {
		interface Grp { key: string; rar: RarTier | null; span: number }
		const out: Grp[] = [];
		for (const s of segs) {
			const last = out[out.length - 1];
			if (last && last.key === s.group && s.rar) {
				last.span += s.count;
			} else {
				out.push({ key: s.group, rar: s.rar, span: s.count });
			}
		}
		return out;
	})();
</script>

<div class="pn-md-bar">
	<div class="bar-section">
		<div class="lbl-row">
			{#each segs as s (s.lbl)}
				<!-- A 0-count segment has zero flex width: its text would
				     overflow and overlap the neighbouring label, so it
				     renders nothing (the bar + brace rows already do). -->
				<div class="seg-lbl" style="flex: {s.count}; min-width: 0;">
					{#if s.count > 0}
						<b>{s.lbl}</b>
						<span>{s.count} pick{s.count !== 1 ? 's' : ''} · {s.sub}</span>
					{/if}
				</div>
			{/each}
		</div>

		<div class="bar-row">
			{#each segs as s (s.lbl)}
				<div class={'seg ' + s.k + (s.you ? ' you' : '')} style="flex: {s.count};">
					{#if s.count > 0}{s.count}{/if}
				</div>
			{/each}
		</div>

		<div class="rar-row">
			{#each groups as g, i (i)}
				<div class="rar-cell" style="flex: {g.span}; min-width: 0;">
					{#if g.rar}
						<div class="rar-brace">
							<div class="brace" />
							<div class="stem" />
							<div class={'rar-chip rar-' + g.rar.cls}>
								<span class="bonus">{g.rar.bonus > 0 ? '+' + g.rar.bonus : '+0'}</span>
								<span class="lab">{g.rar.lbl} bonus</span>
							</div>
						</div>
					{/if}
				</div>
			{/each}
		</div>
	</div>

	<div class="footnote">
		<span>
			{#if mode === 'post'}
				★ exact result · YOU = your pick · cell shade ∝ # of picks · rarity bonus follows the match outcome
			{:else}
				cell shade ∝ # of picks · rarity bonus rewards backing the rarer outcome
			{/if}
		</span>
		<span><b>{total}</b> player predictions</span>
	</div>
</div>
