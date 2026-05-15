<script lang="ts">
	// A single match card inside the Panini knockout bracket. Two team rows;
	// clicking either picks them as the winner of this match. When the bracket
	// is locked, clicks are inert. Special `isFinal` mode renders the gold
	// trophy card used at the centre of the desktop wall chart.
	import PnFlag from './PnFlag.svelte';
	import { teamCode } from '$lib/utils/teamCodes';

	export let homeTeam: string | null = null;
	export let awayTeam: string | null = null;
	export let winner: string | null = null;
	export let locked: boolean = false;
	export let isFinal: boolean = false;
	export let onSelect: (team: string) => void = () => {};
	/** Hide flags to keep cells tight (used on the mobile bracket). */
	export let compact: boolean = false;

	$: pickedHome = homeTeam !== null && winner === homeTeam;
	$: pickedAway = awayTeam !== null && winner === awayTeam;
	$: anyTeam = !!(homeTeam || awayTeam);

	function clickHome() {
		if (locked || !homeTeam) return;
		onSelect(homeTeam);
	}
	function clickAway() {
		if (locked || !awayTeam) return;
		onSelect(awayTeam);
	}
</script>

{#if isFinal}
	<div class="pn-bm final">
		<div class="l">★ Predicted Champion</div>
		{#if winner}
			<button class="winner-row" type="button" on:click={pickedHome ? clickHome : clickAway}>
				<PnFlag code={teamCode(winner)} w={28} h={20} />
				<span>{winner.toUpperCase()}</span>
			</button>
			{#if homeTeam && homeTeam !== winner}
				<button class="alt-row" type="button" on:click={clickHome} disabled={locked}>
					<PnFlag code={teamCode(homeTeam)} w={16} h={11} />
					<span>{homeTeam.toUpperCase()}</span>
				</button>
			{/if}
			{#if awayTeam && awayTeam !== winner}
				<button class="alt-row" type="button" on:click={clickAway} disabled={locked}>
					<PnFlag code={teamCode(awayTeam)} w={16} h={11} />
					<span>{awayTeam.toUpperCase()}</span>
				</button>
			{/if}
			<div class="sub">over {winner === homeTeam ? awayTeam ?? '—' : homeTeam ?? '—'}</div>
		{:else if homeTeam || awayTeam}
			<button class="alt-row" type="button" on:click={clickHome} disabled={locked || !homeTeam}>
				<PnFlag code={teamCode(homeTeam ?? '???')} w={16} h={11} />
				<span>{(homeTeam ?? 'TBD').toUpperCase()}</span>
			</button>
			<button class="alt-row" type="button" on:click={clickAway} disabled={locked || !awayTeam}>
				<PnFlag code={teamCode(awayTeam ?? '???')} w={16} h={11} />
				<span>{(awayTeam ?? 'TBD').toUpperCase()}</span>
			</button>
		{:else}
			<div class="sub" style="margin-top: 8px;">Final awaits semi winners</div>
		{/if}
	</div>
{:else if !anyTeam}
	<div class="pn-bm tbd"></div>
{:else}
	<div class="pn-bm" class:locked>
		<button
			type="button"
			class="row"
			class:pred={pickedHome}
			class:lose-pred={winner !== null && !pickedHome}
			on:click={clickHome}
			disabled={locked || !homeTeam}
		>
			<span class="nm">
				{#if homeTeam && !compact}
					<PnFlag code={teamCode(homeTeam)} w={14} h={10} />
				{/if}
				<span class="nm-text">{homeTeam ?? '—'}</span>
			</span>
		</button>
		<button
			type="button"
			class="row"
			class:pred={pickedAway}
			class:lose-pred={winner !== null && !pickedAway}
			on:click={clickAway}
			disabled={locked || !awayTeam}
		>
			<span class="nm">
				{#if awayTeam && !compact}
					<PnFlag code={teamCode(awayTeam)} w={14} h={10} />
				{/if}
				<span class="nm-text">{awayTeam ?? '—'}</span>
			</span>
		</button>
	</div>
{/if}

<style>
	/* Button-reset so the click target inherits the row styling from
	 * panini-bracket.css cleanly. */
	button.row {
		display: flex;
		justify-content: space-between;
		align-items: center;
		width: 100%;
		text-align: left;
		border: 0;
		font: inherit;
		color: inherit;
	}
	button.row:disabled { cursor: default; }
</style>
