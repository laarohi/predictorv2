/**
 * Utility for comparing predictions against actual match results.
 */

import type { Fixture, MatchPrediction } from '$types';

export type PredictionResult = 'exact' | 'outcome' | 'wrong' | 'pending';

/**
 * Derive predicted outcome from scores: '1' (home win), 'X' (draw), '2' (away win).
 */
function getOutcome(home: number, away: number): string {
	if (home > away) return '1';
	if (home < away) return '2';
	return 'X';
}

/**
 * Compare a user's prediction against the actual fixture result.
 *
 * Returns:
 * - 'exact'   — predicted the exact score
 * - 'outcome' — predicted correct outcome (1/X/2) but wrong score
 * - 'wrong'   — completely wrong
 * - 'pending' — fixture not finished or no prediction
 */
export function getPredictionResult(
	fixture: Fixture,
	prediction: MatchPrediction | undefined
): PredictionResult {
	if (!prediction || fixture.status !== 'finished' || !fixture.score) {
		return 'pending';
	}

	const score = fixture.score;

	// Check exact score match
	if (prediction.home_score === score.home_score && prediction.away_score === score.away_score) {
		return 'exact';
	}

	// Check outcome match
	const predictedOutcome = getOutcome(prediction.home_score, prediction.away_score);
	if (predictedOutcome === score.outcome) {
		return 'outcome';
	}

	return 'wrong';
}
