<script context="module" lang="ts">
	export type GroupSummaryRow = {
		group: string;
		outcome: number;
		exact: number;
		total: number;
	};
</script>

<script lang="ts">
	/**
	 * Between-phases group summary table. 12 group rows (A–L, split into
	 * two side-by-side 6-row halves on desktop) × 3 metrics:
	 *   Outc  — match outcome points (incl. rarity bonus)
	 *   Exact — exact-score points
	 *   Total — sum of the two
	 * followed by full-width summary rows: qualification (aggregate),
	 * bonus questions, phase total.
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
	export let footLeft: string = 'Outc includes rarity bonus';
	export let footRight: string = 'Per-match breakdown →';
	export let footRightHref: string = '/predictions';
</script>

<!-- The 12 group rows split into two side-by-side 6-row tables on desktop
     (stacked on mobile) so the card stays inside one screen; the
     qualification / bonus / total summary rows span the full width. -->
<div class="pn-summary">
	<div class="hd">
		<span>{title} <em>{titleEm}</em></span>
		<span class="right">{meta}</span>
	</div>
	<div class="halves">
		{#each [rows.slice(0, 6), rows.slice(6)] as half, hi (hi)}
			<table>
				<thead>
					<tr>
						<th>Group</th>
						<th>Outc</th>
						<th>Exact</th>
						<th>Total</th>
					</tr>
				</thead>
				<tbody>
					{#each half as r (r.group)}
						<tr>
							<td class="grp">Group {r.group}</td>
							<td class="outc">{r.outcome || '—'}</td>
							<td class="exact">{r.exact || '—'}</td>
							<td class="total">{r.total}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		{/each}
	</div>
	<div class="totline">
		<span class="adds">
			{#if qualPoints !== null}<span>+ qualification <b>{qualPoints}</b></span>{/if}
			{#if bonusPoints > 0}<span>+ bonus questions <b>{bonusPoints}</b></span>{/if}
		</span>
		<span class="grand">Phase 1 total <b>{phaseTotal}</b></span>
	</div>
	<div class="foot">
		<span>{footLeft}</span>
		<a href={footRightHref}>{footRight}</a>
	</div>
</div>
