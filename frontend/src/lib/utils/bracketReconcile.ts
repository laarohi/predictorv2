/**
 * Bracket ↔ group-standings reconciliation.
 *
 * A Phase 1 bracket is seeded from the user's *predicted* group standings.
 * When the user later edits group scores, previously saved knockout picks
 * can stop fitting the bracket those standings imply (a picked team no
 * longer qualifies, or now sits in a different R32 pairing). The save flow
 * must then persist the bracket exactly as the UI re-resolves it — holes
 * included — instead of leaving stale advancement rows in the database.
 *
 * `reconcileBracketWithStandings` runs the same resolution pipeline the
 * bracket component renders with (`predictionToBracketState`) and reports
 * which user picks did not survive. It is pure and side-effect free; the
 * predictions page decides what to do with the result.
 */
import type { BracketPrediction } from '$types';
import {
	bracketStateToPrediction,
	predictionToBracketState,
	type GroupStandingsMap
} from './bracketResolver';

/** Stages that hold explicit user picks (the R32 line-up is derived). */
export type ReconcileStage =
	| 'round_of_16'
	| 'quarter_finals'
	| 'semi_finals'
	| 'final'
	| 'winner';

export interface RemovedPick {
	stage: ReconcileStage;
	team: string;
}

export interface BracketReconciliation {
	/** The bracket as it resolves against the given standings — what should
	 *  be persisted. Identical to the input when nothing drifted. */
	resolved: BracketPrediction;
	/** User picks (R16 → champion) that no longer fit and were dropped. */
	removed: RemovedPick[];
	/** True when the derived R32 line-up itself differs from the saved one. */
	rosterChanged: boolean;
	/** True when persisting `resolved` would change anything at all. */
	changed: boolean;
}

const PICK_STAGES = ['round_of_16', 'quarter_finals', 'semi_finals', 'final'] as const;

// The FIFA 2026 bracket (see $lib/config/bracketConfig) is hardcoded to
// 12 groups of 4. Reconciling against anything less than fully ranked
// standings would mass-prune valid picks, so we refuse instead.
const EXPECTED_GROUPS = 'ABCDEFGHIJKL'.split('');
const TEAMS_PER_GROUP = 4;

function teamSet(teams: readonly (string | undefined)[] | undefined): Set<string> {
	const out = new Set<string>();
	for (const t of teams || []) if (t) out.add(t);
	return out;
}

function setsEqual(a: Set<string>, b: Set<string>): boolean {
	if (a.size !== b.size) return false;
	for (const t of a) if (!b.has(t)) return false;
	return true;
}

/** Every group fully ranked — the precondition for trusting a resolution. */
export function standingsAreComplete(standings: GroupStandingsMap): boolean {
	return EXPECTED_GROUPS.every((g) => {
		const teams = standings[g];
		return (
			Array.isArray(teams) &&
			teams.length === TEAMS_PER_GROUP &&
			teams.every((t) => !!t?.team)
		);
	});
}

export function reconcileBracketWithStandings(
	bracket: BracketPrediction,
	standings: GroupStandingsMap,
	fifaRankings: string[] = []
): BracketReconciliation {
	// Safety invariant: NEVER prune against partial standings. Callers gate
	// on group completeness too; this guard makes the function safe even if
	// a caller forgets.
	if (!standingsAreComplete(standings)) {
		return { resolved: bracket, removed: [], rosterChanged: false, changed: false };
	}

	const resolved = bracketStateToPrediction(
		predictionToBracketState(bracket, standings, fifaRankings)
	);

	// Per pick-stage, resolution can only ever KEEP or DROP a stored pick
	// (a team appears in at most one match per round, and only stored picks
	// are applied as winners) — so `before − after` is exactly the prune set.
	const removed: RemovedPick[] = [];
	for (const stage of PICK_STAGES) {
		const before = teamSet(bracket[stage]);
		const after = teamSet(resolved[stage]);
		for (const team of [...before].sort()) {
			if (!after.has(team)) removed.push({ stage, team });
		}
	}
	if (bracket.winner && resolved.winner !== bracket.winner) {
		removed.push({ stage: 'winner', team: bracket.winner });
	}

	const rosterChanged = !setsEqual(teamSet(bracket.round_of_32), teamSet(resolved.round_of_32));

	// `removed` already implies pick-stage drift; the extra set comparison is
	// defensive in case resolution ever yields a pick the input lacked.
	const changed =
		rosterChanged ||
		removed.length > 0 ||
		PICK_STAGES.some((s) => !setsEqual(teamSet(bracket[s]), teamSet(resolved[s]))) ||
		(bracket.winner || '') !== (resolved.winner || '');

	return { resolved, removed, rosterChanged, changed };
}
