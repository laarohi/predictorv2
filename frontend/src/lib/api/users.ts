/**
 * Users API functions — public profiles and prediction viewing.
 */

import { api } from './client';
import type { PublicProfile, UserPredictionsResponse } from '$types';
import type { AuditEvent } from './admin';

/** The caller's own prediction-change audit events (GET /users/me/history). */
export interface MyHistoryResponse {
	events: AuditEvent[];
}

export async function getMyHistory(): Promise<MyHistoryResponse> {
	return api.get<MyHistoryResponse>('/users/me/history');
}

export async function getUserProfile(userId: string): Promise<PublicProfile> {
	return api.get<PublicProfile>(`/users/${userId}/profile`);
}

export async function getUserPredictions(userId: string): Promise<UserPredictionsResponse> {
	return api.get<UserPredictionsResponse>(`/users/${userId}/predictions`);
}

// ---- Roster (Phase 1 pre-tournament dashboard) -----------------------------
export interface RosterEntry {
	user_id: string;
	name: string;
	match_predictions_filled: number;
	bracket_picks_filled: number;
	is_current_user: boolean;
	paid: boolean;
}

export interface RosterResponse {
	entries: RosterEntry[];
	total_active_users: number;
}

export async function getRoster(): Promise<RosterResponse> {
	return api.get<RosterResponse>('/users/roster');
}
