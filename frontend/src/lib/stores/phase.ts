/**
 * Phase store for competition phase status.
 */

import { writable, derived, readable } from 'svelte/store';
import { browser } from '$app/environment';
import * as competitionApi from '$api/competition';
import { fixtures } from '$stores/fixtures';
import type { Fixture, PhaseStatus, UxPhase } from '$types';

// Stores
export const phaseStatus = writable<PhaseStatus | null>(null);
export const phaseLoading = writable<boolean>(false);
export const phaseError = writable<string | null>(null);

// Current time store that updates every second (for countdown)
export const currentTime = readable(new Date(), (set) => {
	if (!browser) return;

	set(new Date());
	const interval = setInterval(() => {
		set(new Date());
	}, 1000);

	return () => clearInterval(interval);
});

// Derived stores - Phase 1
export const phase1Deadline = derived(
	phaseStatus,
	($phaseStatus) => $phaseStatus?.phase1_deadline ?? null
);

// Composed with the ticking clock so a tab left open across the deadline
// flips to locked at the exact second, even though phaseStatus itself is
// only re-fetched periodically. The server stays authoritative at save
// time; this only keeps the UI honest. (Booleans short-circuit in Svelte's
// equality check, so the 1 Hz tick doesn't re-notify subscribers.)
export const isPhase1Locked = derived(
	[phaseStatus, currentTime],
	([$phaseStatus, $now]) => {
		if (!$phaseStatus) return false;
		if ($phaseStatus.phase1_locked) return true;
		const deadline = $phaseStatus.phase1_deadline;
		return deadline !== null && new Date(deadline).getTime() <= $now.getTime();
	}
);

// Derived stores - Phase 2
export const currentPhase = derived(
	phaseStatus,
	($phaseStatus) => $phaseStatus?.current_phase ?? 'phase_1'
);

export const isPhase2Active = derived(
	phaseStatus,
	($phaseStatus) => $phaseStatus?.is_phase2_active ?? false
);

// Same live-deadline composition as isPhase1Locked above.
export const isPhase2BracketLocked = derived(
	[phaseStatus, currentTime],
	([$phaseStatus, $now]) => {
		if (!$phaseStatus) return false;
		if ($phaseStatus.phase2_bracket_locked) return true;
		if (!$phaseStatus.is_phase2_active) return false;
		const deadline = $phaseStatus.phase2_bracket_deadline;
		return deadline !== null && new Date(deadline).getTime() <= $now.getTime();
	}
);

export const phase2BracketDeadline = derived(
	phaseStatus,
	($phaseStatus) => $phaseStatus?.phase2_bracket_deadline ?? null
);

// Live countdown stores (update every second)
export const phase1Countdown = derived(
	[phase1Deadline, currentTime],
	([$deadline, $now]) => getTimeUntilDeadline($deadline, $now)
);

export const phase2Countdown = derived(
	[phase2BracketDeadline, currentTime],
	([$deadline, $now]) => getTimeUntilDeadline($deadline, $now)
);

// ---- UX phase (composed phase + fixture-derived) ---------------------------
//
// The backend tracks two technical phases (phase_1, phase_2). The UX layer
// needs a richer taxonomy because user goals shift several times within
// "phase_1" alone (pre-tournament vs. group stage) and after phase_2
// activation (between-phases vs. KO-stage). uxPhase composes the lock
// signals into one enum that drives the landing dashboard's layout.
//
// Post-competition (final fixture finished) is detected via a SEPARATE
// derived store (`isFinalFinished`) below — we don't put fixtures into the
// uxPhase derived's dependency list because the group-stage dashboard
// mutates `fixtures` heavily on mount via fetchAllFixtures, and that
// cascade triggered an infinite reactive loop (Maximum call stack size
// exceeded in scheduler.flush) when the dispatcher's many transitive
// subscribers all re-fired together. The dispatcher does the
// post-competition check itself, so uxPhase stays stable across fixture
// writes.

/**
 * Dev-only override for the derived uxPhase. Set by +layout.svelte when the
 * URL carries ?uxPhase=... and import.meta.env.DEV is true. null in
 * production builds and when no override is requested.
 */
export const uxPhaseOverride = writable<UxPhase | null>(null);

/**
 * Pure UX-phase derivation. Exported separately for unit testing — the
 * derived store below is a thin Svelte wrapper around this function.
 *
 * The function takes the *final-finished* boolean as input rather than the
 * full fixtures list so that the derived store can stay decoupled from the
 * heavy `fixtures` writable. The dispatcher composes the two.
 *
 * Priority of checks matters:
 *   1. Defensive default while phaseStatus is null (first paint, backend
 *      unreachable). Pre-tournament is the only phase whose dashboard works
 *      without backend data.
 *   2. Post-competition is checked *before* the lock-based phases — a
 *      finished final overrides any lingering phase2_bracket_locked=true.
 *   3. Lock states then partition the remaining space deterministically.
 */
export function deriveUxPhase(
	phaseStatus: PhaseStatus | null,
	finalFinished: boolean
): UxPhase {
	if (!phaseStatus) return 'pre_tournament';
	if (finalFinished) return 'post_competition';

	if (!phaseStatus.phase1_locked) return 'pre_tournament';
	if (!phaseStatus.is_phase2_active) return 'group_stage';
	if (!phaseStatus.phase2_bracket_locked) return 'between_phases';
	return 'knockout_stage';
}

/**
 * True when the FINAL fixture has status="finished". Derived from `fixtures`
 * so it tracks score-sync writes, but kept separate from `uxPhase` to avoid
 * cascading reactive updates into every uxPhase subscriber on every fixture
 * write.
 */
export const isFinalFinished = derived(fixtures, ($fixtures) => {
	const finalFixture = $fixtures.find((f) => f.stage === 'final');
	return finalFixture?.status === 'finished';
});

export const uxPhase = derived(
	[phaseStatus, isFinalFinished, uxPhaseOverride],
	([$phaseStatus, $finalFinished, $override]) =>
		$override ?? deriveUxPhase($phaseStatus, $finalFinished)
);

// Actions
export async function fetchPhaseStatus(): Promise<void> {
	phaseLoading.set(true);
	phaseError.set(null);

	try {
		const data = await competitionApi.getPhaseStatus();
		phaseStatus.set(data);
	} catch (e) {
		phaseError.set(e instanceof Error ? e.message : 'Failed to load phase status');
	} finally {
		phaseLoading.set(false);
	}
}

/**
 * Keep phaseStatus fresh in long-lived tabs: re-fetch every 60s and on
 * tab-refocus. The deadline-composed lock stores above handle the exact
 * flip moment; this true-up catches server-side changes (admin moves a
 * deadline, activates Phase 2) and refreshes per-fixture lock state
 * consumers that re-read on phaseStatus changes.
 *
 * Returns a cleanup function; call from the root layout's onMount.
 */
export function startPhaseStatusRefresh(intervalMs = 60_000): () => void {
	if (!browser) return () => {};

	const interval = setInterval(() => {
		void fetchPhaseStatus();
	}, intervalMs);

	const onVisible = () => {
		if (document.visibilityState === 'visible') void fetchPhaseStatus();
	};
	document.addEventListener('visibilitychange', onVisible);

	return () => {
		clearInterval(interval);
		document.removeEventListener('visibilitychange', onVisible);
	};
}

// Utility functions
export function formatDeadline(deadline: string | null): string {
	if (!deadline) return 'Not set';
	const date = new Date(deadline);
	return date.toLocaleString('en-GB', {
		weekday: 'short',
		day: 'numeric',
		month: 'short',
		hour: '2-digit',
		minute: '2-digit'
	});
}

export function getTimeUntilDeadline(deadline: string | null, now: Date = new Date()): string {
	if (!deadline) return 'Not set';

	const deadlineDate = new Date(deadline);
	const diff = deadlineDate.getTime() - now.getTime();

	if (diff <= 0) return 'Locked';

	const days = Math.floor(diff / (1000 * 60 * 60 * 24));
	const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
	const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
	const seconds = Math.floor((diff % (1000 * 60)) / 1000);

	if (days > 0) return `${days}d ${hours}h ${minutes}m ${seconds}s`;
	if (hours > 0) return `${hours}h ${minutes}m ${seconds}s`;
	if (minutes > 0) return `${minutes}m ${seconds}s`;
	return `${seconds}s`;
}
