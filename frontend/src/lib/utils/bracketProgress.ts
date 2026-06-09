/**
 * Bracket-progress helpers — shared between the wizard
 * (routes/predictions/+page.svelte) and the Phase 1 dashboard
 * (components/panini/dashboard/DashboardPre.svelte).
 *
 * Both surfaces need to answer "how many of the 63 knockout bracket slots
 * has the user filled in?" — the wizard for its overall progress bar, the
 * dashboard for the hero countdown. They MUST agree, otherwise the
 * dashboard's "44 to fill" and the wizard's "you're done" badges
 * contradict each other.
 *
 * The 63 = 32 (R32 entrants) + 16 (R16) + 8 (QF) + 4 (SF) + 2 (Final)
 * + 1 (Winner) = sum of the per-round team picks across the FIFA 2026
 * bracket. Group-stage predictions are scored separately (group fixtures
 * + group_position picks) and don't roll into this count.
 */

import type { BracketPrediction } from '$types';

export const BRACKET_TOTAL_SLOTS = 63;

/**
 * Phase 2 re-pick total. By the time Phase 2 opens the 32 R32 entrants
 * are known facts, so the re-pick covers R16 onward only:
 * 16 + 8 + 4 + 2 + 1 = 31. Counting a complete Phase 2 bracket against
 * 63 would show "31/63 set" forever.
 */
export const BRACKET_TOTAL_SLOTS_PHASE2 = 31;

export interface BracketProgress {
	done: number;
	total: number;
}

/**
 * Count how many of the user's bracket slots are filled. `null` (no
 * bracket fetched yet) returns 0/63 — the same shape the wizard returns
 * pre-load so callers don't need a branch.
 */
export function countBracketSlotsFilled(b: BracketPrediction | null): BracketProgress {
	const total = BRACKET_TOTAL_SLOTS;
	if (!b) return { done: 0, total };
	let done = 0;
	for (const arr of [b.round_of_32, b.round_of_16, b.quarter_finals, b.semi_finals, b.final]) {
		for (const t of arr || []) if (t) done++;
	}
	if (b.winner) done++;
	return { done, total };
}
