/**
 * Fixtures API functions.
 */

import { api } from './client';
import type { Fixture, FixturesByGroup, LockStatus, ActualStandingsResponse } from '$types';

export async function getAllFixtures(): Promise<Fixture[]> {
	return api.get<Fixture[]>('/fixtures/');
}

export async function getGroupFixtures(): Promise<FixturesByGroup[]> {
	return api.get<FixturesByGroup[]>('/fixtures/groups');
}

export async function getKnockoutFixtures(): Promise<Fixture[]> {
	return api.get<Fixture[]>('/fixtures/knockout');
}

export async function getActualKnockoutFixtures(): Promise<Fixture[]> {
	return api.get<Fixture[]>('/fixtures/knockout/actual');
}

export async function getActualStandings(): Promise<ActualStandingsResponse> {
	return api.get<ActualStandingsResponse>('/fixtures/standings/actual');
}

/** Ordered FIFA Rankings for our tournament teams (index 0 = rank #1).
 *  Feeds Article 13 Step 3 in the predicted-standings tiebreaker chain so the
 *  frontend resolves deep ties identically to the backend. Empty when the
 *  rankings table is unsynced. */
export async function getFifaRankings(): Promise<string[]> {
	return (await api.get<{ rankings: string[] }>('/fixtures/fifa-rankings')).rankings;
}

export async function getFixture(fixtureId: string): Promise<Fixture> {
	return api.get<Fixture>(`/fixtures/${fixtureId}`);
}

export async function getLockStatus(fixtureId: string): Promise<LockStatus> {
	return api.get<LockStatus>(`/fixtures/${fixtureId}/lock-status`);
}
