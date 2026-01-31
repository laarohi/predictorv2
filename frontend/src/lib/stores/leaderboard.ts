/**
 * Leaderboard store for standings and points.
 */

import { writable, derived, get } from 'svelte/store';
import * as leaderboardApi from '$api/leaderboard';
import { user } from './auth';
import type { LeaderboardEntry, LeaderboardResponse, PointBreakdown } from '$types';

// Stores
export const leaderboard = writable<LeaderboardEntry[]>([]);
export const lastCalculated = writable<string | null>(null);
export const totalParticipants = writable<number>(0);
export const leaderboardLoading = writable<boolean>(false);
export const leaderboardError = writable<string | null>(null);

// Polling state
let pollInterval: ReturnType<typeof setInterval> | null = null;

// Derived stores
export const currentUserPosition = derived([leaderboard, user], ([$leaderboard, $user]) => {
	if (!$user) return null;
	return $leaderboard.find((entry) => entry.user_id === $user.id) ?? null;
});

export const topThree = derived(leaderboard, ($leaderboard) => $leaderboard.slice(0, 3));

// Actions
export async function fetchLeaderboard(): Promise<void> {
	leaderboardLoading.set(true);
	leaderboardError.set(null);

	try {
		const data: LeaderboardResponse = await leaderboardApi.getLeaderboard();
		leaderboard.set(data.entries);
		lastCalculated.set(data.last_calculated);
		totalParticipants.set(data.total_participants);
	} catch (e) {
		leaderboardError.set(e instanceof Error ? e.message : 'Failed to load leaderboard');
	} finally {
		leaderboardLoading.set(false);
	}
}

export async function fetchUserBreakdown(userId: string): Promise<PointBreakdown | null> {
	try {
		return await leaderboardApi.getUserBreakdown(userId);
	} catch (e) {
		return null;
	}
}

// Polling for live updates
export function startPolling(intervalMs: number = 60000): void {
	if (pollInterval) return;

	fetchLeaderboard();
	pollInterval = setInterval(fetchLeaderboard, intervalMs);
}

export function stopPolling(): void {
	if (pollInterval) {
		clearInterval(pollInterval);
		pollInterval = null;
	}
}

// Utility functions
export function getMovementIndicator(movement: number): { icon: string; class: string } {
	if (movement > 0) {
		return { icon: '▲', class: 'text-success' };
	} else if (movement < 0) {
		return { icon: '▼', class: 'text-error' };
	}
	return { icon: '–', class: 'text-base-content/50' };
}

export function formatPoints(points: number): string {
	return points.toLocaleString();
}
