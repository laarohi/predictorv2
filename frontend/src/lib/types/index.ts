/**
 * TypeScript interfaces for the Predictor v2 frontend.
 * Mirrors backend Pydantic schemas.
 */

// Auth types
export interface User {
	id: string;
	email: string;
	name: string;
	auth_provider: 'email' | 'google';
	is_admin: boolean;
	is_active: boolean;
	competition_id: string | null;
	created_at: string;
}

export interface Token {
	access_token: string;
	token_type: string;
}

export interface UserCreate {
	email: string;
	name: string;
	password: string;
}

export interface UserLogin {
	email: string;
	password: string;
}

// Fixture types
export type MatchStatus = 'scheduled' | 'live' | 'halftime' | 'finished' | 'postponed' | 'cancelled';

export interface Fixture {
	id: string;
	home_team: string;
	away_team: string;
	kickoff: string;
	stage: string;
	group: string | null;
	match_number: number | null;
	status: MatchStatus;
	minute: number | null;
	is_locked: boolean;
	time_until_lock: number | null;
}

export interface FixturesByGroup {
	group: string;
	fixtures: Fixture[];
}

export interface LockStatus {
	fixture_id: string;
	is_locked: boolean;
	locks_at: string;
	time_remaining: number | null;
}

// Prediction types
export type PredictionPhase = 'phase_1' | 'phase_2';

export interface MatchPrediction {
	id: string;
	fixture_id: string;
	home_score: number;
	away_score: number;
	phase: PredictionPhase;
	locked_at: string | null;
	created_at: string;
	updated_at: string;
	home_team?: string;
	away_team?: string;
	kickoff?: string;
	is_locked: boolean;
}

export interface MatchPredictionUpdate {
	home_score: number;
	away_score: number;
}

export interface MatchPredictionCreate {
	fixture_id: string;
	home_score: number;
	away_score: number;
}

export interface BracketPrediction {
	group_winners: Record<string, string[]>;
	round_of_32: string[];
	round_of_16: string[];
	quarter_finals: string[];
	semi_finals: string[];
	final: string[];
	winner: string;
}

export interface TeamAdvancementPrediction {
	team: string;
	stage: string;
	group_position: number | null;
}

// Score types
export type ScoreSource = 'api' | 'manual';

export interface Score {
	id: string;
	fixture_id: string;
	home_score: number;
	away_score: number;
	home_score_et: number | null;
	away_score_et: number | null;
	home_penalties: number | null;
	away_penalties: number | null;
	source: ScoreSource;
	verified: boolean;
	outcome: string;
}

export interface LiveMatchScore {
	fixture_id: string;
	home_team: string;
	away_team: string;
	home_score: number;
	away_score: number;
	status: string;
	minute: number | null;
	kickoff: string;
}

export interface LiveScoreResponse {
	matches: LiveMatchScore[];
	last_updated: string;
}

// Leaderboard types
export interface PointBreakdown {
	match_outcome_points: number;
	exact_score_points: number;
	group_advancement_points: number;
	knockout_advancement_points: number;
}

export interface LeaderboardEntry {
	user_id: string;
	user_name: string;
	position: number;
	total_points: number;
	breakdown: PointBreakdown;
	correct_outcomes: number;
	exact_scores: number;
	movement: number;
}

export interface LeaderboardResponse {
	entries: LeaderboardEntry[];
	last_calculated: string;
	total_participants: number;
}

// Competition/Phase types
export interface PhaseStatus {
	current_phase: PredictionPhase;
	// Phase 1
	phase1_deadline: string | null;
	phase1_locked: boolean;
	// Phase 2
	is_phase2_active: boolean;
	phase2_bracket_deadline: string | null;
	phase2_bracket_locked: boolean;
}

// Bracket configuration types
/** Maps group winner positions (e.g., "1A") to third-place positions (e.g., "3E") */
export type ThirdPlaceMatchup = Record<string, string>;

/** Maps qualifying third-place group combinations (e.g., "EFGHIJKL") to their matchups */
export type ThirdPlaceMappingTable = Record<string, ThirdPlaceMatchup>;

// Standings types
export interface TeamStanding {
	team: string;
	group: string;
	played: number;
	won: number;
	drawn: number;
	lost: number;
	goals_for: number;
	goals_against: number;
	goal_difference: number;
	points: number;
}

export interface ActualStandingsResponse {
	standings: Record<string, TeamStanding[]>;
	qualifying_third_place: TeamStanding[];
}

// API Response types
export interface ApiError {
	detail: string;
}
