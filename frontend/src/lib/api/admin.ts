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
	/** Backend may omit this until the migration lands; treat undefined as false. */
	paid?: boolean;
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

/**
 * Toggle a user's paid status.
 *
 * The backend endpoint /admin/users/{id}/paid will exist once the worktree's
 * backend changes merge (User.paid field, migration, endpoint) and
 * `alembic upgrade head` runs against the prod-shape DB. Until then this
 * falls back to a per-browser localStorage flag so the UI is fully demoable.
 *
 * Once the backend is live the localStorage cache becomes harmless mirror.
 */
const PAID_LOCAL_PREFIX = 'predictor.paid.';

export function getPaidLocal(userId: string): boolean {
	if (typeof localStorage === 'undefined') return false;
	return localStorage.getItem(PAID_LOCAL_PREFIX + userId) === '1';
}

export async function toggleUserPaid(userId: string): Promise<boolean> {
	try {
		const view = await api.patch<UserAdminView>(`/admin/users/${userId}/paid`);
		const next = !!view.paid;
		if (typeof localStorage !== 'undefined') {
			localStorage.setItem(PAID_LOCAL_PREFIX + userId, next ? '1' : '0');
		}
		return next;
	} catch (_e) {
		// Backend doesn't have the endpoint yet — fall back to localStorage.
		const current = getPaidLocal(userId);
		const next = !current;
		if (typeof localStorage !== 'undefined') {
			localStorage.setItem(PAID_LOCAL_PREFIX + userId, next ? '1' : '0');
		}
		return next;
	}
}

export async function syncScores(): Promise<SyncScoresResponse> {
	return api.post<SyncScoresResponse>('/admin/scores/sync');
}
