/**
 * Frontend ghost-exclusion checks — mirrors the backend's
 * test_ghost_exclusion.py invariants for the client-side chokepoint
 * (utils/ghosts.ts): ghosts must never displace a human in a top-N
 * slice or inflate a participant count.
 */

import { describe, it, expect } from 'vitest';
import { humanCount, humanEntries } from './ghosts';

const board = [
	{ user_name: 'Luke', position: 1, is_ghost: false },
	{ user_name: 'The Crowd', position: 0, is_ghost: true },
	{ user_name: 'Kurt', position: 2, is_ghost: false },
	{ user_name: 'Polymarket', position: 0, is_ghost: true },
	{ user_name: 'Maya', position: 3, is_ghost: false }
];

describe('humanEntries', () => {
	it('drops every ghost and keeps human order', () => {
		expect(humanEntries(board).map((e) => e.user_name)).toEqual(['Luke', 'Kurt', 'Maya']);
	});

	it('a top-N slice over humans can never contain a ghost', () => {
		// The dashboard standings widget pattern: filter first, slice after.
		const topTwo = humanEntries(board).slice(0, 2);
		expect(topTwo.some((e) => e.is_ghost)).toBe(false);
		expect(topTwo.map((e) => e.position)).toEqual([1, 2]);
	});

	it('human row indices line up with backend competition ranking', () => {
		// findIndex over humans (the "is the user in the top 5" gate) must not
		// be shifted by ghosts sitting above the user in the points order.
		const idx = humanEntries(board).findIndex((e) => e.user_name === 'Kurt');
		expect(idx).toBe(1);
	});

	it('handles an empty board', () => {
		expect(humanEntries([])).toEqual([]);
	});
});

describe('humanCount', () => {
	it('counts humans only', () => {
		expect(humanCount(board)).toBe(3);
	});

	it('is zero for an all-ghost list', () => {
		expect(humanCount(board.filter((e) => e.is_ghost))).toBe(0);
	});
});
