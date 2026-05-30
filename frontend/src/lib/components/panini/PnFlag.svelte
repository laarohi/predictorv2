<script lang="ts">
	// Real flag artwork (vector SVG via flag-icons), force-stretched to a
	// uniform 3:2 aspect so Switzerland (1:1) and Qatar (11:28) don't
	// disrupt layout. flag-icons SVGs are authored at viewBox 640x480 (4:3)
	// with the document's default preserveAspectRatio="xMidYMid meet" —
	// which letterboxes 4:3 content inside a 3:2 box. Neither <img> with
	// object-fit:fill NOR background-image with background-size:100% 100%
	// reliably overrides that document-level attribute; the only robust
	// fix is to inline the SVG content and inject preserveAspectRatio="none"
	// on the root <svg> tag before rendering. Trade-off: all 271 SVGs land
	// in the JS bundle as strings rather than as separate hashed assets,
	// which is fine for this app's ~30-user audience.
	//
	// Unknown codes render a neutral grey rectangle in the same chrome so
	// the layout stays stable.

	import { flagIsoCode } from '$lib/utils/teamCodes';
	import { loadFlag, flagCache } from '$lib/utils/flagSvgs';

	export let code: string;
	export let w: number = 18;
	export let h: number = 12;
	export let border: boolean = true;

	$: iso = flagIsoCode(code);
	$: loadFlag(iso); // lazily fetch this flag's chunk
	// Reactive on the cache: undefined until the chunk loads (placeholder shows).
	$: rawSvg = iso ? $flagCache[iso] : undefined;
	// Inject preserveAspectRatio="none" on the root <svg> tag so the
	// browser stretches the artwork to fill our viewport instead of
	// letterboxing it. The regex inserts the attribute right after `<svg`
	// (word-boundary) so it lands before existing attrs like xmlns.
	$: svg = rawSvg ? rawSvg.replace(/<svg\b/, '<svg preserveAspectRatio="none"') : undefined;
</script>

<span
	class="pn-flag"
	class:has-border={border}
	style="width: {w}px; height: {h}px;"
	aria-label={code}
	role="img"
>
	{#if svg}
		{@html svg}
	{/if}
</span>

<style>
	.pn-flag {
		display: inline-block;
		flex-shrink: 0;
		box-sizing: border-box;
		border-radius: 2px;
		background-color: #888;
		overflow: hidden;
		line-height: 0;
	}
	.pn-flag.has-border {
		border: 1.5px solid #161513;
	}
	.pn-flag :global(svg) {
		display: block;
		width: 100%;
		height: 100%;
		filter: saturate(0.94) contrast(1.04);
	}
</style>
