<script context="module" lang="ts">
	export type GroupSummaryRow = {
		group: string;
		outcome: number;
		exact: number;
		qual: number;
		total: number;
		qualPending?: boolean;
	};
</script>

<script lang="ts">
	/**
	 * Between-phases group summary table. 12 rows (groups A–L) × 4 metrics:
	 *   Outc  — match outcome points (incl. rarity bonus)
	 *   Exact — exact-score points
	 *   Qual  — group_advance + group_position points the user earned for
	 *           predicting which two teams from this group make R32
	 *   Total — sum of the above three
	 *
	 * Pure presentational. The caller composes the structure from the
	 * authoritative phase-1 PointBreakdown + fixture/prediction stores.
	 */
	export let rows: GroupSummaryRow[] = [];
	export let bonusPoints: number = 0;
	/** Aggregate qualification points (group_advance + group_position) from
	 *  the authoritative backend PointBreakdown. Rendered as its own summary
	 *  row — the per-group split isn't exposed by the backend (best-thirds
	 *  attribution is genuinely cross-group), so we don't fake one. */
	export let qualPoints: number | null = null;
	export let phaseTotal: number = 0;
	export let title: string = 'Group stage';
	export let titleEm: string = 'summary';
	export let meta: string = 'final · all matches played';
	export let footLeft: string = 'Outc includes rarity bonus · Qual = bracket R32 entry × group';
	export let footRight: string = 'Per-match breakdown →';
	export let footRightHref: string = '/predictions';
</script>

<div class="pn-summary">
	<div class="hd">
		<span>{title} <em>{titleEm}</em></span>
		<span class="right">{meta}</span>
	</div>
	<table>
		<thead>
			<tr>
				<th>Group</th>
				<th>Outc</th>
				<th>Exact</th>
				<th>Qual</th>
				<th>Total</th>
			</tr>
		</thead>
		<tbody>
			{#each rows as r (r.group)}
				<tr>
					<td class="grp">Group {r.group}</td>
					<td class="outc">{r.outcome || '—'}</td>
					<td class="exact">{r.exact || '—'}</td>
					<td class="qual" class:pending={r.qualPending}>
						{r.qualPending ? 'pending' : r.qual || '—'}
					</td>
					<td class="total">{r.total}</td>
				</tr>
			{/each}
			{#if qualPoints !== null}
				<tr class="bonus">
					<td>+ qualification (R32 entries)</td>
					<td>—</td>
					<td>—</td>
					<td>{qualPoints}</td>
					<td>{qualPoints}</td>
				</tr>
			{/if}
			{#if bonusPoints > 0}
				<tr class="bonus">
					<td>+ bonus questions</td>
					<td>—</td>
					<td>—</td>
					<td>—</td>
					<td>{bonusPoints}</td>
				</tr>
			{/if}
			<tr class="grand">
				<td>Phase 1 total</td>
				<td colspan="3"></td>
				<td>{phaseTotal}</td>
			</tr>
		</tbody>
	</table>
	<div class="foot">
		<span>{footLeft}</span>
		<a href={footRightHref}>{footRight}</a>
	</div>
</div>
