/**
 * Tests for bracket ↔ standings reconciliation.
 *
 * The fixtures are synthetic but the resolution path is the real one
 * (initializeBracketState / predictionToBracketState), so these tests lock
 * the exact prune behaviour the predictions page relies on when a user
 * edits group scores after saving a bracket.
 *
 * Standings model: 12 groups (A–L) × 4 teams ("A1".."L4"), position by
 * points, third-place ranking made total via staggered goal difference —
 * groups A–H supply the 8 qualifying thirds, I–L miss out.
 */
import { describe, expect, it } from 'vitest';
import {
	FINAL,
	QUARTER_FINALS,
	ROUND_OF_16,
	ROUND_OF_32,
	SEMI_FINALS
} from '$lib/config/bracketConfig';
import type { BracketPrediction } from '$types';
import {
	bracketStateToPrediction,
	initializeBracketState,
	setMatchWinner,
	type GroupStandingsMap
} from './bracketResolver';
import {
	reconcileBracketWithStandings,
	standingsAreComplete,
	type ReconcileStage
} from './bracketReconcile';
import type { TeamStanding } from './standings';

const GROUPS = 'ABCDEFGHIJKL'.split('');
const PICK_STAGES = ['round_of_16', 'quarter_finals', 'semi_finals', 'final'] as const;

function makeStanding(team: string, group: string, gi: number, pos: number): TeamStanding {
	return {
		team,
		group,
		played: 3,
		won: 3 - pos,
		drawn: 0,
		lost: pos,
		goalsFor: 24 - gi - pos * 4,
		goalsAgainst: pos * 4,
		goalDifference: 24 - gi - pos * 8,
		points: (3 - pos) * 3
	};
}

/** Groups A–L, teams "<G>1".."<G>4" ranked 1st–4th. */
function buildStandings(): GroupStandingsMap {
	const standings: GroupStandingsMap = {};
	for (const [gi, g] of GROUPS.entries()) {
		standings[g] = [0, 1, 2, 3].map((pos) => makeStanding(`${g}${pos + 1}`, g, gi, pos));
	}
	return standings;
}

/** Swap which TEAMS occupy two positions of a group (stats stay with the
 *  position, exactly like editing scores reorders real standings). */
function swapTeams(standings: GroupStandingsMap, group: string, posA: number, posB: number): void {
	const gi = GROUPS.indexOf(group);
	const teamA = standings[group][posA].team;
	const teamB = standings[group][posB].team;
	standings[group] = standings[group].map((s, pos) =>
		makeStanding(pos === posA ? teamB : pos === posB ? teamA : s.team, group, gi, pos)
	);
}

/** Fully picked bracket: `preferred` wins every match it appears in,
 *  otherwise the home team advances. */
function buildFullBracket(standings: GroupStandingsMap, preferred?: string): BracketPrediction {
	let state = initializeBracketState(standings, []);
	for (const matches of [ROUND_OF_32, ROUND_OF_16, QUARTER_FINALS, SEMI_FINALS, [FINAL]]) {
		for (const m of matches) {
			const r = state.matchResults[m.matchNumber];
			expect(r?.homeTeam, `match ${m.matchNumber} home`).toBeTruthy();
			expect(r?.awayTeam, `match ${m.matchNumber} away`).toBeTruthy();
			const winner =
				preferred && (r.homeTeam === preferred || r.awayTeam === preferred)
					? preferred
					: (r.homeTeam as string);
			state = setMatchWinner(state, m.matchNumber, winner);
		}
	}
	return bracketStateToPrediction(state);
}

function picks(b: BracketPrediction, stage: (typeof PICK_STAGES)[number]): Set<string> {
	return new Set(b[stage].filter((t) => t));
}

/** Invariants every reconciliation result must satisfy, drift or not. */
function assertStructurallySound(
	bracket: BracketPrediction,
	standings: GroupStandingsMap,
	fifaRankings: string[] = []
): void {
	const r = reconcileBracketWithStandings(bracket, standings, fifaRankings);

	// 1. Resolution only ever keeps or drops picks — never invents them.
	for (const stage of PICK_STAGES) {
		const before = picks(bracket, stage);
		for (const t of picks(r.resolved, stage)) expect(before.has(t), `${stage}: ${t}`).toBe(true);
	}

	// 2. removed is EXACTLY the per-stage difference (no more, no less).
	const expectedRemoved: { stage: ReconcileStage; team: string }[] = [];
	for (const stage of PICK_STAGES) {
		const after = picks(r.resolved, stage);
		for (const t of [...picks(bracket, stage)].sort()) {
			if (!after.has(t)) expectedRemoved.push({ stage, team: t });
		}
	}
	if (bracket.winner && r.resolved.winner !== bracket.winner) {
		expectedRemoved.push({ stage: 'winner', team: bracket.winner });
	}
	expect(r.removed).toEqual(expectedRemoved);

	// 3. Stage-chain consistency of the resolved bracket: a team in stage N
	//    must also be in stage N-1 (and the roster).
	const roster = new Set(r.resolved.round_of_32.filter((t) => t));
	let prev = roster;
	for (const stage of PICK_STAGES) {
		const cur = picks(r.resolved, stage);
		for (const t of cur) expect(prev.has(t), `${stage}: ${t} missing upstream`).toBe(true);
		prev = cur;
	}
	if (r.resolved.winner) expect(prev.has(r.resolved.winner)).toBe(true);

	// 4. Idempotence: persisting `resolved` and reconciling again is a no-op.
	const again = reconcileBracketWithStandings(r.resolved, standings, fifaRankings);
	expect(again.changed).toBe(false);
	expect(again.removed).toEqual([]);
	expect(again.resolved).toEqual(r.resolved);
}

describe('reconcileBracketWithStandings', () => {
	it('is a no-op for a bracket consistent with its standings', () => {
		const standings = buildStandings();
		const bracket = buildFullBracket(standings);
		const r = reconcileBracketWithStandings(bracket, standings, []);

		expect(r.changed).toBe(false);
		expect(r.rosterChanged).toBe(false);
		expect(r.removed).toEqual([]);
		expect(new Set(r.resolved.round_of_32)).toEqual(new Set(bracket.round_of_32));
		for (const stage of PICK_STAGES) {
			expect(picks(r.resolved, stage)).toEqual(picks(bracket, stage));
		}
		expect(r.resolved.winner).toBe(bracket.winner);
		assertStructurallySound(bracket, standings);
	});

	it('prunes every pick of a team that drops out of the qualifiers (prod scenario)', () => {
		// Bracket built while I2 was Group I runner-up AND picked as champion.
		const before = buildStandings();
		const bracket = buildFullBracket(before, 'I2');
		expect(bracket.winner).toBe('I2');

		// Group score edit demotes I2 to 3rd; Group I's third doesn't make the
		// best-8, so I2 falls out of the R32 line-up entirely (I3 replaces it).
		const after = buildStandings();
		swapTeams(after, 'I', 1, 2);

		const r = reconcileBracketWithStandings(bracket, after, []);
		expect(r.changed).toBe(true);
		expect(r.rosterChanged).toBe(true);

		const roster = new Set(r.resolved.round_of_32.filter((t) => t));
		expect(roster.has('I2')).toBe(false);
		expect(roster.has('I3')).toBe(true);
		expect(roster.size).toBe(32);

		// I2 was picked through every stage; all five picks must be pruned and
		// nothing else may be touched.
		expect(r.removed).toEqual([
			{ stage: 'round_of_16', team: 'I2' },
			{ stage: 'quarter_finals', team: 'I2' },
			{ stage: 'semi_finals', team: 'I2' },
			{ stage: 'final', team: 'I2' },
			{ stage: 'winner', team: 'I2' }
		]);
		expect(picks(r.resolved, 'round_of_16').size).toBe(15);
		expect(r.resolved.winner).toBe('');

		assertStructurallySound(bracket, after);
	});

	it('handles a 1st/2nd-style swap that keeps the roster set but moves pairings', () => {
		const before = buildStandings();
		const bracket = buildFullBracket(before, 'A2');

		// A2 ↔ A3 swap: A2 drops to 3rd but Group A's third still qualifies,
		// so the roster SET is unchanged while R32 pairings shift.
		const after = buildStandings();
		swapTeams(after, 'A', 1, 2);

		const r = reconcileBracketWithStandings(bracket, after, []);
		expect(r.rosterChanged).toBe(false);
		// Pairings moved under a fully-picked bracket — picks must have dropped.
		expect(r.changed).toBe(true);
		expect(r.removed.length).toBeGreaterThan(0);

		assertStructurallySound(bracket, after);
	});

	it('re-saves a picks-free bracket whose derived roster drifted', () => {
		const before = buildStandings();
		// Roster only — no winner picks at all.
		const bracket = bracketStateToPrediction(initializeBracketState(before, []));
		expect(bracket.round_of_32.filter((t) => t)).toHaveLength(32);
		expect(bracket.round_of_16.filter((t) => t)).toHaveLength(0);

		const after = buildStandings();
		swapTeams(after, 'I', 1, 2);

		const r = reconcileBracketWithStandings(bracket, after, []);
		expect(r.changed).toBe(true);
		expect(r.rosterChanged).toBe(true);
		expect(r.removed).toEqual([]);
		assertStructurallySound(bracket, after);
	});

	it('refuses to prune against incomplete standings', () => {
		const standings = buildStandings();
		const bracket = buildFullBracket(standings, 'L1');

		const partial = buildStandings();
		delete partial.L;
		expect(standingsAreComplete(partial)).toBe(false);

		const r = reconcileBracketWithStandings(bracket, partial, []);
		expect(r.changed).toBe(false);
		expect(r.removed).toEqual([]);
		expect(r.resolved).toBe(bracket); // identity, untouched

		// Same for a group that exists but isn't fully ranked.
		const short = buildStandings();
		short.L = short.L.slice(0, 3);
		expect(standingsAreComplete(short)).toBe(false);
		expect(reconcileBracketWithStandings(bracket, short, []).changed).toBe(false);
	});
});
