<script lang="ts">
	import type { Fixture, MatchPrediction } from '$types';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import { calculateGroupStandings } from '$lib/utils/standings';

	export let group: string;
	export let fixtures: Fixture[];
	export let predictions: Map<string, MatchPrediction>;

	$: standings = calculateGroupStandings(fixtures, predictions, group);

	// Position indicator styling
	function getPositionClass(index: number): string {
		if (index < 2) return 'qualifies';
		if (index === 2) return 'third-place';
		return '';
	}
</script>

<div class="group-standings">
	<div class="overflow-x-auto -mx-2 sm:mx-0">
		<table class="standings-table">
			<thead>
				<tr>
					<th class="w-8 text-center">#</th>
					<th class="text-left">Team</th>
					<th class="text-center w-8">P</th>
					<th class="text-center w-8">W</th>
					<th class="text-center w-8">D</th>
					<th class="text-center w-8">L</th>
					<th class="text-center w-10 hidden sm:table-cell">GF</th>
					<th class="text-center w-10 hidden sm:table-cell">GA</th>
					<th class="text-center w-10">GD</th>
					<th class="text-center w-10">Pts</th>
				</tr>
			</thead>
			<tbody>
				{#each standings as standing, i}
					{@const posClass = getPositionClass(i)}
					<tr class="standing-row {posClass} animate-fade-in" style="animation-delay: {i * 50}ms; animation-fill-mode: both;">
						<td class="text-center">
							<span class="position-indicator {posClass}">
								{i + 1}
							</span>
						</td>
						<td class="team-cell">
							<div class="flex items-center gap-2">
								{#if hasFlag(standing.team)}
									<img
										src={getFlagUrl(standing.team, 'sm')}
										alt="{standing.team} flag"
										class="w-5 h-auto rounded-sm shadow-sm flex-shrink-0"
										loading="lazy"
									/>
								{:else}
									<div class="w-5 h-3.5 bg-base-300 rounded-sm flex-shrink-0"></div>
								{/if}
								<span class="team-name-table">{standing.team}</span>
							</div>
						</td>
						<td class="text-center text-base-content/70">{standing.played}</td>
						<td class="text-center text-success font-medium">{standing.won}</td>
						<td class="text-center text-base-content/50">{standing.drawn}</td>
						<td class="text-center text-error/80">{standing.lost}</td>
						<td class="text-center text-base-content/70 hidden sm:table-cell">{standing.goalsFor}</td>
						<td class="text-center text-base-content/70 hidden sm:table-cell">{standing.goalsAgainst}</td>
						<td class="text-center gd-cell {standing.goalDifference > 0 ? 'positive' : standing.goalDifference < 0 ? 'negative' : ''}">
							{standing.goalDifference > 0 ? '+' : ''}{standing.goalDifference}
						</td>
						<td class="text-center">
							<span class="points-badge">{standing.points}</span>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>

</div>

<style>
	.group-standings {
		@apply rounded-xl bg-base-200/50 border border-base-300/30 overflow-hidden;
	}

	.standings-table {
		@apply w-full min-w-[320px];
	}

	.standings-table thead tr {
		@apply bg-base-300/30;
	}

	.standings-table th {
		@apply py-3 px-2 text-[10px] uppercase tracking-wider text-base-content/40 font-medium;
	}

	.standings-table td {
		@apply py-2.5 px-2 text-sm;
	}

	.standing-row {
		@apply border-b border-base-300/20 transition-colors duration-200;
	}

	.standing-row:hover {
		@apply bg-base-300/20;
	}

	/* Qualification indicators - subtle left border instead of background */
	.standing-row.qualifies {
		@apply border-l-2 border-l-success;
	}

	.standing-row.third-place {
		@apply border-l-2 border-l-warning;
	}

	.position-indicator {
		@apply inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold;
		@apply bg-base-300 text-base-content/60;
	}

	.position-indicator.qualifies {
		@apply bg-success/20 text-success;
	}

	.position-indicator.third-place {
		@apply bg-warning/20 text-warning;
	}

	.team-cell {
		@apply min-w-0;
	}

	.team-name-table {
		@apply font-semibold;
		/* Keep words intact, allow wrapping between words */
		white-space: nowrap;
	}

	.gd-cell {
		@apply font-medium;
	}

	.gd-cell.positive {
		@apply text-success;
	}

	.gd-cell.negative {
		@apply text-error/70;
	}

	.points-badge {
		@apply inline-flex items-center justify-center min-w-[28px] h-7 px-2;
		@apply bg-base-300 rounded-md font-bold text-base-content;
		font-family: 'Bebas Neue', sans-serif;
		@apply text-lg tracking-wide;
	}
</style>
