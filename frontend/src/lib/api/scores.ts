/**
 * Scores API functions.
 */

import { api } from './client';
import type { LiveScoreResponse, LivePollingResponse } from '$types';

export async function getLiveScores(): Promise<LiveScoreResponse> {
	return api.get<LiveScoreResponse>('/scores/live');
}

export async function pollLiveData(): Promise<LivePollingResponse> {
	return api.get<LivePollingResponse>('/scores/poll');
}
