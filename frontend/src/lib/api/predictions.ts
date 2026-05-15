/**
 * Predictions API functions.
 */

import { api } from './client';
import type {
	MatchPrediction,
	MatchPredictionCreate,
	MatchPredictionUpdate,
	BracketPrediction,
	TeamAdvancementPrediction,
	CommunityPredictionsResponse
} from '$types';

export async function getMatchPredictions(): Promise<MatchPrediction[]> {
	return api.get<MatchPrediction[]>('/predictions/matches');
}

// ---- Social signals (replaces stubSocialSignal / building block for stubHotPick) ----

export interface FixtureAgreement {
	fixture_id: string;
	agrees_exact: number;
	agrees_outcome: number;
	total: number;
}

export async function getAgreements(fixtureIds?: string[]): Promise<FixtureAgreement[]> {
	const params = new URLSearchParams();
	if (fixtureIds && fixtureIds.length > 0) {
		for (const id of fixtureIds) params.append('fixture_ids', id);
	}
	const qs = params.toString();
	const url = qs ? `/predictions/agreements?${qs}` : '/predictions/agreements';
	return api.get<FixtureAgreement[]>(url);
}

// ---- Bracket exposure (replaces stubBracketExposure) ----

export interface BracketExposureResponse {
	points_available: number;
	picks_locked: number;
	picks_total: number;
	/** Team name (not code) of the user's predicted tournament winner; null if not picked yet. */
	final_winner: string | null;
	/** The other finalist; null if not predicted or only the winner is set. */
	final_opponent: string | null;
}

export async function getBracketExposure(
	phase: 'phase_1' | 'phase_2' = 'phase_1'
): Promise<BracketExposureResponse> {
	return api.get<BracketExposureResponse>(`/predictions/bracket-exposure?phase=${phase}`);
}

export async function updateMatchPrediction(
	fixtureId: string,
	data: MatchPredictionUpdate
): Promise<MatchPrediction> {
	return api.put<MatchPrediction>(`/predictions/matches/${fixtureId}`, data);
}

export async function batchUpdatePredictions(
	predictions: MatchPredictionCreate[]
): Promise<MatchPrediction[]> {
	return api.post<MatchPrediction[]>('/predictions/matches/batch', predictions);
}

export async function getBracketPredictions(phase?: 'phase_1' | 'phase_2'): Promise<BracketPrediction | null> {
	const url = phase ? `/predictions/bracket?phase=${phase}` : '/predictions/bracket';
	return api.get<BracketPrediction | null>(url);
}

export async function updateBracketPredictions(
	predictions: TeamAdvancementPrediction[]
): Promise<{ status: string }> {
	return api.put<{ status: string }>('/predictions/bracket', { predictions });
}

export async function getCommunityPredictions(
	fixtureId: string
): Promise<CommunityPredictionsResponse> {
	return api.get<CommunityPredictionsResponse>(`/predictions/matches/${fixtureId}/community`);
}
