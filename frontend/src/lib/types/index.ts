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
	paid: boolean;
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

export interface FixtureScore {
	home_score: number;
	away_score: number;
	home_score_et: number | null;
	away_score_et: number | null;
	home_penalties: number | null;
	away_penalties: number | null;
	outcome: string; // '1', 'X', '2'
}

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
	score: FixtureScore | null;
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

export interface LivePollingResponse {
	matches: LiveMatchScore[];
	leaderboard: LeaderboardEntry[];
	last_updated: string;
}

// Leaderboard types

/** Points breakdown for a single phase */
export interface PhaseBreakdown {
	// Match predictions
	match_outcome_points: number;
	exact_score_points: number;
	hybrid_bonus_points: number;

	// Raw match-prediction counts for this phase only
	correct_outcomes: number;
	exact_scores: number;

	// Bracket predictions - by stage
	group_advance_points: number;
	group_position_points: number;
	round_of_32_points: number;
	round_of_16_points: number;
	quarter_final_points: number;
	semi_final_points: number;
	final_points: number;
	winner_points: number;

	// Computed totals (from backend)
	match_total: number;
	bracket_total: number;
	total: number;
}

/** Full breakdown with phase separation */
export interface PointBreakdown {
	phase1: PhaseBreakdown;
	phase2: PhaseBreakdown;

	// Aggregate statistics
	correct_outcomes: number;
	exact_scores: number;
	total_predictions: number;

	// Bonus-question points (cross-phase — locked with Phase 1 but separate
	// from the phase breakdown). Awarded when an admin sets the matching
	// correct answer on /api/admin/bonus/answers.
	bonus_question_points: number;

	// Computed totals (from backend) - combined across phases + bonus
	match_total: number;
	bracket_total: number;
	total: number;

	// Legacy fields (combined across phases, from backend computed fields)
	match_outcome_points: number;
	exact_score_points: number;
	hybrid_bonus_points: number;
	group_advance_points: number;
	group_position_points: number;
	round_of_32_points: number;
	round_of_16_points: number;
	quarter_final_points: number;
	semi_final_points: number;
	final_points: number;
	winner_points: number;
}

// Helper functions for phase breakdowns
export function getPhaseMatchTotal(p: PhaseBreakdown): number {
	return p.match_outcome_points + p.exact_score_points + p.hybrid_bonus_points;
}

export function getPhaseBracketTotal(p: PhaseBreakdown): number {
	return (
		p.group_advance_points +
		p.group_position_points +
		p.round_of_32_points +
		p.round_of_16_points +
		p.quarter_final_points +
		p.semi_final_points +
		p.final_points +
		p.winner_points
	);
}

export function getPhaseTotal(p: PhaseBreakdown): number {
	return getPhaseMatchTotal(p) + getPhaseBracketTotal(p);
}

// Helper to calculate totals from full breakdown (legacy support)
export function getMatchTotal(b: PointBreakdown): number {
	return b.match_outcome_points + b.exact_score_points + b.hybrid_bonus_points;
}

export function getBracketTotal(b: PointBreakdown): number {
	return (
		b.group_advance_points +
		b.group_position_points +
		b.round_of_32_points +
		b.round_of_16_points +
		b.quarter_final_points +
		b.semi_final_points +
		b.final_points +
		b.winner_points
	);
}

// Helper to get knockout total (excluding groups) for a phase
export function getKnockoutTotal(p: PhaseBreakdown): number {
	return (
		p.round_of_32_points +
		p.round_of_16_points +
		p.quarter_final_points +
		p.semi_final_points +
		p.final_points +
		p.winner_points
	);
}

// Helper to get group total for a phase
export function getGroupTotal(p: PhaseBreakdown): number {
	return p.group_advance_points + p.group_position_points;
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
	/** Current form: trailing run of finished matches ending at the latest
	 *  result. Exactly one is non-zero — last result was a correct outcome
	 *  (hot) or a miss (cold). Outcome-level, not exact score. */
	hot_streak: number;
	cold_streak: number;
	/** Synthetic entrant (crowd consensus / market bot) — interleaved by
	 *  points but unranked (position stays 0). */
	is_ghost: boolean;
}

export interface LeaderboardResponse {
	entries: LeaderboardEntry[];
	last_calculated: string;
	total_participants: number;
	phase: string | null;
}

// ---- Daily Drop (the once-a-day broadcast banter card) ----
// Every stat is nullable: when there isn't data yet, the row is omitted.
// Broadcast stats carry the full tied set (`names`); the modal formats it with
// overflow ("A", "A & B", "A, B & C", "A, B +N").
export interface DropLeader { names: string[]; points: number; lead: number; }
export interface DropMove { names: string[]; delta: number; }
export interface DropPointsHaul { names: string[]; points_gained: number; }
export interface DropSpoon { names: string[]; position: number; behind_leader: number; }
// Daily worst performer. `names` lists all tied when few; on a big tie it shows
// one rotating representative and `tied_count` carries the true total ("+N").
export interface DropClueless { names: string[]; points: number; tied_count: number; is_floor: boolean; }
export interface DropCalledIt {
	names: string[]; count: number; home_team: string; away_team: string;
	home_score: number; away_score: number;
}
export interface DropContrarian {
	names: string[]; avg_pct: number;
}
export interface DropBlunder {
	names: string[]; home_team: string; away_team: string;
	predicted: string; actual: string; swing: number;
}
export interface DropStreak { names: string[]; length: number; }
export interface PointsCategory { label: string; points: number; }
export interface MatchResult {
	home_team: string;
	away_team: string;
	predicted: string; // "3-0"
	actual: string; // "0-0"
	points: number;
	result: 'exact' | 'outcome' | 'miss';
}
export interface PersonalStats {
	user_name: string;
	position: number;
	movement: number;
	points: number;
	points_gained: number | null;
	hot_streak: number;
	cold_streak: number;
	match_results: MatchResult[];
}
export interface DropPayload {
	leader: DropLeader | null;
	mover: DropMove | null;
	faceplant: DropMove | null;
	points_haul: DropPointsHaul | null;
	wooden_spoon: DropSpoon | null;
	clueless: DropClueless | null;
	called_it: DropCalledIt | null;
	contrarian: DropContrarian | null;
	blunder: DropBlunder | null;
	hottest_streak: DropStreak | null;
	coldest_streak: DropStreak | null;
	match_count: number;
	player_count: number;
}
export interface DailyDrop {
	drop_date: string;
	payload: DropPayload;
	roast: string | null;
	roast_is_placeholder: boolean;
	roast_generated_at: string | null;
	created_at: string;
	personal: PersonalStats | null;
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

/**
 * UX-level competition phase. Derived from PhaseStatus + fixture state in
 * frontend/src/lib/stores/phase.ts. Drives which Dashboard*.svelte renders
 * on the landing page and which phase-aware widgets appear.
 */
export type UxPhase =
	| 'pre_tournament'
	| 'group_stage'
	| 'between_phases'
	| 'knockout_stage'
	| 'post_competition';

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

// Profile types
export interface PasswordChange {
	current_password: string;
	new_password: string;
}

export interface UserStats {
	total_match_predictions: number;
	total_team_predictions: number;
	total_predictions: number;
	correct_outcomes: number;
	exact_scores: number;
	accuracy_pct: number;
	total_points: number;
	leaderboard_position: number | null;
	total_participants: number;
	breakdown: PointBreakdown;
}

// Community predictions (for scatter plot on results page)
export interface CommunityPrediction {
	user_name: string;
	home_score: number;
	away_score: number;
}

export interface CommunityPredictionsResponse {
	fixture_id: string;
	home_team: string;
	away_team: string;
	predictions: CommunityPrediction[];
	actual: FixtureScore | null;
}

// Prediction overview (who-picked-what distribution pages)
export interface OverviewCountCell {
	count: number;
	/** Exactly who is behind the count, alphabetical. */
	users: string[];
}

export interface OverviewTeamRow {
	team: string;
	/** Index 0..3 — players whose predicted standings put this team 1st..4th. */
	positions: OverviewCountCell[];
	/** Players whose Phase 1 bracket carries this team into the R32. */
	advance: OverviewCountCell;
}

export interface OverviewFixtureRow {
	fixture_id: string;
	home_team: string;
	away_team: string;
	kickoff: string;
	status: string;
	home_count: number;
	draw_count: number;
	away_count: number;
	actual_home: number | null;
	actual_away: number | null;
}

export interface OverviewGroup {
	group: string;
	teams: OverviewTeamRow[];
	fixtures: OverviewFixtureRow[];
}

export interface GroupsOverviewResponse {
	total_predictors: number;
	groups: OverviewGroup[];
}

export interface BracketOverviewTeamRow {
	team: string;
	group: string | null;
	round_of_32: OverviewCountCell;
	round_of_16: OverviewCountCell;
	quarter_final: OverviewCountCell;
	semi_final: OverviewCountCell;
	final: OverviewCountCell;
	winner: OverviewCountCell;
}

export interface BracketOverviewResponse {
	phase: number;
	total_predictors: number;
	teams: BracketOverviewTeamRow[];
}

/** One knockout fixture's pool-wide score-pick split (1/X/2). Same shape as
 *  OverviewFixtureRow plus the knockout `stage` label. Only present for
 *  fixtures that are individually locked or finished (per-match blind pool). */
export interface KnockoutScoreFixtureRow extends OverviewFixtureRow {
	stage: string;
}

export interface KnockoutScoresOverviewResponse {
	total_predictors: number;
	/** Ordered by round (round_of_32 → final) then kickoff. */
	fixtures: KnockoutScoreFixtureRow[];
}

// Public user profile types
export interface PublicProfile {
	id: string;
	name: string;
	created_at: string;
	stats: UserStats;
}

export interface UserMatchPredictionView {
	fixture_id: string;
	home_team: string;
	away_team: string;
	kickoff: string;
	stage: string;
	group: string | null;
	status: MatchStatus;
	predicted_home: number;
	predicted_away: number;
	actual_home: number | null;
	actual_away: number | null;
	actual_outcome: string | null;
	is_exact: boolean;
	is_correct_outcome: boolean;
}

export interface BracketSummary {
	stages: Record<string, string[]>;
	phase1_stages: Record<string, string[]>;
	phase2_stages: Record<string, string[]>;
}

export interface UserBonusPredictionView {
	question_id: string;
	label: string;
	category: 'group_stage' | 'top_flop' | 'awards';
	points: number;
	answer: string;
	/** Recorded correct answer(s) — multiple on ties; empty until entered. */
	correct_answers: string[];
	/** Null while no correct answer is recorded; true/false afterwards. */
	is_correct: boolean | null;
}

export interface ProfileQualTeam {
	team: string;
	predicted_position: number | null;
	actual_position: number;
	base_points: number; // +round_of_32 for getting out of the group
	position_points: number; // +group_position for the correct finishing spot
}
export interface ProfileQualEntry {
	group: string;
	total: number;
	teams: ProfileQualTeam[];
}

export interface UserPredictionsResponse {
	user_id: string;
	user_name: string;
	match_predictions: UserMatchPredictionView[];
	bracket_summary: BracketSummary;
	/** Bonus-question picks — empty before Phase 1 locks (blind pool). */
	bonus_predictions: UserBonusPredictionView[];
	/** Per-group Phase-1 qualification ledger — empty until the Phase-1 bracket
	 *  is visible. Drives the per-team R32 scoring colour on the profile. */
	group_qualification: ProfileQualEntry[];
}

// API Response types
export interface ApiError {
	detail: string;
}
