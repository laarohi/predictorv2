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

export async function getFixture(fixtureId: string): Promise<Fixture> {
	return api.get<Fixture>(`/fixtures/${fixtureId}`);
}

export async function getLockStatus(fixtureId: string): Promise<LockStatus> {
	return api.get<LockStatus>(`/fixtures/${fixtureId}/lock-status`);
}
