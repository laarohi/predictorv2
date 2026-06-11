/**
 * Bracket-misalignment audit — NOT a regular unit test.
 *
 * Finds users whose saved Phase 1 knockout picks no longer fit the bracket
 * implied by their (since-edited) group score predictions. Saving group
 * scores never touches `team_predictions`, so a user who reshuffles a group
 * after saving a full bracket leaves stale advancement rows in the DB while
 * the progress bar still reports the bracket complete.
 *
 * Runs the EXACT pipeline the predictions page uses to render the bracket
 * (computeGroupStandingsMap → predictionToBracketState), so a pick reported
 * here as "no longer resolves" is precisely one the user sees as an empty
 * "—" slot. No re-implemented logic, no parity risk.
 *
 * Workflow (dump first — see backend/scripts/audit_bracket_dump.py):
 *
 *   ssh pred-mplex 'cd ~/predictorv2 && docker compose exec -T backend python -' \
 *       < backend/scripts/audit_bracket_dump.py > /tmp/bracket_dump_prod.json
 *   cd frontend && BRACKET_AUDIT_DUMP=/tmp/bracket_dump_prod.json npx vitest run bracketAudit
 *
 * Without BRACKET_AUDIT_DUMP set, the suite skips itself (normal CI runs).
 */
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import {
	ROUND_OF_32,
	ROUND_OF_16,
	QUARTER_FINALS,
	SEMI_FINALS,
	FINAL,
	type KnockoutMatch
} from '$lib/config/bracketConfig';
import type { BracketPrediction, Fixture, MatchPrediction } from '$types';
import {
	bracketStateToPrediction,
	initializeBracketState,
	predictionToBracketState,
	setMatchWinner,
	type BracketState
} from './bracketResolver';
import { computeGroupStandingsMap, type GroupFixtures, type TeamStanding } from './standings';

interface DumpFixture {
	id: string;
	group: string | null;
	home_team: string;
	away_team: string;
}

interface DumpUser {
	id: string;
	name: string;
	email: string;
	match_predictions: { fixture_id: string; home_score: number; away_score: number }[];
	bracket: { team: string; stage: string }[];
}

interface Dump {
	fifa_rankings: string[];
	fixtures: DumpFixture[];
	users: DumpUser[];
}

const DUMP_PATH = process.env.BRACKET_AUDIT_DUMP;
const auditDescribe = DUMP_PATH ? describe : describe.skip;

/** team_predictions rows (singular stage names) → frontend BracketPrediction. */
function rowsToBracket(rows: { team: string; stage: string }[]): BracketPrediction {
	const by = (stage: string) => rows.filter((r) => r.stage === stage).map((r) => r.team);
	return {
		group_winners: {},
		round_of_32: by('round_of_32'),
		round_of_16: by('round_of_16'),
		quarter_finals: by('quarter_final'),
		semi_finals: by('semi_final'),
		final: by('final'),
		winner: by('winner')[0] || ''
	};
}

function participantsOf(state: BracketState, matches: KnockoutMatch[]): Set<string> {
	const out = new Set<string>();
	for (const m of matches) {
		const r = state.matchResults[m.matchNumber];
		if (r?.homeTeam) out.add(r.homeTeam);
		if (r?.awayTeam) out.add(r.awayTeam);
	}
	return out;
}

function winnersOf(state: BracketState, matches: KnockoutMatch[]): Set<string> {
	const out = new Set<string>();
	for (const m of matches) {
		const w = state.matchResults[m.matchNumber]?.winner;
		if (w) out.add(w);
	}
	return out;
}

// Always-on guard for the audit logic itself: a bracket built entirely
// through the resolver against a given standings map must audit clean.
// If this fails, the audit's stale/orphan checks are producing false
// positives and any prod report is untrustworthy.
describe('bracket audit self-check', () => {
	it('reports zero issues for a bracket consistent with its standings', () => {
		const groups = 'ABCDEFGHIJKL'.split('');
		const standings: Record<string, TeamStanding[]> = {};
		for (const [gi, g] of groups.entries()) {
			standings[g] = [0, 1, 2, 3].map((pos) => ({
				team: `Team ${g}${pos + 1}`,
				group: g,
				played: 3,
				won: 3 - pos,
				drawn: 0,
				lost: pos,
				// Stagger goals so the cross-group third-place ranking is total
				// (no ties to fall through to alphabetical/rankings).
				goalsFor: 24 - gi - pos * 4,
				goalsAgainst: pos * 4,
				goalDifference: 24 - gi - pos * 8,
				points: (3 - pos) * 3
			}));
		}

		let state = initializeBracketState(standings, []);
		for (const matches of [ROUND_OF_32, ROUND_OF_16, QUARTER_FINALS, SEMI_FINALS, [FINAL]]) {
			for (const m of matches) {
				const home = state.matchResults[m.matchNumber]?.homeTeam;
				expect(home, `match ${m.matchNumber} should have a home team`).toBeTruthy();
				state = setMatchWinner(state, m.matchNumber, home as string);
			}
		}
		const consistent = bracketStateToPrediction(state);

		// Re-resolve the consistent prediction the way the audit does.
		const reState = predictionToBracketState(consistent, standings, []);
		const resolvedRoster = participantsOf(reState, ROUND_OF_32);
		const storedRoster = new Set(consistent.round_of_32.filter((t) => t));
		expect(storedRoster.size).toBe(32);
		expect([...storedRoster].filter((t) => !resolvedRoster.has(t))).toEqual([]);
		expect([...resolvedRoster].filter((t) => !storedRoster.has(t))).toEqual([]);

		const finalWinner = reState.matchResults[FINAL.matchNumber]?.winner;
		const rounds: [Set<string>, string[]][] = [
			[winnersOf(reState, ROUND_OF_32), consistent.round_of_16],
			[winnersOf(reState, ROUND_OF_16), consistent.quarter_finals],
			[winnersOf(reState, QUARTER_FINALS), consistent.semi_finals],
			[winnersOf(reState, SEMI_FINALS), consistent.final],
			[new Set(finalWinner ? [finalWinner] : []), consistent.winner ? [consistent.winner] : []]
		];
		for (const [applied, storedPicks] of rounds) {
			expect(storedPicks.length).toBeGreaterThan(0);
			expect(storedPicks.filter((t) => !applied.has(t))).toEqual([]);
		}
	});
});

auditDescribe('bracket misalignment audit', () => {
	it('reports per-user alignment of saved bracket vs predicted standings', () => {
		const dump: Dump = JSON.parse(readFileSync(DUMP_PATH as string, 'utf-8'));

		const byGroup = new Map<string, Fixture[]>();
		for (const f of dump.fixtures) {
			if (!f.group) continue;
			const fixture = {
				id: f.id,
				group: f.group,
				home_team: f.home_team,
				away_team: f.away_team,
				stage: 'group'
			} as unknown as Fixture;
			const arr = byGroup.get(f.group) || [];
			arr.push(fixture);
			byGroup.set(f.group, arr);
		}
		const groupFixtures: GroupFixtures[] = Array.from(byGroup.entries())
			.sort(([a], [b]) => a.localeCompare(b))
			.map(([group, fixtures]) => ({ group, fixtures }));
		const totalGroupFixtures = dump.fixtures.length;

		const lines: string[] = [];
		let misaligned = 0;
		let aligned = 0;
		let noBracket = 0;

		for (const user of dump.users) {
			const who = `${user.name} <${user.email}>`;
			if (user.bracket.length === 0) {
				noBracket++;
				lines.push(`  – ${who} — no bracket saved`);
				continue;
			}

			const predMap = new Map<string, MatchPrediction>();
			for (const p of user.match_predictions) {
				predMap.set(p.fixture_id, {
					fixture_id: p.fixture_id,
					home_score: p.home_score,
					away_score: p.away_score
				} as unknown as MatchPrediction);
			}

			const standingsMap = computeGroupStandingsMap(
				groupFixtures,
				predMap,
				dump.fifa_rankings
			);
			const bracket = rowsToBracket(user.bracket);
			const state = predictionToBracketState(bracket, standingsMap, dump.fifa_rankings);

			const issues: string[] = [];
			if (predMap.size < totalGroupFixtures) {
				issues.push(
					`group predictions incomplete (${predMap.size}/${totalGroupFixtures}) — seeding below is unreliable`
				);
			}

			// 1. R32 roster drift: saved qualifiers vs qualifiers implied by
			//    current group score predictions.
			const resolvedRoster = participantsOf(state, ROUND_OF_32);
			const storedRoster = new Set(bracket.round_of_32);
			const stale = [...storedRoster].filter((t) => !resolvedRoster.has(t)).sort();
			const missing = [...resolvedRoster].filter((t) => !storedRoster.has(t)).sort();
			if (stale.length || missing.length) {
				issues.push(
					`R32 roster drift — saved but no longer qualifying: [${stale.join(', ')}] · ` +
						`now qualifying but not in saved bracket: [${missing.join(', ')}]`
				);
			}

			// 2. Per-round orphaned picks: a saved advancement pick that the UI
			//    resolver could not place as the winner of any match in the
			//    previous round (renders as an empty "—" slot downstream).
			const finalWinner = state.matchResults[FINAL.matchNumber]?.winner;
			const rounds: [string, Set<string>, string[]][] = [
				['R32→R16', winnersOf(state, ROUND_OF_32), bracket.round_of_16],
				['R16→QF', winnersOf(state, ROUND_OF_16), bracket.quarter_finals],
				['QF→SF', winnersOf(state, QUARTER_FINALS), bracket.semi_finals],
				['SF→Final', winnersOf(state, SEMI_FINALS), bracket.final],
				['Champion', new Set(finalWinner ? [finalWinner] : []), bracket.winner ? [bracket.winner] : []]
			];
			let orphanCount = 0;
			for (const [label, applied, storedPicks] of rounds) {
				const orphans = storedPicks.filter((t) => !applied.has(t)).sort();
				if (orphans.length) {
					orphanCount += orphans.length;
					issues.push(`${label}: ${orphans.length} saved pick(s) no longer resolve — ${orphans.join(', ')}`);
				}
			}

			const storedTotal =
				storedRoster.size +
				bracket.round_of_16.length +
				bracket.quarter_finals.length +
				bracket.semi_finals.length +
				bracket.final.length +
				(bracket.winner ? 1 : 0);
			const validTotal = storedTotal - stale.length - orphanCount;

			if (issues.length) {
				misaligned++;
				lines.push(
					`✗ ${who} — MISALIGNED: ${validTotal}/${storedTotal} saved bracket picks still fit ` +
						`(progress bar claims all ${storedTotal})`
				);
				for (const issue of issues) lines.push(`      ${issue}`);
			} else {
				aligned++;
				lines.push(`✓ ${who} — aligned (${storedTotal}/63 picks)`);
			}
		}

		const summary = [
			'',
			'================ BRACKET MISALIGNMENT AUDIT ================',
			`users: ${dump.users.length} · aligned: ${aligned} · MISALIGNED: ${misaligned} · no bracket: ${noBracket}`,
			'-------------------------------------------------------------',
			...lines,
			'============================================================='
		].join('\n');
		// eslint-disable-next-line no-console
		console.log(summary);

		// The audit is a report, not a gate — it always passes; read stdout.
		expect(dump.users.length).toBeGreaterThanOrEqual(0);
	});
});
