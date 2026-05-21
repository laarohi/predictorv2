/**
 * Per-match detail helpers. Pure — no I/O, no Svelte.
 *
 * Backs the /results/[fixture_id] page and its supporting components
 * (PnBubbleGrid, PnPointsBar, PnMatchLeaderboard). Mirrors the logic of
 * panini-match.jsx in the design handoff, but expressed against our
 * existing Fixture / FixtureScore / CommunityPrediction types so the
 * components plug straight into the API.
 */

import type { CommunityPrediction, FixtureScore } from '$types';

/** Outcome of a (home, away) score pair. */
export type Outcome = 'home' | 'draw' | 'away';

export function outcomeOf(home: number, away: number): Outcome {
	if (home > away) return 'home';
	if (home < away) return 'away';
	return 'draw';
}

/**
 * Per-pick classification vs. the actual score.
 *  - `exact`: the pick matches both scores.
 *  - `outcome`: same 1/X/2 as the result, different score.
 *  - `miss`: wrong outcome.
 *  - `unknown`: no actual score yet (caller should treat as not-classifiable).
 */
export type PickKind = 'exact' | 'outcome' | 'miss' | 'unknown';

export function classifyPick(
	pick: { home_score: number; away_score: number },
	actual: { home_score: number; away_score: number } | null | undefined
): PickKind {
	if (!actual) return 'unknown';
	if (pick.home_score === actual.home_score && pick.away_score === actual.away_score) return 'exact';
	return outcomeOf(pick.home_score, pick.away_score) === outcomeOf(actual.home_score, actual.away_score)
		? 'outcome'
		: 'miss';
}

/** Group bubble-grid cell — one per (home_score, away_score) coordinate. */
export interface BubbleCell {
	h: number;
	a: number;
	players: GridPlayer[];
}

/** Player + their pick for the per-match views. The optional fields
 * (rank, totalPts, movement) come from joining in the leaderboard. */
export interface GridPlayer {
	name: string;
	initial: string;
	home: number;
	away: number;
	you: boolean;
	rank: number | null;
	totalPts: number | null;
	movement: number | null;
}

export function toGridPlayer(
	cp: CommunityPrediction,
	you: boolean,
	rank: number | null,
	totalPts: number | null,
	movement: number | null
): GridPlayer {
	return {
		name: cp.user_name,
		initial: (cp.user_name.trim().charAt(0) || '?').toUpperCase(),
		home: cp.home_score,
		away: cp.away_score,
		you,
		rank,
		totalPts,
		movement
	};
}

/** Group all picks by (home, away) cell — clamped to [0, gridMax] inclusive. */
export function buildCells(players: GridPlayer[], gridMax: number = 4): Record<string, BubbleCell> {
	const cells: Record<string, BubbleCell> = {};
	for (const p of players) {
		const h = Math.min(gridMax, Math.max(0, p.home));
		const a = Math.min(gridMax, Math.max(0, p.away));
		const k = `${h},${a}`;
		if (!cells[k]) cells[k] = { h, a, players: [] };
		cells[k].players.push(p);
	}
	return cells;
}

/** Rarity bucket for a pick percentage — matches the design's tier labels. */
export interface RarityTierLabel {
	cls: 'solo' | 'rare' | 'uncommon' | 'common';
	lbl: string;
}

export function rarityLabel(count: number, total: number): RarityTierLabel {
	if (count <= 1) return { cls: 'solo', lbl: 'Solo' };
	const pct = (count / Math.max(1, total)) * 100;
	if (pct < 8) return { cls: 'rare', lbl: 'Rare' };
	if (pct < 18) return { cls: 'uncommon', lbl: 'Uncommon' };
	return { cls: 'common', lbl: 'Common' };
}

/** Display string for a pick: e.g. "2–1". */
export function pickStr(home: number, away: number): string {
	return `${home}–${away}`;
}

/** Format a kickoff ISO string for the breadcrumb meta line. */
export function fmtKickoff(iso: string): { dow: string; date: string; time: string } {
	const d = new Date(iso);
	return {
		dow: d.toLocaleDateString('en-GB', { weekday: 'short' }).toUpperCase(),
		date: d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }).toUpperCase(),
		time: d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
	};
}

/** "Live · 67'" / "Full Time" / "Pre-match" / "Locked" labels for the hero pill. */
export type MatchPhase = 'pre' | 'post';

export function pickActualScore(
	fixtureScore: FixtureScore | null
): { home_score: number; away_score: number } | null {
	if (!fixtureScore) return null;
	return { home_score: fixtureScore.home_score, away_score: fixtureScore.away_score };
}
