/**
 * Tests for utils/matchBreakdown.ts — the pure helper that the Results &
 * Fixtures page uses to derive per-card pills, tiers, totals.
 *
 * Focus is the scoring projection: confirming that the rarity bonus we
 * surface matches what `LogarithmicScoring.calculate()` in
 * `backend/app/services/scoring.py` will actually award when the match
 * finishes. The key invariant: when the caller's outcome equals the actual
 * result, `agrees_outcome == correct_predictors`, so the same
 * `R = min(cap, round(alpha * log2(1/(2f))))` formula applies, where
 * `f = agrees_outcome / total` and `alpha = 10/log2(15)`.
 */

import { describe, it, expect } from 'vitest';
import {
	computeBreakdown,
	logarithmicRarityBonus,
	matchState,
	rarityTier,
	stageLabel,
	stageShort
} from './matchBreakdown';
import type { Fixture, MatchPrediction } from '$types';
import type { FixtureAgreement } from '$api/predictions';
import type { ScoringConfig } from '$api/competition';

const CFG: ScoringConfig = {
	mode: 'logarithmic',
	outcome_points: 5,
	exact_points: 10,
	rarity_cap: 10
};

function fx(over: Partial<Fixture>): Fixture {
	return {
		id: 'f1',
		home_team: 'England',
		away_team: 'France',
		kickoff: '2026-06-10T18:00:00Z',
		stage: 'group',
		group: 'A',
		match_number: 1,
		status: 'scheduled',
		minute: null,
		is_locked: false,
		time_until_lock: 3600,
		score: null,
		...over
	};
}

function pr(home: number, away: number): MatchPrediction {
	return {
		id: 'p1',
		fixture_id: 'f1',
		home_score: home,
		away_score: away,
		phase: 'phase_1',
		locked_at: null,
		created_at: '2026-06-01T00:00:00Z',
		updated_at: '2026-06-01T00:00:00Z',
		is_locked: false
	};
}

function ag(exact: number, outcome: number, total: number): FixtureAgreement {
	return { fixture_id: 'f1', agrees_exact: exact, agrees_outcome: outcome, total };
}

describe('matchState', () => {
	it('reports finished from status', () => {
		expect(matchState(fx({ status: 'finished' }))).toBe('finished');
	});
	it('reports live for live and halftime', () => {
		expect(matchState(fx({ status: 'live' }))).toBe('live');
		expect(matchState(fx({ status: 'halftime' }))).toBe('live');
	});
	it('reports locked when is_locked but still scheduled', () => {
		expect(matchState(fx({ status: 'scheduled', is_locked: true }))).toBe('locked');
	});
	it('reports open for scheduled-and-unlocked', () => {
		expect(matchState(fx({ status: 'scheduled', is_locked: false }))).toBe('open');
	});
});

describe('rarityTier', () => {
	it('returns Only You whenever agrees_outcome is 1', () => {
		expect(rarityTier(10, 1).cls).toBe('solo');
	});
	it('returns Rare for bonus >= 5 (with more than 1 agree)', () => {
		expect(rarityTier(6, 5).cls).toBe('rare');
	});
	it('returns Uncommon for bonus 2-4', () => {
		expect(rarityTier(3, 8).cls).toBe('uncommon');
	});
	it('returns Common for bonus < 2', () => {
		expect(rarityTier(1, 25).cls).toBe('common');
	});
});

describe('logarithmicRarityBonus', () => {
	// Same anchor as backend: alpha = 10/log2(15), so f = 1/30 hits cap 10.
	it('returns 0 when everyone got it right', () => {
		expect(logarithmicRarityBonus(30, 30, 10)).toBe(0);
	});
	it('returns 0 at the 50% gate', () => {
		expect(logarithmicRarityBonus(30, 15, 10)).toBe(0);
	});
	it('returns 1 for the three-way-split case (f = 1/3)', () => {
		expect(logarithmicRarityBonus(30, 10, 10)).toBe(1);
	});
	it('returns 4 for one-in-six (f = 1/6)', () => {
		expect(logarithmicRarityBonus(30, 5, 10)).toBe(4);
	});
	it('hits the cap for uniquely correct at the anchor (f = 1/30)', () => {
		expect(logarithmicRarityBonus(30, 1, 10)).toBe(10);
	});
	it('stays capped for rarer-than-anchor (f = 1/60)', () => {
		expect(logarithmicRarityBonus(60, 1, 10)).toBe(10);
	});
	it('returns 0 (no crash) for zero predictors', () => {
		expect(logarithmicRarityBonus(0, 0, 10)).toBe(0);
	});
	it('is scale-invariant: same f produces same R', () => {
		// f = 1/6 in both cases
		expect(logarithmicRarityBonus(12, 2, 10)).toBe(logarithmicRarityBonus(60, 10, 10));
	});
});

describe('computeBreakdown — finished matches', () => {
	const finished = fx({
		status: 'finished',
		score: {
			home_score: 2,
			away_score: 1,
			home_score_et: null,
			away_score_et: null,
			home_penalties: null,
			away_penalties: null,
			outcome: '1'
		}
	});

	it('exact pick: outcome + exact + rarity, total = 5 + 10 + bonus', () => {
		// 6 of 25 predictors picked the home win → f = 0.24.
		// R = round(2.5596 * log2(1/0.48)) = round(2.71) = 3.
		const bd = computeBreakdown(finished, pr(2, 1), ag(2, 6, 25), CFG);
		expect(bd.tier).toBe('tier-exact');
		expect(bd.outcomePill.state).toBe('hit-outcome');
		expect(bd.scorePill.state).toBe('hit-exact');
		expect(bd.rarityPill.state).toBe('hit-rarity');
		expect(bd.rarityPill.pts).toBe(3);
		expect(bd.totalPts).toBe(18);
		expect(bd.totalLabel).toBe('Banked');
		expect(bd.totalDisplay).toBe('+18');
		expect(bd.ypickClass).toBe('exact');
	});

	it('outcome-only pick: 5 outcome + bonus, no exact', () => {
		// Pick 3-1, actual 2-1: same outcome (1), wrong score.
		// 1 of 12 predictors picked this outcome → f = 1/12.
		// R = round(2.5596 * log2(6)) = round(6.62) = 7. "Only You" solo.
		const bd = computeBreakdown(finished, pr(3, 1), ag(0, 1, 12), CFG);
		expect(bd.tier).toBe('tier-outcome');
		expect(bd.outcomePill.state).toBe('hit-outcome');
		expect(bd.scorePill.state).toBe('miss');
		expect(bd.rarityPill.state).toBe('hit-rarity solo');
		expect(bd.rarityPill.pts).toBe(7);
		expect(bd.rarityPill.lab).toBe('Only You');
		expect(bd.totalPts).toBe(12);
		expect(bd.ypickClass).toBe('outcome');
	});

	it('miss: all zero, tier-miss, total 0', () => {
		// Pick 0-2 (away win), actual 2-1 (home win): wrong outcome.
		const bd = computeBreakdown(finished, pr(0, 2), ag(0, 8, 20), CFG);
		expect(bd.tier).toBe('tier-miss');
		expect(bd.outcomePill.state).toBe('miss');
		expect(bd.scorePill.state).toBe('miss');
		expect(bd.rarityPill.state).toBe('none');
		expect(bd.totalPts).toBe(0);
		expect(bd.totalDisplay).toBe('0');
		expect(bd.ypickClass).toBe('miss');
	});

	it('no pick on finished match: empty ypick, totalPts 0 (treated like a miss per design)', () => {
		const bd = computeBreakdown(finished, undefined, undefined, CFG);
		expect(bd.ypickClass).toBe('empty');
		expect(bd.totalPts).toBe(0);
		expect(bd.totalDisplay).toBe('0');
	});
});

describe('computeBreakdown — upcoming matches', () => {
	it('open fixture with pick projects "Up to" total with potential pills', () => {
		const f = fx({ status: 'scheduled', is_locked: false });
		// 4 of 18 predictors picked the home-win outcome → f = 4/18 = 0.222.
		// R = round(2.5596 * log2(1/0.444)) = round(2.99) = 3.
		const bd = computeBreakdown(f, pr(1, 0), ag(0, 4, 18), CFG);
		expect(bd.tier).toBe('tier-open');
		expect(bd.outcomePill.state).toBe('potential');
		expect(bd.scorePill.state).toBe('potential');
		expect(bd.rarityPill.state).toBe('potential');
		expect(bd.rarityPill.pts).toBe(3);
		expect(bd.totalLabel).toBe('Up to');
		expect(bd.totalPts).toBe(18); // 5 + 10 + 3
	});

	it('locked fixture switches tier and label', () => {
		const f = fx({ status: 'scheduled', is_locked: true });
		const bd = computeBreakdown(f, pr(1, 0), ag(0, 10, 28), CFG);
		expect(bd.tier).toBe('tier-locked');
		expect(bd.totalLabel).toBe('Locked');
	});

	it('upcoming with no pick → "No pick" rarity label, total —', () => {
		const f = fx({ status: 'scheduled' });
		const bd = computeBreakdown(f, undefined, undefined, CFG);
		expect(bd.rarityPill.lab).toBe('No pick');
		expect(bd.totalDisplay).toBe('—');
	});
});

describe('computeBreakdown — live matches', () => {
	it('live + correct-outcome-so-far projects "If FT now" total', () => {
		const f = fx({
			status: 'live',
			minute: 41,
			score: {
				home_score: 1,
				away_score: 0,
				home_score_et: null,
				away_score_et: null,
				home_penalties: null,
				away_penalties: null,
				outcome: '1'
			}
		});
		const bd = computeBreakdown(f, pr(1, 0), ag(1, 3, 22), CFG);
		expect(bd.tier).toBe('tier-exact');
		expect(bd.scorePill.state).toBe('hit-exact');
		expect(bd.outcomePill.state).toBe('hit-outcome');
		expect(bd.totalLabel).toBe('If FT now');
		expect(bd.liveResult).toBe('exact');
	});

	it('live with no pick uses tier-live with no projection', () => {
		const f = fx({
			status: 'live',
			minute: 12,
			score: {
				home_score: 0,
				away_score: 0,
				home_score_et: null,
				away_score_et: null,
				home_penalties: null,
				away_penalties: null,
				outcome: 'X'
			}
		});
		const bd = computeBreakdown(f, undefined, undefined, CFG);
		expect(bd.tier).toBe('tier-live');
		expect(bd.ypickClass).toBe('empty');
		expect(bd.totalDisplay).toBe('—');
	});
});

describe('computeBreakdown — fixed scoring mode', () => {
	const FIXED: ScoringConfig = { ...CFG, mode: 'fixed' };
	it('does not award a rarity bonus and labels the pill as Fixed', () => {
		const finished = fx({
			status: 'finished',
			score: {
				home_score: 2,
				away_score: 1,
				home_score_et: null,
				away_score_et: null,
				home_penalties: null,
				away_penalties: null,
				outcome: '1'
			}
		});
		const bd = computeBreakdown(finished, pr(2, 1), ag(2, 6, 25), FIXED);
		expect(bd.rarityPill.state).toBe('none');
		expect(bd.rarityPill.lab).toBe('Fixed');
		expect(bd.totalPts).toBe(15); // 5 + 10 only
	});
});

describe('stageLabel / stageShort', () => {
	it('maps known stages', () => {
		expect(stageLabel('round_of_32')).toBe('Round of 32');
		expect(stageLabel('quarter_final')).toBe('Quarter-final');
		expect(stageShort('round_of_16')).toBe('R16');
		expect(stageShort('semi_final')).toBe('SF');
		expect(stageShort('final')).toBe('F');
	});
	it('falls back to a humanised version for unknown stages', () => {
		expect(stageLabel('some_other')).toBe('some other');
		expect(stageShort('mystery')).toBe('MYSTERY');
	});
});
