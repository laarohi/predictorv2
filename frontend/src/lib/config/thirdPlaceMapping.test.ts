/**
 * Structural validation for thirdPlaceMapping.json.
 *
 * The JSON encodes the FIFA 2026 R32 matchup grid — which 3rd-placed team plays
 * which group winner, for each of the C(12,8) = 495 possible qualifying combinations.
 * A separate backend test (test_third_place_mapping.py) validates the contents
 * against the FIFA-source Wikipedia table; these tests validate the *shape*
 * from the frontend's side so the resolver can rely on its invariants.
 */

import { describe, it, expect } from 'vitest';
import mapping from './thirdPlaceMapping.json';

// The 8 group-winner positions that play a 3rd-placed team in R32.
// Mirrors MATCH_TO_WINNER_KEY in bracketResolver.ts.
const EXPECTED_SUB_KEYS = new Set(['1A', '1B', '1D', '1E', '1G', '1I', '1K', '1L']);

const entries = Object.entries(mapping as Record<string, Record<string, string>>);

describe('thirdPlaceMapping.json — structure', () => {
	it('has exactly 495 entries (C(12,8))', () => {
		expect(entries.length).toBe(495);
	});

	it('every key is 8 distinct uppercase letters from A-L in ascending order', () => {
		for (const [key] of entries) {
			expect(key.length, `key ${key}`).toBe(8);
			expect([...key].every((c) => 'ABCDEFGHIJKL'.includes(c)), `key ${key}`).toBe(true);
			expect(key, `key ${key} not alphabetised`).toBe([...key].sort().join(''));
			expect(new Set(key).size, `key ${key} has duplicates`).toBe(8);
		}
	});

	it('every entry has exactly the 8 expected winner sub-keys', () => {
		for (const [key, entry] of entries) {
			expect(new Set(Object.keys(entry)), `entry ${key}`).toEqual(EXPECTED_SUB_KEYS);
		}
	});

	it('every target is a valid 3X code with X inside the entry key', () => {
		const codeRe = /^3[A-L]$/;
		for (const [key, entry] of entries) {
			for (const [winnerPos, target] of Object.entries(entry)) {
				expect(target, `entry ${key}[${winnerPos}]`).toMatch(codeRe);
				const targetGroup = target[1];
				expect(
					key.includes(targetGroup),
					`entry ${key}[${winnerPos}] = ${target} but group ${targetGroup} not in key`
				).toBe(true);
			}
		}
	});

	it('no two winner positions in the same entry map to the same target', () => {
		for (const [key, entry] of entries) {
			const targets = Object.values(entry);
			const unique = new Set(targets);
			expect(unique.size, `entry ${key} has duplicate targets: ${targets.join(', ')}`).toBe(
				targets.length
			);
		}
	});
});
