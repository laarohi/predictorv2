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

/** Scoring config. The Results page projects per-match rarity bonuses with
 *  the same formula the backend uses. For mode='logarithmic':
 *  R = min(rarity_cap, round(alpha * log2(1 / (2f)))) where f = agrees_outcome
 *  / total and alpha = 10/log2(15) ≈ 2.5596. Per-fixture predictor counts
 *  come from FixtureAgreement.total. Mirrors backend ScoringConfigResponse.
 *
 *  `advancement` / `advancement_phase2` are the per-round bracket point tables
 *  (round_of_32 … winner), and `group_position` the Phase 1 group-position
 *  bonus — the public /rules page renders these as a round × phase table.
 *  Endpoint is public (no auth), matching getCompetitionInfo. */
export interface ScoringConfig {
	mode: 'fixed' | 'hybrid' | 'logarithmic';
	outcome_points: number;
	exact_points: number;
	rarity_cap: number;
	// Bracket point tables. The endpoint always returns these, but they're
	// optional here so the Results pages — which only need the match fields —
	// can keep constructing minimal ScoringConfig literals. Only the /rules
	// page reads them (guarded with fallbacks).
	group_position?: number;
	advancement?: Record<string, number>;
	advancement_phase2?: Record<string, number>;
}

export async function getScoringConfig(): Promise<ScoringConfig> {
	return api.get<ScoringConfig>('/competition/scoring-config');
}
