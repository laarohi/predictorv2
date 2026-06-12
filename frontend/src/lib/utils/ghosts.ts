/**
 * Ghost-entrant helpers — the single frontend chokepoint for "humans only".
 *
 * Ghosts (crowd consensus / Polymarket bot) are unranked leaderboard
 * extras: the backend already excludes them from every aggregate it
 * serves, and `position` is 0 on their entries. Anything client-side
 * that ranks, slices top-N, or counts participants must go through
 * these helpers so a ghost can never displace a human row or inflate
 * a count. Covered by ghosts.test.ts.
 */

interface GhostFlagged {
	is_ghost: boolean;
}

/** Entries without the ghosts, original order preserved. */
export function humanEntries<T extends GhostFlagged>(entries: T[]): T[] {
	return entries.filter((e) => !e.is_ghost);
}

/** How many real participants an entry list holds. */
export function humanCount(entries: GhostFlagged[]): number {
	return humanEntries(entries).length;
}
