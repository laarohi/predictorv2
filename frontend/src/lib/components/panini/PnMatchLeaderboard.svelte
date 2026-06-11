<script lang="ts">
	/**
	 * Per-match leaderboard table. Pinned YOU row + interactive filter tabs.
	 *
	 * Post-match: 'Point scorers' (default) | 'All N'.
	 *   - Shows pick, result tag (Exact/Outcome/No-pts), points scored on
	 *     this match, current overall competition points.
	 *
	 * Pre-match: 'All' | 'Home' | 'Draw' | 'Away'.
	 *   - Shows pick, rarity label, % popularity, current overall standing.
	 *
	 * Ported from `PnMatchLeaderboard` in panini-match.jsx. Only difference:
	 * the ▲▼ movement column was dropped — see decision in conversation.
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
		rareCls: string;
		outcomeBucket: 'home' | 'draw' | 'away';
	}

	$: rows = (() => {
		// Count pick popularity by (home, away) cell.
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
				rareCls: r.cls,
				outcomeBucket: outcomeOf(p.home, p.away)
			};
		});

		if (mode === 'post') {
			// Sort by points scored desc, then by total comp points desc.
			all.sort((a, b) => {
				const ap = a.pts ?? 0;
				const bp = b.pts ?? 0;
				if (bp !== ap) return bp - ap;
				const at = a.totalPts ?? -1;
				const bt = b.totalPts ?? -1;
				return bt - at;
			});
		} else {
			// Sort by overall standing ASC (lower rank = better)
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
		// Pre-match outcome filter
		if (filter === 'all') return rows;
		return rows.filter((r) => r.outcomeBucket === filter);
	})();

	$: youRow = filtered.find((r) => r.you) ?? rows.find((r) => r.you) ?? null;
	$: youDisplayRk = youRow
		? mode === 'post'
			? rows.findIndex((r) => r.you) + 1
			: youRow.rank ?? null
		: null;

	function rowCls(r: Row): string {
		return (
			'row-' + r.kind + (r.you ? ' you' : '') + (r.rareCount === 1 ? ' row-solo' : '')
		);
	}
</script>

<div class="pn-md-lb">
	<div class="lh">
		<span>
			{mode === 'post' ? 'Points scored' : 'Predictions'}
		</span>
		<span class="right">
			{#if mode === 'post'}
				Showing <b>{filtered.length}</b> of {rows.length}
				{#if filter === 'scorers'} · only point-scorers{/if}
			{:else}
				All <b>{rows.length}</b> competitors · sorted by overall standing
			{/if}
		</span>
	</div>

	<div class="lb-tools">
		<div class="seg-title">
			VIEW <b>{mode === 'post' ? 'POINTS' : 'PICKS'}</b>
		</div>
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

	<div class="lb-scroll">
		<table class="pn-md-tbl">
			<thead>
				<tr>
					<th>{mode === 'post' ? '#' : 'Rk'}</th>
					<th>Player</th>
					<th class="c">Pick</th>
					<th class="c">{mode === 'post' ? 'Result' : 'Rarity'}</th>
					{#if mode === 'pre'}
						<th class="c">Pct</th>
					{/if}
					{#if mode === 'post'}
						<th class="r">+Pts</th>
					{/if}
				</tr>
			</thead>
			<tbody>
				<!-- Pinned YOU row -->
				{#if youRow}
					{@const colCount = mode === 'post' ? 5 : 5}
					<tr class={'pinned-you row-' + youRow.kind + (youRow.rareCount === 1 ? ' row-solo' : '')}>
						<td class="rk">
							<span class="rk-v">#{youDisplayRk ?? '—'}</span>
						</td>
						<td class="nm">{youRow.name}</td>
						<td class="pick">
							<span class="pick-chip">{pickStr(youRow.home, youRow.away)}</span>
						</td>
						<td class="tag-c">
							{#if mode === 'post'}
								<span class="tg">
									{youRow.kind === 'exact'
										? '★ Exact'
										: youRow.kind === 'outcome'
											? 'Outcome'
											: 'No pts'}
								</span>
							{:else}
								<span class="tg">{youRow.rareLbl}</span>
							{/if}
						</td>
						{#if mode === 'pre'}
							<td class="rare-c">
								<span class="pct">{youRow.rarePct}%</span>({youRow.rareCount})
							</td>
						{/if}
						{#if mode === 'post'}
							<td class="pts-c">{(youRow.pts ?? 0) > 0 ? '+' + youRow.pts : '0'}</td>
						{/if}
					</tr>
					<tr class="pinned-sep">
						<td colspan={colCount}>
							{#if mode === 'post'}
								{#if filter === 'scorers'}
									All point-scorers · sorted by points scored on this match
								{:else}
									All competitors · sorted by points scored on this match
								{/if}
							{:else}
								{#if filter === 'all'}
									All {rows.length} competitors · sorted by overall standing
								{:else}
									{filtered.length} {filter}-pick{filtered.length === 1 ? '' : 's'} · sorted by overall standing
								{/if}
							{/if}
						</td>
					</tr>
				{/if}

				{#each filtered as r, i (r.name)}
					<tr class={rowCls(r)}>
						<td class="rk">
							{mode === 'post' ? i + 1 : r.rank ?? '—'}
						</td>
						<td class="nm">{r.name}</td>
						<td class="pick">
							<span class="pick-chip">{pickStr(r.home, r.away)}</span>
						</td>
						<td class="tag-c">
							{#if mode === 'post'}
								<span class="tg">
									{r.kind === 'exact'
										? '★ Exact'
										: r.kind === 'outcome'
											? 'Outcome'
											: 'No pts'}
								</span>
							{:else}
								<span class="tg">{r.rareLbl}</span>
							{/if}
						</td>
						{#if mode === 'pre'}
							<td class="rare-c">
								<span class="pct">{r.rarePct}%</span>({r.rareCount})
							</td>
						{/if}
						{#if mode === 'post'}
							<td class="pts-c">{(r.pts ?? 0) > 0 ? '+' + r.pts : '0'}</td>
						{/if}
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</div>
