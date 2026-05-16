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

	// 3-letter codes keep the cards a fixed visual width regardless of
	// which teams advance — so card layout is determined at render time,
	// not at content time. Final card stays full-name (it has the room).
	$: homeCode = homeTeam ? teamCode(homeTeam) : '—';
	$: awayCode = awayTeam ? teamCode(awayTeam) : '—';

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
	{#if !anyTeam}
		<div class="pn-bm final empty">
			<div class="empty-l">Final awaits semi winners</div>
		</div>
	{:else}
		<!-- Option B: same two-row click-to-switch pattern as other bracket
		     cells, but on a gold "centerpiece" body (thicker border, red
		     offset shadow, bigger flag + code). The "celebration" lives in
		     the champion sticker rendered above this card in PnKnockoutBracket. -->
		<div class="pn-bm final" class:locked>
			<button
				type="button"
				class="row"
				class:pred={pickedHome}
				class:lose-pred={winner !== null && !pickedHome}
				on:click={clickHome}
				disabled={locked || !homeTeam}
			>
				<span class="nm">
					<PnFlag code={teamCode(homeTeam ?? '???')} w={18} h={12} />
					<span class="nm-text">{homeCode}</span>
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
					<PnFlag code={teamCode(awayTeam ?? '???')} w={18} h={12} />
					<span class="nm-text">{awayCode}</span>
				</span>
			</button>
		</div>
	{/if}
{:else if !anyTeam}
	<div class="pn-bm tbd"></div>
{:else}
	<div class="pn-bm" class:locked class:compact>
		<button
			type="button"
			class="row"
			class:pred={pickedHome}
			class:lose-pred={winner !== null && !pickedHome}
			on:click={clickHome}
			disabled={locked || !homeTeam}
		>
			<span class="nm">
				{#if homeTeam}
					<PnFlag code={teamCode(homeTeam)} w={compact ? 13 : 14} h={compact ? 9 : 10} />
				{/if}
				<span class="nm-text">{homeCode}</span>
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
				{#if awayTeam}
					<PnFlag code={teamCode(awayTeam)} w={compact ? 13 : 14} h={compact ? 9 : 10} />
				{/if}
				<span class="nm-text">{awayCode}</span>
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
