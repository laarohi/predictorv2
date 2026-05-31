/**
 * Utility functions for calculating group standings and qualifying teams.
 *
 * Tiebreaker chain — FIFA World Cup 2026 Regulations, Article 13. This MUST
 * stay byte-for-byte equivalent to the backend (`backend/app/services/
 * standings.py`); the shared golden cases in `shared/standings-parity-cases.json`
 * are run by both this module's Vitest suite and the backend pytest suite to
 * guarantee it. Change one side → change both.
 *
 *   Among teams equal on POINTS:
 *     Step 1 — head-to-head among the tied teams' mutual matches:
 *       a) H2H points (desc)  b) H2H goal difference (desc)  c) H2H goals (desc)
 *     Step 2 — if any subset is still tied after step 1:
 *       • Re-apply a-c using ONLY the still-tied subset's mutual matches
 *         (re-scoped H2H, modelled as recursion). If a tie still survives:
 *       d) overall goal difference (desc)   e) overall goals scored (desc)
 *       f) fair-play conduct — untracked, so we emit a TieWarning and proceed.
 *       (The "second step does not restart" clause: once we descend from
 *        step 1 to d/e/f we never loop back to H2H.)
 *     Step 3 — FIFA Rankings (most recent edition). Listed teams rank above
 *       unlisted by ranking index; the list comes from the backend
 *       `/fixtures/fifa-rankings` endpoint via the `fifaRankings` store.
 *     Last resort — alphabetical (only when FIFA Rankings cover none of the
 *       still-tied teams).
 *
 * For the cross-group third-place ranking, step 1 H2H is not applicable (the
 * teams come from different groups), so the chain collapses to overall points
 * → GD → GF → fair-play(warn) → FIFA Rankings → alphabetical.
 *
 * Every fair-play-tier descent emits a TieWarning so the UI can flag "this
 * order isn't fully FIFA-resolved — it needed conduct data we don't track."
 */

import type { Fixture, MatchPrediction } from '$types';

export interface TeamStanding {
	team: string;
	group: string;
	played: number;
	won: number;
	drawn: number;
	lost: number;
	goalsFor: number;
	goalsAgainst: number;
	goalDifference: number;
	points: number;
}

/** A tie that couldn't be broken by FIFA's chain up to H2H goals — resolved
 *  alphabetically. The UI should surface this so the user can adjust scores. */
export interface TieWarning {
	group: string;
	tiedTeams: string[]; // alphabetically sorted for stable display
	context: 'group_standings' | 'third_place_qualifying';
}

interface H2hStats {
	points: number;
	goalDifference: number;
	goalsFor: number;
}

/** Build the raw (un-tiebroken) standings map for one group. Internal helper. */
function _buildRawStandings(
	fixtures: Fixture[],
	predictions: Map<string, MatchPrediction>,
	group: string
): Map<string, TeamStanding> {
	const teams = new Set<string>();
	fixtures.forEach((f) => {
		if (f.home_team) teams.add(f.home_team);
		if (f.away_team) teams.add(f.away_team);
	});

	const standings = new Map<string, TeamStanding>();
	teams.forEach((team) => {
		standings.set(team, {
			team,
			group,
			played: 0,
			won: 0,
			drawn: 0,
			lost: 0,
			goalsFor: 0,
			goalsAgainst: 0,
			goalDifference: 0,
			points: 0
		});
	});

	fixtures.forEach((fixture) => {
		const prediction = predictions.get(fixture.id);
		if (!prediction) return;
		const home = standings.get(fixture.home_team);
		const away = standings.get(fixture.away_team);
		if (!home || !away) return;

		home.played++;
		away.played++;
		home.goalsFor += prediction.home_score;
		home.goalsAgainst += prediction.away_score;
		away.goalsFor += prediction.away_score;
		away.goalsAgainst += prediction.home_score;

		if (prediction.home_score > prediction.away_score) {
			home.won++;
			home.points += 3;
			away.lost++;
		} else if (prediction.home_score < prediction.away_score) {
			away.won++;
			away.points += 3;
			home.lost++;
		} else {
			home.drawn++;
			away.drawn++;
			home.points += 1;
			away.points += 1;
		}
	});

	standings.forEach((s) => {
		s.goalDifference = s.goalsFor - s.goalsAgainst;
	});

	return standings;
}

/** Compute the H2H mini-table for `tiedTeams` using `fixtures` + `predictions`.
 *  Returns a map from team name → H2H stats. */
function _computeH2hStats(
	tiedTeams: TeamStanding[],
	fixtures: Fixture[],
	predictions: Map<string, MatchPrediction>
): Map<string, H2hStats> {
	const tiedNames = new Set(tiedTeams.map((t) => t.team));
	const stats = new Map<string, H2hStats>();
	for (const t of tiedTeams) {
		stats.set(t.team, { points: 0, goalDifference: 0, goalsFor: 0 });
	}

	for (const fixture of fixtures) {
		if (!tiedNames.has(fixture.home_team) || !tiedNames.has(fixture.away_team)) continue;
		const pred = predictions.get(fixture.id);
		if (!pred) continue;

		const h = stats.get(fixture.home_team)!;
		const a = stats.get(fixture.away_team)!;
		if (pred.home_score > pred.away_score) {
			h.points += 3;
		} else if (pred.home_score < pred.away_score) {
			a.points += 3;
		} else {
			h.points += 1;
			a.points += 1;
		}
		h.goalsFor += pred.home_score;
		h.goalDifference += pred.home_score - pred.away_score;
		a.goalsFor += pred.away_score;
		a.goalDifference += pred.away_score - pred.home_score;
	}

	return stats;
}

/** Find the longest run starting at `start` where the keyFn returns the same value. */
function _segmentEnd<T>(items: T[], start: number, keyFn: (t: T) => unknown): number {
	const base = JSON.stringify(keyFn(items[start]));
	let j = start + 1;
	while (j < items.length && JSON.stringify(keyFn(items[j])) === base) j++;
	return j;
}

/** Generic segment walker: sort `items` by `sortCmp`, then for each maximal run
 *  sharing the same `segKey` value call `onSegment` (singletons pass through).
 *  Mirrors backend `_walk_segments`. */
function _walkSegments(
	items: TeamStanding[],
	sortCmp: (a: TeamStanding, b: TeamStanding) => number,
	segKey: (t: TeamStanding) => unknown,
	onSegment: (segment: TeamStanding[]) => TeamStanding[]
): TeamStanding[] {
	const sorted = [...items].sort(sortCmp);
	const out: TeamStanding[] = [];
	let i = 0;
	while (i < sorted.length) {
		const j = _segmentEnd(sorted, i, segKey);
		const segment = sorted.slice(i, j);
		out.push(...(segment.length === 1 ? segment : onSegment(segment)));
		i = j;
	}
	return out;
}

/** Article 13 Step 1 (H2H a-c) with the Step 2 "re-apply to the remaining teams
 *  only" clause modelled as recursion: each still-tied subset recomputes its H2H
 *  over that subset's mutual matches. Drops to Step 2 d-f/g when H2H can't
 *  separate any team, or when H2H isn't applicable (cross-group ranking).
 *  Mirrors backend `_resolve_points_tied_subset`. */
function _resolvePointsTiedSubset(
	tied: TeamStanding[],
	fixtures: Fixture[],
	predictions: Map<string, MatchPrediction>,
	context: TieWarning['context'],
	fifaRankings: string[],
	warnings: TieWarning[]
): TeamStanding[] {
	// H2H isn't applicable across groups (third-place ranking) — go to Step 2.
	const allowH2h = fixtures.length > 0 && context === 'group_standings';
	if (!allowH2h) {
		return _resolveStep2Overall(tied, context, fifaRankings, warnings);
	}

	const h2h = _computeH2hStats(tied, fixtures, predictions);
	const byH2h = [...tied].sort((a, b) => {
		const sa = h2h.get(a.team)!;
		const sb = h2h.get(b.team)!;
		if (sb.points !== sa.points) return sb.points - sa.points;
		if (sb.goalDifference !== sa.goalDifference) return sb.goalDifference - sa.goalDifference;
		return sb.goalsFor - sa.goalsFor;
	});

	const out: TeamStanding[] = [];
	let i = 0;
	while (i < byH2h.length) {
		const j = _segmentEnd(byH2h, i, (t) => {
			const s = h2h.get(t.team)!;
			return [s.points, s.goalDifference, s.goalsFor];
		});
		const segment = byH2h.slice(i, j);
		if (segment.length === 1) {
			out.push(segment[0]);
		} else if (segment.length === tied.length) {
			// H2H separated nobody → descend to Step 2 (the "does not restart" clause).
			out.push(..._resolveStep2Overall(segment, context, fifaRankings, warnings));
		} else {
			// H2H separated some → recurse on the still-tied subset (re-scoped H2H).
			out.push(
				..._resolvePointsTiedSubset(segment, fixtures, predictions, context, fifaRankings, warnings)
			);
		}
		i = j;
	}
	return out;
}

/** Article 13 Step 2 d (overall GD) then e (overall GF). Mirrors backend
 *  `_resolve_step_2_overall`. */
function _resolveStep2Overall(
	tied: TeamStanding[],
	context: TieWarning['context'],
	fifaRankings: string[],
	warnings: TieWarning[]
): TeamStanding[] {
	return _walkSegments(
		tied,
		(a, b) => b.goalDifference - a.goalDifference || b.goalsFor - a.goalsFor,
		(t) => t.goalDifference,
		(segment) => _resolveStep2e(segment, context, fifaRankings, warnings)
	);
}

/** Article 13 Step 2 e (overall GF). Still tied → fair-play(warn) + Step 3.
 *  Mirrors backend `_resolve_step_2e`. */
function _resolveStep2e(
	tied: TeamStanding[],
	context: TieWarning['context'],
	fifaRankings: string[],
	warnings: TieWarning[]
): TeamStanding[] {
	return _walkSegments(
		tied,
		(a, b) => b.goalsFor - a.goalsFor,
		(t) => t.goalsFor,
		(segment) => _resolveFairPlayThenRankings(segment, context, fifaRankings, warnings)
	);
}

/** Article 13 Step 2 f (fair-play — untracked, so emit a warning) + Step 3 g/h
 *  (FIFA Rankings). Listed teams rank above unlisted by ranking index; teams not
 *  on the list fall to alphabetical. Mirrors backend `_resolve_fair_play_then_rankings`. */
function _resolveFairPlayThenRankings(
	tied: TeamStanding[],
	context: TieWarning['context'],
	fifaRankings: string[],
	warnings: TieWarning[]
): TeamStanding[] {
	warnings.push({
		group: tied[0].group,
		tiedTeams: tied.map((t) => t.team).sort((a, b) => a.localeCompare(b)),
		context
	});
	const rankIndex = new Map(fifaRankings.map((team, i) => [team, i] as const));
	const notListed = fifaRankings.length + 1; // any value larger than the max listed index
	return [...tied].sort((a, b) => {
		const ra = rankIndex.get(a.team) ?? notListed;
		const rb = rankIndex.get(b.team) ?? notListed;
		return ra - rb || a.team.localeCompare(b.team);
	});
}

/** Apply FIFA WC2026 Article 13. Returns `{ sorted, warnings }`. Pass
 *  `fixtures: []` and `context: 'third_place_qualifying'` to skip H2H (cross-group
 *  sorts). `fifaRankings` is the ordered ranking list (index 0 = rank #1) used by
 *  Step 3; default `[]` falls through to alphabetical. Mirrors backend
 *  `_apply_fifa_tiebreakers`. */
export function applyFifaTiebreakers(
	teams: TeamStanding[],
	fixtures: Fixture[],
	predictions: Map<string, MatchPrediction>,
	context: TieWarning['context'],
	fifaRankings: string[] = []
): { sorted: TeamStanding[]; warnings: TieWarning[] } {
	const warnings: TieWarning[] = [];
	// Sort by POINTS only and walk segments tied on points — Article 13's
	// "equal on points → head-to-head" triggers on points equality, NOT on full
	// (points, GD, GF) equality (the legacy bug that ranked overall GD ahead of H2H).
	const byPoints = [...teams].sort((a, b) => b.points - a.points);
	const out: TeamStanding[] = [];
	let i = 0;
	while (i < byPoints.length) {
		const j = _segmentEnd(byPoints, i, (t) => t.points);
		const segment = byPoints.slice(i, j);
		if (segment.length === 1) {
			out.push(segment[0]);
		} else {
			out.push(
				..._resolvePointsTiedSubset(segment, fixtures, predictions, context, fifaRankings, warnings)
			);
		}
		i = j;
	}
	return { sorted: out, warnings };
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/** Calculate standings for a single group based on predictions. `fifaRankings`
 *  (ordered, index 0 = rank #1) feeds Article 13 Step 3; default `[]`. */
export function calculateGroupStandings(
	fixtures: Fixture[],
	predictions: Map<string, MatchPrediction>,
	group: string,
	fifaRankings: string[] = []
): TeamStanding[] {
	return calculateGroupStandingsWithWarnings(fixtures, predictions, group, fifaRankings).standings;
}

/** Same as calculateGroupStandings but also returns fair-play-tier tie warnings. */
export function calculateGroupStandingsWithWarnings(
	fixtures: Fixture[],
	predictions: Map<string, MatchPrediction>,
	group: string,
	fifaRankings: string[] = []
): { standings: TeamStanding[]; warnings: TieWarning[] } {
	const raw = _buildRawStandings(fixtures, predictions, group);
	const teams = Array.from(raw.values());
	const { sorted, warnings } = applyFifaTiebreakers(
		teams,
		fixtures,
		predictions,
		'group_standings',
		fifaRankings
	);
	return { standings: sorted, warnings };
}

export interface GroupFixtures {
	group: string;
	fixtures: Fixture[];
}

/** Get all unique teams from group fixtures (sorted alphabetically). */
export function getAllTeamsFromGroups(groupFixtures: GroupFixtures[]): string[] {
	const teams = new Set<string>();
	for (const { fixtures } of groupFixtures) {
		for (const fixture of fixtures) {
			if (fixture.home_team) teams.add(fixture.home_team);
			if (fixture.away_team) teams.add(fixture.away_team);
		}
	}
	return Array.from(teams).sort();
}

/** Compute group standings map for the bracket component. `fifaRankings` feeds
 *  Article 13 Step 3 so the bracket seeds match the backend; default `[]`. */
export function computeGroupStandingsMap(
	groupFixtures: GroupFixtures[],
	predictions: Map<string, MatchPrediction>,
	fifaRankings: string[] = []
): Record<string, TeamStanding[]> {
	return computeGroupStandingsMapWithWarnings(groupFixtures, predictions, fifaRankings).standingsMap;
}

/** Same as computeGroupStandingsMap but also returns all per-group tie warnings. */
export function computeGroupStandingsMapWithWarnings(
	groupFixtures: GroupFixtures[],
	predictions: Map<string, MatchPrediction>,
	fifaRankings: string[] = []
): { standingsMap: Record<string, TeamStanding[]>; warnings: TieWarning[] } {
	const standingsMap: Record<string, TeamStanding[]> = {};
	const warnings: TieWarning[] = [];

	for (const { group, fixtures } of groupFixtures) {
		const result = calculateGroupStandingsWithWarnings(fixtures, predictions, group, fifaRankings);
		standingsMap[group] = result.standings;
		warnings.push(...result.warnings);
	}

	return { standingsMap, warnings };
}

/**
 * Filter tie-warnings down to those that actually affect qualification.
 *
 * A tiebreaker warning only *matters* when the tie straddles the qualification
 * boundary. Ties entirely within qualifying positions (all teams advance
 * regardless of order) or entirely within non-qualifying positions (all out
 * regardless of order) don't change outcomes — surfacing those warnings would
 * falsely alarm the user about ties with no consequence.
 *
 * Used by the third-place modal in the predictions wizard: with `qualifyingCount = 8`
 * a tie at positions 8↔9 is shown (one in, one out), but ties at 1↔2 or 11↔12
 * are suppressed. Generalises to any "top N of M qualify" scheme.
 *
 * Per-group tie warnings are NOT filtered through this — within a group every
 * tie matters (1st vs 2nd determines the bracket side, 2nd vs 3rd determines
 * direct vs best-3rd qualification, etc.).
 *
 * @param warnings        Tie warnings from {@link applyFifaTiebreakers}.
 * @param sorted          Standings array in ranked order; tied teams' positions
 *                        are looked up here.
 * @param qualifyingCount How many top positions qualify (e.g. 8 for FIFA 2026
 *                        third-place ranking).
 * @returns Subset of `warnings` whose tied teams cross the qualifying boundary.
 */
export function filterQualificationRelevantWarnings(
	warnings: TieWarning[],
	sorted: TeamStanding[],
	qualifyingCount: number
): TieWarning[] {
	return warnings.filter((w) => {
		// Locate each tied team in the sorted standings. Defensive against
		// stale warnings whose teams have since been removed from `sorted`.
		const positions = w.tiedTeams
			.map((team) => sorted.findIndex((t) => t.team === team))
			.filter((p) => p >= 0);
		if (positions.length < 2) return false;
		const hasQualifier = positions.some((p) => p < qualifyingCount);
		const hasNonQualifier = positions.some((p) => p >= qualifyingCount);
		return hasQualifier && hasNonQualifier;
	});
}
