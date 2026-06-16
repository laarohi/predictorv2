<script lang="ts">
	/**
	 * Slim, dismissible "Replay The Back Page" bar for the dashboards.
	 *
	 * Appears AFTER the day's Back Page has been seen (so it never competes with
	 * the auto-open), lets people play the story back, and is dismissible per
	 * drop date (a new day's drop brings it back). One compact line — the heavy
	 * DwAlert treatment was too much for a replay nudge.
	 */
	import PnIcon from '$components/panini/PnIcon.svelte';
	import { latestDrop, dropSeen, requestReplay } from '$stores/backPage';

	const DISMISS_KEY = 'predictor_backpage_replay_dismissed';

	function readDismissed(): string {
		try {
			return localStorage.getItem(DISMISS_KEY) || '';
		} catch {
			return '';
		}
	}
	let dismissedDate = readDismissed();

	$: drop = $latestDrop;
	$: visible = drop !== null && $dropSeen && dismissedDate !== drop.drop_date;

	function dismiss(): void {
		if (!drop) return;
		try {
			localStorage.setItem(DISMISS_KEY, drop.drop_date);
		} catch {
			/* ignore — worst case the bar reappears next load */
		}
		dismissedDate = drop.drop_date;
	}
</script>

{#if visible && drop}
	<div class="bp-replay">
		<button class="bp-go" on:click={requestReplay}>
			<span class="bp-ic"><PnIcon name="replay" size={15} color="var(--ink)" stroke={2.4} /></span>
			<span>Replay the Back Page</span>
		</button>
		<button class="bp-x" on:click={dismiss} aria-label="Dismiss">
			<PnIcon name="close" size={14} color="currentColor" stroke={2.4} />
		</button>
	</div>
{/if}

<style>
	/* A gold sticker-button: filled gold, ink border + hard shadow, centred
	   label — with the dismiss × overlaid at the right so it doesn't pull the
	   text off-centre. */
	.bp-replay {
		position: relative;
		background: var(--gold);
		border: 2px solid var(--ink);
		box-shadow: 4px 4px 0 var(--ink);
		margin-bottom: 14px;
		transition:
			transform 0.12s ease,
			box-shadow 0.12s ease;
	}
	.bp-replay:hover {
		transform: translate(-1px, -1px);
		box-shadow: 5px 5px 0 var(--ink);
	}
	.bp-replay:active {
		transform: translate(1px, 1px);
		box-shadow: 2px 2px 0 var(--ink);
	}
	.bp-go {
		width: 100%;
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 8px;
		padding: 11px 34px;
		background: transparent;
		border: none;
		cursor: pointer;
		font-family: var(--display);
		font-size: 13px;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--ink);
	}
	.bp-ic {
		display: grid;
		place-items: center;
		flex-shrink: 0;
	}
	.bp-x {
		position: absolute;
		top: 50%;
		right: 7px;
		transform: translateY(-50%);
		width: 26px;
		height: 26px;
		display: grid;
		place-items: center;
		border: none;
		background: transparent;
		cursor: pointer;
		color: var(--ink);
		opacity: 0.65;
	}
	.bp-x:hover {
		opacity: 1;
	}
</style>
