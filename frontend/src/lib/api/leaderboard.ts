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

// ---- Rank trajectory + climbers (replaces stubRankTrajectory / stubSteepestClimb) -----

export interface RankSnapshotPoint {
	position: number;
	total_points: number;
	captured_date: string; // ISO date YYYY-MM-DD
}

export interface RankTrajectoryResponse {
	user_id: string;
	points: RankSnapshotPoint[];
	total_participants: number;
}

export interface SteepestClimberEntry {
	user_id: string;
	user_name: string;
	places: number;
	current_position: number;
	previous_position: number;
}

export interface SteepestClimbersResponse {
	days: number;
	entries: SteepestClimberEntry[];
}

export async function getMyRankTrajectory(days: number = 7): Promise<RankTrajectoryResponse> {
	return api.get<RankTrajectoryResponse>(`/leaderboard/snapshots/me?days=${days}`);
}

export async function getRankTrajectory(
	userId: string,
	days: number = 7
): Promise<RankTrajectoryResponse> {
	return api.get<RankTrajectoryResponse>(`/leaderboard/snapshots/${userId}?days=${days}`);
}

export async function getSteepestClimbers(
	days: number = 7,
	limit: number = 5
): Promise<SteepestClimbersResponse> {
	return api.get<SteepestClimbersResponse>(`/leaderboard/climbers?days=${days}&limit=${limit}`);
}
