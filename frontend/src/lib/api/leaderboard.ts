/**
 * Leaderboard API functions.
 */

import { api } from './client';
import type { LeaderboardResponse, PointBreakdown } from '$types';

export async function getLeaderboard(): Promise<LeaderboardResponse> {
	return api.get<LeaderboardResponse>('/leaderboard/');
}

export async function getUserBreakdown(userId: string): Promise<PointBreakdown> {
	return api.get<PointBreakdown>(`/leaderboard/breakdown/${userId}`);
}
