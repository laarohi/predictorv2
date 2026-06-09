<script lang="ts">
	/**
	 * Slim live group-standings table for the Match Detail page. Gives a
	 * group fixture its tournament context ("why this match matters"):
	 * positions, played, GD, points — with the two teams contesting the
	 * fixture highlighted and the qualification cut (top 2 + possible
	 * best-third) marked by a divider under 2nd place.
	 *
	 * Pure presentational — the caller passes the group's TeamStanding[]
	 * already sorted by the backend's tiebreaker chain.
	 */
	import PnFlag from './PnFlag.svelte';
	import { teamCode } from '$lib/utils/teamCodes';
	import type { TeamStanding } from '$types';

	export let rows: TeamStanding[] = [];
	export let group: string = '';
	/** Team names (as stored on the fixture) to highlight. */
	export let highlight: string[] = [];

	$: highlightSet = new Set(highlight);
</script>

<div class="pn-gsm">
	<div class="hd">
		<span>Group {group} <em>standings</em></span>
		<span class="right">live · top 2 advance</span>
	</div>
	<table>
		<thead>
			<tr>
				<th class="pos">#</th>
				<th class="team">Team</th>
				<th>P</th>
				<th>GD</th>
				<th class="pts">Pts</th>
			</tr>
		</thead>
		<tbody>
			{#each rows as r, i (r.team)}
				<tr class:you-team={highlightSet.has(r.team)} class:cut={i === 1}>
					<td class="pos">{i + 1}</td>
					<td class="team">
						<PnFlag code={teamCode(r.team)} w={20} h={14} />
						<span class="nm">{teamCode(r.team)}</span>
					</td>
					<td>{r.played}</td>
					<td>{r.goal_difference > 0 ? '+' + r.goal_difference : r.goal_difference}</td>
					<td class="pts">{r.points}</td>
				</tr>
			{/each}
		</tbody>
	</table>
	<div class="foot">3rd place can still qualify among the 8 best thirds</div>
</div>

<style>
	.pn-gsm {
		background: var(--paper-2);
		border: 2px solid var(--ink);
		box-shadow: 5px 5px 0 var(--ink);
		padding: 12px 14px 10px;
	}
	.hd {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		font-family: var(--display);
		font-size: 14px;
		text-transform: uppercase;
		letter-spacing: 0.02em;
		margin-bottom: 8px;
	}
	.hd em {
		color: var(--red);
		font-style: normal;
	}
	.hd .right {
		font-family: var(--mono);
		font-size: 9px;
		letter-spacing: 0.1em;
		color: var(--ink-3);
	}
	table {
		width: 100%;
		border-collapse: collapse;
		font-family: var(--mono);
		font-size: 12px;
	}
	th {
		font-size: 9px;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--ink-3);
		text-align: right;
		padding: 2px 4px;
		border-bottom: 2px solid var(--ink);
	}
	th.pos,
	th.team {
		text-align: left;
	}
	td {
		padding: 5px 4px;
		text-align: right;
		border-bottom: 1px solid var(--paper-3);
		color: var(--ink-2);
	}
	td.pos {
		text-align: left;
		color: var(--ink-3);
		width: 18px;
	}
	td.team {
		text-align: left;
	}
	td.team .nm {
		font-family: var(--body);
		font-weight: 700;
		color: var(--ink);
		margin-left: 6px;
	}
	td.pts {
		font-family: var(--display);
		font-size: 13px;
		color: var(--ink);
	}
	tr.you-team td {
		background: rgba(212, 154, 46, 0.14);
	}
	tr.cut td {
		border-bottom: 2px dashed var(--ink-2);
	}
	.foot {
		margin-top: 6px;
		font-family: var(--mono);
		font-size: 9px;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--ink-3);
	}
</style>
