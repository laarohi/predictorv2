/**
 * Fixtures store for tournament matches.
 */

import { writable, derived } from 'svelte/store';
import * as fixturesApi from '$api/fixtures';
import type { Fixture, FixturesByGroup, ActualStandingsResponse, TeamStanding } from '$types';

// Stores
export const fixtures = writable<Fixture[]>([]);
export const groupFixtures = writable<FixturesByGroup[]>([]);
export const knockoutFixtures = writable<Fixture[]>([]);
export const fixturesLoading = writable<boolean>(false);
export const fixturesError = writable<string | null>(null);

// Phase 2 actual data stores
export const actualKnockoutFixtures = writable<Fixture[]>([]);
export const actualStandings = writable<ActualStandingsResponse | null>(null);
export const actualStandingsLoading = writable<boolean>(false);
export const actualStandingsError = writable<string | null>(null);

// Derived stores
export const fixtureById = derived(fixtures, ($fixtures) => {
	const map = new Map<string, Fixture>();
	for (const fixture of $fixtures) {
		map.set(fixture.id, fixture);
	}
	return map;
});

export const liveFixtures = derived(fixtures, ($fixtures) =>
	$fixtures.filter((f) => f.status === 'live' || f.status === 'halftime')
);

export const upcomingFixtures = derived(fixtures, ($fixtures) =>
	$fixtures.filter((f) => f.status === 'scheduled').slice(0, 10)
);

export const finishedFixtures = derived(fixtures, ($fixtures) =>
	$fixtures.filter((f) => f.status === 'finished')
);

// Actions
export async function fetchAllFixtures(): Promise<void> {
	fixturesLoading.set(true);
	fixturesError.set(null);

	try {
		const data = await fixturesApi.getAllFixtures();
		fixtures.set(data);
	} catch (e) {
		fixturesError.set(e instanceof Error ? e.message : 'Failed to load fixtures');
	} finally {
		fixturesLoading.set(false);
	}
}

export async function fetchGroupFixtures(): Promise<void> {
	fixturesLoading.set(true);
	fixturesError.set(null);

	try {
		const data = await fixturesApi.getGroupFixtures();
		groupFixtures.set(data);
	} catch (e) {
		fixturesError.set(e instanceof Error ? e.message : 'Failed to load group fixtures');
	} finally {
		fixturesLoading.set(false);
	}
}

export async function fetchKnockoutFixtures(): Promise<void> {
	fixturesLoading.set(true);
	fixturesError.set(null);

	try {
		const data = await fixturesApi.getKnockoutFixtures();
		knockoutFixtures.set(data);
	} catch (e) {
		fixturesError.set(e instanceof Error ? e.message : 'Failed to load knockout fixtures');
	} finally {
		fixturesLoading.set(false);
	}
}

export async function fetchActualKnockoutFixtures(): Promise<void> {
	fixturesLoading.set(true);
	fixturesError.set(null);

	try {
		const data = await fixturesApi.getActualKnockoutFixtures();
		actualKnockoutFixtures.set(data);
	} catch (e) {
		// Silently fail if Phase 2 not active (403)
		if (e instanceof Error && !e.message.includes('Phase 2')) {
			fixturesError.set(e.message);
		}
	} finally {
		fixturesLoading.set(false);
	}
}

export async function fetchActualStandings(): Promise<void> {
	actualStandingsLoading.set(true);
	actualStandingsError.set(null);

	try {
		const data = await fixturesApi.getActualStandings();
		actualStandings.set(data);
	} catch (e) {
		// Silently fail if Phase 2 not active (403)
		if (e instanceof Error && !e.message.includes('Phase 2')) {
			actualStandingsError.set(e.message);
		}
	} finally {
		actualStandingsLoading.set(false);
	}
}

// Derived store: Convert actual standings to GroupStandingsMap format for bracket component
// This converts from backend format (goals_for) to frontend format (goalsFor)
export const actualGroupStandingsMap = derived(actualStandings, ($actualStandings) => {
	if (!$actualStandings) return {};

	const result: Record<string, Array<{
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
	}>> = {};

	for (const [group, standings] of Object.entries($actualStandings.standings)) {
		result[group] = standings.map((s) => ({
			team: s.team,
			group: s.group,
			played: s.played,
			won: s.won,
			drawn: s.drawn,
			lost: s.lost,
			goalsFor: s.goals_for,
			goalsAgainst: s.goals_against,
			goalDifference: s.goal_difference,
			points: s.points
		}));
	}

	return result;
});

// Utility functions
export function formatKickoff(kickoff: string): string {
	const date = new Date(kickoff);
	return date.toLocaleString('en-GB', {
		weekday: 'short',
		day: 'numeric',
		month: 'short',
		hour: '2-digit',
		minute: '2-digit'
	});
}

export function getTimeUntilKickoff(kickoff: string): string {
	const now = new Date();
	const kickoffDate = new Date(kickoff);
	const diff = kickoffDate.getTime() - now.getTime();

	if (diff <= 0) return 'Started';

	const days = Math.floor(diff / (1000 * 60 * 60 * 24));
	const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
	const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));

	if (days > 0) return `${days}d ${hours}h`;
	if (hours > 0) return `${hours}h ${minutes}m`;
	return `${minutes}m`;
}
