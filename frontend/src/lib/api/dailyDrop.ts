/**
 * Daily Drop API — the once-a-day broadcast banter card.
 */

import { api } from './client';
import type { DailyDrop } from '$types';

/** The most recent Drop, or null if none has been built yet. */
export async function getLatestDrop(): Promise<DailyDrop | null> {
	return api.get<DailyDrop | null>('/daily-drop/latest');
}
