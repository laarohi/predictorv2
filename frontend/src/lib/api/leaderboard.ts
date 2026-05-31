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

export async function getMyRankTrajectory(days: number = 7): Promise<RankTrajectoryResponse> {
	return api.get<RankTrajectoryResponse>(`/leaderboard/snapshots/me?days=${days}`);
}

// ---- Tournament winner pickers (post-competition) ---------------------------
export interface TournamentWinnerPickers {
	actual_winner: string | null;
	phase1_picker_count: number;
	phase2_picker_count: number;
	total_phase1_predictors: number;
	total_phase2_predictors: number;
}

export async function getTournamentWinnerPickers(): Promise<TournamentWinnerPickers> {
	return api.get<TournamentWinnerPickers>('/leaderboard/tournament-winner');
}

// ---- Personal highlights (post-competition retrospective) -------------------
export interface StreakHighlight {
	count: number;
	fixture_ids: string[];
}
export interface ClimbHighlight {
	places: number;
	captured_date: string;
	from_position: number;
	to_position: number;
}
export interface ContrarianHighlight {
	fixture_id: string;
	home_team: string;
	away_team: string;
	actual_score: string;
	user_pick: string;
	agrees_exact: number;
	total: number;
}
export interface PhaseHighlight {
	phase: 'phase_1' | 'phase_2';
	points: number;
}
export interface MyHighlights {
	best_exact_streak: StreakHighlight | null;
	biggest_climb: ClimbHighlight | null;
	most_contrarian_correct: ContrarianHighlight | null;
	best_phase: PhaseHighlight | null;
}

export async function getMyHighlights(): Promise<MyHighlights> {
	return api.get<MyHighlights>('/leaderboard/me/highlights');
}
