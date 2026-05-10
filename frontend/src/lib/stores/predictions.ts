/**
 * Predictions store for managing match and bracket predictions.
 */

import { writable, derived, get } from 'svelte/store';
import * as predictionsApi from '$api/predictions';
import type {
	MatchPrediction,
	MatchPredictionCreate,
	BracketPrediction,
	TeamAdvancementPrediction
} from '$types';

// Match predictions
export const matchPredictions = writable<MatchPrediction[]>([]);
export const matchPredictionsLoading = writable<boolean>(false);
export const matchPredictionsError = writable<string | null>(null);

// Unsaved changes tracking - using Record for better immutability patterns
export type UnsavedPrediction = { home_score: number; away_score: number };
export const unsavedChanges = writable<Record<string, UnsavedPrediction>>({});

// Phase 1 Bracket predictions
export const bracketPrediction = writable<BracketPrediction | null>(null);
export const bracketLoading = writable<boolean>(false);
export const bracketError = writable<string | null>(null);
// Unsaved bracket prediction (local changes before saving)
export const unsavedBracketPrediction = writable<BracketPrediction | null>(null);
// Whether there are unsaved bracket changes
export const hasUnsavedBracketChanges = derived(
	unsavedBracketPrediction,
	($unsaved) => $unsaved !== null
);
// Get the working bracket (unsaved if exists, otherwise saved)
export const workingBracketPrediction = derived(
	[unsavedBracketPrediction, bracketPrediction],
	([$unsaved, $saved]) => $unsaved || $saved
);

// Phase 2 Bracket predictions (separate from Phase 1)
export const phase2BracketPrediction = writable<BracketPrediction | null>(null);
export const phase2BracketLoading = writable<boolean>(false);
export const phase2BracketError = writable<string | null>(null);
// Unsaved Phase 2 bracket prediction (local changes before saving)
export const unsavedPhase2BracketPrediction = writable<BracketPrediction | null>(null);
// Whether there are unsaved Phase 2 bracket changes
export const hasUnsavedPhase2BracketChanges = derived(
	unsavedPhase2BracketPrediction,
	($unsaved) => $unsaved !== null
);
// Get the working Phase 2 bracket (unsaved if exists, otherwise saved)
export const workingPhase2BracketPrediction = derived(
	[unsavedPhase2BracketPrediction, phase2BracketPrediction],
	([$unsaved, $saved]) => $unsaved || $saved
);

// Derived stores
export const hasUnsavedChanges = derived(
	unsavedChanges,
	($unsavedChanges) => Object.keys($unsavedChanges).length > 0
);

export const unsavedChangesCount = derived(
	unsavedChanges,
	($unsavedChanges) => Object.keys($unsavedChanges).length
);

export const predictionsByFixture = derived(matchPredictions, ($predictions) => {
	const map = new Map<string, MatchPrediction>();
	for (const pred of $predictions) {
		map.set(pred.fixture_id, pred);
	}
	return map;
});

// Match prediction actions
export async function fetchMatchPredictions(): Promise<void> {
	matchPredictionsLoading.set(true);
	matchPredictionsError.set(null);

	try {
		const predictions = await predictionsApi.getMatchPredictions();
		matchPredictions.set(predictions);
		unsavedChanges.set({});
	} catch (e) {
		matchPredictionsError.set(e instanceof Error ? e.message : 'Failed to load predictions');
	} finally {
		matchPredictionsLoading.set(false);
	}
}

export function updateLocalPrediction(
	fixtureId: string,
	homeScore: number,
	awayScore: number
): void {
	unsavedChanges.update((changes) => ({
		...changes,
		[fixtureId]: { home_score: homeScore, away_score: awayScore }
	}));
}

export function clearLocalPrediction(fixtureId: string): void {
	unsavedChanges.update((changes) => {
		const { [fixtureId]: _, ...rest } = changes;
		return rest;
	});
}

export async function savePrediction(fixtureId: string): Promise<boolean> {
	const changes = get(unsavedChanges);
	const change = changes[fixtureId];

	if (!change) return true;

	try {
		const updated = await predictionsApi.updateMatchPrediction(fixtureId, change);

		// Update local state
		matchPredictions.update((predictions) => {
			const existing = predictions.findIndex((p) => p.fixture_id === fixtureId);
			if (existing >= 0) {
				predictions[existing] = updated;
			} else {
				predictions.push(updated);
			}
			return predictions;
		});

		clearLocalPrediction(fixtureId);
		return true;
	} catch (e) {
		matchPredictionsError.set(e instanceof Error ? e.message : 'Failed to save prediction');
		return false;
	}
}

export async function saveAllPredictions(): Promise<boolean> {
	const changes = get(unsavedChanges);
	const changeEntries = Object.entries(changes);

	if (changeEntries.length === 0) return true;

	matchPredictionsLoading.set(true);
	matchPredictionsError.set(null);

	try {
		const predictions: MatchPredictionCreate[] = changeEntries.map(([fixtureId, scores]) => ({
			fixture_id: fixtureId,
			home_score: scores.home_score,
			away_score: scores.away_score
		}));

		const updated = await predictionsApi.batchUpdatePredictions(predictions);

		// Update local state
		matchPredictions.update((current) => {
			for (const pred of updated) {
				const existing = current.findIndex((p) => p.fixture_id === pred.fixture_id);
				if (existing >= 0) {
					current[existing] = pred;
				} else {
					current.push(pred);
				}
			}
			return current;
		});

		unsavedChanges.set({});
		return true;
	} catch (e) {
		matchPredictionsError.set(e instanceof Error ? e.message : 'Failed to save predictions');
		return false;
	} finally {
		matchPredictionsLoading.set(false);
	}
}

// Bracket prediction actions (Phase 1)
export async function fetchBracketPredictions(): Promise<void> {
	bracketLoading.set(true);
	bracketError.set(null);

	try {
		// Explicitly fetch Phase 1 bracket predictions
		const bracket = await predictionsApi.getBracketPredictions('phase_1');
		bracketPrediction.set(bracket);
	} catch (e) {
		bracketError.set(e instanceof Error ? e.message : 'Failed to load bracket');
	} finally {
		bracketLoading.set(false);
	}
}

// Phase 2 bracket prediction actions
export async function fetchPhase2BracketPredictions(): Promise<void> {
	phase2BracketLoading.set(true);
	phase2BracketError.set(null);

	try {
		const bracket = await predictionsApi.getBracketPredictions('phase_2');
		phase2BracketPrediction.set(bracket);
	} catch (e) {
		phase2BracketError.set(e instanceof Error ? e.message : 'Failed to load Phase 2 bracket');
	} finally {
		phase2BracketLoading.set(false);
	}
}

export async function saveBracketPredictions(
	predictions: TeamAdvancementPrediction[]
): Promise<boolean> {
	bracketLoading.set(true);
	bracketError.set(null);

	try {
		await predictionsApi.updateBracketPredictions(predictions);
		// Refresh the appropriate bracket based on current phase
		// The backend uses current phase to determine which predictions to update
		await fetchBracketPredictions();
		await fetchPhase2BracketPredictions();
		return true;
	} catch (e) {
		bracketError.set(e instanceof Error ? e.message : 'Failed to save bracket');
		return false;
	} finally {
		bracketLoading.set(false);
	}
}
