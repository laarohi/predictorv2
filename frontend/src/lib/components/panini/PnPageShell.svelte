<script lang="ts">
	// Page wrapper that establishes the .pn CSS scope and hosts the chrome.
	// Above 700px: shows the desktop masthead + optional red sub-strip.
	// Below 700px: shows the fixed bottom 5-tab nav (the existing root layout's
	// dark nav still renders above us; the sandbox accepts that intentionally).
	import PnMast from './PnMast.svelte';
	import PnBottomNav from './PnBottomNav.svelte';
	import PnStrip from './PnStrip.svelte';

	export let activeOverride: string | null = null;
	export let liveLabel: string | null = null;
	export let lockLabel: string | null = null;
	export let youLabel: string | null = null;
	export let showStrip: boolean = true;
</script>

<div class="pn pn-shell">
	<div class="desktop-only">
		<PnMast {activeOverride} />
		{#if showStrip}
			<PnStrip {liveLabel} {lockLabel} {youLabel} />
		{/if}
	</div>

	<main class="pn-body">
		<slot />
	</main>

	<div class="mobile-only">
		<PnBottomNav />
	</div>
</div>

<style>
	.pn-shell {
		display: flex;
		flex-direction: column;
		min-height: 100vh;
	}
	.desktop-only {
		display: none;
	}
	.mobile-only {
		display: block;
	}
	:global(.pn-shell main.pn-body) {
		flex: 1;
		padding-bottom: 80px; /* room for fixed mobile bottom nav */
	}
	@media (min-width: 700px) {
		.desktop-only {
			display: block;
		}
		.mobile-only {
			display: none;
		}
		:global(.pn-shell main.pn-body) {
			padding-bottom: 28px;
		}
	}
</style>
