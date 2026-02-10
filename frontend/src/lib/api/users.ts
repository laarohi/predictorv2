/**
 * Users API functions — public profiles and prediction viewing.
 */

import { api } from './client';
import type { PublicProfile, UserPredictionsResponse } from '$types';

export async function getUserProfile(userId: string): Promise<PublicProfile> {
	return api.get<PublicProfile>(`/users/${userId}/profile`);
}

export async function getUserPredictions(userId: string): Promise<UserPredictionsResponse> {
	return api.get<UserPredictionsResponse>(`/users/${userId}/predictions`);
}
