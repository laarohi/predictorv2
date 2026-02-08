/**
 * Leaderboard API functions.
 */

import { api } from './client';
import type { LeaderboardResponse, PointBreakdown } from '$types';

export type PhaseFilter = 'phase_1' | 'phase_2' | null;

export async function getLeaderboard(phase?: PhaseFilter): Promise<LeaderboardResponse> {
	const params = new URLSearchParams();
	if (phase) {
		params.set('phase', phase);
	}
	const queryString = params.toString();
	const url = queryString ? `/leaderboard/?${queryString}` : '/leaderboard/';
	return api.get<LeaderboardResponse>(url);
}

export async function getUserBreakdown(userId: string): Promise<PointBreakdown> {
	return api.get<PointBreakdown>(`/leaderboard/breakdown/${userId}`);
}
