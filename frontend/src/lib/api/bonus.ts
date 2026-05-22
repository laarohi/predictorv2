/**
 * Bonus-question API functions.
 *
 * Questions are defined in worldcup2026.yml under `bonus:` and shipped to
 * the frontend pre-rendered (with {n} substituted from each question's own
 * cutoff.rank). The DB holds per-user picks and per-competition correct
 * answers.
 */

import { api } from './client';

export type BonusCategory = 'group_stage' | 'top_flop' | 'awards';
export type BonusInputType = 'team' | 'player';

export interface BonusQuestion {
	id: string;
	category: BonusCategory;
	label: string;
	input_type: BonusInputType;
	points: number;
	/** For team-input questions with a YAML cutoff (e.g. dark_horse "outside
	 *  FIFA top 12", flop "inside FIFA top 7"), the pre-filtered list of
	 *  competition teams the user is allowed to pick from. The wizard
	 *  filters its team dropdown to just these teams. Null/undefined for
	 *  questions without a cutoff or non-team inputs. */
	eligible_teams?: string[] | null;
}

export interface BonusPrediction {
	question_id: string;
	answer: string;
}

export interface BonusAnswerView {
	question_id: string;
	label: string;
	category: BonusCategory;
	points: number;
	input_type: BonusInputType;
	/** All accepted correct answers (multiple entries = a tie). Empty if unresolved. */
	correct_answers: string[];
	/** Auto-derived suggestion(s) from fixtures + scores. Group-stage and
	 *  top/flop only; awards-category questions always have []. Advisory
	 *  — admin can apply via "Use computed" or override manually. */
	computed_answers: string[];
	resolved_at: string | null;
}

// User-side ----------------------------------------------------------------

export async function getBonusQuestions(): Promise<BonusQuestion[]> {
	return api.get<BonusQuestion[]>('/predictions/bonus/questions');
}

export async function getMyBonusPredictions(): Promise<BonusPrediction[]> {
	return api.get<BonusPrediction[]>('/predictions/bonus');
}

export async function saveBonusPredictions(
	predictions: BonusPrediction[]
): Promise<BonusPrediction[]> {
	return api.post<BonusPrediction[]>('/predictions/bonus', { predictions });
}

// Admin-side ---------------------------------------------------------------

export async function listBonusAnswers(): Promise<BonusAnswerView[]> {
	return api.get<BonusAnswerView[]>('/admin/bonus/answers');
}

export async function setBonusAnswer(
	questionId: string,
	correctAnswers: string[]
): Promise<BonusAnswerView> {
	return api.post<BonusAnswerView>('/admin/bonus/answers', {
		question_id: questionId,
		correct_answers: correctAnswers
	});
}
