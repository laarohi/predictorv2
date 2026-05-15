/**
 * Tests for bracketResolver — the FIFA 2026 knockout bracket logic.
 *
 * Covers buildGroupPositions, getQualifyingThirdPlaceTeams, resolveMatchSource,
 * initializeBracketState, setMatchWinner propagation, and BracketState↔Prediction
 * round-trip. Per CLAUDE.md the bracket logic is one of the two highest-stakes
 * pieces of business logic in the app — a silent bug here changes who plays whom
 * in R32 for the entire tournament.
 */

import { describe, it, expect } from 'vitest';
import {
	buildGroupPositions,
	getQualifyingThirdPlaceTeams,
	getQualifyingThirdPlaceTeamsWithWarnings,
	resolveMatchSource,
	initializeBracketState,
	setMatchWinner,
	bracketStateToPrediction,
	predictionToBracketState,
	type GroupStandingsMap
} from './bracketResolver';
import type { TeamStanding } from './standings';

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

/** Build a "standard" 12-group standings map where every group has a clean
 *  1st/2nd/3rd/4th ordering. Use this for tests that don't care about the
 *  internal stats. */
function _standardStandings(): GroupStandingsMap {
	const result: GroupStandingsMap = {};
	for (const g of 'ABCDEFGHIJKL') {
		result[g] = [
			_ts(`Top1${g}`, g, 9, 5, 7),
			_ts(`Top2${g}`, g, 6, 2, 4),
			_ts(`Third${g}`, g, 3, 0, 2),
			_ts(`Bot4${g}`, g, 0, -5, 0)
		];
	}
	return result;
}

// ---------------------------------------------------------------------------
// buildGroupPositions
// ---------------------------------------------------------------------------

describe('buildGroupPositions', () => {
	it('builds 1A..4L from full standings', () => {
		const positions = buildGroupPositions(_standardStandings());
		expect(positions['1A']).toBe('Top1A');
		expect(positions['2A']).toBe('Top2A');
		expect(positions['3A']).toBe('ThirdA');
		expect(positions['4A']).toBe('Bot4A');
		expect(positions['1L']).toBe('Top1L');
		expect(Object.keys(positions).length).toBe(48); // 4 positions × 12 groups
	});

	it('omits keys for missing positions in incomplete groups', () => {
		const standings: GroupStandingsMap = {
			A: [_ts('OnlyOne', 'A', 9, 5)]
		};
		const positions = buildGroupPositions(standings);
		expect(positions).toEqual({ '1A': 'OnlyOne' });
	});

	it('handles empty standings', () => {
		expect(buildGroupPositions({})).toEqual({});
	});
});

// ---------------------------------------------------------------------------
// getQualifyingThirdPlaceTeams
// ---------------------------------------------------------------------------

describe('getQualifyingThirdPlaceTeams', () => {
	it('returns top 8 sorted by points descending', () => {
		const standings: GroupStandingsMap = {};
		for (let i = 0; i < 12; i++) {
			const g = 'ABCDEFGHIJKL'[i];
			standings[g] = [
				_ts(`Top1${g}`, g, 9, 5),
				_ts(`Top2${g}`, g, 6, 2),
				_ts(`Third${g}`, g, i, 0), // points vary 0..11
				_ts(`Bot4${g}`, g, 0, -5)
			];
		}
		const top8 = getQualifyingThirdPlaceTeams(standings);
		expect(top8.length).toBe(8);
		// Highest points first: L(11), K(10), J(9), I(8), H(7), G(6), F(5), E(4)
		expect(top8.map((t) => t.group)).toEqual(['L', 'K', 'J', 'I', 'H', 'G', 'F', 'E']);
	});

	it('breaks ties by goal difference', () => {
		const standings: GroupStandingsMap = {
			A: [
				_ts('1A', 'A', 9, 5),
				_ts('2A', 'A', 6, 2),
				_ts('3A', 'A', 3, +1, 2),
				_ts('4A', 'A', 0, -5)
			],
			B: [
				_ts('1B', 'B', 9, 5),
				_ts('2B', 'B', 6, 2),
				_ts('3B', 'B', 3, +3, 2),
				_ts('4B', 'B', 0, -5)
			]
		};
		const top8 = getQualifyingThirdPlaceTeams(standings);
		// Same points, B has better GD → B first
		expect(top8[0].group).toBe('B');
		expect(top8[1].group).toBe('A');
	});

	it('breaks ties by goals-for when points and GD are equal', () => {
		const standings: GroupStandingsMap = {
			A: [
				_ts('1A', 'A', 9, 5),
				_ts('2A', 'A', 6, 2),
				_ts('3A', 'A', 3, +2, 3),
				_ts('4A', 'A', 0, -5)
			],
			B: [
				_ts('1B', 'B', 9, 5),
				_ts('2B', 'B', 6, 2),
				_ts('3B', 'B', 3, +2, 5),
				_ts('4B', 'B', 0, -5)
			]
		};
		const top8 = getQualifyingThirdPlaceTeams(standings);
		// Same points, same GD, B has higher GF → B first
		expect(top8[0].group).toBe('B');
		expect(top8[1].group).toBe('A');
	});

	it('breaks ties alphabetically by team name as the final fallback', () => {
		// Mirrors backend's behavior in standings.py — required so frontend
		// and backend agree on edge cases where all stats tie. H2H isn't
		// applicable here (cross-group), so the chain goes:
		// points → GD → GF → alphabetical (+ TieWarning).
		const standings: GroupStandingsMap = {
			Z: [
				_ts('1Z', 'Z', 9, 5),
				_ts('2Z', 'Z', 6, 2),
				_ts('Zebra', 'Z', 3, 0, 2),
				_ts('4Z', 'Z', 0, -5)
			],
			A: [
				_ts('1A', 'A', 9, 5),
				_ts('2A', 'A', 6, 2),
				_ts('Aardvark', 'A', 3, 0, 2),
				_ts('4A', 'A', 0, -5)
			]
		};
		const top8 = getQualifyingThirdPlaceTeams(standings);
		expect(top8.map((t) => t.team)).toEqual(['Aardvark', 'Zebra']);
	});

	it('returns a third_place_qualifying TieWarning when alphabetical fallback fires', () => {
		// Same 2-team tie as above, now also asserting the warning surface.
		const standings: GroupStandingsMap = {
			A: [
				_ts('1A', 'A', 9, 5),
				_ts('2A', 'A', 6, 2),
				_ts('Aardvark', 'A', 3, 0, 2),
				_ts('4A', 'A', 0, -5)
			],
			Z: [
				_ts('1Z', 'Z', 9, 5),
				_ts('2Z', 'Z', 6, 2),
				_ts('Zebra', 'Z', 3, 0, 2),
				_ts('4Z', 'Z', 0, -5)
			]
		};
		const { qualifying, warnings } = getQualifyingThirdPlaceTeamsWithWarnings(standings);
		expect(qualifying.map((t) => t.team)).toEqual(['Aardvark', 'Zebra']);
		expect(warnings.length).toBe(1);
		expect(warnings[0].context).toBe('third_place_qualifying');
		expect(warnings[0].tiedTeams).toEqual(['Aardvark', 'Zebra']);
	});

	it('returns no warnings when third-place ranking is clean', () => {
		const standings: GroupStandingsMap = {
			A: [
				_ts('1A', 'A', 9, 5),
				_ts('2A', 'A', 6, 2),
				_ts('ClearWinner', 'A', 6, +3, 5),
				_ts('4A', 'A', 0, -5)
			],
			B: [
				_ts('1B', 'B', 9, 5),
				_ts('2B', 'B', 6, 2),
				_ts('ClearSecond', 'B', 3, 0, 2),
				_ts('4B', 'B', 0, -5)
			]
		};
		const { qualifying, warnings } = getQualifyingThirdPlaceTeamsWithWarnings(standings);
		expect(qualifying.map((t) => t.team)).toEqual(['ClearWinner', 'ClearSecond']);
		expect(warnings).toEqual([]);
	});

	it('returns fewer than 8 when not enough groups have a 3rd-placed team', () => {
		const standings: GroupStandingsMap = {
			A: [_ts('1A', 'A', 9, 5), _ts('2A', 'A', 6, 2)], // no 3rd
			B: [
				_ts('1B', 'B', 9, 5),
				_ts('2B', 'B', 6, 2),
				_ts('3B', 'B', 3, 0),
				_ts('4B', 'B', 0, -5)
			]
		};
		const top8 = getQualifyingThirdPlaceTeams(standings);
		expect(top8.length).toBe(1);
		expect(top8[0].group).toBe('B');
	});
});

// ---------------------------------------------------------------------------
// resolveMatchSource
// ---------------------------------------------------------------------------

describe('resolveMatchSource', () => {
	const standings = _standardStandings();
	const positions = buildGroupPositions(standings);
	const top8 = getQualifyingThirdPlaceTeams(standings).map(({ group, team }) => ({ group, team }));

	it('group source returns team at the position', () => {
		const result = resolveMatchSource(
			{ type: 'group', position: '1A' },
			positions,
			top8,
			{}
		);
		expect(result).toBe('Top1A');
	});

	it('group source returns null for unknown position', () => {
		const result = resolveMatchSource(
			// eslint-disable-next-line @typescript-eslint/no-explicit-any
			{ type: 'group', position: '1Z' as any },
			positions,
			top8,
			{}
		);
		expect(result).toBeNull();
	});

	it('winner source returns winner of referenced match', () => {
		const matchResults = {
			74: { matchNumber: 74, homeTeam: 'X', awayTeam: 'Y', winner: 'X', loser: 'Y' }
		};
		const result = resolveMatchSource(
			{ type: 'winner', matchNumber: 74 },
			{},
			[],
			matchResults
		);
		expect(result).toBe('X');
	});

	it('winner source returns null when match has no winner yet', () => {
		const matchResults = {
			74: { matchNumber: 74, homeTeam: 'X', awayTeam: 'Y', winner: null, loser: null }
		};
		const result = resolveMatchSource(
			{ type: 'winner', matchNumber: 74 },
			{},
			[],
			matchResults
		);
		expect(result).toBeNull();
	});

	it('loser source returns loser of referenced match', () => {
		const matchResults = {
			101: { matchNumber: 101, homeTeam: 'X', awayTeam: 'Y', winner: 'X', loser: 'Y' }
		};
		const result = resolveMatchSource(
			{ type: 'loser', matchNumber: 101 },
			{},
			[],
			matchResults
		);
		expect(result).toBe('Y');
	});

	it('third_place source resolves via mapping table for matches 74/77/79/80/81/82/85/87', () => {
		// In the standard fixture every group has a 3rd-place team with 3pts/GD0/GF2.
		// The frontend sort has no final alphabetical tiebreaker, so the top-8 ordering
		// among these ties relies on Object.entries insertion order (groups inserted
		// alphabetically here → top 8 are A-H).
		const groupKey = top8
			.map((t) => t.group)
			.sort()
			.join('');

		const matchResults = {};
		// Each of these 8 R32 matches should resolve to a valid 3X team
		for (const matchNumber of [74, 77, 79, 80, 81, 82, 85, 87]) {
			const result = resolveMatchSource(
				{ type: 'third_place', possibleGroups: [] },
				positions,
				top8,
				matchResults,
				matchNumber,
				groupKey
			);
			expect(result, `match ${matchNumber}`).toMatch(/^Third[A-L]$/);
		}
	});

	it('third_place source returns null without matchNumber + groupKey', () => {
		const result = resolveMatchSource(
			{ type: 'third_place', possibleGroups: [] },
			positions,
			top8,
			{}
			// matchNumber and groupKey omitted
		);
		expect(result).toBeNull();
	});
});

// ---------------------------------------------------------------------------
// initializeBracketState
// ---------------------------------------------------------------------------

describe('initializeBracketState', () => {
	it('populates all 16 R32 matches with home + away teams', () => {
		const state = initializeBracketState(_standardStandings());
		// R32 match numbers are 73..88 inclusive
		for (let n = 73; n <= 88; n++) {
			expect(state.matchResults[n].homeTeam, `match ${n} home`).not.toBeNull();
			expect(state.matchResults[n].awayTeam, `match ${n} away`).not.toBeNull();
		}
	});

	it('leaves later rounds initialized but empty', () => {
		const state = initializeBracketState(_standardStandings());
		// R16=89-96, QF=97-100, SF=101-102, 3rd=103, Final=104
		for (const n of [89, 92, 96, 97, 100, 101, 102, 103, 104]) {
			expect(state.matchResults[n], `match ${n}`).toBeDefined();
			expect(state.matchResults[n].homeTeam, `match ${n} home`).toBeNull();
			expect(state.matchResults[n].awayTeam, `match ${n} away`).toBeNull();
			expect(state.matchResults[n].winner, `match ${n} winner`).toBeNull();
		}
	});

	it('produces exactly 8 qualifying third-place teams', () => {
		const state = initializeBracketState(_standardStandings());
		expect(state.qualifyingThirdPlace.length).toBe(8);
	});

	it('groupPositions contains 48 entries (1A..4L)', () => {
		const state = initializeBracketState(_standardStandings());
		expect(Object.keys(state.groupPositions).length).toBe(48);
	});
});

// ---------------------------------------------------------------------------
// setMatchWinner — winner/loser semantics + bracket progression
// ---------------------------------------------------------------------------

describe('setMatchWinner', () => {
	it('sets winner and loser on the target match', () => {
		const initial = initializeBracketState(_standardStandings());
		const home = initial.matchResults[73].homeTeam!;
		const away = initial.matchResults[73].awayTeam!;
		const next = setMatchWinner(initial, 73, home);
		expect(next.matchResults[73].winner).toBe(home);
		expect(next.matchResults[73].loser).toBe(away);
	});

	it('rejects a winner that is neither home nor away', () => {
		const state = initializeBracketState(_standardStandings());
		const orig = { ...state.matchResults[73] };
		const next = setMatchWinner(state, 73, 'NotARealTeam');
		expect(next.matchResults[73]).toEqual(orig);
	});

	it('propagates R32 winner to the home slot of R16 match 90', () => {
		// Per bracketConfig: R16 match 90 home = winner(73)
		let state = initializeBracketState(_standardStandings());
		const home73 = state.matchResults[73].homeTeam!;
		state = setMatchWinner(state, 73, home73);
		expect(state.matchResults[90].homeTeam).toBe(home73);
	});

	it('propagates R32 winner to the away slot when configured as away source', () => {
		// Per bracketConfig: R16 match 90 away = winner(75)
		let state = initializeBracketState(_standardStandings());
		const home75 = state.matchResults[75].homeTeam!;
		state = setMatchWinner(state, 75, home75);
		expect(state.matchResults[90].awayTeam).toBe(home75);
	});

	it('propagates SF losers to the third-place match', () => {
		// Match 103 (third place): home = loser(101), away = loser(102)
		let state = initializeBracketState(_standardStandings());
		state = {
			...state,
			matchResults: {
				...state.matchResults,
				101: { matchNumber: 101, homeTeam: 'Alpha', awayTeam: 'Beta', winner: null, loser: null },
				102: { matchNumber: 102, homeTeam: 'Gamma', awayTeam: 'Delta', winner: null, loser: null }
			}
		};
		state = setMatchWinner(state, 101, 'Alpha');
		expect(state.matchResults[103].homeTeam).toBe('Beta'); // loser of 101
		state = setMatchWinner(state, 102, 'Gamma');
		expect(state.matchResults[103].awayTeam).toBe('Delta'); // loser of 102
	});

	it('clears the downstream winner when reselection invalidates it', () => {
		let state = initializeBracketState(_standardStandings());
		const home73 = state.matchResults[73].homeTeam!;
		const away73 = state.matchResults[73].awayTeam!;
		const home75 = state.matchResults[75].homeTeam!;

		// Pick winners for both R32 feeders into match 90
		state = setMatchWinner(state, 73, home73);
		state = setMatchWinner(state, 75, home75);

		// Verify the R16 match 90 picked up our two winners
		expect(state.matchResults[90].homeTeam).toBe(home73);
		expect(state.matchResults[90].awayTeam).toBe(home75);

		// Pick a R16 winner so there's something downstream to invalidate
		state = setMatchWinner(state, 90, home73);
		expect(state.matchResults[90].winner).toBe(home73);

		// Now change the R32 match 73 result → home73 is no longer in match 90
		state = setMatchWinner(state, 73, away73);
		expect(state.matchResults[90].homeTeam).toBe(away73);
		expect(state.matchResults[90].winner).toBeNull(); // cleared
		expect(state.matchResults[90].loser).toBeNull();
	});
});

// ---------------------------------------------------------------------------
// bracketStateToPrediction ↔ predictionToBracketState round-trip
// ---------------------------------------------------------------------------

describe('BracketState ↔ BracketPrediction round-trip', () => {
	it('preserves the initial R32 lineup through a roundtrip', () => {
		const initial = initializeBracketState(_standardStandings());
		const prediction = bracketStateToPrediction(initial);
		const restored = predictionToBracketState(prediction, _standardStandings());

		for (let n = 73; n <= 88; n++) {
			expect(restored.matchResults[n].homeTeam, `R32 m${n} home`).toBe(
				initial.matchResults[n].homeTeam
			);
			expect(restored.matchResults[n].awayTeam, `R32 m${n} away`).toBe(
				initial.matchResults[n].awayTeam
			);
		}
	});

	it('serializes group_winners as 1st + 2nd from each group', () => {
		const initial = initializeBracketState(_standardStandings());
		const prediction = bracketStateToPrediction(initial);
		expect(prediction.group_winners['A']).toEqual(['Top1A', 'Top2A']);
		expect(prediction.group_winners['L']).toEqual(['Top1L', 'Top2L']);
		expect(Object.keys(prediction.group_winners).length).toBe(12);
	});

	it('preserves R32 winners through a roundtrip', () => {
		let state = initializeBracketState(_standardStandings());
		// Pick winners for 4 R32 matches with a mix of home/away picks
		state = setMatchWinner(state, 73, state.matchResults[73].homeTeam!);
		state = setMatchWinner(state, 74, state.matchResults[74].awayTeam!);
		state = setMatchWinner(state, 75, state.matchResults[75].homeTeam!);
		state = setMatchWinner(state, 76, state.matchResults[76].awayTeam!);

		const prediction = bracketStateToPrediction(state);
		const restored = predictionToBracketState(prediction, _standardStandings());

		expect(restored.matchResults[73].winner).toBe(state.matchResults[73].winner);
		expect(restored.matchResults[74].winner).toBe(state.matchResults[74].winner);
		expect(restored.matchResults[75].winner).toBe(state.matchResults[75].winner);
		expect(restored.matchResults[76].winner).toBe(state.matchResults[76].winner);
	});

	it('preserves a tournament winner through a roundtrip', () => {
		let state = initializeBracketState(_standardStandings());
		// Inject Final teams without going through all R32→R16→QF→SF picks
		state = {
			...state,
			matchResults: {
				...state.matchResults,
				104: {
					matchNumber: 104,
					homeTeam: 'Champion',
					awayTeam: 'Runner-up',
					winner: null,
					loser: null
				}
			}
		};
		state = setMatchWinner(state, 104, 'Champion');
		const prediction = bracketStateToPrediction(state);
		expect(prediction.winner).toBe('Champion');
	});
});
