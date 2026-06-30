import { describe, it, expect } from 'vitest';
import type { Fixture } from '$types';
import { computeTeamFate, tagFate } from './bracketFate';

let nextId = 0;
function fx(
	stage: string,
	home: string,
	away: string,
	opts: { status?: Fixture['status']; outcome?: '1' | '2'; group?: string } = {}
): Fixture {
	const finished = opts.status === 'finished';
	return {
		id: `fx-${nextId++}`,
		home_team: home,
		away_team: away,
		kickoff: '2026-06-20T18:00:00Z',
		stage,
		group: opts.group ?? null,
		match_number: null,
		status: opts.status ?? 'scheduled',
		minute: null,
		is_locked: false,
		time_until_lock: null,
		score:
			finished && opts.outcome
				? {
						home_score: opts.outcome === '1' ? 1 : 0,
						away_score: opts.outcome === '2' ? 1 : 0,
						home_score_et: null,
						away_score_et: null,
						home_penalties: null,
						away_penalties: null,
						outcome: opts.outcome
					}
				: null
	};
}

/** A slot placeholder is what the backend leaves on a KO fixture until BOTH
 *  feeder matches have finished. */
const slot = (stage: string, n: number) => `slot:${stage}:${n}:home`;

describe('computeTeamFate / tagFate', () => {
	it('marks a finished R32 winner as "in" at R16 even when the R16 fixture is still a slot placeholder', () => {
		const fixtures = [
			// Brazil won its R32 match; its R16 opponent is still undecided, so the
			// R16 fixture carries no real names — the exact prod scenario.
			fx('round_of_32', 'Brazil', 'Canada', { status: 'finished', outcome: '1' }),
			fx('round_of_16', slot('round_of_16', 537377), slot('round_of_16', 537378))
		];
		const fate = computeTeamFate(fixtures);

		expect(tagFate(fate, 'Brazil', 'round_of_16')).toBe('in'); // ← the bug fix
		expect(tagFate(fate, 'Brazil', 'round_of_32')).toBe('in');
		// The R32 loser is out at R16 but still counts as having reached R32.
		expect(tagFate(fate, 'Canada', 'round_of_16')).toBe('out');
		expect(tagFate(fate, 'Canada', 'round_of_32')).toBe('in');
	});

	it('also lights up an R16 pick whose fixture IS drawn (both feeders done)', () => {
		const fate = computeTeamFate([
			fx('round_of_16', 'Germany', 'France', { status: 'scheduled' })
		]);
		expect(tagFate(fate, 'Germany', 'round_of_16')).toBe('in');
		expect(tagFate(fate, 'France', 'round_of_16')).toBe('in');
	});

	it('propagates winners through every knockout round, including the champion', () => {
		const fate = computeTeamFate([
			fx('round_of_16', 'Spain', 'Italy', { status: 'finished', outcome: '1' }),
			fx('quarter_final', 'Spain', 'Portugal', { status: 'finished', outcome: '1' }),
			fx('semi_final', 'Spain', 'Brazil', { status: 'finished', outcome: '1' }),
			fx('final', 'Spain', 'Argentina', { status: 'finished', outcome: '1' })
		]);
		expect(tagFate(fate, 'Spain', 'quarter_final')).toBe('in');
		expect(tagFate(fate, 'Spain', 'semi_final')).toBe('in');
		expect(tagFate(fate, 'Spain', 'final')).toBe('in');
		expect(tagFate(fate, 'Spain', 'winner')).toBe('in');
		// Beaten finalist is out of the "winner" stage but reached the final.
		expect(tagFate(fate, 'Argentina', 'final')).toBe('in');
		expect(tagFate(fate, 'Argentina', 'winner')).toBe('out');
	});

	it('returns "tbd" for a team whose deciding match has not finished', () => {
		const fate = computeTeamFate([
			fx('round_of_32', 'Mexico', 'Norway', { status: 'scheduled' })
		]);
		expect(tagFate(fate, 'Mexico', 'round_of_16')).toBe('tbd');
		expect(tagFate(fate, 'Mexico', 'round_of_32')).toBe('in');
	});

	it('marks a group team "out" only once the full 32-team R32 is drawn', () => {
		// 16 R32 fixtures → 32 distinct real teams qualified.
		const r32: Fixture[] = [];
		for (let i = 0; i < 16; i++) {
			r32.push(fx('round_of_32', `Q${2 * i}`, `Q${2 * i + 1}`));
		}
		// A group fixture featuring a team (NONQ) that never appears in the R32.
		const group = fx('group', 'Q0', 'NONQ', { status: 'finished', outcome: '1', group: 'A' });

		const drawn = computeTeamFate([...r32, group]);
		expect(tagFate(drawn, 'NONQ', 'group')).toBe('out'); // didn't make the KO
		expect(tagFate(drawn, 'Q0', 'group')).toBe('in'); // "group winners" pick = reached R32

		// With an incomplete R32 the absence isn't yet certain → not "out".
		const partial = computeTeamFate([...r32.slice(0, 8), group]);
		expect(tagFate(partial, 'NONQ', 'group')).toBe('tbd');
	});

	it('ignores third_place fixtures (they do not drive bracket fate)', () => {
		const fate = computeTeamFate([
			fx('third_place', 'Croatia', 'Morocco', { status: 'finished', outcome: '1' })
		]);
		// Winning the 3rd-place playoff does NOT advance anyone to the final.
		expect(tagFate(fate, 'Croatia', 'final')).toBe('tbd');
	});
});
