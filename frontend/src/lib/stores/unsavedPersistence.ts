/**
 * Silent localStorage mirror for unsaved prediction drafts.
 *
 * - Subscribes to the three unsaved stores and debounce-writes envelopes.
 * - Hydrates on mount; drops kicked-off match entries and locked-phase brackets.
 * - Listens for `storage` events so multiple tabs of the same user stay in sync.
 * - Per-key dedup cache breaks the cross-tab write/echo loop.
 */

import { writable, type Readable, type Unsubscriber } from 'svelte/store';
import { browser } from '$app/environment';
import {
	unsavedChanges,
	unsavedBracketPrediction,
	unsavedPhase2BracketPrediction,
	type UnsavedPrediction
} from '$stores/predictions';
import type { BracketPrediction, FixturesByGroup } from '$types';
import { debounce } from '$lib/utils/debounce';

const CURRENT_VERSION = 1;
const DEBOUNCE_MS = 300;

type MatchesData = Record<string, UnsavedPrediction>;

interface Envelope<T> {
	v: number;
	savedAt: number;
	data: T;
}

const _lastLocalSave = writable<Date | null>(null);
export const lastLocalSave: Readable<Date | null> = _lastLocalSave;

const initializedUserIds = new Set<string>();
const subscribers = new Map<string, Unsubscriber[]>();

function keyMatches(userId: string): string {
	return `predictor_unsaved_${userId}_matches`;
}
function keyP1(userId: string): string {
	return `predictor_unsaved_${userId}_bracket_phase1`;
}
function keyP2(userId: string): string {
	return `predictor_unsaved_${userId}_bracket_phase2`;
}

function safeParse<T>(raw: string): Envelope<T> | null {
	try {
		const parsed = JSON.parse(raw);
		if (parsed && typeof parsed === 'object' && 'v' in parsed && 'data' in parsed) {
			return parsed as Envelope<T>;
		}
	} catch {
		// fall through
	}
	return null;
}

function readEnvelope<T>(key: string): Envelope<T> | null {
	if (!browser) return null;
	const raw = localStorage.getItem(key);
	if (!raw) return null;
	const env = safeParse<T>(raw);
	if (!env || env.v !== CURRENT_VERSION) {
		localStorage.removeItem(key);
		return null;
	}
	return env;
}

function isEmpty(data: unknown): boolean {
	if (data === null || data === undefined) return true;
	if (typeof data === 'object' && Object.keys(data as object).length === 0) return true;
	return false;
}

export function initPersistence(userId: string): void {
	if (!browser || initializedUserIds.has(userId)) return;
	initializedUserIds.add(userId);

	// Per-key dedup cache. Stores JSON.stringify(data) so identical follow-ups
	// (including echoes from cross-tab `storage` events) don't bounce-write.
	const lastWritten: { matches?: string; p1?: string; p2?: string } = {};

	function writeOrRemove(key: string, data: unknown): void {
		try {
			if (isEmpty(data)) {
				localStorage.removeItem(key);
			} else {
				const envelope: Envelope<unknown> = {
					v: CURRENT_VERSION,
					savedAt: Date.now(),
					data
				};
				localStorage.setItem(key, JSON.stringify(envelope));
			}
			_lastLocalSave.set(new Date());
		} catch {
			// Quota exceeded or storage unavailable — silently degrade.
		}
	}

	const writeMatches = debounce((data: MatchesData) => {
		writeOrRemove(keyMatches(userId), data);
	}, DEBOUNCE_MS);

	const writeP1 = debounce((data: BracketPrediction | null) => {
		writeOrRemove(keyP1(userId), data);
	}, DEBOUNCE_MS);

	const writeP2 = debounce((data: BracketPrediction | null) => {
		writeOrRemove(keyP2(userId), data);
	}, DEBOUNCE_MS);

	const subs: Unsubscriber[] = [];

	subs.push(
		unsavedChanges.subscribe((changes) => {
			const stringified = JSON.stringify(changes);
			if (lastWritten.matches === stringified) return;
			lastWritten.matches = stringified;
			writeMatches(changes);
		})
	);

	subs.push(
		unsavedBracketPrediction.subscribe((bracket) => {
			const stringified = JSON.stringify(bracket);
			if (lastWritten.p1 === stringified) return;
			lastWritten.p1 = stringified;
			writeP1(bracket);
		})
	);

	subs.push(
		unsavedPhase2BracketPrediction.subscribe((bracket) => {
			const stringified = JSON.stringify(bracket);
			if (lastWritten.p2 === stringified) return;
			lastWritten.p2 = stringified;
			writeP2(bracket);
		})
	);

	function onStorage(e: StorageEvent) {
		if (!e.key || !e.key.startsWith(`predictor_unsaved_${userId}_`)) return;

		const env = e.newValue ? safeParse<unknown>(e.newValue) : null;
		const data = env && env.v === CURRENT_VERSION ? env.data : null;
		const stringified = JSON.stringify(data);

		// Prime the cache BEFORE .set() so this tab's subscriber sees
		// "no change" and skips the bounce-write.
		if (e.key === keyMatches(userId)) {
			lastWritten.matches = stringified;
			unsavedChanges.set((data as MatchesData) ?? {});
		} else if (e.key === keyP1(userId)) {
			lastWritten.p1 = stringified;
			unsavedBracketPrediction.set((data as BracketPrediction) ?? null);
		} else if (e.key === keyP2(userId)) {
			lastWritten.p2 = stringified;
			unsavedPhase2BracketPrediction.set((data as BracketPrediction) ?? null);
		}
	}

	window.addEventListener('storage', onStorage);
	subs.push(() => window.removeEventListener('storage', onStorage));
	subs.push(() => {
		writeMatches.cancel();
		writeP1.cancel();
		writeP2.cancel();
	});

	subscribers.set(userId, subs);
}

export function hydrateFromStorage(
	userId: string,
	groupFixtures: FixturesByGroup[],
	isPhase1Locked: boolean,
	isPhase2BracketLocked: boolean
): {
	matchCount: number;
	bracketPhase1Restored: boolean;
	bracketPhase2Restored: boolean;
} | null {
	if (!browser) return null;

	const result = {
		matchCount: 0,
		bracketPhase1Restored: false,
		bracketPhase2Restored: false
	};

	// --- Match scores: drop kicked-off fixtures ---
	const matchesEnv = readEnvelope<MatchesData>(keyMatches(userId));
	if (matchesEnv) {
		const lockedIds = new Set<string>();
		for (const group of groupFixtures) {
			for (const fixture of group.fixtures) {
				if (fixture.is_locked) lockedIds.add(fixture.id);
			}
		}
		const survivors: MatchesData = {};
		for (const [fixtureId, scores] of Object.entries(matchesEnv.data)) {
			if (!lockedIds.has(fixtureId)) survivors[fixtureId] = scores;
		}
		const survivorCount = Object.keys(survivors).length;
		if (survivorCount > 0) {
			unsavedChanges.set(survivors);
			result.matchCount = survivorCount;
		}
		// If everything was kicked off, leave the key in place — the persistence
		// subscriber will overwrite/remove on the next store change. (Re-saving
		// here would cause a redundant write before any user action.)
	}

	// --- Phase 1 bracket: drop if phase is locked ---
	if (isPhase1Locked) {
		if (browser) localStorage.removeItem(keyP1(userId));
	} else {
		const p1Env = readEnvelope<BracketPrediction>(keyP1(userId));
		if (p1Env) {
			unsavedBracketPrediction.set(p1Env.data);
			result.bracketPhase1Restored = true;
		}
	}

	// --- Phase 2 bracket: drop if phase is locked ---
	if (isPhase2BracketLocked) {
		if (browser) localStorage.removeItem(keyP2(userId));
	} else {
		const p2Env = readEnvelope<BracketPrediction>(keyP2(userId));
		if (p2Env) {
			unsavedPhase2BracketPrediction.set(p2Env.data);
			result.bracketPhase2Restored = true;
		}
	}

	if (
		result.matchCount === 0 &&
		!result.bracketPhase1Restored &&
		!result.bracketPhase2Restored
	) {
		return null;
	}
	return result;
}

export function clearAllForUser(userId: string): void {
	if (!browser) return;
	try {
		localStorage.removeItem(keyMatches(userId));
		localStorage.removeItem(keyP1(userId));
		localStorage.removeItem(keyP2(userId));
	} catch {
		// no-op
	}
	const subs = subscribers.get(userId);
	if (subs) {
		for (const unsub of subs) unsub();
		subscribers.delete(userId);
	}
	initializedUserIds.delete(userId);
}
