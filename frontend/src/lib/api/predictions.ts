/**
 * Predictions API functions.
 */

import { api } from './client';
import type {
	MatchPrediction,
	MatchPredictionCreate,
	MatchPredictionUpdate,
	BracketPrediction,
	BracketOverviewResponse,
	GroupsOverviewResponse,
	KnockoutScoresOverviewResponse,
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

export interface StageCellResponse {
	n: number;
	of: number;
	pts: number;
	teams: string[];
}

export interface StageRowResponse {
	earned: StageCellResponse;
	available: StageCellResponse;
	/** Eliminated picks at this stage (feeder match finished, team lost). Carries
	 *  0 pts; drives the muted-red "missed" segment + tooltip. Optional for
	 *  backward-compat with a response cached before the field existed. */
	missed?: StageCellResponse;
}

export interface BracketExposureResponse {
	points_available: number;
	picks_locked: number;
	picks_total: number;
	/** Team name (not code) of the user's predicted tournament winner; null if not picked yet. */
	final_winner: string | null;
	/** The other finalist; null if not predicted or only the winner is set. */
	final_opponent: string | null;
	/** v1 per-stage alive picks (round_of_16 .. winner) — count of user picks that
	 * actually made it to or past that stage. */
	alive_per_stage?: Record<string, number>;
	/** Per-stage team-count denominator (16, 8, 4, 2, 1). */
	teams_per_stage?: Record<string, number>;
	/** v4 per-stage breakdown — drives DwScoringJourney. Each stage gets
	 * an earned + available cell with progressive denominators. */
	per_stage?: Record<string, StageRowResponse>;
}

export async function getBracketExposure(
	phase: 'phase_1' | 'phase_2' = 'phase_1'
): Promise<BracketExposureResponse> {
	return api.get<BracketExposureResponse>(`/predictions/bracket-exposure?phase=${phase}`);
}

export interface GroupQualTeam {
	team: string;
	predicted_position: number | null;
	actual_position: number;
	base_points: number; // +round_of_32 for getting out of the group
	position_points: number; // +group_position for the correct finishing spot
}

export interface GroupQualEntry {
	group: string;
	total: number;
	teams: GroupQualTeam[];
}

/** Per-group Phase-1 qualification breakdown for the calling user (completed
 *  groups only). Powers the group summary table's Qual column + per-team
 *  tooltip; reconciles with the leaderboard (same scoring engine). */
export async function getMyGroupQualification(): Promise<GroupQualEntry[]> {
	return api.get<GroupQualEntry[]>('/predictions/me/group-qualification');
}

// ---- Knockout match-score points (the "KO matches so far" strip) ----

export interface KnockoutMatchFixtureRow {
	home_team: string;
	away_team: string;
	predicted: string; // "2-1"
	actual: string | null; // final (ET/pens) score for display, null if unplayed
	points: number | null; // banked points, null if unplayed
	result: 'exact' | 'outcome' | 'miss' | null;
	status: string; // "finished" | "scheduled" | "live" | ...
}

export interface KnockoutMatchRoundRow {
	stage: string; // round_of_32 .. final, third_place
	earned_pts: number;
	/** Best-case ceiling (≤) for unplayed predicted fixtures, never awarded. */
	available_pts: number;
	fixtures: KnockoutMatchFixtureRow[];
}

/** Per-KO-round match-SCORE points for the calling user — banked (finished)
 *  plus a best-case still-in-play ceiling. Sibling of the bracket Scoring
 *  Journey; reconciles with the leaderboard (same scoring engine). */
export async function getMyKnockoutMatchPoints(): Promise<KnockoutMatchRoundRow[]> {
	return api.get<KnockoutMatchRoundRow[]>('/predictions/me/knockout-match-points');
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

// ---- Overview (who-picked-what distributions; blind-pool gated server-side) ----

export async function getGroupsOverview(): Promise<GroupsOverviewResponse> {
	return api.get<GroupsOverviewResponse>('/predictions/overview/groups');
}

export async function getBracketOverview(phase: 1 | 2 = 1): Promise<BracketOverviewResponse> {
	return api.get<BracketOverviewResponse>(`/predictions/overview/bracket?phase=${phase}`);
}

/** Pool-wide distribution of Phase 2 knockout match-score picks. Per-match
 *  blind pool: the backend only returns a fixture's split once that fixture
 *  individually locks (or finishes), so unlocked picks never leak. */
export async function getKnockoutScoresOverview(): Promise<KnockoutScoresOverviewResponse> {
	return api.get<KnockoutScoresOverviewResponse>('/predictions/overview/knockout-scores');
}
