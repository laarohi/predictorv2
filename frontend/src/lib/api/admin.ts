/**
 * Admin API functions.
 */

import { api } from './client';

export interface AdminStats {
	total_users: number;
	active_users: number;
	total_fixtures: number;
	completed_fixtures: number;
	live_fixtures: number;
	total_predictions: number;
	total_scores: number;
}

export interface CompetitionAdminView {
	id: string;
	name: string;
	entry_fee: number;
	phase1_deadline: string | null;
	is_phase2_active: boolean;
	phase2_activated_at: string | null;
	phase2_bracket_deadline: string | null;
	phase2_deadline: string | null;
	is_active: boolean;
	fixture_count: number;
	user_count: number;
}

export interface UserAdminView {
	id: string;
	email: string;
	name: string;
	auth_provider: string;
	is_admin: boolean;
	is_active: boolean;
	created_at: string;
	prediction_count: number;
}

export interface SyncScoresResponse {
	synced: number;
	updated: number;
	errors: string[];
}

export async function getAdminStats(): Promise<AdminStats> {
	return api.get<AdminStats>('/admin/stats');
}

export async function getCompetitions(): Promise<CompetitionAdminView[]> {
	return api.get<CompetitionAdminView[]>('/admin/competitions');
}

export async function setPhase1Deadline(deadline: string): Promise<{ status: string; deadline: string }> {
	return api.post('/admin/competition/phase1/deadline', { deadline });
}

export async function activatePhase2(bracketDeadline: string): Promise<{ status: string; bracket_deadline: string; activated_at: string }> {
	return api.post('/admin/competition/phase2/activate', { bracket_deadline: bracketDeadline });
}

export async function deactivatePhase2(): Promise<{ status: string }> {
	return api.post('/admin/competition/phase2/deactivate');
}

export async function getAllUsers(): Promise<UserAdminView[]> {
	return api.get<UserAdminView[]>('/admin/users');
}

export async function toggleUserAdmin(userId: string): Promise<UserAdminView> {
	return api.patch<UserAdminView>(`/admin/users/${userId}/admin`);
}

export async function toggleUserActive(userId: string): Promise<UserAdminView> {
	return api.patch<UserAdminView>(`/admin/users/${userId}/active`);
}

export async function syncScores(): Promise<SyncScoresResponse> {
	return api.post<SyncScoresResponse>('/admin/scores/sync');
}
