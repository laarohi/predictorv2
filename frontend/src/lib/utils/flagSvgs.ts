/**
 * Shared accessor for the flag-icons SVG bundle.
 *
 * Vite inlines every `flag-icons/flags/4x3/*.svg` as a raw string at build
 * time. We expose two derived forms:
 *
 *  - `rawFlagSvg(iso)` — the original `<svg…>` markup, ready to embed
 *    inline as HTML (used by PnFlag).
 *  - `flagDataUrl(iso)` — a `data:image/svg+xml;utf8,…` URI suitable for
 *    `<image href="…" />` inside another SVG (used by PnAxisFlag).
 *
 * Centralising the glob in one module keeps the bundle deduped — Vite was
 * previously creating two glob maps when both PnFlag and the axis flag
 * component pulled the SVGs separately.
 */

const flagSvgs = import.meta.glob<string>(
	'/node_modules/flag-icons/flags/4x3/*.svg',
	{ eager: true, query: '?raw', import: 'default' }
);

export function rawFlagSvg(iso: string | null | undefined): string | undefined {
	if (!iso) return undefined;
	return flagSvgs[`/node_modules/flag-icons/flags/4x3/${iso}.svg`];
}

/** A `data:image/svg+xml` URL, ready for an SVG `<image href>` attribute.
 * Returns `null` when the ISO code is unknown. */
export function flagDataUrl(iso: string | null | undefined): string | null {
	const raw = rawFlagSvg(iso);
	if (!raw) return null;
	// Force the flag to fill the target box (each flag-icons SVG has
	// preserveAspectRatio="xMidYMid meet" baked in which would letterbox
	// inside the non-4:3 boxes we put them in).
	const stretched = raw.replace(/<svg\b/, '<svg preserveAspectRatio="none"');
	return 'data:image/svg+xml;utf8,' + encodeURIComponent(stretched);
}
