<script context="module" lang="ts">
	/** One finished match's contribution to a group's points (per-match tooltip).
	 *  `pts` includes the rarity bonus, so matches sum back to the Match total. */
	export type GroupMatchPts = {
		home: string; // team code
		away: string; // team code
		pts: number;
		kind: 'exact' | 'outc' | 'miss';
	};
	/** One team's qualification contribution within a group (per-team Qual tooltip). */
	export type GroupQualTeam = {
		team: string; // team code
		position: number; // actual finishing position (1-based)
		pts: number; // got-out-of-group base (+10) + correct-position bonus (+5)
	};
	export type GroupSummaryRow = {
		group: string;
		/** Match points: outcome + exact + rarity. */
		match: number;
		/** Per-match breakdown for the Match-cell tooltip. */
		matches?: GroupMatchPts[];
		/** Qualification points: got-out-of-group base + correct-position bonus. */
		qual: number;
		/** Per-team breakdown for the Qual-cell tooltip. */
		qualTeams?: GroupQualTeam[];
		/** match + qual. */
		total: number;
	};
</script>

<script lang="ts">
	/**
	 * Group summary table. 12 group rows (A–L, two side-by-side 6-row halves on
	 * desktop, stacked on mobile) × Match / Qual / Total:
	 *   Match — outcome + exact + rarity; tap the cell for the per-match split.
	 *   Qual  — qualification (got-out-of-group +10, correct-position +5); tap
	 *           the cell for the per-team split (which team, what position).
	 *   Total — Match + Qual.
	 * Below: aggregate qualification + bonus adders and the running phase total.
	 *
	 * Pure presentational — the caller composes the rows (and the per-team Qual
	 * detail) from the authoritative backend ledger + fixture/prediction stores.
	 */
	export let rows: GroupSummaryRow[] = [];
	export let bonusPoints: number = 0;
	export let phaseTotal: number = 0;
	export let title: string = 'Group stage';
	export let titleEm: string = 'summary';
	export let meta: string = 'final · all matches played';
	export let footLeft: string = 'Match incl. rarity';
	export let footLeftSub: string = '';
	export let footRight: string = 'Per-match breakdown →';
	export let footRightHref: string = '/predictions';

	function ord(n: number): string {
		if (n % 100 >= 11 && n % 100 <= 13) return 'th';
		return ['th', 'st', 'nd', 'rd'][n % 10] ?? 'th';
	}
</script>

<div class="pn-sec-h">
	<span class="ttl"><span class="pip"></span> {title} <em>{titleEm}</em></span>
	<span class="meta">{meta}</span>
</div>
<div class="pn-summary">
	<div class="halves">
		{#each [rows.slice(0, 6), rows.slice(6)] as half, hi (hi)}
			<table>
				<thead>
					<tr>
						<th>Group</th>
						<th>Match</th>
						<th>Qual</th>
						<th>Total</th>
					</tr>
				</thead>
				<tbody>
					{#each half as r (r.group)}
						<tr>
							<td class="grp">Group {r.group}</td>
							<td class="outc">
								{#if r.matches && r.matches.length}
									<span
										class="gpts"
										role="button"
										tabindex="0"
										aria-label={`Group ${r.group} match points: ${r.match} from ${r.matches.length} matches`}
									>
										{r.match || '—'}
										<span class="gtip" role="tooltip">
											<span class="tip-h"><span>Grp {r.group} · match</span><b>{r.match} pts</b></span>
											<ul>
												{#each r.matches as m (m.home + m.away)}
													<li class={m.kind}>
														<span>{m.home}–{m.away}</span>
														<span>{m.pts > 0 ? `+${m.pts}` : '0'}</span>
													</li>
												{/each}
											</ul>
										</span>
									</span>
								{:else}{r.match || '—'}{/if}
							</td>
							<td class="qual">
								{#if r.qualTeams && r.qualTeams.length}
									<span
										class="gpts"
										role="button"
										tabindex="0"
										aria-label={`Group ${r.group} qualification points: ${r.qual}`}
									>
										{r.qual || '—'}
										<span class="gtip" role="tooltip">
											<span class="tip-h"><span>Grp {r.group} · qual</span><b>{r.qual} pts</b></span>
											<ul>
												{#each r.qualTeams as q (q.team)}
													<li><span>{q.team} {q.position}{ord(q.position)}</span><span>+{q.pts}</span></li>
												{/each}
											</ul>
										</span>
									</span>
								{:else}{r.qual || '—'}{/if}
							</td>
							<td class="total">{r.total}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		{/each}
	</div>
	<div class="totline">
		<span class="adds">
			{#if bonusPoints > 0}<span>+ bonus questions <b>{bonusPoints}</b></span>{/if}
		</span>
		<span class="grand">Phase 1 total <b>{phaseTotal}</b></span>
	</div>
	<div class="foot">
		<span class="fl">{footLeft}{#if footLeftSub}<br />{footLeftSub}{/if}</span>
		<a href={footRightHref}>{footRight}</a>
	</div>
</div>
