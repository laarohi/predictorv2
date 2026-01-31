/**
 * Predictions API functions.
 */

import { api } from './client';
import type {
	MatchPrediction,
	MatchPredictionCreate,
	MatchPredictionUpdate,
	BracketPrediction,
	TeamAdvancementPrediction
} from '$types';

export async function getMatchPredictions(): Promise<MatchPrediction[]> {
	return api.get<MatchPrediction[]>('/predictions/matches');
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
