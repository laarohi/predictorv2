/**
 * FIFA World Cup 2026 Knockout Stage Configuration
 *
 * This file encodes the official FIFA bracket structure for the 2026 World Cup.
 * Source: https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_knockout_stage
 *
 * Tournament structure:
 * - 48 teams in 12 groups (A-L), 4 teams per group
 * - Top 2 from each group (24 teams) + Best 8 third-place teams = 32 teams advance
 * - Round of 32 (16 matches) → Round of 16 (8 matches) → Quarter-Finals (4 matches)
 *   → Semi-Finals (2 matches) → Third Place + Final
 */

// Group position identifiers
export type GroupPosition = '1A' | '1B' | '1C' | '1D' | '1E' | '1F' | '1G' | '1H' | '1I' | '1J' | '1K' | '1L'
	| '2A' | '2B' | '2C' | '2D' | '2E' | '2F' | '2G' | '2H' | '2I' | '2J' | '2K' | '2L'
	| '3A' | '3B' | '3C' | '3D' | '3E' | '3F' | '3G' | '3H' | '3I' | '3J' | '3K' | '3L';

// Match source can be a group position or a previous match winner/loser
export type MatchSource =
	| { type: 'group'; position: GroupPosition }
	| { type: 'third_place'; possibleGroups: string[] }
	| { type: 'winner'; matchNumber: number }
	| { type: 'loser'; matchNumber: number };

export interface KnockoutMatch {
	matchNumber: number;
	round: 'round_of_32' | 'round_of_16' | 'quarter_finals' | 'semi_finals' | 'third_place' | 'final';
	homeSource: MatchSource;
	awaySource: MatchSource;
	// Which bracket half this match is in (for visualization)
	bracketHalf: 'top' | 'bottom';
	// Index within the round (0-based)
	roundIndex: number;
}

/**
 * Round of 32 matches (Matches 73-88)
 * These matches determine who plays in Round of 16
 */
export const ROUND_OF_32: KnockoutMatch[] = [
	// Top bracket
	{
		matchNumber: 73,
		round: 'round_of_32',
		homeSource: { type: 'group', position: '2A' },
		awaySource: { type: 'group', position: '2B' },
		bracketHalf: 'top',
		roundIndex: 0
	},
	{
		matchNumber: 74,
		round: 'round_of_32',
		homeSource: { type: 'group', position: '1E' },
		awaySource: { type: 'third_place', possibleGroups: ['A', 'B', 'C', 'D', 'F'] },
		bracketHalf: 'top',
		roundIndex: 1
	},
	{
		matchNumber: 75,
		round: 'round_of_32',
		homeSource: { type: 'group', position: '1F' },
		awaySource: { type: 'group', position: '2C' },
		bracketHalf: 'top',
		roundIndex: 2
	},
	{
		matchNumber: 76,
		round: 'round_of_32',
		homeSource: { type: 'group', position: '1C' },
		awaySource: { type: 'group', position: '2F' },
		bracketHalf: 'top',
		roundIndex: 3
	},
	{
		matchNumber: 77,
		round: 'round_of_32',
		homeSource: { type: 'group', position: '1I' },
		awaySource: { type: 'third_place', possibleGroups: ['C', 'D', 'F', 'G', 'H'] },
		bracketHalf: 'top',
		roundIndex: 4
	},
	{
		matchNumber: 78,
		round: 'round_of_32',
		homeSource: { type: 'group', position: '2E' },
		awaySource: { type: 'group', position: '2I' },
		bracketHalf: 'top',
		roundIndex: 5
	},
	{
		matchNumber: 79,
		round: 'round_of_32',
		homeSource: { type: 'group', position: '1A' },
		awaySource: { type: 'third_place', possibleGroups: ['C', 'E', 'F', 'H', 'I'] },
		bracketHalf: 'top',
		roundIndex: 6
	},
	{
		matchNumber: 80,
		round: 'round_of_32',
		homeSource: { type: 'group', position: '1L' },
		awaySource: { type: 'third_place', possibleGroups: ['E', 'H', 'I', 'J', 'K'] },
		bracketHalf: 'top',
		roundIndex: 7
	},
	// Bottom bracket
	{
		matchNumber: 81,
		round: 'round_of_32',
		homeSource: { type: 'group', position: '1D' },
		awaySource: { type: 'third_place', possibleGroups: ['B', 'E', 'F', 'I', 'J'] },
		bracketHalf: 'bottom',
		roundIndex: 8
	},
	{
		matchNumber: 82,
		round: 'round_of_32',
		homeSource: { type: 'group', position: '1G' },
		awaySource: { type: 'third_place', possibleGroups: ['A', 'E', 'H', 'I', 'J'] },
		bracketHalf: 'bottom',
		roundIndex: 9
	},
	{
		matchNumber: 83,
		round: 'round_of_32',
		homeSource: { type: 'group', position: '2K' },
		awaySource: { type: 'group', position: '2L' },
		bracketHalf: 'bottom',
		roundIndex: 10
	},
	{
		matchNumber: 84,
		round: 'round_of_32',
		homeSource: { type: 'group', position: '1H' },
		awaySource: { type: 'group', position: '2J' },
		bracketHalf: 'bottom',
		roundIndex: 11
	},
	{
		matchNumber: 85,
		round: 'round_of_32',
		homeSource: { type: 'group', position: '1B' },
		awaySource: { type: 'third_place', possibleGroups: ['E', 'F', 'G', 'I', 'J'] },
		bracketHalf: 'bottom',
		roundIndex: 12
	},
	{
		matchNumber: 86,
		round: 'round_of_32',
		homeSource: { type: 'group', position: '1J' },
		awaySource: { type: 'group', position: '2H' },
		bracketHalf: 'bottom',
		roundIndex: 13
	},
	{
		matchNumber: 87,
		round: 'round_of_32',
		homeSource: { type: 'group', position: '1K' },
		awaySource: { type: 'third_place', possibleGroups: ['D', 'E', 'I', 'J', 'L'] },
		bracketHalf: 'bottom',
		roundIndex: 14
	},
	{
		matchNumber: 88,
		round: 'round_of_32',
		homeSource: { type: 'group', position: '2D' },
		awaySource: { type: 'group', position: '2G' },
		bracketHalf: 'bottom',
		roundIndex: 15
	}
];

/**
 * Round of 16 matches (Matches 89-96)
 */
export const ROUND_OF_16: KnockoutMatch[] = [
	// Top bracket
	{
		matchNumber: 89,
		round: 'round_of_16',
		homeSource: { type: 'winner', matchNumber: 74 },
		awaySource: { type: 'winner', matchNumber: 77 },
		bracketHalf: 'top',
		roundIndex: 0
	},
	{
		matchNumber: 90,
		round: 'round_of_16',
		homeSource: { type: 'winner', matchNumber: 73 },
		awaySource: { type: 'winner', matchNumber: 75 },
		bracketHalf: 'top',
		roundIndex: 1
	},
	{
		matchNumber: 91,
		round: 'round_of_16',
		homeSource: { type: 'winner', matchNumber: 76 },
		awaySource: { type: 'winner', matchNumber: 78 },
		bracketHalf: 'top',
		roundIndex: 2
	},
	{
		matchNumber: 92,
		round: 'round_of_16',
		homeSource: { type: 'winner', matchNumber: 79 },
		awaySource: { type: 'winner', matchNumber: 80 },
		bracketHalf: 'top',
		roundIndex: 3
	},
	// Bottom bracket
	{
		matchNumber: 93,
		round: 'round_of_16',
		homeSource: { type: 'winner', matchNumber: 83 },
		awaySource: { type: 'winner', matchNumber: 84 },
		bracketHalf: 'bottom',
		roundIndex: 4
	},
	{
		matchNumber: 94,
		round: 'round_of_16',
		homeSource: { type: 'winner', matchNumber: 81 },
		awaySource: { type: 'winner', matchNumber: 82 },
		bracketHalf: 'bottom',
		roundIndex: 5
	},
	{
		matchNumber: 95,
		round: 'round_of_16',
		homeSource: { type: 'winner', matchNumber: 86 },
		awaySource: { type: 'winner', matchNumber: 88 },
		bracketHalf: 'bottom',
		roundIndex: 6
	},
	{
		matchNumber: 96,
		round: 'round_of_16',
		homeSource: { type: 'winner', matchNumber: 85 },
		awaySource: { type: 'winner', matchNumber: 87 },
		bracketHalf: 'bottom',
		roundIndex: 7
	}
];

/**
 * Quarter-Final matches (Matches 97-100)
 */
export const QUARTER_FINALS: KnockoutMatch[] = [
	// Top bracket
	{
		matchNumber: 97,
		round: 'quarter_finals',
		homeSource: { type: 'winner', matchNumber: 89 },
		awaySource: { type: 'winner', matchNumber: 90 },
		bracketHalf: 'top',
		roundIndex: 0
	},
	{
		matchNumber: 98,
		round: 'quarter_finals',
		homeSource: { type: 'winner', matchNumber: 93 },
		awaySource: { type: 'winner', matchNumber: 94 },
		bracketHalf: 'top',
		roundIndex: 1
	},
	// Bottom bracket
	{
		matchNumber: 99,
		round: 'quarter_finals',
		homeSource: { type: 'winner', matchNumber: 91 },
		awaySource: { type: 'winner', matchNumber: 92 },
		bracketHalf: 'bottom',
		roundIndex: 2
	},
	{
		matchNumber: 100,
		round: 'quarter_finals',
		homeSource: { type: 'winner', matchNumber: 95 },
		awaySource: { type: 'winner', matchNumber: 96 },
		bracketHalf: 'bottom',
		roundIndex: 3
	}
];

/**
 * Semi-Final matches (Matches 101-102)
 */
export const SEMI_FINALS: KnockoutMatch[] = [
	{
		matchNumber: 101,
		round: 'semi_finals',
		homeSource: { type: 'winner', matchNumber: 97 },
		awaySource: { type: 'winner', matchNumber: 98 },
		bracketHalf: 'top',
		roundIndex: 0
	},
	{
		matchNumber: 102,
		round: 'semi_finals',
		homeSource: { type: 'winner', matchNumber: 99 },
		awaySource: { type: 'winner', matchNumber: 100 },
		bracketHalf: 'bottom',
		roundIndex: 1
	}
];

/**
 * Third Place match (Match 103)
 */
export const THIRD_PLACE: KnockoutMatch = {
	matchNumber: 103,
	round: 'third_place',
	homeSource: { type: 'loser', matchNumber: 101 },
	awaySource: { type: 'loser', matchNumber: 102 },
	bracketHalf: 'top',
	roundIndex: 0
};

/**
 * Final match (Match 104)
 */
export const FINAL: KnockoutMatch = {
	matchNumber: 104,
	round: 'final',
	homeSource: { type: 'winner', matchNumber: 101 },
	awaySource: { type: 'winner', matchNumber: 102 },
	bracketHalf: 'top',
	roundIndex: 0
};

/**
 * All knockout matches combined
 */
export const ALL_KNOCKOUT_MATCHES: KnockoutMatch[] = [
	...ROUND_OF_32,
	...ROUND_OF_16,
	...QUARTER_FINALS,
	...SEMI_FINALS,
	THIRD_PLACE,
	FINAL
];

/**
 * Get a match by its official FIFA match number
 */
export function getMatchByNumber(matchNumber: number): KnockoutMatch | undefined {
	return ALL_KNOCKOUT_MATCHES.find(m => m.matchNumber === matchNumber);
}

/**
 * Get all matches for a specific round
 */
export function getMatchesForRound(round: KnockoutMatch['round']): KnockoutMatch[] {
	return ALL_KNOCKOUT_MATCHES.filter(m => m.round === round);
}

/**
 * Get the match that a winner advances to
 */
export function getNextMatch(matchNumber: number): KnockoutMatch | undefined {
	return ALL_KNOCKOUT_MATCHES.find(m => {
		return (
			(m.homeSource.type === 'winner' && m.homeSource.matchNumber === matchNumber) ||
			(m.awaySource.type === 'winner' && m.awaySource.matchNumber === matchNumber)
		);
	});
}

/**
 * Get which position (home/away) a match winner takes in the next round
 */
export function getNextMatchPosition(matchNumber: number): 'home' | 'away' | null {
	const nextMatch = getNextMatch(matchNumber);
	if (!nextMatch) return null;

	if (nextMatch.homeSource.type === 'winner' && nextMatch.homeSource.matchNumber === matchNumber) {
		return 'home';
	}
	if (nextMatch.awaySource.type === 'winner' && nextMatch.awaySource.matchNumber === matchNumber) {
		return 'away';
	}
	return null;
}

/**
 * Round display metadata
 */
export const ROUND_INFO = {
	round_of_32: { name: 'Round of 32', shortName: 'R32', matches: 16 },
	round_of_16: { name: 'Round of 16', shortName: 'R16', matches: 8 },
	quarter_finals: { name: 'Quarter-Finals', shortName: 'QF', matches: 4 },
	semi_finals: { name: 'Semi-Finals', shortName: 'SF', matches: 2 },
	third_place: { name: 'Third Place', shortName: '3rd', matches: 1 },
	final: { name: 'Final', shortName: 'F', matches: 1 }
} as const;

/**
 * Generate human-readable description for a match source
 */
export function describeMatchSource(source: MatchSource): string {
	switch (source.type) {
		case 'group':
			const pos = source.position;
			const place = pos[0] === '1' ? 'Winner' : pos[0] === '2' ? 'Runner-up' : '3rd Place';
			const group = pos.slice(1);
			return `${place} Group ${group}`;
		case 'third_place':
			return `Best 3rd (${source.possibleGroups.join('/')})`;
		case 'winner':
			return `Winner Match ${source.matchNumber}`;
		case 'loser':
			return `Loser Match ${source.matchNumber}`;
	}
}
