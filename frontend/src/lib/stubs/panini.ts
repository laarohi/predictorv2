/**
 * Panini stubs for backend-dependent features.
 *
 * Each function here produces plausible, deterministic data for a Panini
 * widget that doesn't yet have backend support. Components import the
 * stub they need; when the backend lands for that feature, swap the
 * import for a real API call and delete the stub function.
 *
 * Determinism: every stub is seeded by stable identifiers (user ID,
 * fixture ID, etc.) using a small hash + linear congruential generator.
 * This means the same input produces the same output across reloads —
 * critical so the UI doesn't shuffle on every render (and so tests are
 * reproducible).
 *
 * Every stub emits a single console.debug('[panini:stub] ...') in dev
 * mode so it's easy to grep for stub call sites.
 */

import { dev } from '$app/environment';

// ---------------------------------------------------------------------------
// Seeded deterministic randomness (no Math.random in render paths)
// ---------------------------------------------------------------------------

function fnv1a(input: string): number {
	let h = 2166136261;
	for (let i = 0; i < input.length; i++) {
		h ^= input.charCodeAt(i);
		h = Math.imul(h, 16777619);
	}
	return h >>> 0;
}

class SeededRng {
	private state: number;
	constructor(seed: string) {
		// Start with a non-zero state, otherwise LCG locks at 0.
		this.state = fnv1a(seed) || 1;
	}
	/** Returns a uint in [0, 2^32). */
	nextInt(): number {
		// Numerical recipes LCG
		this.state = (Math.imul(1664525, this.state) + 1013904223) >>> 0;
		return this.state;
	}
	/** Returns a float in [0, 1). */
	next(): number {
		return this.nextInt() / 0x1_0000_0000;
	}
	/** Returns an int in [min, max) (max exclusive). */
	intBetween(min: number, max: number): number {
		return Math.floor(this.next() * (max - min)) + min;
	}
}

function debug(label: string, ...rest: unknown[]): void {
	if (dev) console.debug('[panini:stub]', label, ...rest);
}

// ---------------------------------------------------------------------------
// Rank trajectory — 7-day sparkline of ranks
// ---------------------------------------------------------------------------

export interface RankTrajectory {
	/** 7 values, oldest at [0], current at [6]. Smaller number = better rank. */
	ranks: number[];
	/** Total players (for normalising the y-axis). */
	maxRank: number;
}

export function stubRankTrajectory(
	userId: string,
	currentRank: number,
	totalPlayers: number
): RankTrajectory {
	debug('rankTrajectory', { userId, currentRank, totalPlayers });
	const rng = new SeededRng(`rank:${userId}`);
	const ranks: number[] = [];
	// Walk backwards from currentRank with bounded random jitter so the
	// line trends toward where we are now.
	let r = currentRank + rng.intBetween(-6, 7); // ~7 days ago
	for (let i = 0; i < 7; i++) {
		const drift = rng.intBetween(-2, 3);
		r = Math.min(totalPlayers, Math.max(1, r + drift));
		ranks.push(r);
	}
	// Force final point to equal currentRank so the chart anchors correctly.
	ranks[6] = currentRank;
	return { ranks, maxRank: totalPlayers };
}

// ---------------------------------------------------------------------------
// Social signal — "X of N picked same"
// ---------------------------------------------------------------------------

export interface SocialSignal {
	/** Players who picked the same outcome (W/D/L) including the current user. */
	agreesOutcome: number;
	/** Players who picked the same exact score including the current user. */
	agreesExact: number;
	/** Total players in the pool. */
	total: number;
}

export function stubSocialSignal(fixtureId: string, total: number): SocialSignal {
	debug('socialSignal', { fixtureId, total });
	const rng = new SeededRng(`social:${fixtureId}`);
	const outcomeShare = 0.2 + rng.next() * 0.6; // 20–80% agreement on outcome
	const agreesOutcome = Math.max(1, Math.min(total, Math.round(total * outcomeShare)));
	const exactShare = 0.05 + rng.next() * 0.2; // 5–25% on exact
	const agreesExact = Math.max(1, Math.min(agreesOutcome, Math.round(total * exactShare)));
	return { agreesOutcome, agreesExact, total };
}

// ---------------------------------------------------------------------------
// Hot pick — your highest-yield open prediction
// ---------------------------------------------------------------------------

export interface HotPick {
	fixtureId: string;
	homeCode: string;
	awayCode: string;
	yourScore: [number, number];
	agreesExact: number;
	total: number;
	/** Potential points if your exact pick lands. */
	potentialPoints: number;
	/** Multiplier over the average pick's expected value (label-only). */
	multiplier: number;
}

interface HotPickCandidate {
	fixtureId: string;
	homeCode: string;
	awayCode: string;
	yourScore: [number, number];
}

export function stubHotPick(candidates: HotPickCandidate[]): HotPick | null {
	debug('hotPick', { candidateCount: candidates.length });
	if (candidates.length === 0) return null;
	// Pick the candidate with the lowest "agrees exact" — that's the highest EV.
	let best: { c: HotPickCandidate; sig: SocialSignal } | null = null;
	const total = 32;
	for (const c of candidates) {
		const sig = stubSocialSignal(c.fixtureId, total);
		if (!best || sig.agreesExact < best.sig.agreesExact) {
			best = { c, sig };
		}
	}
	if (!best) return null;
	// Higher rarity → higher multiplier (rough linear ramp).
	const rarity = 1 - best.sig.agreesExact / total;
	const multiplier = +(1 + rarity * 1.5).toFixed(1);
	return {
		fixtureId: best.c.fixtureId,
		homeCode: best.c.homeCode,
		awayCode: best.c.awayCode,
		yourScore: best.c.yourScore,
		agreesExact: best.sig.agreesExact,
		total,
		potentialPoints: 15,
		multiplier
	};
}

// ---------------------------------------------------------------------------
// Bracket exposure — points still in play from your locked bracket
// ---------------------------------------------------------------------------

export interface BracketExposure {
	pointsAvailable: number;
	picksLocked: number;
	picksTotal: number;
	/** Your predicted final outcome. */
	finalPick: { winnerCode: string; opponentCode: string } | null;
}

export function stubBracketExposure(userId: string): BracketExposure {
	debug('bracketExposure', { userId });
	return {
		pointsAvailable: 235,
		picksLocked: 22,
		picksTotal: 22,
		finalPick: { winnerCode: 'ARG', opponentCode: 'FRA' }
	};
}

// ---------------------------------------------------------------------------
// Underdog stats — bonus haul from rare-but-correct picks
// ---------------------------------------------------------------------------

export interface UnderdogStats {
	count: number;
	exampleCodes: string[];
	pointsFromUnderdogs: number;
}

export function stubUnderdogStats(userId: string): UnderdogStats {
	debug('underdogStats', { userId });
	const rng = new SeededRng(`underdog:${userId}`);
	const pool = ['KSA', 'MAR', 'JPN', 'KOR', 'SEN', 'GHA', 'TUN', 'AUS', 'CAN'];
	const count = 1 + rng.intBetween(0, 3); // 1-3 underdogs
	const exampleCodes: string[] = [];
	const seen = new Set<number>();
	while (exampleCodes.length < count) {
		const idx = rng.intBetween(0, pool.length);
		if (seen.has(idx)) continue;
		seen.add(idx);
		exampleCodes.push(pool[idx]);
	}
	return {
		count,
		exampleCodes,
		pointsFromUnderdogs: count * (5 + rng.intBetween(2, 8))
	};
}

// ---------------------------------------------------------------------------
// Steepest climb — your 7-day movement compared across the pool
// ---------------------------------------------------------------------------

export interface SteepestClimb {
	yourPlaces: number;
	rankAmongClimbers: number;
	totalPlayers: number;
}

export function stubSteepestClimb(
	userId: string,
	currentMovement: number,
	totalPlayers: number
): SteepestClimb {
	debug('steepestClimb', { userId, currentMovement, totalPlayers });
	// In the absence of real data, claim a respectable middle finish if
	// the user moved up at all; otherwise mid-pack.
	const rankAmongClimbers = currentMovement > 0 ? Math.max(1, Math.min(5, 6 - currentMovement)) : 16;
	return {
		yourPlaces: currentMovement,
		rankAmongClimbers,
		totalPlayers
	};
}

// ---------------------------------------------------------------------------
// Bonus haul (KPI display) — total bonus points + breakdown
// ---------------------------------------------------------------------------

export interface BonusHaul {
	total: number;
	fromUnderdogs: number;
	fromExact: number;
}

export function stubBonusHaul(userId: string, exactScores: number): BonusHaul {
	debug('bonusHaul', { userId, exactScores });
	const underdog = stubUnderdogStats(userId);
	return {
		total: underdog.pointsFromUnderdogs + exactScores * 5,
		fromUnderdogs: underdog.pointsFromUnderdogs,
		fromExact: exactScores * 5
	};
}

// ---------------------------------------------------------------------------
// Live match in-progress score (until the live feed is wired up)
// ---------------------------------------------------------------------------

export interface LiveScore {
	homeScore: number;
	awayScore: number;
	minute: number;
	half: 1 | 2;
}

/** Deterministic mock score so the dashboard isn't permanently ?-? */
export function stubLiveScore(fixtureId: string, declaredMinute: number | null): LiveScore {
	debug('liveScore', { fixtureId, declaredMinute });
	const rng = new SeededRng(`livescore:${fixtureId}`);
	// 0-3 goals each side, weighted toward low scores.
	const pick = () => {
		const r = rng.next();
		if (r < 0.5) return 0;
		if (r < 0.85) return 1;
		if (r < 0.97) return 2;
		return 3;
	};
	const minute = declaredMinute ?? rng.intBetween(5, 90);
	return {
		homeScore: pick(),
		awayScore: pick(),
		minute,
		half: minute > 45 ? 2 : 1
	};
}

// ---------------------------------------------------------------------------
// Sparkline path generator (pure utility, no random)
// ---------------------------------------------------------------------------

export interface SparklineOptions {
	width: number;
	height: number;
	padTop?: number;
	padBottom?: number;
}

/**
 * Build an SVG path string from rank values. Smaller rank = better, so we
 * invert the y-axis so a climbing player draws a falling line on screen.
 * Returns { linePath, fillPath, points } so consumers can render markers.
 */
export function sparklinePath(
	ranks: number[],
	maxRank: number,
	opts: SparklineOptions
): { linePath: string; fillPath: string; points: Array<[number, number]> } {
	const { width, height, padTop = 0.05, padBottom = 0.05 } = opts;
	if (ranks.length < 2) return { linePath: '', fillPath: '', points: [] };
	const points: Array<[number, number]> = ranks.map((r, i) => {
		const x = (i / (ranks.length - 1)) * width;
		// Map rank → y: rank 1 is the top of the chart, rank maxRank the bottom.
		const norm = (r - 1) / Math.max(1, maxRank - 1);
		const y = padTop * height + norm * (1 - padTop - padBottom) * height;
		return [x, y];
	});
	const linePath = points.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x},${y}`).join(' ');
	const fillPath = `${linePath} L${width},${height} L0,${height} Z`;
	return { linePath, fillPath, points };
}
