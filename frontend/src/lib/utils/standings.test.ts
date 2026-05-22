/**
 * Tests for utils/standings.ts — the FIFA tiebreaker chain used to compute
 * the wizard's *predicted* group standings.
 *
 * The chain (per the file header):
 *   points → GD → GF → H2H points → H2H GD → H2H goals → alphabetical (+warning)
 *
 * Covered:
 *   - applyFifaTiebreakers directly with synthetic standings (3-way H2H
 *     separation, partial H2H + alphabetical sub-tie, no-H2H cross-group case)
 *   - calculateGroupStandingsWithWarnings end-to-end through Fixture+prediction
 *   - computeGroupStandingsMapWithWarnings aggregating warnings across groups
 */

import { describe, it, expect } from 'vitest';
import {
	applyFifaTiebreakers,
	calculateGroupStandings,
	calculateGroupStandingsWithWarnings,
	computeGroupStandingsMapWithWarnings,
	filterQualificationRelevantWarnings,
	type TeamStanding,
	type TieWarning
} from './standings';
import type { Fixture, MatchPrediction } from '$types';

// ---------------------------------------------------------------------------
// Fixture builders
// ---------------------------------------------------------------------------

function _ts(team: string, group: string, points: number, gd: number, gf = 0): TeamStanding {
	return {
		team,
		group,
		played: 3,
		won: 0,
		drawn: 0,
		lost: 0,
		goalsFor: gf,
		goalsAgainst: gf - gd,
		goalDifference: gd,
		points
	};
}

function _fixture(id: string, home: string, away: string, group = 'A'): Fixture {
	return {
		id,
		home_team: home,
		away_team: away,
		kickoff: '2026-06-11T19:00:00Z',
		stage: 'group',
		group,
		match_number: null,
		status: 'finished',
		minute: null,
		is_locked: true,
		time_until_lock: null,
		score: null
	};
}

function _pred(id: string, homeScore: number, awayScore: number): [string, MatchPrediction] {
	return [
		id,
		{
			id: `pred-${id}`,
			fixture_id: id,
			home_score: homeScore,
			away_score: awayScore,
			phase: 'phase_1',
			locked_at: null,
			created_at: '2026-06-11T00:00:00Z',
			updated_at: '2026-06-11T00:00:00Z',
			is_locked: false
		}
	];
}

// ---------------------------------------------------------------------------
// applyFifaTiebreakers — direct unit tests
// ---------------------------------------------------------------------------

describe('applyFifaTiebreakers', () => {
	it('separates a clean overall ranking with no warnings', () => {
		const teams = [
			_ts('France', 'A', 9, 5, 7),
			_ts('Germany', 'A', 6, 2, 4),
			_ts('Spain', 'A', 3, 0, 2),
			_ts('Italy', 'A', 0, -7, 0)
		];
		const { sorted, warnings } = applyFifaTiebreakers(teams, [], new Map(), 'group_standings');
		expect(sorted.map((t) => t.team)).toEqual(['France', 'Germany', 'Spain', 'Italy']);
		expect(warnings).toEqual([]);
	});

	it('falls to alphabetical with a warning when no H2H matches are provided', () => {
		// Three teams tied on overall stats, no H2H to consult → alphabetical + warning.
		const teams = [
			_ts('Wales', 'A', 3, 0, 1),
			_ts('Senegal', 'A', 3, 0, 1),
			_ts('Iran', 'A', 3, 0, 1)
		];
		const { sorted, warnings } = applyFifaTiebreakers(
			teams,
			[],
			new Map(),
			'third_place_qualifying'
		);
		expect(sorted.map((t) => t.team)).toEqual(['Iran', 'Senegal', 'Wales']);
		expect(warnings.length).toBe(1);
		expect(warnings[0].tiedTeams).toEqual(['Iran', 'Senegal', 'Wales']);
		expect(warnings[0].context).toBe('third_place_qualifying');
	});

	it('uses H2H to separate a 3-way tie cleanly (no warning)', () => {
		// A, B, C all tied on overall (5pts, GD 0, GF 2). H2H mini-table:
		// A beats B, A beats C, B beats C → A=6 H2H pts, B=3, C=0.
		const teams = [
			_ts('Argentina', 'A', 5, 0, 2),
			_ts('Brazil', 'A', 5, 0, 2),
			_ts('Chile', 'A', 5, 0, 2)
		];
		const fixtures: Fixture[] = [
			_fixture('m1', 'Argentina', 'Brazil'),
			_fixture('m2', 'Brazil', 'Chile'),
			_fixture('m3', 'Argentina', 'Chile')
		];
		const predictions = new Map([_pred('m1', 1, 0), _pred('m2', 1, 0), _pred('m3', 1, 0)]);
		const { sorted, warnings } = applyFifaTiebreakers(
			teams,
			fixtures,
			predictions,
			'group_standings'
		);
		expect(sorted.map((t) => t.team)).toEqual(['Argentina', 'Brazil', 'Chile']);
		expect(warnings).toEqual([]);
	});

	it('partially resolves a tie via H2H then alphabetical on the sub-tie', () => {
		// A beats both B and C, but B and C draw → H2H mini-table:
		//   A = 6pts, B = 1pt, C = 1pt → A clear first; B/C tied on H2H → alphabetical.
		const teams = [
			_ts('Argentina', 'A', 5, 0, 2),
			_ts('Brazil', 'A', 5, 0, 2),
			_ts('Chile', 'A', 5, 0, 2)
		];
		const fixtures: Fixture[] = [
			_fixture('m1', 'Argentina', 'Brazil'),
			_fixture('m2', 'Brazil', 'Chile'),
			_fixture('m3', 'Argentina', 'Chile')
		];
		const predictions = new Map([_pred('m1', 1, 0), _pred('m2', 0, 0), _pred('m3', 1, 0)]);
		const { sorted, warnings } = applyFifaTiebreakers(
			teams,
			fixtures,
			predictions,
			'group_standings'
		);
		expect(sorted[0].team).toBe('Argentina');
		expect(sorted.slice(1).map((t) => t.team)).toEqual(['Brazil', 'Chile']);
		expect(warnings.length).toBe(1);
		expect(warnings[0].tiedTeams).toEqual(['Brazil', 'Chile']);
	});

	it('respects goal difference before goals-for in the overall sort', () => {
		const teams = [
			_ts('TeamHighGd', 'A', 6, +5, 5),
			_ts('TeamLowGd', 'A', 6, +1, 5)
		];
		const { sorted } = applyFifaTiebreakers(teams, [], new Map(), 'group_standings');
		expect(sorted[0].team).toBe('TeamHighGd');
	});

	it('respects goals-for after points and GD tie', () => {
		const teams = [_ts('Lo', 'A', 6, +2, 3), _ts('Hi', 'A', 6, +2, 5)];
		const { sorted } = applyFifaTiebreakers(teams, [], new Map(), 'group_standings');
		expect(sorted[0].team).toBe('Hi');
	});
});

// ---------------------------------------------------------------------------
// calculateGroupStandings(WithWarnings) — end-to-end through fixtures + predictions
// ---------------------------------------------------------------------------

describe('calculateGroupStandings', () => {
	it('computes a clean 4-team group with no warnings', () => {
		// France beats all, Germany beats Spain & Italy, Spain beats Italy.
		const fixtures: Fixture[] = [
			_fixture('1', 'France', 'Germany'),
			_fixture('2', 'France', 'Spain'),
			_fixture('3', 'France', 'Italy'),
			_fixture('4', 'Germany', 'Spain'),
			_fixture('5', 'Germany', 'Italy'),
			_fixture('6', 'Spain', 'Italy')
		];
		const predictions = new Map([
			_pred('1', 2, 1),
			_pred('2', 3, 0),
			_pred('3', 1, 0),
			_pred('4', 2, 1),
			_pred('5', 2, 1),
			_pred('6', 1, 0)
		]);
		const { standings, warnings } = calculateGroupStandingsWithWarnings(fixtures, predictions, 'A');
		expect(standings.map((t) => t.team)).toEqual(['France', 'Germany', 'Spain', 'Italy']);
		expect(standings.map((t) => t.points)).toEqual([9, 6, 3, 0]);
		expect(warnings).toEqual([]);
	});

	it('returns an empty list with no warnings when no predictions are set', () => {
		const fixtures: Fixture[] = [_fixture('1', 'France', 'Germany')];
		const { standings, warnings } = calculateGroupStandingsWithWarnings(
			fixtures,
			new Map(),
			'A'
		);
		// Both teams appear with 0 played; sort is overall-stats tied so alphabetical
		// kicks in, producing one warning.
		expect(standings.length).toBe(2);
		expect(warnings.length).toBe(1);
		expect(warnings[0].tiedTeams).toEqual(['France', 'Germany']);
	});

	it('emits a warning when all teams draw 0-0 (overall + H2H all equal)', () => {
		const fixtures: Fixture[] = [
			_fixture('1', 'Argentina', 'Belgium'),
			_fixture('2', 'Argentina', 'Croatia'),
			_fixture('3', 'Argentina', 'Denmark'),
			_fixture('4', 'Belgium', 'Croatia'),
			_fixture('5', 'Belgium', 'Denmark'),
			_fixture('6', 'Croatia', 'Denmark')
		];
		const predictions = new Map([
			_pred('1', 0, 0),
			_pred('2', 0, 0),
			_pred('3', 0, 0),
			_pred('4', 0, 0),
			_pred('5', 0, 0),
			_pred('6', 0, 0)
		]);
		const { standings, warnings } = calculateGroupStandingsWithWarnings(fixtures, predictions, 'A');
		expect(standings.map((t) => t.team)).toEqual([
			'Argentina',
			'Belgium',
			'Croatia',
			'Denmark'
		]);
		expect(warnings.length).toBe(1);
		expect(warnings[0].tiedTeams).toEqual(['Argentina', 'Belgium', 'Croatia', 'Denmark']);
		expect(warnings[0].context).toBe('group_standings');
		expect(warnings[0].group).toBe('A');
	});

	it('emits a warning when two teams tie on overall + H2H (drew their H2H)', () => {
		// France & Germany both 2-0 vs Spain and Italy; H2H 1-1.
		const fixtures: Fixture[] = [
			_fixture('1', 'France', 'Germany'),
			_fixture('2', 'France', 'Spain'),
			_fixture('3', 'France', 'Italy'),
			_fixture('4', 'Germany', 'Spain'),
			_fixture('5', 'Germany', 'Italy'),
			_fixture('6', 'Spain', 'Italy')
		];
		const predictions = new Map([
			_pred('1', 1, 1), // France-Germany draw
			_pred('2', 2, 0),
			_pred('3', 1, 0),
			_pred('4', 2, 0),
			_pred('5', 1, 0),
			_pred('6', 1, 0)
		]);
		const { standings, warnings } = calculateGroupStandingsWithWarnings(fixtures, predictions, 'A');
		// France and Germany should occupy positions 1 and 2 (both 7 pts, GD +3, GF 4)
		expect(standings.slice(0, 2).map((t) => t.team).sort()).toEqual(['France', 'Germany']);
		const tieWarning = warnings.find((w) =>
			w.tiedTeams.includes('France') && w.tiedTeams.includes('Germany')
		);
		expect(tieWarning).toBeDefined();
		expect(tieWarning!.context).toBe('group_standings');
	});

	it('backwards-compat: calculateGroupStandings returns only the sorted list', () => {
		const fixtures: Fixture[] = [_fixture('1', 'France', 'Germany')];
		const predictions = new Map([_pred('1', 2, 1)]);
		const result = calculateGroupStandings(fixtures, predictions, 'A');
		expect(Array.isArray(result)).toBe(true);
		expect(result[0].team).toBe('France');
	});
});

// ---------------------------------------------------------------------------
// computeGroupStandingsMapWithWarnings
// ---------------------------------------------------------------------------

describe('computeGroupStandingsMapWithWarnings', () => {
	it('aggregates warnings from multiple groups', () => {
		const groupAFixtures: Fixture[] = [
			_fixture('a1', 'X', 'Y', 'A'),
			_fixture('a2', 'X', 'Z', 'A'),
			_fixture('a3', 'Y', 'Z', 'A')
		];
		const groupBFixtures: Fixture[] = [
			_fixture('b1', 'P', 'Q', 'B'),
			_fixture('b2', 'P', 'R', 'B'),
			_fixture('b3', 'Q', 'R', 'B')
		];
		const predictions = new Map([
			// Group A all 0-0 → 3-way warning
			_pred('a1', 0, 0),
			_pred('a2', 0, 0),
			_pred('a3', 0, 0),
			// Group B all 0-0 → 3-way warning
			_pred('b1', 0, 0),
			_pred('b2', 0, 0),
			_pred('b3', 0, 0)
		]);

		const { standingsMap, warnings } = computeGroupStandingsMapWithWarnings(
			[
				{ group: 'A', fixtures: groupAFixtures },
				{ group: 'B', fixtures: groupBFixtures }
			],
			predictions
		);
		expect(Object.keys(standingsMap).sort()).toEqual(['A', 'B']);
		const groupAWarnings = warnings.filter((w) => w.group === 'A');
		const groupBWarnings = warnings.filter((w) => w.group === 'B');
		expect(groupAWarnings.length).toBe(1);
		expect(groupBWarnings.length).toBe(1);
	});
});

// ---------------------------------------------------------------------------
// filterQualificationRelevantWarnings — drops ties that don't cross the
// qualification boundary, so the modal doesn't alarm users about ties that
// have no consequence (e.g. positions 1↔2 when top 8 advance).
// ---------------------------------------------------------------------------

describe('filterQualificationRelevantWarnings', () => {
	// 12-team standings, alphabetical A-L. Position index = team's char index
	// minus 'A'. Top 8 (A-H) qualify; bottom 4 (I-L) don't.
	const sorted12: TeamStanding[] = [
		'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L'
	].map((t) => _ts(t, 'X', 0, 0, 0));

	function warn(tiedTeams: string[]): TieWarning {
		return { group: 'multi', tiedTeams, context: 'third_place_qualifying' };
	}

	it('keeps a tie straddling the 8↔9 boundary (H + I)', () => {
		const w = warn(['H', 'I']);
		expect(filterQualificationRelevantWarnings([w], sorted12, 8)).toEqual([w]);
	});

	it('drops a tie entirely within qualifying positions (A + B)', () => {
		const w = warn(['A', 'B']);
		expect(filterQualificationRelevantWarnings([w], sorted12, 8)).toEqual([]);
	});

	it('drops a tie entirely within non-qualifying positions (I + J + K)', () => {
		const w = warn(['I', 'J', 'K']);
		expect(filterQualificationRelevantWarnings([w], sorted12, 8)).toEqual([]);
	});

	it('keeps a multi-team tie spanning the boundary (G H I J)', () => {
		const w = warn(['G', 'H', 'I', 'J']);
		expect(filterQualificationRelevantWarnings([w], sorted12, 8)).toEqual([w]);
	});

	it('drops a tie at the very top of qualifying (A B C)', () => {
		const w = warn(['A', 'B', 'C']);
		expect(filterQualificationRelevantWarnings([w], sorted12, 8)).toEqual([]);
	});

	it('drops a tie at the very bottom of non-qualifying (K + L)', () => {
		const w = warn(['K', 'L']);
		expect(filterQualificationRelevantWarnings([w], sorted12, 8)).toEqual([]);
	});

	it('preserves relevant warnings while dropping irrelevant ones in the same list', () => {
		const relevant = warn(['H', 'I']); // straddles
		const irrelevantTop = warn(['A', 'B']); // both qualify
		const irrelevantBottom = warn(['J', 'K']); // both out
		const result = filterQualificationRelevantWarnings(
			[irrelevantTop, relevant, irrelevantBottom],
			sorted12,
			8
		);
		expect(result).toEqual([relevant]);
	});

	it('returns an empty array when given no warnings', () => {
		expect(filterQualificationRelevantWarnings([], sorted12, 8)).toEqual([]);
	});

	it('drops a "tie" whose teams cannot be located in sorted (defensive)', () => {
		// "Phantom" is not in sorted12 at all; A is at position 0. After
		// filtering out -1, only one position remains → not a real tie.
		const w = warn(['A', 'Phantom']);
		expect(filterQualificationRelevantWarnings([w], sorted12, 8)).toEqual([]);
	});

	it('drops a tie whose teams are ALL phantom (zero located)', () => {
		const w = warn(['Phantom1', 'Phantom2']);
		expect(filterQualificationRelevantWarnings([w], sorted12, 8)).toEqual([]);
	});

	it('respects the qualifyingCount parameter (top-2 scheme)', () => {
		const sorted4: TeamStanding[] = ['A', 'B', 'C', 'D'].map((t) =>
			_ts(t, 'X', 0, 0, 0)
		);
		// qualifyingCount=2: B (pos 1) qualifies, C (pos 2) doesn't.
		const straddling = warn(['B', 'C']);
		expect(filterQualificationRelevantWarnings([straddling], sorted4, 2)).toEqual([
			straddling
		]);
		// Both C and D are non-qualifying with qualifyingCount=2.
		const bothOut = warn(['C', 'D']);
		expect(filterQualificationRelevantWarnings([bothOut], sorted4, 2)).toEqual([]);
		// Both A and B qualify with qualifyingCount=2.
		const bothIn = warn(['A', 'B']);
		expect(filterQualificationRelevantWarnings([bothIn], sorted4, 2)).toEqual([]);
	});

	it('keeps a tie at the exact boundary index (qualifyingCount-1 paired with qualifyingCount)', () => {
		// Position 7 is the last qualifier (index 7 < 8), position 8 is the
		// first non-qualifier (index 8 >= 8). This is the most consequential
		// tie possible — make sure it survives.
		const w = warn(['H', 'I']);
		const result = filterQualificationRelevantWarnings([w], sorted12, 8);
		expect(result).toHaveLength(1);
		expect(result[0].tiedTeams).toEqual(['H', 'I']);
	});
});
