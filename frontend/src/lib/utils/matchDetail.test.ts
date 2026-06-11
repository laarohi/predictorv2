/**
 * Tests for utils/matchDetail.ts — the pure helpers behind the
 * /results/[fixture_id] page (classifyPick, buildCells, rarityLabel,
 * outcomeOf, toGridPlayer).
 */

import { describe, it, expect } from 'vitest';
import {
	buildCells,
	classifyPick,
	gridAxes,
	heatColor,
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

	it('keeps high scores on their true cell with per-axis maxima', () => {
		const cells = buildCells([p('A', 7, 1)], 7, 4);
		expect(Object.keys(cells)).toEqual(['7,1']);
	});

	it('preserves the you flag', () => {
		const cells = buildCells([p('A', 2, 1, true)]);
		expect(cells['2,1'].players[0].you).toBe(true);
	});
});

describe('gridAxes', () => {
	function p(name: string, h: number, a: number) {
		return toGridPlayer(
			{ user_name: name, home_score: h, away_score: a } as CommunityPrediction,
			false,
			null,
			null,
			null
		);
	}

	it('floors both axes at 4', () => {
		expect(gridAxes([p('A', 1, 0), p('B', 2, 2)])).toEqual({ homeMax: 4, awayMax: 4 });
		expect(gridAxes([])).toEqual({ homeMax: 4, awayMax: 4 });
	});

	it('expands only the axis a high pick needs', () => {
		expect(gridAxes([p('A', 7, 1)])).toEqual({ homeMax: 7, awayMax: 4 });
		expect(gridAxes([p('A', 1, 6)])).toEqual({ homeMax: 4, awayMax: 6 });
	});

	it('covers the actual result too', () => {
		expect(gridAxes([p('A', 2, 1)], { home_score: 5, away_score: 0 })).toEqual({
			homeMax: 5,
			awayMax: 4
		});
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

describe('heatColor', () => {
	it('scales intensity with count — max count is the full kind colour', () => {
		// --green token, mixed at t=1.0
		expect(heatColor('exact', 10, 10).bg).toBe('rgb(27, 108, 62)');
	});
	it('keeps a visible tint floor for a single pick in a big pool', () => {
		const lone = heatColor('pre-home', 1, 30);
		// t = 0.22 + 0.78/30 ≈ 0.246 of the way from paper to navy — never paper.
		expect(lone.bg).not.toBe('rgb(241, 235, 222)');
	});
	it('picks readable text colour per background luminance', () => {
		expect(heatColor('pre-home', 10, 10).fg).toBe('#f6f1e6'); // full navy → light text
		expect(heatColor('outcome', 1, 30).fg).toBe('#0e1d40'); // pale gold → ink text
	});
	it('monotonic: more picks never gets lighter', () => {
		const mid = heatColor('pre-away', 5, 10).bg;
		const top = heatColor('pre-away', 10, 10).bg;
		const red = (s: string) => Number(s.slice(4).split(',')[0]);
		// red channel ramps from paper(241) down toward --red(200)
		expect(red(top)).toBeLessThanOrEqual(red(mid));
	});
	it('falls back to the miss ramp for unknown kinds', () => {
		expect(heatColor('unknown', 3, 10).bg).toBe(heatColor('miss', 3, 10).bg);
	});
});
