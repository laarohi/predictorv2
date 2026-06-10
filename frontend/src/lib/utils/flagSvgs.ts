/**
 * Lazy accessor for the flag-icons SVG bundle.
 *
 * Previously every `flag-icons/flags/4x3/*.svg` (~270 files) was inlined into
 * the initial JS bundle with `eager: true`. Now the glob produces on-demand
 * `import()` factories, so Vite code-splits each flag into its own chunk and
 * only the flags actually rendered are fetched (perf-frontend:PERF-1/PERF-4).
 *
 * Loading is async, but the consumer degrades gracefully while a flag is in
 * flight: `PnFlag` shows its neutral placeholder box, so there is never a
 * broken state — the flag just pops in when ready. Components subscribe to
 * `flagCache` so they re-render on arrival.
 */

import { get, writable } from 'svelte/store';

const loaders = import.meta.glob<string>('/node_modules/flag-icons/flags/4x3/*.svg', {
	query: '?raw',
	import: 'default'
});

/** iso -> loaded raw `<svg…>` markup. Subscribe so views update on load. */
export const flagCache = writable<Record<string, string>>({});
const inflight = new Set<string>();

function keyFor(iso: string): string {
	return `/node_modules/flag-icons/flags/4x3/${iso}.svg`;
}

/** Kick off loading a flag into the cache. Idempotent, fire-and-forget. */
export function loadFlag(iso: string | null | undefined): void {
	if (!iso || inflight.has(iso) || get(flagCache)[iso] !== undefined) return;
	const loader = loaders[keyFor(iso)];
	if (!loader) return;
	inflight.add(iso);
	loader()
		.then((raw) => flagCache.update((c) => ({ ...c, [iso]: raw })))
		.catch(() => {})
		.finally(() => inflight.delete(iso));
}

/** Cached raw `<svg…>` markup, or undefined until loaded (call loadFlag first). */
export function rawFlagSvg(iso: string | null | undefined): string | undefined {
	if (!iso) return undefined;
	return get(flagCache)[iso];
}

/** A `data:image/svg+xml` URL for an SVG `<image href>`, or null until loaded. */
export function flagDataUrl(iso: string | null | undefined): string | null {
	const raw = rawFlagSvg(iso);
	if (!raw) return null;
	// Force the flag to fill the target box (flag-icons SVGs bake in
	// preserveAspectRatio="xMidYMid meet" which would letterbox).
	const stretched = raw.replace(/<svg\b/, '<svg preserveAspectRatio="none"');
	return 'data:image/svg+xml;utf8,' + encodeURIComponent(stretched);
}
