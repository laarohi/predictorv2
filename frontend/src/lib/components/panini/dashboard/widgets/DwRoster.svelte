<script context="module" lang="ts">
	export type RosterRow = {
		position: string;
		name: string;
		handle: string;
		filled: number;
		total: number;
		isCurrentUser?: boolean;
	};
</script>

<script lang="ts">
	/**
	 * Pre-tournament players roster. Three columns:
	 *   #  |  Player + handle  |  Progress (filled/total) + pip
	 *
	 * The "you" row gets red name colour. A solid pip means the player has
	 * fully completed predictions; faded pip means partial.
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
							{r.name}<span class="h">{r.handle}</span>
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
