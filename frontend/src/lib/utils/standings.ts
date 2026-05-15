/**
 * Utility functions for calculating group standings and qualifying teams.
 *
 * Tiebreaker chain (FIFA, partial):
 *   1. Points (descending)
 *   2. Goal difference (descending)
 *   3. Goals for (descending)
 *   4. Head-to-head points among tied teams (descending)
 *   5. Head-to-head goal difference (descending)
 *   6. Head-to-head goals scored (descending)
 *   7. Alphabetical by team name (deterministic last-resort, with TieWarning)
 *
 * FIFA's real chain continues past step 6 with fair-play points then drawing
 * of lots. We don't track either, so step 7 is alphabetical and a TieWarning
 * is emitted so the UI can prompt the user to adjust their predictions.
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

/** Resolve a segment of tied teams via H2H then alphabetical. Mutates `warnings`. */
function _resolveTiedSegment(
	tied: TeamStanding[],
	fixtures: Fixture[],
	predictions: Map<string, MatchPrediction>,
	context: TieWarning['context'],
	warnings: TieWarning[]
): TeamStanding[] {
	const allowH2h = fixtures.length > 0 && context === 'group_standings';

	if (!allowH2h) {
		warnings.push({
			group: tied[0].group,
			tiedTeams: tied.map((t) => t.team).sort((a, b) => a.localeCompare(b)),
			context
		});
		return [...tied].sort((a, b) => a.team.localeCompare(b.team));
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
		const sub = byH2h.slice(i, j);
		if (sub.length > 1) {
			warnings.push({
				group: sub[0].group,
				tiedTeams: sub.map((t) => t.team).sort((a, b) => a.localeCompare(b)),
				context
			});
			sub.sort((a, b) => a.team.localeCompare(b.team));
		}
		out.push(...sub);
		i = j;
	}
	return out;
}

/** Apply FIFA's tiebreaker chain (up to H2H goals) then alphabetical-with-warning.
 *  Returns `{ sorted, warnings }`. Pass `fixtures: []` and `context: 'third_place_qualifying'`
 *  to skip H2H entirely (cross-group sorts). */
export function applyFifaTiebreakers(
	teams: TeamStanding[],
	fixtures: Fixture[],
	predictions: Map<string, MatchPrediction>,
	context: TieWarning['context']
): { sorted: TeamStanding[]; warnings: TieWarning[] } {
	const warnings: TieWarning[] = [];
	const byOverall = [...teams].sort((a, b) => {
		if (b.points !== a.points) return b.points - a.points;
		if (b.goalDifference !== a.goalDifference) return b.goalDifference - a.goalDifference;
		return b.goalsFor - a.goalsFor;
	});

	const out: TeamStanding[] = [];
	let i = 0;
	while (i < byOverall.length) {
		const j = _segmentEnd(byOverall, i, (t) => [t.points, t.goalDifference, t.goalsFor]);
		const segment = byOverall.slice(i, j);
		if (segment.length === 1) {
			out.push(segment[0]);
		} else {
			out.push(..._resolveTiedSegment(segment, fixtures, predictions, context, warnings));
		}
		i = j;
	}
	return { sorted: out, warnings };
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/** Calculate standings for a single group based on predictions. */
export function calculateGroupStandings(
	fixtures: Fixture[],
	predictions: Map<string, MatchPrediction>,
	group: string
): TeamStanding[] {
	return calculateGroupStandingsWithWarnings(fixtures, predictions, group).standings;
}

/** Same as calculateGroupStandings but also returns alphabetical-tie warnings. */
export function calculateGroupStandingsWithWarnings(
	fixtures: Fixture[],
	predictions: Map<string, MatchPrediction>,
	group: string
): { standings: TeamStanding[]; warnings: TieWarning[] } {
	const raw = _buildRawStandings(fixtures, predictions, group);
	const teams = Array.from(raw.values());
	const { sorted, warnings } = applyFifaTiebreakers(teams, fixtures, predictions, 'group_standings');
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

/** Compute group standings map for the bracket component. */
export function computeGroupStandingsMap(
	groupFixtures: GroupFixtures[],
	predictions: Map<string, MatchPrediction>
): Record<string, TeamStanding[]> {
	return computeGroupStandingsMapWithWarnings(groupFixtures, predictions).standingsMap;
}

/** Same as computeGroupStandingsMap but also returns all per-group tie warnings. */
export function computeGroupStandingsMapWithWarnings(
	groupFixtures: GroupFixtures[],
	predictions: Map<string, MatchPrediction>
): { standingsMap: Record<string, TeamStanding[]>; warnings: TieWarning[] } {
	const standingsMap: Record<string, TeamStanding[]> = {};
	const warnings: TieWarning[] = [];

	for (const { group, fixtures } of groupFixtures) {
		const result = calculateGroupStandingsWithWarnings(fixtures, predictions, group);
		standingsMap[group] = result.standings;
		warnings.push(...result.warnings);
	}

	return { standingsMap, warnings };
}
