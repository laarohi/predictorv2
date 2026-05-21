<script lang="ts">
	/**
	 * Renders a flag inside a parent `<svg>` element, positioned in the
	 * parent's coordinate system. Uses the same flag-icons artwork as
	 * `PnFlag` (via `flagSvgs.ts`) but as a native SVG `<image>` element
	 * with a `data:image/svg+xml` href, which sidesteps the foreignObject
	 * scaling bug on iOS Safari.
	 *
	 * Caller positions in the parent SVG's units; we add an ink border
	 * matching `PnFlag`'s default look.
	 */
	import { flagIsoCode } from '$lib/utils/teamCodes';
	import { flagDataUrl } from '$lib/utils/flagSvgs';

	export let code: string;
	export let x: number;
	export let y: number;
	export let w: number;
	export let h: number;

	$: iso = flagIsoCode(code);
	$: href = flagDataUrl(iso);
</script>

{#if href}
	<image {x} {y} width={w} height={h} {href} preserveAspectRatio="none" />
	<rect {x} {y} width={w} height={h} fill="none" stroke="#161513" stroke-width="1.2" />
{/if}
