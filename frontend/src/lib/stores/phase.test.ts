/**
 * Tests for deriveUxPhase — the pure UX-phase derivation that drives the
 * landing dashboard. Five phases, plus the null-phaseStatus defensive
 * default and the finished-final precedence rule.
 *
 * The function takes a precomputed `finalFinished` boolean (rather than the
 * full fixtures list) so the production derived store can keep `fixtures`
 * out of its dependency chain — see phase.ts for the rationale.
 */

import { describe, it, expect } from 'vitest';
import { deriveUxPhase } from './phase';
import type { PhaseStatus } from '$types';

function makePhase(partial: Partial<PhaseStatus>): PhaseStatus {
	return {
		current_phase: 'phase_1',
		phase1_deadline: null,
		phase1_locked: false,
		is_phase2_active: false,
		phase2_bracket_deadline: null,
		phase2_bracket_locked: false,
		...partial
	};
}

describe('deriveUxPhase', () => {
	it('returns pre_tournament when phaseStatus is null', () => {
		expect(deriveUxPhase(null, false)).toBe('pre_tournament');
	});

	it('returns pre_tournament when phase 1 not yet locked', () => {
		const ps = makePhase({ phase1_locked: false });
		expect(deriveUxPhase(ps, false)).toBe('pre_tournament');
	});

	it('returns group_stage when phase 1 locked but phase 2 not yet activated', () => {
		const ps = makePhase({ phase1_locked: true, is_phase2_active: false });
		expect(deriveUxPhase(ps, false)).toBe('group_stage');
	});

	it('returns between_phases when phase 2 active but bracket still open', () => {
		const ps = makePhase({
			phase1_locked: true,
			is_phase2_active: true,
			phase2_bracket_locked: false
		});
		expect(deriveUxPhase(ps, false)).toBe('between_phases');
	});

	it('returns knockout_stage when phase 2 bracket is locked', () => {
		const ps = makePhase({
			phase1_locked: true,
			is_phase2_active: true,
			phase2_bracket_locked: true
		});
		expect(deriveUxPhase(ps, false)).toBe('knockout_stage');
	});

	it('returns post_competition when the final fixture is finished', () => {
		const ps = makePhase({
			phase1_locked: true,
			is_phase2_active: true,
			phase2_bracket_locked: true
		});
		expect(deriveUxPhase(ps, true)).toBe('post_competition');
	});

	it('post_competition wins over lock-based phases (finished final overrides locked-bracket state)', () => {
		// Real-world race: phase2_bracket_locked stays true post-final. The
		// finished final must take precedence so the dashboard moves to the
		// retrospective layout instead of dwelling on knockout_stage.
		const ps = makePhase({
			phase1_locked: true,
			is_phase2_active: true,
			phase2_bracket_locked: true
		});
		expect(deriveUxPhase(ps, true)).toBe('post_competition');
	});

	it('post_competition is gated by finalFinished, not by any lock state', () => {
		// Sanity: even with everything locked, if the final isn't finished
		// we stay in knockout_stage.
		const ps = makePhase({
			phase1_locked: true,
			is_phase2_active: true,
			phase2_bracket_locked: true
		});
		expect(deriveUxPhase(ps, false)).toBe('knockout_stage');
	});

	it('finalFinished alone (without lock-based phases) still ends in post_competition', () => {
		// Edge case: a competition with a finished final but somehow open
		// phase1 would land in post_competition because post-comp is checked
		// before lock states.
		const ps = makePhase({ phase1_locked: false });
		expect(deriveUxPhase(ps, true)).toBe('post_competition');
	});
});
