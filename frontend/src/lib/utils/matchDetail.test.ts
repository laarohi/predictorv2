/**
 * Tests for utils/matchDetail.ts — the pure helpers behind the
 * /results/[fixture_id] page (classifyPick, buildCells, rarityLabel,
 * outcomeOf, toGridPlayer).
 */

import { describe, it, expect } from 'vitest';
import {
	buildCells,
	classifyPick,
	outcomeOf,
	pickStr,
	rarityLabel,
	toGridPlayer
} from './matchDetail';
import type { CommunityPrediction } from '$types';

describe('outcomeOf', () => {
	it('returns home when home wins', () => {
		expect(outcomeOf(2, 1)).toBe('home');
	});
	it('returns away when away wins', () => {
		expect(outcomeOf(0, 1)).toBe('away');
	});
	it('returns draw for equal scores', () => {
		expect(outcomeOf(1, 1)).toBe('draw');
		expect(outcomeOf(0, 0)).toBe('draw');
	});
});

describe('classifyPick', () => {
	const actual = { home_score: 2, away_score: 1 };

	it('returns unknown when no actual', () => {
		expect(classifyPick({ home_score: 2, away_score: 1 }, null)).toBe('unknown');
		expect(classifyPick({ home_score: 2, away_score: 1 }, undefined)).toBe('unknown');
	});
	it('returns exact when both scores match', () => {
		expect(classifyPick({ home_score: 2, away_score: 1 }, actual)).toBe('exact');
	});
	it('returns outcome when 1/X/2 matches but score differs', () => {
		expect(classifyPick({ home_score: 3, away_score: 0 }, actual)).toBe('outcome');
		expect(classifyPick({ home_score: 1, away_score: 0 }, actual)).toBe('outcome');
	});
	it('returns miss when outcome differs', () => {
		expect(classifyPick({ home_score: 1, away_score: 1 }, actual)).toBe('miss');
		expect(classifyPick({ home_score: 0, away_score: 2 }, actual)).toBe('miss');
	});
});

describe('buildCells', () => {
	function p(name: string, h: number, a: number, you = false) {
		return toGridPlayer(
			{ user_name: name, home_score: h, away_score: a } as CommunityPrediction,
			you,
			null,
			null,
			null
		);
	}

	it('groups players sharing a (home, away) cell', () => {
		const cells = buildCells([p('A', 2, 1), p('B', 2, 1), p('C', 1, 0)]);
		expect(Object.keys(cells).sort()).toEqual(['1,0', '2,1']);
		expect(cells['2,1'].players).toHaveLength(2);
		expect(cells['1,0'].players).toHaveLength(1);
	});

	it('clamps scores above gridMax', () => {
		// 7-1 → clamped to 4-1
		const cells = buildCells([p('A', 7, 1)], 4);
		expect(Object.keys(cells)).toEqual(['4,1']);
		expect(cells['4,1'].players[0].home).toBe(7);
	});

	it('preserves the you flag', () => {
		const cells = buildCells([p('A', 2, 1, true)]);
		expect(cells['2,1'].players[0].you).toBe(true);
	});
});

describe('rarityLabel', () => {
	it('returns Solo when count is 1', () => {
		expect(rarityLabel(1, 30).cls).toBe('solo');
	});
	it('returns Rare for <8%', () => {
		expect(rarityLabel(2, 30).cls).toBe('rare'); // 6.6%
	});
	it('returns Uncommon for <18%', () => {
		expect(rarityLabel(4, 30).cls).toBe('uncommon'); // 13.3%
	});
	it('returns Common otherwise', () => {
		expect(rarityLabel(8, 30).cls).toBe('common'); // 26.6%
	});
	it('handles total=0 without throwing', () => {
		const r = rarityLabel(0, 0);
		expect(r.cls).toBe('solo'); // count <= 1
	});
});

describe('pickStr', () => {
	it('renders with en-dash', () => {
		expect(pickStr(2, 1)).toBe('2–1');
	});
});

describe('toGridPlayer', () => {
	it('uppercases the first letter for initial', () => {
		const cp: CommunityPrediction = {
			user_name: 'marco rossi',
			home_score: 2,
			away_score: 1
		};
		const gp = toGridPlayer(cp, true, 8, 147, 4);
		expect(gp.initial).toBe('M');
		expect(gp.you).toBe(true);
		expect(gp.totalPts).toBe(147);
	});
	it('uses ? when name is empty', () => {
		const cp: CommunityPrediction = {
			user_name: '',
			home_score: 0,
			away_score: 0
		};
		const gp = toGridPlayer(cp, false, null, null, null);
		expect(gp.initial).toBe('?');
	});
});
