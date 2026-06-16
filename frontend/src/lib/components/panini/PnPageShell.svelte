<script lang="ts">
	// Page wrapper that establishes the .pn CSS scope and hosts the chrome.
	//
	// APP-SHELL LAYOUT (the iOS-standalone nav-stranding fix):
	// .pn-shell is exactly one viewport tall (100dvh) and overflow:hidden — it
	// never scrolls. The inner <main class="pn-body"> is the SINGLE scroll
	// container. The bottom nav is therefore a STATIC, in-flow flex child that
	// sits at the bottom by layout, not by sticky/fixed positioning — so iOS
	// WebKit never promotes it to a viewport-anchored composited layer that can
	// be repainted at a stale offset after an app suspend/resume. That compositor
	// behaviour is the Heisenbug that survived the earlier fixed→sticky + nudge +
	// dvh attempts (git 3fdf489 / 64f5a05); removing the nav from the composited
	// layer class deletes the bug's precondition rather than patching it.
	//
	// Above 700px: shows the desktop masthead + optional red sub-strip at the top
	//              of the non-scrolling shell (always visible). Its height is
	//              measured on mount + resize and written to --pn-chrome-h. NOTE:
	//              page-level sticky elements now live INSIDE .pn-body, whose top
	//              already sits below the chrome, so they anchor at top:0 — NOT
	//              top:var(--pn-chrome-h), which would double-count the chrome
	//              (see panini-results.css .pn-rs-sticky).
	// Below 700px: shows the bottom tab nav as the shell's last static child.
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
		/* App-shell: the shell is exactly one viewport tall and NEVER scrolls;
		 * .pn-body below is the only scroll container. This keeps the bottom nav
		 * a static in-flow child instead of a viewport-anchored sticky/fixed
		 * layer — the only object class iOS standalone's compositor strands at a
		 * stale offset on resume. dvh tracks the dynamic viewport (URL bar). */
		height: 100vh; /* fallback for pre-15.4 Safari */
		height: 100dvh;
		overflow: hidden;
	}
	.desktop-only {
		display: none;
	}
	.mobile-only {
		display: block;
		/* Static, in-flow LAST child of the non-scrolling shell: it sits flush at
		 * the bottom by flex layout, NOT by position:sticky/fixed, so WebKit never
		 * composites it as its own layer and it cannot strand on resume. */
		flex-shrink: 0;
		z-index: 40;
	}
	:global(.pn-shell main.pn-body) {
		flex: 1;
		/* CRITICAL: a flex item's default min-height:auto refuses to shrink below
		 * its content, so the body would grow past the shell and push the nav
		 * off-screen (and never scroll). min-height:0 lets it scroll internally. */
		min-height: 0;
		overflow-y: auto;
		-webkit-overflow-scrolling: touch; /* momentum scroll on older iOS */
		overscroll-behavior: contain; /* no scroll-chaining/rubber-band to the shell */
		padding-bottom: 16px; /* breathing room above the nav */
	}
	@media (min-width: 700px) {
		.desktop-only {
			display: block;
			/* First child of the non-scrolling shell → always visible at top.
			 * sticky + z-index kept so the masthead avatar dropdown paints over
			 * body content below it. */
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
