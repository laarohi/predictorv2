<script lang="ts">
	/**
	 * Compact mobile per-match leaderboard.
	 *
	 * Mirrors PnMatchLeaderboard but renders against the `.pn-mm-*` mobile
	 * classes — denser rows, no big chips, "YOUR PICK" surfaces as a
	 * standalone card above the table instead of a sticky table row.
	 * Filter tabs scroll horizontally.
	 *
	 * Logic is identical to the desktop component (same sort, same filter
	 * semantics, same kind classification). Kept as a separate file so the
	 * two layouts can diverge freely without conditional rendering.
	 */
	import {
		classifyPick,
		outcomeOf,
		pickStr,
		rarityLabel,
		type GridPlayer
	} from '$lib/utils/matchDetail';
	import { logarithmicRarityBonus } from '$lib/utils/matchBreakdown';

	export let mode: 'pre' | 'post';
	export let actual: { home_score: number; away_score: number } | null = null;
	export let players: GridPlayer[];
	export let pointsExact: number = 15;
	export let pointsOutcome: number = 5;
	export let rarityCap: number = 10;

	type PickFilter = 'all' | 'scorers' | 'home' | 'draw' | 'away';
	let filter: PickFilter = mode === 'post' ? 'scorers' : 'all';

	interface Row extends GridPlayer {
		kind: 'exact' | 'outcome' | 'miss' | 'all';
		pts: number | null;
		rareCount: number;
		rarePct: number;
		rareLbl: string;
		outcomeBucket: 'home' | 'draw' | 'away';
	}

	$: rows = (() => {
		const counts: Record<string, number> = {};
		for (const p of players) {
			const key = p.home + ',' + p.away;
			counts[key] = (counts[key] || 0) + 1;
		}
		const total = players.length;
		// Rarity bonus paid to everyone who called the actual outcome —
		// same formula as backend scoring (shared logarithmic mirror).
		const actualOutcome =
			mode === 'post' && actual ? outcomeOf(actual.home_score, actual.away_score) : null;
		const correctCt = actualOutcome
			? players.filter((p) => outcomeOf(p.home, p.away) === actualOutcome).length
			: 0;
		const rarBonus = actualOutcome ? logarithmicRarityBonus(total, correctCt, rarityCap) : 0;
		const all: Row[] = players.map((p) => {
			const key = p.home + ',' + p.away;
			const ct = counts[key] || 0;
			const r = rarityLabel(ct, total);
			const kind =
				mode === 'post' && actual
					? classifyPick({ home_score: p.home, away_score: p.away }, actual)
					: 'all';
			const pts =
				mode === 'post' && actual
					? kind === 'exact'
						? pointsExact + pointsOutcome + rarBonus
						: kind === 'outcome'
							? pointsOutcome + rarBonus
							: 0
					: null;
			return {
				...p,
				kind: kind as 'exact' | 'outcome' | 'miss' | 'all',
				pts,
				rareCount: ct,
				rarePct: Math.round((ct / Math.max(1, total)) * 100),
				rareLbl: r.lbl,
				outcomeBucket: outcomeOf(p.home, p.away)
			};
		});

		if (mode === 'post') {
			all.sort((a, b) => {
				const ap = a.pts ?? 0;
				const bp = b.pts ?? 0;
				if (bp !== ap) return bp - ap;
				const at = a.totalPts ?? -1;
				const bt = b.totalPts ?? -1;
				return bt - at;
			});
		} else {
			all.sort((a, b) => {
				const ar = a.rank ?? Number.MAX_SAFE_INTEGER;
				const br = b.rank ?? Number.MAX_SAFE_INTEGER;
				return ar - br;
			});
		}
		return all;
	})();

	$: counts = (() => {
		const c = { all: rows.length, scorers: 0, home: 0, draw: 0, away: 0 };
		for (const r of rows) {
			if ((r.pts ?? 0) > 0) c.scorers++;
			c[r.outcomeBucket]++;
		}
		return c;
	})();

	$: filtered = (() => {
		if (mode === 'post') {
			if (filter === 'scorers') return rows.filter((r) => (r.pts ?? 0) > 0 || r.you);
			return rows;
		}
		if (filter === 'all') return rows;
		return rows.filter((r) => r.outcomeBucket === filter);
	})();

	$: youRow = rows.find((r) => r.you) ?? null;
	$: youDisplayRk = youRow
		? mode === 'post'
			? rows.findIndex((r) => r.you) + 1
			: youRow.rank ?? null
		: null;

	function rowCls(r: Row): string {
		return (
			'row-' + r.kind + (r.you ? ' you-row' : '') + (r.rareCount === 1 ? ' row-solo' : '')
		);
	}
</script>

<div class="pn-mm-lb">
	<div class="lh">
		<span>{mode === 'post' ? 'Points scored' : 'Predictions'}</span>
		<span class="right">
			{#if mode === 'post'}
				<b>{filtered.length}</b> of {rows.length}
			{:else}
				All <b>{rows.length}</b>
			{/if}
		</span>
	</div>

	<div class="filters">
		{#if mode === 'post'}
			<button class={filter === 'scorers' ? 'on' : ''} on:click={() => (filter = 'scorers')}>
				Point scorers <span class="ct">{counts.scorers}</span>
			</button>
			<button class={filter === 'all' ? 'on' : ''} on:click={() => (filter = 'all')}>
				All <span class="ct">{counts.all}</span>
			</button>
		{:else}
			<button class={filter === 'all' ? 'on' : ''} on:click={() => (filter = 'all')}>
				All <span class="ct">{counts.all}</span>
			</button>
			<button class={filter === 'home' ? 'on' : ''} on:click={() => (filter = 'home')}>
				Home <span class="ct">{counts.home}</span>
			</button>
			<button class={filter === 'draw' ? 'on' : ''} on:click={() => (filter = 'draw')}>
				Draw <span class="ct">{counts.draw}</span>
			</button>
			<button class={filter === 'away' ? 'on' : ''} on:click={() => (filter = 'away')}>
				Away <span class="ct">{counts.away}</span>
			</button>
		{/if}
	</div>

	{#if youRow}
		{@const r = youRow}
		<div class={'you-card row-' + r.kind}>
			<div class="rk">#{youDisplayRk}</div>
			<div class="nm">
				<span class="n">{r.name}</span>
				<span class="meta">
					{#if mode === 'post'}
						Comp <b>{r.totalPts ?? '—'}</b> · #{r.rank ?? '—'}
					{:else}
						{r.rareLbl} · <b>{r.rarePct}%</b> picked this
					{/if}
				</span>
			</div>
			<div class="pick">{pickStr(r.home, r.away)}</div>
			<div class="pts">
				{#if mode === 'post'}
					{(r.pts ?? 0) > 0 ? '+' + r.pts : '0'}
				{:else}
					?
				{/if}
			</div>
		</div>
		<div class="pin-sep">
			{#if mode === 'post'}
				{filter === 'scorers' ? 'Point-scorers · by pts' : 'All competitors · by pts'}
			{:else}
				{filter === 'all' ? 'All · by standing' : `${filter}-picks · by standing`}
			{/if}
		</div>
	{/if}

	<table class="pn-mm-tbl">
		<thead>
			<tr>
				<th>#</th>
				<th>Player</th>
				<th class="c">Pick</th>
				<th class="r">{mode === 'post' ? 'Pts' : 'Total'}</th>
			</tr>
		</thead>
		<tbody>
			{#each filtered as r, i (r.name)}
				{@const displayRk = mode === 'post' ? i + 1 : r.rank ?? '—'}
				<tr class={rowCls(r)}>
					<td class="rk">{displayRk}</td>
					<td class="nm">{r.name}</td>
					<td class="pick"><span class="pick-chip">{pickStr(r.home, r.away)}</span></td>
					{#if mode === 'post'}
						<td class="pts-c">{(r.pts ?? 0) > 0 ? '+' + r.pts : '0'}</td>
					{:else}
						<td class="total-c">{r.totalPts ?? '—'}</td>
					{/if}
				</tr>
			{/each}
		</tbody>
	</table>
</div>
