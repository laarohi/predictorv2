/**
 * Competition API functions.
 */

import { api } from './client';
import type { PhaseStatus } from '$types';

export async function getPhaseStatus(): Promise<PhaseStatus> {
	return api.get<PhaseStatus>('/competition/phase-status');
}
