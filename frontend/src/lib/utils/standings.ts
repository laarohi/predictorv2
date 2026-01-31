/**
 * Utility functions for calculating group standings and qualifying teams
 */

import type { Fixture, MatchPrediction } from '$types';

export interface TeamStanding {
	team: string;
	group: string;
	played: number;
	won: number;
	drawn: number;
	lost: number;
	goalsFor: number;
	goalsAgainst: number;
	goalDifference: number;
	points: number;
}

/**
 * Calculate standings for a single group based on predictions
 */
export function calculateGroupStandings(
	fixtures: Fixture[],
	predictions: Map<string, MatchPrediction>,
	group: string
): TeamStanding[] {
	// Get unique teams from fixtures
	const teams = new Set<string>();
	fixtures.forEach((f) => {
		if (f.home_team) teams.add(f.home_team);
		if (f.away_team) teams.add(f.away_team);
	});

	// Initialize standings
	const standings: Map<string, TeamStanding> = new Map();
	teams.forEach((team) => {
		standings.set(team, {
			team,
			group,
			played: 0,
			won: 0,
			drawn: 0,
			lost: 0,
			goalsFor: 0,
			goalsAgainst: 0,
			goalDifference: 0,
			points: 0
		});
	});

	// Calculate based on predictions
	fixtures.forEach((fixture) => {
		const prediction = predictions.get(fixture.id);
		if (!prediction) return;

		const homeTeam = standings.get(fixture.home_team);
		const awayTeam = standings.get(fixture.away_team);
		if (!homeTeam || !awayTeam) return;

		homeTeam.played++;
		awayTeam.played++;

		homeTeam.goalsFor += prediction.home_score;
		homeTeam.goalsAgainst += prediction.away_score;
		awayTeam.goalsFor += prediction.away_score;
		awayTeam.goalsAgainst += prediction.home_score;

		if (prediction.home_score > prediction.away_score) {
			homeTeam.won++;
			homeTeam.points += 3;
			awayTeam.lost++;
		} else if (prediction.home_score < prediction.away_score) {
			awayTeam.won++;
			awayTeam.points += 3;
			homeTeam.lost++;
		} else {
			homeTeam.drawn++;
			awayTeam.drawn++;
			homeTeam.points += 1;
			awayTeam.points += 1;
		}
	});

	// Calculate goal difference
	standings.forEach((s) => {
		s.goalDifference = s.goalsFor - s.goalsAgainst;
	});

	// Sort by points, then GD, then GF, then alphabetically for consistency
	return Array.from(standings.values()).sort((a, b) => {
		if (b.points !== a.points) return b.points - a.points;
		if (b.goalDifference !== a.goalDifference) return b.goalDifference - a.goalDifference;
		if (b.goalsFor !== a.goalsFor) return b.goalsFor - a.goalsFor;
		return a.team.localeCompare(b.team);
	});
}

export interface GroupFixtures {
	group: string;
	fixtures: Fixture[];
}

/**
 * Get all unique teams from group fixtures
 */
export function getAllTeamsFromGroups(groupFixtures: GroupFixtures[]): string[] {
	const teams = new Set<string>();
	for (const { fixtures } of groupFixtures) {
		for (const fixture of fixtures) {
			if (fixture.home_team) teams.add(fixture.home_team);
			if (fixture.away_team) teams.add(fixture.away_team);
		}
	}
	return Array.from(teams).sort();
}

/**
 * Compute group standings map for the bracket component
 * Returns a map of group letter -> array of team standings
 */
export function computeGroupStandingsMap(
	groupFixtures: GroupFixtures[],
	predictions: Map<string, MatchPrediction>
): Record<string, TeamStanding[]> {
	const standingsMap: Record<string, TeamStanding[]> = {};

	for (const { group, fixtures } of groupFixtures) {
		const standings = calculateGroupStandings(fixtures, predictions, group);
		standingsMap[group] = standings;
	}

	return standingsMap;
}
