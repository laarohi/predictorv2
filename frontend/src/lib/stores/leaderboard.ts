/**
 * Leaderboard store for standings and points.
 * Supports filtering by phase (overall, phase_1, phase_2).
 */

import { writable, derived, get } from 'svelte/store';
import * as leaderboardApi from '$api/leaderboard';
import type { PhaseFilter } from '$api/leaderboard';
import * as scoresApi from '$api/scores';
import { user } from './auth';
import type { LeaderboardEntry, LeaderboardResponse, PointBreakdown, LiveMatchScore } from '$types';

// Phase filter type
export type LeaderboardPhase = 'overall' | 'phase_1' | 'phase_2';

// Stores
export const leaderboard = writable<LeaderboardEntry[]>([]);
export const lastCalculated = writable<string | null>(null);
export const totalParticipants = writable<number>(0);
export const leaderboardLoading = writable<boolean>(false);
export const leaderboardError = writable<string | null>(null);
export const leaderboardPhase = writable<LeaderboardPhase>('overall');

// Live scores store
export const liveMatches = writable<LiveMatchScore[]>([]);

// Polling state
let pollInterval: ReturnType<typeof setInterval> | null = null;
let pollMs = 60000;
let visibilityHandler: (() => void) | null = null;

function startInterval(): void {
	if (pollInterval) return;
	pollLiveData();
	pollInterval = setInterval(pollLiveData, pollMs);
}

function clearIntervalOnly(): void {
	if (pollInterval) {
		clearInterval(pollInterval);
		pollInterval = null;
	}
}

// Derived stores
export const currentUserPosition = derived([leaderboard, user], ([$leaderboard, $user]) => {
	if (!$user) return null;
	return $leaderboard.find((entry) => entry.user_id === $user.id) ?? null;
});

export const topThree = derived(leaderboard, ($leaderboard) => $leaderboard.slice(0, 3));

// Convert LeaderboardPhase to API PhaseFilter
function toApiPhase(phase: LeaderboardPhase): PhaseFilter {
	if (phase === 'overall') return null;
	return phase;
}

// Actions
export async function fetchLeaderboard(phase?: LeaderboardPhase): Promise<void> {
	leaderboardLoading.set(true);
	leaderboardError.set(null);

	// Use provided phase or current phase from store
	const effectivePhase = phase ?? 'overall';
	leaderboardPhase.set(effectivePhase);

	try {
		const data: LeaderboardResponse = await leaderboardApi.getLeaderboard(
			toApiPhase(effectivePhase)
		);
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

// Switch phase and refetch
export async function setPhase(phase: LeaderboardPhase): Promise<void> {
	await fetchLeaderboard(phase);
}

// Polling for live updates (always fetches overall for live data)
export function startPolling(intervalMs: number = 60000): void {
	pollMs = intervalMs;
	startInterval();
	// Pause polling while the tab is hidden (no point hammering the API on a
	// backgrounded tab); resume + refresh immediately when it becomes visible.
	if (typeof document !== 'undefined' && !visibilityHandler) {
		visibilityHandler = () => {
			if (document.hidden) clearIntervalOnly();
			else startInterval();
		};
		document.addEventListener('visibilitychange', visibilityHandler);
	}
}

export function stopPolling(): void {
	clearIntervalOnly();
	if (visibilityHandler && typeof document !== 'undefined') {
		document.removeEventListener('visibilitychange', visibilityHandler);
		visibilityHandler = null;
	}
}

// Combined polling function (scores + leaderboard in one request)
// Note: Polling always returns overall leaderboard for live updates
export async function pollLiveData(): Promise<void> {
	// Only show the loading state on the very first poll (empty board), so the
	// header doesn't flash "LOADING…" over already-rendered rows every 60s.
	const isFirstLoad = get(leaderboard).length === 0;
	if (isFirstLoad) leaderboardLoading.set(true);
	leaderboardError.set(null);

	try {
		const data = await scoresApi.pollLiveData();
		liveMatches.set(data.matches);
		lastCalculated.set(data.last_updated);
		// The poll returns the OVERALL board. Only refresh the standings table
		// from it when the user is actually viewing Overall — otherwise we'd
		// yank them off their Phase I/II tab and show overall rows under it.
		if (get(leaderboardPhase) === 'overall') {
			leaderboard.set(data.leaderboard);
			totalParticipants.set(data.leaderboard.length);
		}
	} catch (e) {
		leaderboardError.set(e instanceof Error ? e.message : 'Failed to load live data');
	} finally {
		if (isFirstLoad) leaderboardLoading.set(false);
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
