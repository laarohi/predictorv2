<script context="module" lang="ts">
	export type RosterRow = {
		position: string;
		name: string;
		handle: string;
		filled: number;
		total: number;
		isCurrentUser?: boolean;
		/** Undefined while data is loading; explicit false means show UNPAID. */
		paid?: boolean;
	};
</script>

<script lang="ts">
	/**
	 * Pre-tournament players roster. Three columns:
	 *   #  |  Player + handle (+ UNPAID pill if unpaid)  |  Progress
	 *
	 * The "you" row gets red name colour. A solid pip means the player has
	 * fully completed predictions; faded pip means partial. Players with
	 * paid === false get a small UNPAID pill inline with their name —
	 * name-and-shame for the pre-tournament dashboard. Paid players get
	 * no pill (no positive-badge noise).
	 */
	export let title: string = '';
	export let meta: string = '';
	export let rows: RosterRow[] = [];

	function isFull(r: RosterRow): boolean {
		return r.total > 0 && r.filled >= r.total;
	}
</script>

<div class="pn-roster">
	<div class="hd">
		<span>{title}</span>
		<span class="right">{meta}</span>
	</div>
	<div class="roster-scroll">
		<table>
			<thead>
				<tr>
					<th>#</th>
					<th>Player</th>
					<th class="r">Progress</th>
				</tr>
			</thead>
			<tbody>
				{#each rows as r (r.position)}
					<tr>
						<td class="pos">{r.position}</td>
						<td class="nm" class:you={r.isCurrentUser}>
							{r.name}{#if r.paid === false}<span class="paid-pill unpaid">UNPAID</span>{/if}<span class="h">{r.handle}</span>
						</td>
						<td class="r prog">
							<span class="pip" class:empty={!isFull(r)}></span>
							{r.filled} / {r.total}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</div>
