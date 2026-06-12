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
	let navWrapEl: HTMLElement | null = null;
	let nudgeRaf = 0;

	/**
	 * Re-anchor the sticky bottom nav after visual-viewport changes.
	 *
	 * iOS standalone (home-screen) mode sometimes leaves the sticky layer
	 * composited at a stale offset after keyboard dismissal or app resume —
	 * no layout invalidation happens, so WebKit keeps the cached position
	 * (same bug family that stranded the old position:fixed nav, just
	 * rarer). A one-frame transform toggle forces the compositor to
	 * recompute the layer; visually a no-op everywhere else.
	 */
	function nudgeNav() {
		if (!browser || !navWrapEl) return;
		cancelAnimationFrame(nudgeRaf);
		nudgeRaf = requestAnimationFrame(() => {
			if (!navWrapEl) return;
			navWrapEl.style.transform = 'translateZ(0)';
			void navWrapEl.offsetHeight; // force reflow while transformed
			navWrapEl.style.transform = '';
		});
	}

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

		// Sticky-nav re-anchor triggers: every event iOS standalone fires
		// around keyboard show/hide, app resume and rotation.
		const vv = window.visualViewport;
		vv?.addEventListener('resize', nudgeNav);
		vv?.addEventListener('scroll', nudgeNav);
		window.addEventListener('pageshow', nudgeNav);
		window.addEventListener('orientationchange', nudgeNav);
		document.addEventListener('visibilitychange', nudgeNav);

		return () => {
			ro.disconnect();
			window.removeEventListener('resize', onResize);
			vv?.removeEventListener('resize', nudgeNav);
			vv?.removeEventListener('scroll', nudgeNav);
			window.removeEventListener('pageshow', nudgeNav);
			window.removeEventListener('orientationchange', nudgeNav);
			document.removeEventListener('visibilitychange', nudgeNav);
			cancelAnimationFrame(nudgeRaf);
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

	<div class="mobile-only" bind:this={navWrapEl}>
		<PnBottomNav />
	</div>
</div>

<style>
	.pn-shell {
		display: flex;
		flex-direction: column;
		/* dvh tracks the DYNAMIC viewport: with plain 100vh (the large
		 * viewport), a short page in non-standalone Safari with the URL bar
		 * expanded puts the nav's natural position below the visible area. */
		min-height: 100vh; /* fallback for pre-15.4 Safari */
		min-height: 100dvh;
	}
	.desktop-only {
		display: none;
	}
	.mobile-only {
		display: block;
		/* Sticky (not fixed) bottom nav: iOS standalone (home-screen) mode
		 * leaves position:fixed layers composited at stale offsets after
		 * keyboard dismissal / app resume — the nav would freeze mid-screen.
		 * Sticky is anchored to the scroller, which stays correct. This
		 * wrapper is the shell's last flex child, so bottom: 0 has the whole
		 * document as travel room (the nav itself can't stick — its containing
		 * block would be this wrapper, which is exactly its own height). */
		position: sticky;
		bottom: 0;
		z-index: 40;
	}
	:global(.pn-shell main.pn-body) {
		flex: 1;
		padding-bottom: 16px; /* nav is in-flow now; just breathing room */
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
