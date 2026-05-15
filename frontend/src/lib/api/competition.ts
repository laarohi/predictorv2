/**
 * Competition API functions.
 */

import { api } from './client';
import type { PhaseStatus } from '$types';

export async function getPhaseStatus(): Promise<PhaseStatus> {
	return api.get<PhaseStatus>('/competition/phase-status');
}

/** Public competition metadata. Shape mirrors the backend's CompetitionInfo
 *  schema in backend/app/api/competition.py. */
export interface CompetitionInfo {
	name: string;
	entry_fee: number;
	is_phase2_active: boolean;
	phase1_deadline: string | null;
	phase2_bracket_deadline: string | null;
	total_players: number;
	paid_players: number;
}

/** Fetch public competition metadata (no auth required) — used by the /rules
 *  page to render the entry fee, player counts, and lock dates. */
export async function getCompetitionInfo(): Promise<CompetitionInfo> {
	return api.get<CompetitionInfo>('/competition/info');
}
