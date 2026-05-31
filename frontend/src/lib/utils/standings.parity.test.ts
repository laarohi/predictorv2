/**
 * Cross-language parity for the FIFA WC2026 Article 13 tiebreaker.
 *
 * This is the frontend half of a two-language guarantee: the SAME golden cases
 * in `shared/standings-parity-cases.json` are also run by the backend pytest
 * suite (`backend/tests/test_standings_parity.py`). Both implementations must
 * produce the identical ranked order + warnings for every case. If the frontend
 * `standings.ts` and the backend `standings.py` ever drift, one of these two
 * suites fails — which is the whole reason the file exists.
 *
 * The fixture lives at the repo root (outside the SvelteKit project), so we
 * locate it with a Node parent-walk rather than a Vite JSON import (which is
 * fenced to the project root). Mirrors the backend's `_find_file`.
 */

import { describe, it, expect } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
	applyFifaTiebreakers,
	calculateGroupStandingsWithWarnings,
	type TeamStanding,
	type TieWarning
} from './standings';
import type { Fixture, MatchPrediction } from '$types';

interface ParityMatch {
	home: string;
	away: string;
	home_score: number;
	away_score: number;
}
interface ParityTeam {
	team: string;
	group: string;
	points: number;
	gd: number;
	gf: number;
}
interface ParityWarning {
	tied_teams: string[];
	context: string;
}
interface ParityCase {
	name: string;
	context: 'group_standings' | 'third_place_qualifying';
	fifa_rankings: string[];
	group?: string;
	matches?: ParityMatch[];
	teams?: ParityTeam[];
	expected_order: string[];
	expected_warnings: ParityWarning[];
}

function findCasesFile(): string | null {
	let dir = dirname(fileURLToPath(import.meta.url));
	for (let i = 0; i < 12; i++) {
		const candidate = resolve(dir, 'shared/standings-parity-cases.json');
		if (existsSync(candidate)) return candidate;
		const parent = dirname(dir);
		if (parent === dir) break;
		dir = parent;
	}
	return null;
}

const casesFile = findCasesFile();
const cases: ParityCase[] = casesFile
	? (JSON.parse(readFileSync(casesFile, 'utf-8')) as { cases: ParityCase[] }).cases
	: [];

// --- builders to feed the production entry points ---------------------------

function buildFixture(index: number, m: ParityMatch, group: string): Fixture {
	return {
		id: `m${index}`,
		home_team: m.home,
		away_team: m.away,
		kickoff: '2026-06-11T19:00:00Z',
		stage: 'group',
		group,
		match_number: null,
		status: 'finished',
		minute: null,
		is_locked: true,
		time_until_lock: null,
		score: null
	};
}

function buildPrediction(index: number, m: ParityMatch): [string, MatchPrediction] {
	return [
		`m${index}`,
		{
			id: `pred-m${index}`,
			fixture_id: `m${index}`,
			home_score: m.home_score,
			away_score: m.away_score,
			phase: 'phase_1',
			locked_at: null,
			created_at: '2026-06-11T00:00:00Z',
			updated_at: '2026-06-11T00:00:00Z',
			is_locked: false
		}
	];
}

function buildTeamStanding(t: ParityTeam): TeamStanding {
	return {
		team: t.team,
		group: t.group,
		played: 0,
		won: 0,
		drawn: 0,
		lost: 0,
		goalsFor: t.gf,
		goalsAgainst: t.gf - t.gd,
		goalDifference: t.gd,
		points: t.points
	};
}

/** Run one case through the production frontend ranking code. */
function runCase(c: ParityCase): { order: string[]; warnings: TieWarning[] } {
	if (c.context === 'group_standings') {
		const matches = c.matches ?? [];
		const fixtures = matches.map((m, i) => buildFixture(i, m, c.group!));
		const predictions = new Map(matches.map((m, i) => buildPrediction(i, m)));
		const { standings, warnings } = calculateGroupStandingsWithWarnings(
			fixtures,
			predictions,
			c.group!,
			c.fifa_rankings
		);
		return { order: standings.map((t) => t.team), warnings };
	}
	// third_place_qualifying — pre-aggregated, H2H not applicable.
	const teams = (c.teams ?? []).map(buildTeamStanding);
	const { sorted, warnings } = applyFifaTiebreakers(
		teams,
		[],
		new Map(),
		'third_place_qualifying',
		c.fifa_rankings
	);
	return { order: sorted.map((t) => t.team), warnings };
}

/** Reduce warnings to (sorted tied teams, context) pairs — `group` is ambiguous
 *  for cross-group ties, so we don't assert it. */
function normalizeWarnings(warnings: { tiedTeams: string[]; context: string }[]): string[] {
	return warnings.map((w) => `${[...w.tiedTeams].sort().join('+')}|${w.context}`).sort();
}
function expectedWarnings(c: ParityCase): string[] {
	return c.expected_warnings.map((w) => `${[...w.tied_teams].sort().join('+')}|${w.context}`).sort();
}

// --- the suite --------------------------------------------------------------

describe('standings parity (frontend ↔ backend golden cases)', () => {
	it('found the shared fixture file (else parity is untested)', () => {
		expect(casesFile, 'shared/standings-parity-cases.json not found via parent-walk').not.toBeNull();
		expect(cases.length).toBeGreaterThan(0);
	});

	for (const c of cases) {
		it(`${c.name}`, () => {
			const { order, warnings } = runCase(c);
			expect(order, `order mismatch for ${c.name}`).toEqual(c.expected_order);
			expect(normalizeWarnings(warnings), `warning mismatch for ${c.name}`).toEqual(
				expectedWarnings(c)
			);
		});
	}
});
