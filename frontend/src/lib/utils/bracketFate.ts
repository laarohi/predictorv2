import type { Fixture } from '$types';

/**
 * Real tournament fate for bracket-pick colouring on the profile page.
 *
 * The profile bracket re-derives, purely from the fixture list, which teams
 * have actually reached each knockout round (green "in") vs been knocked out
 * (red "out"). The subtlety this module exists to handle: advancement must be
 * read from match RESULTS, not from fixture STRUCTURE.
 *
 * The backend resolver only stamps a knockout fixture's real team names once
 * BOTH of its feeder matches have finished. So a team that has clearly
 * advanced (e.g. won its Round-of-32 match) does NOT appear in any Round-of-16
 * fixture until its opponent is also decided — that fixture stays
 * `slot:… v slot:…`. Scanning fixtures alone therefore misses advanced teams
 * whose next match isn't drawn yet. We close that gap by also recording the
 * WINNER of every finished match as having reached the next round.
 */

/** Stage progression index — higher = deeper. `group` and `third_place` are
 *  deliberately absent: they don't drive bracket fate. */
export const STAGE_IDX: Record<string, number> = {
	round_of_32: 1,
	round_of_16: 2,
	quarter_final: 3,
	semi_final: 4,
	final: 5,
	winner: 6
};

/** Where the winner of each knockout stage advances TO. */
export const NEXT_STAGE: Record<string, string> = {
	round_of_32: 'round_of_16',
	round_of_16: 'quarter_final',
	quarter_final: 'semi_final',
	semi_final: 'final',
	final: 'winner'
};

export interface TeamFate {
	/** stage key → set of teams that have actually reached that round */
	reached: Map<string, Set<string>>;
	/** team → index of the last stage their run got past (0 = out at the group) */
	outAt: Map<string, number>;
}

const isReal = (t: string): boolean => !!t && !t.toLowerCase().startsWith('slot:');

/**
 * Derive each team's real tournament fate from the fixture list.
 *
 * `reached(stage)` holds a team when EITHER it literally appears in a drawn
 * fixture at that stage OR it won its feeder match in the previous round
 * (advancement known the instant the result lands — see module note). `outAt`
 * records the depth at which a run ended: a finished-match loser is out at that
 * stage's index; a group team absent from a fully-drawn R32 is out at 0.
 */
export function computeTeamFate(fixtures: Fixture[]): TeamFate {
	const reached = new Map<string, Set<string>>();
	const outAt = new Map<string, number>();
	const addReached = (stage: string, team: string) => {
		if (!reached.has(stage)) reached.set(stage, new Set());
		reached.get(stage)!.add(team);
	};

	for (const f of fixtures) {
		const idx = STAGE_IDX[f.stage];
		if (!idx) continue; // group + third_place don't drive fate
		for (const t of [f.home_team, f.away_team]) {
			if (isReal(t)) addReached(f.stage, t);
		}
		if (f.status === 'finished' && f.score && isReal(f.home_team) && isReal(f.away_team)) {
			// outcome already resolves pens → ET → FT, so KO winner/loser are exact
			const winner =
				f.score.outcome === '1' ? f.home_team : f.score.outcome === '2' ? f.away_team : null;
			const loser =
				f.score.outcome === '1' ? f.away_team : f.score.outcome === '2' ? f.home_team : null;
			if (loser) outAt.set(loser, idx);
			// The winner has reached the NEXT round — record it even if that
			// round's fixture is still a slot placeholder (opponent undecided).
			const next = NEXT_STAGE[f.stage];
			if (winner && next) addReached(next, winner);
		}
	}

	// Group-stage elimination is only certain once the real R32 is fully drawn
	// (all 32 slots resolved to teams) — then anyone absent is out at the group.
	const r32 = reached.get('round_of_32');
	if (r32 && r32.size >= 32) {
		for (const f of fixtures) {
			if (f.stage !== 'group') continue;
			for (const t of [f.home_team, f.away_team]) {
				if (!r32.has(t)) outAt.set(t, 0);
			}
		}
	}
	return { reached, outAt };
}

/** Fate of one bracket tag: did this team actually reach this stage? */
export function tagFate(fate: TeamFate, team: string, stage: string): 'in' | 'out' | 'tbd' {
	// "Group winners" picks succeed exactly when the team makes the knockout.
	const idx = stage === 'group' ? STAGE_IDX.round_of_32 : STAGE_IDX[stage];
	if (!idx) return 'tbd';
	const key = stage === 'group' ? 'round_of_32' : stage;
	if (fate.reached.get(key)?.has(team)) return 'in';
	const out = fate.outAt.get(team);
	if (out !== undefined && out < idx) return 'out';
	return 'tbd';
}
