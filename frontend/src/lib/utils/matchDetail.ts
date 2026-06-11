/**
 * Per-match detail helpers. Pure — no I/O, no Svelte.
 *
 * Backs the /results/[fixture_id] page and its supporting components
 * (PnScoreHeatmap, PnPointsBar, PnMatchLeaderboard). Mirrors the logic of
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

/** Per-axis goal maxima for the heatmap grid: 4 each as the floor, expanded
 *  to cover every pick and the actual score so no scoreline ever clamps
 *  onto an edge cell it doesn't belong to. */
export function gridAxes(
	players: GridPlayer[],
	actual: { home_score: number; away_score: number } | null = null
): { homeMax: number; awayMax: number } {
	let homeMax = 4;
	let awayMax = 4;
	for (const p of players) {
		homeMax = Math.max(homeMax, p.home);
		awayMax = Math.max(awayMax, p.away);
	}
	if (actual) {
		homeMax = Math.max(homeMax, actual.home_score);
		awayMax = Math.max(awayMax, actual.away_score);
	}
	return { homeMax, awayMax };
}

/** Group all picks by (home, away) cell — clamped to [0, max] per axis.
 *  Pass `gridAxes(...)` maxima so the clamp never actually bites; the
 *  defaults only matter for callers that want the fixed 4×4 grid. */
export function buildCells(
	players: GridPlayer[],
	homeMax: number = 4,
	awayMax: number = homeMax
): Record<string, BubbleCell> {
	const cells: Record<string, BubbleCell> = {};
	for (const p of players) {
		const h = Math.min(homeMax, Math.max(0, p.home));
		const a = Math.min(awayMax, Math.max(0, p.away));
		const k = `${h},${a}`;
		if (!cells[k]) cells[k] = { h, a, players: [] };
		cells[k].players.push(p);
	}
	return cells;
}

// ---------------------------------------------------------------------------
// Heatmap colour ramp — paper → kind colour, intensity scaled by pick count.
// RGB constants mirror the Panini tokens in panini-base.css (CSS variables
// aren't reachable from JS colour math) — keep in sync if tokens change.
// ---------------------------------------------------------------------------

type RGB = [number, number, number];

const PAPER_RGB: RGB = [241, 235, 222]; // --paper

const KIND_RGB: Record<string, RGB> = {
	'pre-home': [26, 49, 104], // --navy
	'pre-draw': [81, 74, 61], // --ink-2 (draws ramp into dark sand)
	'pre-away': [200, 40, 31], // --red
	exact: [27, 108, 62], // --green
	outcome: [212, 154, 46], // --gold
	miss: [90, 84, 70] // warm grey, matches the .sw.miss legend swatch
};

export interface HeatCellColor {
	bg: string;
	fg: string;
}

function mixRgb(a: RGB, b: RGB, t: number): RGB {
	return [
		Math.round(a[0] + (b[0] - a[0]) * t),
		Math.round(a[1] + (b[1] - a[1]) * t),
		Math.round(a[2] + (b[2] - a[2]) * t)
	];
}

function luminance([r, g, b]: RGB): number {
	return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
}

/**
 * Background + readable text colour for a heatmap cell.
 *
 * `t` has a floor so a single pick in a 30-player pool still reads as a
 * clearly tinted cell rather than near-paper; it tops out at the full kind
 * colour for the modal pick.
 */
export function heatColor(kind: string, count: number, max: number): HeatCellColor {
	const base = KIND_RGB[kind] ?? KIND_RGB.miss;
	const t = 0.22 + 0.78 * Math.min(1, count / Math.max(1, max));
	const bg = mixRgb(PAPER_RGB, base, t);
	return {
		bg: `rgb(${bg[0]}, ${bg[1]}, ${bg[2]})`,
		fg: luminance(bg) > 0.55 ? '#0e1d40' : '#f6f1e6'
	};
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
