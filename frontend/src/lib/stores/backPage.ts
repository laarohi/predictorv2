/**
 * The Back Page (daily drop) cross-component state.
 *
 * `PnDropModal` (mounted once in +layout) owns fetching the latest drop and the
 * modal itself. It publishes the fetched drop + "has the viewer seen it yet"
 * here so the dashboard can offer a dismissible **Replay** button once the drop
 * has been viewed. `requestReplay()` is the one-way command from that button
 * back to the modal to reopen the story it already closed.
 */
import { writable } from 'svelte/store';
import type { DailyDrop } from '$types';

/** The most recent drop once the modal has fetched it (null until then / none). */
export const latestDrop = writable<DailyDrop | null>(null);

/**
 * True once the viewer has seen the current drop — either it auto-opened and
 * they closed it, or it was already in their seen-list on load. The replay
 * button only appears after this, so it never competes with the auto-open.
 */
export const dropSeen = writable(false);

/** Bumped by `requestReplay()`; the modal watches it and reopens on change. */
export const replaySignal = writable(0);

export function requestReplay(): void {
	replaySignal.update((n) => n + 1);
}
