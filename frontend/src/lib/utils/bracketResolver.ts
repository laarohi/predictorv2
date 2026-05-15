/**
 * Bracket Resolver Utility
 *
 * Resolves teams into their correct knockout bracket positions based on
 * group standings and the FIFA 2026 bracket configuration.
 */

import {
	ROUND_OF_32,
	ROUND_OF_16,
	QUARTER_FINALS,
	SEMI_FINALS,
	FINAL,
	THIRD_PLACE,
	type KnockoutMatch,
	type MatchSource,
	getMatchByNumber
} from '$lib/config/bracketConfig';
import type { BracketPrediction, ThirdPlaceMappingTable } from '$types';
import { applyFifaTiebreakers, type TeamStanding, type TieWarning } from './standings';
import thirdPlaceMappingJson from '$lib/config/thirdPlaceMapping.json';

// Type the imported JSON properly
const thirdPlaceMapping: ThirdPlaceMappingTable = thirdPlaceMappingJson;

/**
 * Group standings mapped by group letter
 */
export type GroupStandingsMap = Record<string, TeamStanding[]>;

/**
 * Result of a single match (for tracking bracket progression)
 */
export interface MatchResult {
	matchNumber: number;
	homeTeam: string | null;
	awayTeam: string | null;
	winner: string | null;
	loser: string | null;
}

/**
 * Complete bracket state with all match results
 */
export interface BracketState {
	// Group results (team name by position)
	groupPositions: Record<string, string>; // e.g., '1A' -> 'France', '2A' -> 'Germany'

	// Which third-place teams qualified (sorted by ranking)
	qualifyingThirdPlace: Array<{ group: string; team: string }>;

	// Match results by match number
	matchResults: Record<number, MatchResult>;
}

// Map of Match Number -> Group Winner Position (e.g., Match 74 features '1E')
// This is used to look up the correct opponent from the third-place mapping.
const MATCH_TO_WINNER_KEY: Record<number, string> = {
	74: '1E',
	77: '1I',
	79: '1A',
	80: '1L',
	81: '1D',
	82: '1G',
	85: '1B',
	87: '1K'
};

/**
 * Build group positions map from standings
 * Returns a map like { '1A': 'France', '2A': 'Germany', '3A': 'Spain', ... }
 */
export function buildGroupPositions(standings: GroupStandingsMap): Record<string, string> {
	const positions: Record<string, string> = {};

	for (const [group, groupStandings] of Object.entries(standings)) {
		if (groupStandings[0]) positions[`1${group}`] = groupStandings[0].team;
		if (groupStandings[1]) positions[`2${group}`] = groupStandings[1].team;
		if (groupStandings[2]) positions[`3${group}`] = groupStandings[2].team;
		if (groupStandings[3]) positions[`4${group}`] = groupStandings[3].team;
	}

	return positions;
}

/**
 * Determine which 8 third-place teams qualify.
 *
 * Uses FIFA's tiebreaker chain (up to head-to-head goals) via
 * `applyFifaTiebreakers`. Head-to-head isn't applicable here because the
 * third-placed teams come from different groups (they never played each
 * other), so any tie that survives points/GD/GF falls to alphabetical
 * with a TieWarning — see `getQualifyingThirdPlaceTeamsWithWarnings`.
 */
export function getQualifyingThirdPlaceTeams(
	standings: GroupStandingsMap
): Array<{ group: string; team: string; standing: TeamStanding }> {
	return getQualifyingThirdPlaceTeamsWithWarnings(standings).qualifying;
}

/**
 * Same as getQualifyingThirdPlaceTeams but also returns alphabetical-tie warnings.
 *
 * Warnings here are particularly load-bearing: a tie at the 8/9 boundary
 * affects who actually advances to R32, which the UI should prompt the user
 * to resolve by adjusting scores.
 */
export function getQualifyingThirdPlaceTeamsWithWarnings(
	standings: GroupStandingsMap
): {
	qualifying: Array<{ group: string; team: string; standing: TeamStanding }>;
	warnings: TieWarning[];
} {
	const thirdPlaceStandings: TeamStanding[] = [];
	for (const [group, groupStandings] of Object.entries(standings)) {
		if (groupStandings[2]) {
			// Ensure `group` is set even if the standing object originated elsewhere.
			thirdPlaceStandings.push({ ...groupStandings[2], group });
		}
	}

	const { sorted, warnings } = applyFifaTiebreakers(
		thirdPlaceStandings,
		[],
		new Map(),
		'third_place_qualifying'
	);

	const qualifying = sorted.slice(0, 8).map((s) => ({
		group: s.group,
		team: s.team,
		standing: s
	}));

	return { qualifying, warnings };
}

/**
 * Resolve the team for a match source
 */
export function resolveMatchSource(
	source: MatchSource,
	groupPositions: Record<string, string>,
	qualifyingThird: Array<{ group: string; team: string }>,
	matchResults: Record<number, MatchResult>,
	matchNumber?: number,
	groupKey?: string
): string | null {
	switch (source.type) {
		case 'group':
			return groupPositions[source.position] || null;

		case 'third_place':
			// Official FIFA Logic using the Grid
			if (!matchNumber || !groupKey) return null;

			const mapping = thirdPlaceMapping[groupKey];
			if (!mapping) return null; // Incomplete data or invalid key

			const winnerPos = MATCH_TO_WINNER_KEY[matchNumber];
			if (!winnerPos) return null;

			const targetSource = mapping[winnerPos]; // e.g., "3E"
			if (!targetSource) return null;

			const targetGroup = targetSource.slice(1); // "E"
			const teamObj = qualifyingThird.find(t => t.group === targetGroup);
			return teamObj ? teamObj.team : null;

		case 'winner':
			return matchResults[source.matchNumber]?.winner || null;

		case 'loser':
			return matchResults[source.matchNumber]?.loser || null;
	}
}

/**
 * Initialize bracket state from group standings
 * This sets up the R32 teams based on group positions
 */
export function initializeBracketState(standings: GroupStandingsMap): BracketState {
	const groupPositions = buildGroupPositions(standings);
	const qualifyingThirdRaw = getQualifyingThirdPlaceTeams(standings);
	const qualifyingThirdPlace = qualifyingThirdRaw.map(({ group, team }) => ({ group, team }));

	// Generate the key for the mapping table (e.g., "ABCDEFGH")
	const groupKey = qualifyingThirdPlace
		.map(t => t.group)
		.sort()
		.join('');

	const matchResults: Record<number, MatchResult> = {};

	// Initialize R32 matches with their teams
	for (const match of ROUND_OF_32) {
		const homeTeam = resolveMatchSource(
			match.homeSource,
			groupPositions,
			qualifyingThirdPlace,
			matchResults,
			match.matchNumber,
			groupKey
		);
		const awayTeam = resolveMatchSource(
			match.awaySource,
			groupPositions,
			qualifyingThirdPlace,
			matchResults,
			match.matchNumber,
			groupKey
		);

		matchResults[match.matchNumber] = {
			matchNumber: match.matchNumber,
			homeTeam,
			awayTeam,
			winner: null,
			loser: null
		};
	}

	// Initialize later round matches (teams TBD until winners selected)
	const laterMatches = [...ROUND_OF_16, ...QUARTER_FINALS, ...SEMI_FINALS, THIRD_PLACE, FINAL];
	for (const match of laterMatches) {
		matchResults[match.matchNumber] = {
			matchNumber: match.matchNumber,
			homeTeam: null,
			awayTeam: null,
			winner: null,
			loser: null
		};
	}

	return {
		groupPositions,
		qualifyingThirdPlace,
		matchResults
	};
}

/**
 * Set a match winner and propagate to the next round
 */
export function setMatchWinner(
	state: BracketState,
	matchNumber: number,
	winner: string
): BracketState {
	const match = state.matchResults[matchNumber];
	if (!match) return state;

	// Validate winner is one of the teams
	if (winner !== match.homeTeam && winner !== match.awayTeam) {
		// console.warn(`Invalid winner ${winner} for match ${matchNumber}`);
		return state;
	}

	// Create new state
	const newState: BracketState = {
		...state,
		matchResults: { ...state.matchResults }
	};

	// Set winner and loser
	const loser = winner === match.homeTeam ? match.awayTeam : match.homeTeam;
	newState.matchResults[matchNumber] = {
		...match,
		winner,
		loser
	};

	// Find and update the next match
	const allMatches = [...ROUND_OF_16, ...QUARTER_FINALS, ...SEMI_FINALS, THIRD_PLACE, FINAL];
	for (const nextMatch of allMatches) {
		let updated = false;
		const nextResult = { ...newState.matchResults[nextMatch.matchNumber] };

		// Check if this match's winner feeds into the next match
		if (nextMatch.homeSource.type === 'winner' && nextMatch.homeSource.matchNumber === matchNumber) {
			nextResult.homeTeam = winner;
			updated = true;
		}
		if (nextMatch.awaySource.type === 'winner' && nextMatch.awaySource.matchNumber === matchNumber) {
			nextResult.awayTeam = winner;
			updated = true;
		}

		// Check if this match's loser feeds into the next match (third place)
		if (nextMatch.homeSource.type === 'loser' && nextMatch.homeSource.matchNumber === matchNumber) {
			nextResult.homeTeam = loser;
			updated = true;
		}
		if (nextMatch.awaySource.type === 'loser' && nextMatch.awaySource.matchNumber === matchNumber) {
			nextResult.awayTeam = loser;
			updated = true;
		}

		if (updated) {
			// Clear winner/loser if teams changed
			if (nextResult.winner && nextResult.winner !== nextResult.homeTeam && nextResult.winner !== nextResult.awayTeam) {
				nextResult.winner = null;
				nextResult.loser = null;
			}
			newState.matchResults[nextMatch.matchNumber] = nextResult;
		}
	}

	return newState;
}

/**
 * Convert BracketState to BracketPrediction format for API compatibility
 */
export function bracketStateToPrediction(state: BracketState): BracketPrediction {
	const r32Teams: string[] = [];
	const r16Teams: string[] = [];
	const qfTeams: string[] = [];
	const sfTeams: string[] = [];
	const finalTeams: string[] = [];
	let winner = '';

	// R32: Extract teams in match order
	for (const match of ROUND_OF_32) {
		const result = state.matchResults[match.matchNumber];
		r32Teams.push(result?.homeTeam || '');
		r32Teams.push(result?.awayTeam || '');
	}

	// R16: Extract winners from R32
	for (const match of ROUND_OF_16) {
		const result = state.matchResults[match.matchNumber];
		if (result?.homeTeam) r16Teams.push(result.homeTeam);
		if (result?.awayTeam) r16Teams.push(result.awayTeam);
	}

	// QF: Extract winners from R16
	for (const match of QUARTER_FINALS) {
		const result = state.matchResults[match.matchNumber];
		if (result?.homeTeam) qfTeams.push(result.homeTeam);
		if (result?.awayTeam) qfTeams.push(result.awayTeam);
	}

	// SF: Extract winners from QF
	for (const match of SEMI_FINALS) {
		const result = state.matchResults[match.matchNumber];
		if (result?.homeTeam) sfTeams.push(result.homeTeam);
		if (result?.awayTeam) sfTeams.push(result.awayTeam);
	}

	// Final: Extract winners from SF
	const finalResult = state.matchResults[104];
	if (finalResult?.homeTeam) finalTeams.push(finalResult.homeTeam);
	if (finalResult?.awayTeam) finalTeams.push(finalResult.awayTeam);
	winner = finalResult?.winner || '';

	// Build group_winners from groupPositions
	const group_winners: Record<string, string[]> = {};
	const groups = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L'];
	for (const group of groups) {
		const first = state.groupPositions[`1${group}`];
		const second = state.groupPositions[`2${group}`];
		if (first || second) {
			group_winners[group] = [first || '', second || ''];
		}
	}

	return {
		group_winners,
		round_of_32: r32Teams,
		round_of_16: r16Teams,
		quarter_finals: qfTeams,
		semi_finals: sfTeams,
		final: finalTeams,
		winner
	};
}

/**
 * Convert BracketPrediction to BracketState for manipulation
 */
export function predictionToBracketState(
	prediction: BracketPrediction,
	standings: GroupStandingsMap
): BracketState {
	let state = initializeBracketState(standings);

	// R32 winners
	const r16Set = new Set(prediction.round_of_16?.filter(t => t) || []);
	for (const match of ROUND_OF_32) {
		const result = state.matchResults[match.matchNumber];
		if (result.homeTeam && r16Set.has(result.homeTeam)) {
			state = setMatchWinner(state, match.matchNumber, result.homeTeam);
		} else if (result.awayTeam && r16Set.has(result.awayTeam)) {
			state = setMatchWinner(state, match.matchNumber, result.awayTeam);
		}
	}

	// R16 winners
	const qfSet = new Set(prediction.quarter_finals?.filter(t => t) || []);
	for (const match of ROUND_OF_16) {
		const result = state.matchResults[match.matchNumber];
		if (result.homeTeam && qfSet.has(result.homeTeam)) {
			state = setMatchWinner(state, match.matchNumber, result.homeTeam);
		} else if (result.awayTeam && qfSet.has(result.awayTeam)) {
			state = setMatchWinner(state, match.matchNumber, result.awayTeam);
		}
	}

	// QF winners
	const sfSet = new Set(prediction.semi_finals?.filter(t => t) || []);
	for (const match of QUARTER_FINALS) {
		const result = state.matchResults[match.matchNumber];
		if (result.homeTeam && sfSet.has(result.homeTeam)) {
			state = setMatchWinner(state, match.matchNumber, result.homeTeam);
		} else if (result.awayTeam && sfSet.has(result.awayTeam)) {
			state = setMatchWinner(state, match.matchNumber, result.awayTeam);
		}
	}

	// SF winners
	const finalSet = new Set(prediction.final?.filter(t => t) || []);
	for (const match of SEMI_FINALS) {
		const result = state.matchResults[match.matchNumber];
		if (result.homeTeam && finalSet.has(result.homeTeam)) {
			state = setMatchWinner(state, match.matchNumber, result.homeTeam);
		} else if (result.awayTeam && finalSet.has(result.awayTeam)) {
			state = setMatchWinner(state, match.matchNumber, result.awayTeam);
		}
	}

	// Final winner
	if (prediction.winner) {
		const finalResult = state.matchResults[104];
		if (finalResult.homeTeam === prediction.winner || finalResult.awayTeam === prediction.winner) {
			state = setMatchWinner(state, 104, prediction.winner);
		}
	}

	return state;
}

// Cache for the visually sorted matches
let VISUAL_MATCH_CACHE: Record<string, KnockoutMatch[]> | null = null;

/**
 * Generate the visual order of matches by traversing the tree from Final down to R32
 */
function getVisualMatchSequence(): Record<string, KnockoutMatch[]> {
	if (VISUAL_MATCH_CACHE) return VISUAL_MATCH_CACHE;

	const levels: Record<string, KnockoutMatch[]> = {
		final: [FINAL],
		semi_finals: [],
		quarter_finals: [],
		round_of_16: [],
		round_of_32: []
	};

	// Helper to collect sources
	function collectSources(match: KnockoutMatch, nextRoundKey: string) {
		const sources: KnockoutMatch[] = [];
		
		// Home Source
		if (match.homeSource.type === 'winner') {
			const sourceMatch = getMatchByNumber(match.homeSource.matchNumber);
			if (sourceMatch) sources.push(sourceMatch);
		}
		
		// Away Source
		if (match.awaySource.type === 'winner') {
			const sourceMatch = getMatchByNumber(match.awaySource.matchNumber);
			if (sourceMatch) sources.push(sourceMatch);
		}
		
		if (sources.length > 0) {
			levels[nextRoundKey].push(...sources);
		}
	}

	// Traverse Top-Down
	// Final -> SF
	collectSources(FINAL, 'semi_finals');
	
	// SF -> QF
	levels.semi_finals.forEach(m => collectSources(m, 'quarter_finals'));
	
	// QF -> R16
	levels.quarter_finals.forEach(m => collectSources(m, 'round_of_16'));
	
	// R16 -> R32
	levels.round_of_16.forEach(m => collectSources(m, 'round_of_32'));

	// Add Third Place separately if needed
	levels.third_place = [THIRD_PLACE];

	VISUAL_MATCH_CACHE = levels;
	return levels;
}

/**
 * Get matches for display, enriched with team names, in correct visual order
 */
export function getDisplayMatches(
	state: BracketState,
	round: KnockoutMatch['round']
): Array<{
	match: KnockoutMatch;
	homeTeam: string | null;
	awayTeam: string | null;
	winner: string | null;
}> {
	const visualMap = getVisualMatchSequence();
	const matches = visualMap[round] || [];

	return matches.map((match) => {
		const result = state.matchResults[match.matchNumber];
		return {
			match,
			homeTeam: result?.homeTeam || null,
			awayTeam: result?.awayTeam || null,
			winner: result?.winner || null
		};
	});
}
