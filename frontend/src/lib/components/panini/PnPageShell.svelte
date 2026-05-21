<script lang="ts">
	// Page wrapper that establishes the .pn CSS scope and hosts the chrome.
	// Above 700px: shows the desktop masthead + optional red sub-strip,
	//              both kept sticky at top so the nav is always reachable
	//              without having to scroll back. The chrome's actual height
	//              is measured on mount + resize and written to a CSS custom
	//              property (--pn-chrome-h) so pages with their own sticky
	//              elements can stack below it via calc().
	// Below 700px: shows the fixed bottom 5-tab nav (the existing root layout's
	// dark nav still renders above us; the sandbox accepts that intentionally).
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import PnMast from './PnMast.svelte';
	import PnBottomNav from './PnBottomNav.svelte';
	import PnStrip from './PnStrip.svelte';

	export let activeOverride: string | null = null;
	export let liveLabel: string | null = null;
	export let lockLabel: string | null = null;
	export let youLabel: string | null = null;
	export let showStrip: boolean = true;

	let chromeEl: HTMLElement | null = null;

	function updateChromeHeight() {
		if (!browser || !chromeEl) return;
		// At <700px the chrome is display:none, so offsetHeight is 0 — that's
		// the correct value for the CSS var (no chrome to clear on mobile).
		const h = chromeEl.offsetHeight;
		document.documentElement.style.setProperty('--pn-chrome-h', `${h}px`);
	}

	onMount(() => {
		if (!browser || !chromeEl) return;
		const ro = new ResizeObserver(updateChromeHeight);
		ro.observe(chromeEl);
		updateChromeHeight();
		// Also respond to viewport changes — the chrome's display flips at
		// 700px and offsetHeight jumps between 0 and ~76px.
		const onResize = () => updateChromeHeight();
		window.addEventListener('resize', onResize);
		return () => {
			ro.disconnect();
			window.removeEventListener('resize', onResize);
		};
	});
</script>

<div class="pn pn-shell">
	<div class="desktop-only" bind:this={chromeEl}>
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
			/* Keep nav reachable without scrolling back to the top. Pages with
			 * their own sticky elements (e.g. Results' ribbon) stack below
			 * this using top: var(--pn-chrome-h). z-index keeps it over any
			 * page-level sticky elements. */
			position: sticky;
			top: 0;
			z-index: 50;
		}
		.mobile-only {
			display: none;
		}
		:global(.pn-shell main.pn-body) {
			padding-bottom: 28px;
		}
	}
</style>
