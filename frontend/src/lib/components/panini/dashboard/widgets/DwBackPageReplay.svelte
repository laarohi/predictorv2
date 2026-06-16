<script lang="ts">
	/**
	 * Dismissible "Replay The Back Page" banner for the dashboards.
	 *
	 * Mirrors the unpaid-fee reminder (DwAlert), but its CTA reopens the day's
	 * Back Page story (which auto-shows once, then closes). It only appears AFTER
	 * the viewer has seen the drop — so it never competes with the auto-open — and
	 * is dismissible per drop date (a new day's drop brings it back).
	 */
	import { latestDrop, dropSeen, requestReplay } from '$stores/backPage';
	import DwAlert from './DwAlert.svelte';

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
			/* ignore — worst case the banner reappears next load */
		}
		dismissedDate = drop.drop_date;
	}
</script>

{#if visible && drop}
	<DwAlert
		variant="gold"
		icon="↺"
		title="The Back Page"
		meta="Today’s winners, bottlers &amp; the roast — give it another read."
		ctaLabel="Replay"
		onCta={requestReplay}
		onDismiss={dismiss}
	/>
{/if}
