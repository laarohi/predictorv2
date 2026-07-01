<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { fade } from 'svelte/transition';
	import { browser } from '$app/environment';
	import { page } from '$app/stores';
	import { goto, beforeNavigate } from '$app/navigation';
	import { isAuthenticated, user } from '$stores/auth';
	import {
		fetchMatchPredictions,
		fetchBracketPredictions,
		fetchPhase2BracketPredictions,
		matchPredictions,
		predictionsByFixture,
		unsavedChanges,
		hasUnsavedChanges,
		unsavedChangesCount,
		updateLocalPrediction,
		saveAllPredictions,
		matchPredictionsLoading,
		bracketPrediction,
		unsavedBracketPrediction,
		hasUnsavedBracketChanges,
		saveBracketPredictions,
		phase2BracketPrediction,
		unsavedPhase2BracketPrediction,
		hasUnsavedPhase2BracketChanges,
		matchPredictionsError,
		bracketError,
		phase2BracketError
	} from '$stores/predictions';
	import {
		fetchGroupFixtures,
		groupFixtures,
		fetchFifaRankings,
		fifaRankings,
		fetchActualKnockoutFixtures,
		fetchActualStandings,
		actualKnockoutFixtures,
		actualGroupStandingsMap,
		actualStandingsLoading
	} from '$stores/fixtures';
	import {
		isPhase2Active,
		isPhase2BracketLocked,
		isPhase1Locked,
		phase1Countdown,
		phase2Countdown,
		phaseStatus,
		currentTime
	} from '$stores/phase';
	import {
		applyFifaTiebreakers,
		computeGroupStandingsMapWithWarnings,
		filterQualificationRelevantWarnings
	} from '$lib/utils/standings';
	import { BRACKET_TOTAL_SLOTS_PHASE2, countBracketSlotsFilled } from '$lib/utils/bracketProgress';
	import {
		reconcileBracketWithStandings,
		type RemovedPick
	} from '$lib/utils/bracketReconcile';
	import {
		initPersistence,
		hydrateFromStorage,
		lastLocalSave
	} from '$stores/unsavedPersistence';
	import { teamCode } from '$lib/utils/teamCodes';
	import { displayTeamName } from '$lib/utils/teamName';
	import type { Fixture, MatchPrediction, BracketPrediction, TeamAdvancementPrediction } from '$types';
	import {
		getMyGroupQualification,
		getAgreements,
		type GroupQualEntry,
		type FixtureAgreement
	} from '$api/predictions';
	import { getScoringConfig, type ScoringConfig } from '$api/competition';
	import { computeMatchPoints } from '$lib/utils/matchBreakdown';

	import PnPageShell from '$components/panini/PnPageShell.svelte';
	import PnFlag from '$components/panini/PnFlag.svelte';
	import PnDropdown from '$components/panini/PnDropdown.svelte';
	import PnCombobox from '$components/panini/PnCombobox.svelte';
	import type { ComboOption } from '$components/panini/PnCombobox.svelte';
	import PnKnockoutBracket from '$components/panini/PnKnockoutBracket.svelte';

	$: if (!$isAuthenticated) {
		goto('/login');
	}

	// Phase + pill selection state
	let activePhase: 'phase1' | 'phase2' = 'phase1';
	let initialPhaseSet = false;
	// Wait for phaseStatus to actually LOAD before latching the default:
	// isPhase2Active reads `false` while phaseStatus is still null, so keying
	// off it alone would latch Phase I before the real status arrives (then
	// never flip, because the guard is one-shot). Gating on $phaseStatus —
	// the same signal the default-view redirect uses — fixes the race.
	$: if (!initialPhaseSet && $phaseStatus) {
		activePhase = $isPhase2Active ? 'phase2' : 'phase1';
		initialPhaseSet = true;
	}

	// Deep-link targeting from "make your prediction" links (results page +
	// dashboard upcoming rows): land on the right section / round. Runs once,
	// after phaseStatus has loaded so isPhase2Active is real.
	let deepLinkApplied = false;
	$: if (browser && !deepLinkApplied && $phaseStatus && initialPhaseSet) {
		deepLinkApplied = true;
		const sp = $page.url.searchParams;
		const grp = sp.get('group');
		const section = sp.get('section');
		const stage = sp.get('stage');
		if (grp) {
			activeSection = 'groups';
			activeGroupPill = grp;
		}
		if ($isPhase2Active && section === 'matches') {
			activePhase = 'phase2';
			phase2Section = 'matches';
		}
		if ($isPhase2Active && stage) activeKoStage = stage;
	}

	// Section toggle controls the outer mode (Groups / Knockout / Bonus).
	// Group pills are a sub-selection that only appears in the Groups section.
	type Section = 'groups' | 'knockout' | 'bonus';
	let activeSection: Section = 'groups';
	// Active group pill — either a group letter (e.g. 'A') or 'thirdplace'.
	let activeGroupPill: string = '';

	let saveStatus: 'idle' | 'saving' | 'saved' | 'error' = 'idle';
	// Detail for a failed save (FLOW-8): surfaced on the Retry button so the
	// user knows WHY (e.g. "2 matches have already locked") instead of a bare ×.
	let saveError: string | null = null;
	// Knockout picks the last save CLEARED because group-score changes
	// reshaped the predicted standings beneath the saved bracket. Persisting
	// the re-resolved bracket (holes included) is the integrity fix — this
	// banner tells the user what was cleared and where to re-pick.
	let bracketPruneNotice: RemovedPick[] | null = null;

	// Cross-tab + cross-refresh draft persistence (silent localStorage mirror).
	// fetchesDone gates hydration so we only overlay localStorage drafts AFTER
	// the server baseline is loaded — otherwise the rehydrated drafts would
	// get clobbered by fetchMatchPredictions resetting unsavedChanges.
	let fetchesDone = false;
	let hydrated = false;
	let restorationBanner: {
		matchCount: number;
		bracketPhase1Restored: boolean;
		bracketPhase2Restored: boolean;
	} | null = null;

	// Editing state — set when the user's cursor is inside one of the two
	// score inputs of a match card. Drives the "EDITING" chip on the card
	// and the gold-with-red-shadow styling on the focused input cell.
	// We use focusin/focusout (which bubble) on the parent .pn-mcard so
	// tabbing between the home and away inputs doesn't briefly clear the
	// state — focusout's relatedTarget check confirms whether focus left
	// the card entirely.
	let editingFixtureId: string | null = null;

	function handleMatchCardFocusIn(fixtureId: string, isLocked: boolean): void {
		if (!isLocked) editingFixtureId = fixtureId;
	}

	function handleMatchCardFocusOut(e: FocusEvent): void {
		const card = e.currentTarget as HTMLElement;
		const next = e.relatedTarget as Node | null;
		// Only clear when focus moved entirely outside this card. Tabbing
		// between the home and away inputs keeps the state intact.
		if (!next || !card.contains(next)) editingFixtureId = null;
	}

	// Mobile-only dropdown state for the group picker. On desktop the
	// pill grid is shown directly; on mobile (< 800px) we collapse to
	// a single dropdown with prev/next arrows on either side.
	let groupDropdownOpen = false;

	// Reactive details about whichever group is currently active. Used by
	// the mobile dropdown trigger so it can show the right label, progress
	// counter, and done/tied/special styling without per-render @const blocks.
	$: currentGroupObj = $groupFixtures.find((g) => g.group === activeGroupPill);
	$: currentGp = currentGroupObj ? groupProgress(currentGroupObj) : null;
	$: currentIsComplete = !!(currentGp && currentGp.total > 0 && currentGp.done === currentGp.total);
	$: currentHasTie = groupStandingsWarnings.some((w) => w.group === activeGroupPill);

	function selectGroup(g: string) {
		activeGroupPill = g;
		groupDropdownOpen = false;
	}

	function prevGroup() {
		const list = $groupFixtures.map((g) => g.group);
		if (list.length === 0) return;
		const idx = list.indexOf(activeGroupPill);
		// Cycle A↔L (3rd Place is no longer a sibling sub-view — it lives in
		// a modal triggered from a separate pill).
		activeGroupPill = idx <= 0 ? list[list.length - 1] : list[idx - 1];
	}

	function nextGroup() {
		const list = $groupFixtures.map((g) => g.group);
		if (list.length === 0) return;
		const idx = list.indexOf(activeGroupPill);
		activeGroupPill = idx >= list.length - 1 ? list[0] : list[idx + 1];
	}

	// ---- 3rd Place modal -------------------------------------------------
	// The third-place standings used to be a sub-view of the wizard (selected
	// via the 'thirdplace' pill in the group nav). It's now a modal dialog —
	// users want to glance at it quickly without losing their place. The pill
	// still triggers it; the body of the wizard no longer renders the table.
	let thirdPlaceModalOpen = false;
	let thirdPlaceDialog: HTMLDialogElement;

	function openThirdPlace() {
		thirdPlaceModalOpen = true;
		thirdPlaceDialog?.showModal();
	}
	function closeThirdPlace() {
		thirdPlaceDialog?.close();
		// `close` event handler below also sets thirdPlaceModalOpen = false,
		// so this assignment is defensive (no-op if the event fired first).
		thirdPlaceModalOpen = false;
	}
	// Native <dialog> bubbles a click event from the backdrop pseudo-element
	// up to the dialog element itself. Inner content has its own event target
	// (the inner div / descendants), so we can distinguish backdrop clicks by
	// checking that the event target IS the dialog.
	function onDialogBackdropClick(e: MouseEvent) {
		if (e.target === thirdPlaceDialog) closeThirdPlace();
	}

	// Svelte action: invoke `callback` when a mousedown lands outside `node`.
	// Used to close the mobile group dropdown when the user taps elsewhere.
	function clickOutside(node: HTMLElement, callback: () => void) {
		function handle(e: MouseEvent) {
			if (!node.contains(e.target as Node)) callback();
		}
		document.addEventListener('mousedown', handle);
		return {
			destroy() {
				document.removeEventListener('mousedown', handle);
			}
		};
	}

	// Per-group qualification ledger (drives the +15/+10 standings stickers) +
	// per-match scoring inputs (drive the +pts sticker on finished matches).
	let qualLedger: GroupQualEntry[] = [];
	let wizAgreements: FixtureAgreement[] = [];
	let wizScoringConfig: ScoringConfig | null = null;
	// Gates the group section so its standings + stickers reveal complete instead
	// of flashing in after the per-match + qualification data loads.
	let pointsReady = false;
	// team name -> qualification points earned (got-out-of-group + position).
	$: qualByTeam = (() => {
		const m = new Map<string, { pts: number; correctPos: boolean }>();
		for (const e of qualLedger) {
			for (const t of e.teams) {
				m.set(t.team, { pts: t.base_points + t.position_points, correctPos: t.position_points > 0 });
			}
		}
		return m;
	})();
	$: wizAgreementMap = new Map(wizAgreements.map((a) => [a.fixture_id, a]));
	// Points a FINISHED group match scored the user (incl. rarity), for the +pts
	// sticker; null when not finished or unpicked. Mirrors the dashboard math.
	function matchPts(f: Fixture): { pts: number; kind: 'exact' | 'outc' | 'miss' } | null {
		if (f.status !== 'finished' || !f.score) return null;
		const p = $predictionsByFixture.get(f.id);
		if (!p) return null;
		const ag = wizAgreementMap.get(f.id);
		const res = computeMatchPoints({
			mode: wizScoringConfig?.mode ?? 'fixed',
			predictedHome: p.home_score,
			predictedAway: p.away_score,
			actualHome: f.score.home_score,
			actualAway: f.score.away_score,
			totalPredictors: ag?.total ?? 0,
			correctPredictors: ag?.agrees_outcome ?? 0,
			outcomePoints: wizScoringConfig?.outcome_points ?? 5,
			exactPoints: wizScoringConfig?.exact_points ?? 10,
			cap: wizScoringConfig?.rarity_cap ?? 10
		});
		const kind = res.exactScore ? 'exact' : res.correctOutcome ? 'outc' : 'miss';
		return { pts: res.points, kind };
	}

	onMount(async () => {
		if ($isAuthenticated) {
			await Promise.all([
				fetchMatchPredictions(),
				fetchGroupFixtures(),
				fetchFifaRankings(),
				fetchBracketPredictions()
			]);
			if ($isPhase2Active) {
				await Promise.all([
					fetchActualKnockoutFixtures(),
					fetchActualStandings(),
					fetchPhase2BracketPredictions()
				]);
			}
			fetchesDone = true;
			try {
				const [led, agg, cfg] = await Promise.all([
					getMyGroupQualification(),
					getAgreements(),
					getScoringConfig()
				]);
				qualLedger = led;
				wizAgreements = agg;
				wizScoringConfig = cfg;
			} catch {
				/* stickers stay hidden until/unless these load */
			} finally {
				pointsReady = true;
			}
		}
		window.addEventListener('beforeunload', handleBeforeUnload);
	});

	// Hydrate drafts from localStorage + start the persistence subscription
	// once user is loaded AND initial fetches are done AND we have group
	// fixtures to dedupe locked matches against. Runs at most once per user
	// session via the `hydrated` guard.
	$: if ($user && fetchesDone && !hydrated && $groupFixtures.length > 0) {
		hydrated = true;
		initPersistence($user.id);
		const r = hydrateFromStorage(
			$user.id,
			$groupFixtures,
			$isPhase1Locked,
			$isPhase2BracketLocked
		);
		if (r) {
			restorationBanner = r;
			// Auto-dismiss after 5s. The user can still click × to dismiss
			// it sooner; if they do, restorationBanner is already null when
			// this timeout fires so the assignment is a harmless no-op.
			setTimeout(() => {
				restorationBanner = null;
			}, 5000);
		}
	}

	onDestroy(() => {
		if (typeof window !== 'undefined') {
			window.removeEventListener('beforeunload', handleBeforeUnload);
		}
	});

	// ---- Smart default view (Your picks vs Overview) -----------------------
	// While Phase 1 is open, OR once Phase 2 goes live, the Predict tab
	// defaults to the wizard ("Your picks") — that's where the user fills in
	// group scores (Phase 1) or their knockout bracket + match scores
	// (Phase 2). Only in the BETWEEN-PHASES window (Phase 1 locked, Phase 2
	// not yet active) is there nothing left to enter, so we default to the
	// pool overview instead of a frozen wizard. An explicit ?view=picks (the
	// Overview page's "Your picks" tab and lock-card CTA) always shows the wizard.
	const isRealTeam = (t: string) => !!t && t !== 'TBD' && !t.toLowerCase().startsWith('slot:');

	// Draft hygiene: a score may only exist for a fixture whose teams are known.
	// The KO grid already hides 'slot:' placeholder fixtures (no input is ever
	// rendered for them), but the silent localStorage draft mirror can re-overlay
	// a stale entry for one — which the next save would persist as a phantom 0-0
	// on a TBD match (then silently become a scored pick once it resolves). Drop
	// any draft keyed to an unresolved knockout fixture before it can be saved.
	$: koPlaceholderIds = new Set(
		$actualKnockoutFixtures
			.filter((f) => !isRealTeam(f.home_team) || !isRealTeam(f.away_team))
			.map((f) => f.id)
	);
	$: if (koPlaceholderIds.size) {
		const entries = Object.entries($unsavedChanges);
		const kept = entries.filter(([id]) => !koPlaceholderIds.has(id));
		if (kept.length !== entries.length) {
			unsavedChanges.set(Object.fromEntries(kept));
		}
	}

	// Decide once per visit, and only when the inputs it depends on have
	// actually arrived (phaseStatus hydrates async). replaceState keeps the
	// bare /predictions entry out of history so Back doesn't bounce.
	let viewRouteDecided = false;
	$: if (browser && !viewRouteDecided && $phaseStatus) {
		if ($page.url.searchParams.get('view') === 'picks' || !$isPhase1Locked || $isPhase2Active) {
			// Phase 1 still open, Phase 2 live, or an explicit request → wizard.
			viewRouteDecided = true;
		} else {
			// Between phases: nothing left to fill, show the pool overview.
			viewRouteDecided = true;
			void goto('/predictions/overview', { replaceState: true });
		}
	}

	// Default the active group pill to the first group once fixtures load
	$: if (!activeGroupPill && $groupFixtures.length > 0) {
		activeGroupPill = $groupFixtures[0].group;
	}

	// ---- Derived: standings, progress, predictions -----------------------
	$: livePredictionMap = (() => {
		const map = new Map<string, MatchPrediction>();
		for (const p of $matchPredictions) map.set(p.fixture_id, p);
		for (const [id, scores] of Object.entries($unsavedChanges)) {
			const existing = map.get(id);
			if (existing) map.set(id, { ...existing, ...scores });
			else
				map.set(id, {
					id: '',
					fixture_id: id,
					home_score: scores.home_score,
					away_score: scores.away_score,
					phase: 'phase_1',
					locked_at: null,
					created_at: '',
					updated_at: '',
					is_locked: false
				});
		}
		return map;
	})();
	$: standingsResult = computeGroupStandingsMapWithWarnings(
		$groupFixtures,
		livePredictionMap,
		$fifaRankings
	);
	$: standingsMap = standingsResult.standingsMap;
	$: groupStandingsWarnings = standingsResult.warnings;

	// Per-group progress: count of fixtures that have a saved or unsaved pick.
	// REACTIVE lambda (not plain function) so the call site
	// `{@const gp = groupProgress(g)}` re-evaluates when livePredictionMap
	// updates. See the same pattern on predictionState / scoreValue earlier
	// in this file — Svelte doesn't trace into function bodies for template
	// reactivity, so a plain function declaration here would freeze the
	// counter on first render.
	$: groupProgress = (g: { group: string; fixtures: Fixture[] }) => {
		let done = 0;
		for (const f of g.fixtures) {
			if (livePredictionMap.has(f.id)) done++;
		}
		return { done, total: g.fixtures.length };
	};

	// Phase 1 knockout bracket is gated on completing every group prediction.
	// Phase 2 uses real standings so doesn't need the gate. Note we use
	// allGroupsComplete (group fixtures only) rather than phaseProgress —
	// the latter now sums groups + bracket + bonus and would never satisfy
	// the gate until the user has filled the bracket they can't yet open.
	$: phase1BracketGated = activePhase === 'phase1' && !allGroupsComplete;

	// Gate the meter until groups + bracket + bonus are all loaded, so the total
	// doesn't visibly climb (e.g. 63 → 145) as the three sources stream in post-mount.
	$: progressReady = fetchesDone && bonusLoaded && $groupFixtures.length > 0;

	$: phaseProgress = (() => {
		let done = 0;
		let total = 0;
		// Group-stage fixtures
		for (const g of $groupFixtures) {
			const p = groupProgress(g);
			done += p.done;
			total += p.total;
		}
		// Phase 1 bracket — 63 advancement picks (R32 + R16 + QF + SF + F + W).
		// Counted on the RESOLVED bracket: a saved pick invalidated by group
		// edits renders as an empty slot and must not count as predicted.
		const bracket = countBracketSlotsFilled(resolvedDisplayBracket);
		done += bracket.done;
		total += bracket.total;
		// Bonus questions — only count once they've loaded (avoids "100%" flash
		// on initial mount before the bonus list arrives from the backend).
		if (bonusQuestions.length > 0) {
			done += bonusAnswers.size;
			total += bonusQuestions.length;
		}
		const pct = total > 0 ? Math.round((done / total) * 100) : 0;
		return { done, total, pct };
	})();

	// Group-only progress — kept for the "matches predicted · N%" mini-bar
	// shown on the locked-knockout gate screen, which specifically measures
	// the group-completion gate condition rather than overall Phase 1 progress.
	$: groupOnlyProgress = (() => {
		let done = 0;
		let total = 0;
		for (const g of $groupFixtures) {
			const p = groupProgress(g);
			done += p.done;
			total += p.total;
		}
		const pct = total > 0 ? Math.round((done / total) * 100) : 0;
		return { done, total, pct };
	})();

	// True only when every fixture in every group has a saved or draft pick.
	// Used to gate the third-place tie-warning banner — ties between
	// third-placed teams are only meaningful once all 12 third-place stats
	// are final, since the ranking depends on cross-group comparison.
	$: allGroupsComplete = $groupFixtures.length > 0 && $groupFixtures.every((g) => {
		const p = groupProgress(g);
		return p.total > 0 && p.done === p.total;
	});

	// ---- Selected group's fixtures ---------------------------------------
	$: selectedGroup =
		activeGroupPill && activeGroupPill !== 'thirdplace'
			? $groupFixtures.find((g) => g.group === activeGroupPill) ?? null
			: null;

	// ---- Third-place qualifying standings (top 8 of 12 advance to R32) ----
	// Uses applyFifaTiebreakers (H2H is N/A across groups, so the chain is
	// points→GD→GF→fair-play→FIFA Rankings→alphabetical). A fair-play-tier
	// descent emits a TieWarning, surfaced in a banner so the user can adjust
	// scores if they want a specific team to advance.
	$: thirdPlaceResult = (() => {
		const thirds = [];
		for (const [group, std] of Object.entries(standingsMap)) {
			if (std[2]) thirds.push({ ...std[2], group });
		}
		return applyFifaTiebreakers(thirds, [], new Map(), 'third_place_qualifying', $fifaRankings);
	})();
	$: thirdPlaceStandings = thirdPlaceResult.sorted;
	// Only surface ties that actually change qualification (cross the 8↔9
	// boundary). See filterQualificationRelevantWarnings for the rationale.
	$: thirdPlaceWarnings = filterQualificationRelevantWarnings(
		thirdPlaceResult.warnings,
		thirdPlaceResult.sorted,
		8
	);
	// Set of team names that qualify via the third-place ranking (top 8 of 12).
	// Per-group standings consult this for position 3 — once every group has
	// predictions, position 3 resolves to either "qualified" (green) or "out"
	// (grey) based on whether the team is in this set. Before then, the answer
	// is undetermined and position 3 stays gold ("tentative / best 3rd match").
	$: thirdPlaceQualifiedSet = new Set(
		thirdPlaceStandings.slice(0, 8).map((t) => t.team)
	);

	// Maximum goals allowed in a single match's score input. Enforced both in
	// the handler and via clampScoreInput on every keystroke so the user
	// sees the cap immediately — typing "16" instantly becomes "15".
	const MAX_GOALS = 15;

	function clampScoreInput(el: HTMLInputElement): void {
		// Normalise the visible value to a canonical 0–15 integer on every
		// keystroke, so the box never shows a nonsensical leading-zero string:
		//   ""        -> ""          (a genuinely empty box stays empty)
		//   "01","02" -> "1","2"     "00","000" -> "0"     "007" -> "7"
		//   ">15"     -> "15"        (the per-side goal cap, MAX_GOALS)
		//   non-digit characters are stripped entirely
		const digits = el.value.replace(/\D/g, '');
		el.value = digits === '' ? '' : String(Math.min(MAX_GOALS, parseInt(digits, 10)));
	}

	// Highlight the cell's current value when it gains focus, so the next
	// keystroke REPLACES the digit instead of appending — the user no longer
	// has to backspace the auto-filled "0" in the partner box before typing
	// (the friction that surfaced on mobile). Deferred one frame because iOS
	// Safari collapses the selection to a caret immediately after the tap that
	// triggered focus; selecting on the next frame wins that race. The inputs
	// are type="text" (not number) precisely so this highlight renders on iOS.
	function selectScoreOnFocus(e: FocusEvent): void {
		const el = e.currentTarget as HTMLInputElement;
		requestAnimationFrame(() => el.select());
	}

	// ---- Score input handlers --------------------------------------------
	function handleScoreInput(fixtureId: string, side: 'home' | 'away', raw: string) {
		const value = Math.max(0, Math.min(MAX_GOALS, parseInt(raw || '0', 10) || 0));
		const current =
			$unsavedChanges[fixtureId] ??
			(() => {
				const p = $predictionsByFixture.get(fixtureId);
				return p ? { home_score: p.home_score, away_score: p.away_score } : { home_score: 0, away_score: 0 };
			})();
		const next =
			side === 'home'
				? { home_score: value, away_score: current.away_score }
				: { home_score: current.home_score, away_score: value };
		updateLocalPrediction(fixtureId, next.home_score, next.away_score);
	}

	// Per-fixture state + score values, computed reactively so the UI updates
	// without a page refresh when stores change.
	//
	// Note: the previous implementation was non-reactive function calls
	// (`scoreValue(f.id, side)`, `predictionState(f)`). Svelte doesn't follow
	// store reads INSIDE a function body, so those expressions in the template
	// never re-evaluated when $unsavedChanges or $predictionsByFixture changed.
	// Result: saving did update the stores, but the per-card input value, the
	// .empty class on the cell, and the per-group progress counter all stayed
	// stale until a full page refresh. Migrating to reactive Maps fixes all
	// three symptoms at once.
	type FixtureState = 'locked' | 'saved' | 'draft' | 'empty';

	$: predictionStateMap = (() => {
		const map = new Map<string, FixtureState>();
		const stateOf = (f: Fixture, phase1Applies: boolean): FixtureState => {
			// $isPhase1Locked: group fixtures all lock at the Phase 1
			// deadline; the live store catches a tab left open across it
			// (f.is_locked is only as fresh as the last fixtures fetch).
			if (f.is_locked || (phase1Applies && $isPhase1Locked)) return 'locked';
			if ($unsavedChanges[f.id]) return 'draft';
			if ($predictionsByFixture.get(f.id)) return 'saved';
			return 'empty';
		};
		for (const g of $groupFixtures) {
			for (const f of g.fixtures) map.set(f.id, stateOf(f, true));
		}
		// Phase 2 knockout fixtures lock per-match only — the Phase 1
		// deadline doesn't apply to them.
		for (const f of $actualKnockoutFixtures) map.set(f.id, stateOf(f, false));
		return map;
	})();

	$: scoreValueMap = (() => {
		const map = new Map<string, { home: string; away: string }>();
		const valueOf = (f: Fixture): { home: string; away: string } => {
			const u = $unsavedChanges[f.id];
			if (u) return { home: String(u.home_score), away: String(u.away_score) };
			const p = $predictionsByFixture.get(f.id);
			if (p) return { home: String(p.home_score), away: String(p.away_score) };
			return { home: '', away: '' };
		};
		for (const g of $groupFixtures) {
			for (const f of g.fixtures) map.set(f.id, valueOf(f));
		}
		// Phase 2 knockout score inputs read from the same map.
		for (const f of $actualKnockoutFixtures) map.set(f.id, valueOf(f));
		return map;
	})();

	// Reactive lambdas (not plain `function` declarations) so the call-site
	// expression `{@const state = predictionState(f)}` is reactive: when
	// predictionStateMap updates, the `$:` block here reassigns
	// predictionState to a new function reference, which Svelte's compiler
	// tracks as a dependency of the call site. Plain function declarations
	// would be referentially stable and the compiler would never re-evaluate
	// the call.
	$: predictionState = (f: Fixture): FixtureState =>
		predictionStateMap.get(f.id) ?? (f.is_locked ? 'locked' : 'empty');

	$: scoreValue = (fixtureId: string, side: 'home' | 'away'): string => {
		const entry = scoreValueMap.get(fixtureId);
		return entry ? entry[side] : '';
	};

	// ---- Bracket (Phase 1) ------------------------------------------------
	let bracketComponent: PnKnockoutBracket;
	$: displayBracket = $unsavedBracketPrediction || $bracketPrediction;

	// The bracket as it actually RESOLVES against current (saved + draft)
	// standings. Saved picks that no longer fit render as empty slots, so
	// progress and save flows must count/persist this, never the raw stored
	// strings — otherwise the progress bar claims 145/145 over a bracket
	// with holes. Guarded on allGroupsComplete: reconciliation against
	// partial standings is a no-op by design (see bracketReconcile.ts).
	$: bracketReconciliation =
		displayBracket && allGroupsComplete
			? reconcileBracketWithStandings(displayBracket, standingsMap, $fifaRankings)
			: null;
	$: resolvedDisplayBracket = bracketReconciliation?.resolved ?? displayBracket;

	// Picks the NEXT save will clear: only group-score edits change the
	// standings beneath the bracket, so the warning only applies while
	// group changes are pending (the save flow prunes exactly then — and
	// only while Phase 1 is open, mirroring handleSaveAll's guard).
	$: pendingBracketPrune =
		$hasUnsavedChanges &&
		!$isPhase1Locked &&
		bracketReconciliation &&
		bracketReconciliation.removed.length > 0
			? bracketReconciliation.removed
			: null;

	function bracketToPredictions(b: BracketPrediction): TeamAdvancementPrediction[] {
		const out: TeamAdvancementPrediction[] = [];
		const push = (stage: string, teams: (string | undefined)[] | undefined) => {
			if (!teams) return;
			for (const t of teams) if (t) out.push({ team: t, stage, group_position: null });
		};
		// Stored stage values are singular to match scoring + fixture-side
		// convention (`Fixture.stage = "quarter_final"`). The plural field
		// names on `BracketPrediction` are a frontend display convention only.
		push('round_of_32', b.round_of_32);
		push('round_of_16', b.round_of_16);
		push('quarter_final', b.quarter_finals);
		push('semi_final', b.semi_finals);
		push('final', b.final);
		if (b.winner) out.push({ team: b.winner, stage: 'winner', group_position: null });
		return out;
	}

	function handleBracketUpdate(event: CustomEvent<BracketPrediction>) {
		unsavedBracketPrediction.set(event.detail);
	}

	// ---- Phase 2 wiring ---------------------------------------------------
	$: phase2DisplayBracket = $unsavedPhase2BracketPrediction || $phase2BracketPrediction;
	$: hasPhase2BracketSelections = !!(
		phase2DisplayBracket &&
		(phase2DisplayBracket.round_of_16?.some((t) => t) ||
			phase2DisplayBracket.quarter_finals?.some((t) => t) ||
			phase2DisplayBracket.semi_finals?.some((t) => t) ||
			phase2DisplayBracket.final?.some((t) => t) ||
			phase2DisplayBracket.winner)
	);
	function handlePhase2BracketUpdate(event: CustomEvent<BracketPrediction>) {
		unsavedPhase2BracketPrediction.set(event.detail);
	}

	// ---- Phase 2 sections: Bracket / Matches ------------------------------
	// Mirrors the Phase 1 Groups/Knockout split. A section toggle picks
	// Bracket vs Matches; within Matches a STAGE picker (R32→Final, with
	// prev/next arrows) swaps which round's knockout score cards are shown —
	// exactly like the group A–L picker in Phase 1.
	type Phase2Section = 'bracket' | 'matches';
	// Default Phase 2 view is Matches (knockout score picks) — that's the live,
	// per-match action surface during the knockout stage. Bracket is still one
	// tap away via the section toggle.
	let phase2Section: Phase2Section = 'matches';

	const KO_STAGES = [
		{ key: 'round_of_32', label: 'Round of 32', short: 'R32' },
		{ key: 'round_of_16', label: 'Round of 16', short: 'R16' },
		{ key: 'quarter_final', label: 'Quarter-finals', short: 'QF' },
		{ key: 'semi_final', label: 'Semi-finals', short: 'SF' },
		{ key: 'third_place', label: 'Third place', short: '3rd' },
		{ key: 'final', label: 'Final', short: 'F' }
	] as const;
	let activeKoStage: string = 'round_of_32';
	let koStageDropdownOpen = false;

	function prevKoStage() {
		const idx = KO_STAGES.findIndex((s) => s.key === activeKoStage);
		activeKoStage = (idx <= 0 ? KO_STAGES[KO_STAGES.length - 1] : KO_STAGES[idx - 1]).key;
	}
	function nextKoStage() {
		const idx = KO_STAGES.findIndex((s) => s.key === activeKoStage);
		activeKoStage = (idx >= KO_STAGES.length - 1 ? KO_STAGES[0] : KO_STAGES[idx + 1]).key;
	}
	function selectKoStage(key: string) {
		activeKoStage = key;
		koStageDropdownOpen = false;
	}

	// Per-match lock countdown for the Phase 2 score cards. Each knockout
	// match locks 15 min before its own kickoff; combined with the 1 Hz
	// `currentTime` clock this ticks live. `soon` (< 1h to lock) drives the
	// urgent red styling.
	const MATCH_LOCK_LEAD_MS = 15 * 60 * 1000;
	function koLockCountdown(
		kickoff: string,
		now: Date
	): { text: string; soon: boolean; locked: boolean } {
		const diff = new Date(kickoff).getTime() - MATCH_LOCK_LEAD_MS - now.getTime();
		if (diff <= 0) return { text: 'Locked', soon: false, locked: true };
		const d = Math.floor(diff / 86_400_000);
		const h = Math.floor((diff % 86_400_000) / 3_600_000);
		const m = Math.floor((diff % 3_600_000) / 60_000);
		const s = Math.floor((diff % 60_000) / 1000);
		const text =
			d > 0
				? `${d}d ${h}h`
				: h > 0
					? `${h}h ${String(m).padStart(2, '0')}m`
					: `${m}m ${String(s).padStart(2, '0')}s`;
		return { text, soon: diff < 3_600_000, locked: false };
	}

	// Real-team knockout fixtures grouped by stage (TBD/slot rows excluded —
	// a round only becomes pickable once its teams resolve).
	$: knockoutByStage = (() => {
		const m = new Map<string, Fixture[]>();
		for (const f of $actualKnockoutFixtures) {
			if (!isRealTeam(f.home_team) || !isRealTeam(f.away_team)) continue;
			const arr = m.get(f.stage) ?? [];
			arr.push(f);
			m.set(f.stage, arr);
		}
		return m;
	})();
	$: activeKoStageFixtures = knockoutByStage.get(activeKoStage) ?? [];
	$: activeKoStageMeta = KO_STAGES.find((s) => s.key === activeKoStage) ?? KO_STAGES[0];
	// Reactive lambda (not a plain fn) so call-sites re-evaluate when the
	// stage map / predictions change — same pattern as groupProgress.
	$: koStageProgress = (key: string) => {
		const fx = knockoutByStage.get(key) ?? [];
		let done = 0;
		for (const f of fx) if ((predictionStateMap.get(f.id) ?? 'empty') !== 'empty') done++;
		return { done, total: fx.length };
	};
	$: activeKoProg = koStageProgress(activeKoStage);
	// Match-score progress across ALL resolved knockout fixtures — the hero
	// meter when the Matches section is active.
	$: phase2MatchProgress = (() => {
		let done = 0;
		let total = 0;
		for (const [, fx] of knockoutByStage) {
			for (const f of fx) {
				total++;
				if ((predictionStateMap.get(f.id) ?? 'empty') !== 'empty') done++;
			}
		}
		return { done, total, pct: total ? Math.round((done / total) * 100) : 0 };
	})();

	// ---- Unified save -----------------------------------------------------
	// Phase 1 has three independent dirty sources: match picks, the knockout
	// bracket, and bonus questions. We treat them as one logical "save Phase I"
	// from the user's POV — one button, one progress count, one round-trip
	// (parallel under the hood).
	$: hasAnyPhase1Unsaved = $hasUnsavedChanges || $hasUnsavedBracketChanges || hasUnsavedBonus;
	// Phase 2 commits BOTH knockout score drafts and the Phase 2 bracket via
	// the single hero "Save Phase II" button. Tie the enable to phase2UnsavedTotal
	// (R16-onward bracket changes + score drafts) so the button is enabled iff
	// its badge is > 0 — an R32-only no-op pick (round_of_32 is never persisted)
	// leaves nothing to save and must not light up a "Save Phase II [0]" button.
	$: hasAnyPhase2Unsaved = phase2UnsavedTotal > 0;
	$: hasAnyUnsaved = $hasUnsavedChanges || $hasUnsavedBracketChanges || $hasUnsavedPhase2BracketChanges || hasUnsavedBonus;
	beforeNavigate(({ cancel, type }) => {
		if (!hasAnyUnsaved) return;
		if (type === 'leave') return;
		if (!confirm("You have unsaved predictions. Leave anyway? Drafts persist locally.")) cancel();
	});
	function handleBeforeUnload(e: BeforeUnloadEvent) {
		if (!hasAnyUnsaved) return;
		e.preventDefault();
		e.returnValue = '';
	}

	async function handleSaveAll() {
		saveStatus = 'saving';
		saveError = null;
		bracketPruneNotice = null;
		let bonusErr: string | null = null;

		// ---- Phase 1 bracket reconciliation, captured up front -------------
		// Snapshotted BEFORE any await: standingsMap already reflects draft
		// group scores (it derives from livePredictionMap), and reading it now
		// keeps this function independent of when Svelte flushes reactive
		// recomputes during the awaits below.
		//
		// The bracket is (re-)saved when the user edited it, OR when pending
		// group-score changes invalidate saved picks. In both cases we persist
		// the RESOLVED bracket — exactly what the user sees rendered — so the
		// DB can never hold knockout picks that contradict the group picks
		// saved alongside them. Resolution is idempotent for a consistent
		// bracket (locked by bracketReconcile.test.ts), so this never alters
		// picks that still fit.
		const groupsDirty = $hasUnsavedChanges;
		const userEditedBracket = $hasUnsavedBracketChanges && !!$unsavedBracketPrediction;
		const bracketSource = $unsavedBracketPrediction || $bracketPrediction;
		let phase1BracketSave: { toSave: BracketPrediction; removed: RemovedPick[] } | null = null;
		// The !$isPhase1Locked guard matters once Phase 2 is active: PUT
		// /bracket writes to the CURRENT phase, so a Phase 1 prune fired from
		// stale restored drafts would overwrite the user's Phase 2 bracket
		// with Phase 1 data. Post-lock there is nothing to prune anyway.
		if (
			bracketSource &&
			allGroupsComplete &&
			!$isPhase1Locked &&
			(userEditedBracket || groupsDirty)
		) {
			const r = reconcileBracketWithStandings(bracketSource, standingsMap, $fifaRankings);
			if (userEditedBracket || r.changed) {
				phase1BracketSave = { toSave: r.resolved, removed: r.removed };
			}
		} else if (bracketSource && userEditedBracket) {
			// Groups incomplete — the wizard gates the bracket UI so this
			// shouldn't happen, but a user edit must never be silently dropped.
			phase1BracketSave = { toSave: bracketSource, removed: [] };
		}

		// ---- 1. Group scores FIRST (sequential) -----------------------------
		// The bracket save below prunes against the standings these scores
		// imply, and the backend validates the bracket against SAVED match
		// predictions — both require the group save to have landed first.
		let groupsOk = true;
		if (groupsDirty) {
			groupsOk = await saveAllPredictions();
		}

		// ---- 2. Everything else (parallel) ----------------------------------
		const tasks: Promise<boolean>[] = [];

		// Phase 1 bracket — skipped if the group save failed: pruning against
		// standings that didn't persist could clear picks that are still valid.
		if (groupsOk && phase1BracketSave) {
			const { toSave, removed } = phase1BracketSave;
			tasks.push(
				saveBracketPredictions(bracketToPredictions(toSave)).then((ok) => {
					if (ok) {
						unsavedBracketPrediction.set(null);
						if (removed.length > 0) bracketPruneNotice = removed;
					}
					return ok;
				})
			);
		}
		if ($hasUnsavedPhase2BracketChanges && $unsavedPhase2BracketPrediction) {
			const p2 = $unsavedPhase2BracketPrediction;
			// Phase 2 stores R16-onward only: the 32 R32 entrants are known
			// facts and their advancement is credited at group qualification,
			// so we never persist round_of_32 rows for Phase 2.
			const p2preds = bracketToPredictions(p2).filter((p) => p.stage !== 'round_of_32');
			tasks.push(
				saveBracketPredictions(p2preds).then((ok) => {
					if (ok) unsavedPhase2BracketPrediction.set(null);
					return ok;
				})
			);
		}
		if (hasUnsavedBonus) {
			tasks.push(
				(async () => {
					try {
						const { saveBonusPredictions } = await import('$api/bonus');
						const preds = Array.from(bonusAnswers.entries()).map(([question_id, answer]) => ({
							question_id,
							answer
						}));
						const saved = await saveBonusPredictions(preds);
						const fresh = new Map<string, string>();
						for (const p of saved) fresh.set(p.question_id, p.answer);
						bonusAnswers = fresh;
						bonusInitial = new Map(fresh);
						return true;
					} catch (e) { bonusErr = e instanceof Error ? e.message : 'Bonus save failed';
						return false;
					}
				})()
			);
		}

		const results = await Promise.all(tasks);
		// "Did everything we attempted succeed, and did we attempt anything?"
		// The group save runs before the parallel tasks, so it counts as an
		// attempt of its own (the old `results.length > 0` no longer covers it).
		const attempted = (groupsDirty ? 1 : 0) + tasks.length;
		const allOk = attempted > 0 && groupsOk && results.every((r) => r);
		saveStatus = allOk ? 'saved' : 'error';
		if (!allOk) saveError = $matchPredictionsError || $bracketError || $phase2BracketError || bonusErr || 'Some predictions could not be saved — please check your connection and Retry.';
		if (allOk) setTimeout(() => (saveStatus = 'idle'), 2000);
	}

	// Diff helpers — count INDIVIDUAL prediction changes (not section flags)
	// so the save button's badge can show "X unsaved out of 145" in user terms.
	function countBracketChangedSlots(
		unsaved: BracketPrediction | null,
		saved: BracketPrediction | null,
		skipR32 = false
	): number {
		if (!unsaved) return 0;
		let count = 0;
		const empty = { round_of_32: [], round_of_16: [], quarter_finals: [], semi_finals: [], final: [] };
		const base = saved || ({ ...empty, group_winners: {}, winner: '' } as BracketPrediction);
		const allStages: (keyof typeof empty)[] = [
			'round_of_32',
			'round_of_16',
			'quarter_finals',
			'semi_finals',
			'final'
		];
		// Phase 2 never persists round_of_32 (the 32 entrants are known facts),
		// so its change-count must ignore that stage or every pick reads as +32.
		const stages = skipR32 ? allStages.filter((s) => s !== 'round_of_32') : allStages;
		for (const key of stages) {
			const u = unsaved[key] || [];
			const s = base[key] || [];
			const len = Math.max(u.length, s.length);
			for (let i = 0; i < len; i++) {
				const uv = u[i] || '';
				const sv = s[i] || '';
				if (uv !== sv) count++;
			}
		}
		if ((unsaved.winner || '') !== (base.winner || '')) count++;
		return count;
	}

	function countBonusChangedAnswers(
		answers: Map<string, string>,
		initial: Map<string, string>
	): number {
		let count = 0;
		// Changed or newly added answers
		for (const [k, v] of answers) {
			if (initial.get(k) !== v) count++;
		}
		// Removed answers (in initial but not in current)
		for (const k of initial.keys()) {
			if (!answers.has(k)) count++;
		}
		return count;
	}

	// Reactive count of TOTAL unsaved individual predictions across all three
	// Phase 1 sources. This is the number shown on the save button's badge —
	// reads naturally as "N unsaved out of 145".
	$: phase1UnsavedTotal =
		$unsavedChangesCount +
		countBracketChangedSlots($unsavedBracketPrediction, $bracketPrediction) +
		(bonusQuestions.length > 0 ? countBonusChangedAnswers(bonusAnswers, bonusInitial) : 0);

	// Human-readable breakdown of which Phase 1 sources are unsaved.
	// Used by the save button's tooltip.
	$: phase1DirtySources = (() => {
		const parts: string[] = [];
		if ($unsavedChangesCount > 0)
			parts.push(`${$unsavedChangesCount} match ${$unsavedChangesCount === 1 ? 'pick' : 'picks'}`);
		const bracketChanged = countBracketChangedSlots($unsavedBracketPrediction, $bracketPrediction);
		if (bracketChanged > 0)
			parts.push(`${bracketChanged} bracket ${bracketChanged === 1 ? 'pick' : 'picks'}`);
		if (bonusQuestions.length > 0) {
			const bonusChanged = countBonusChangedAnswers(bonusAnswers, bonusInitial);
			if (bonusChanged > 0)
				parts.push(`${bonusChanged} bonus ${bonusChanged === 1 ? 'answer' : 'answers'}`);
		}
		return parts;
	})();

	// Phase 2 unsaved tally + breakdown — knockout score drafts + Phase 2
	// bracket changes (R16-onward only), surfaced on the hero "Save Phase II"
	// button + tooltip.
	$: phase2UnsavedTotal =
		$unsavedChangesCount +
		countBracketChangedSlots($unsavedPhase2BracketPrediction, $phase2BracketPrediction, true);
	$: phase2DirtySources = (() => {
		const parts: string[] = [];
		if ($unsavedChangesCount > 0)
			parts.push(`${$unsavedChangesCount} score ${$unsavedChangesCount === 1 ? 'pick' : 'picks'}`);
		const bracketChanged = countBracketChangedSlots($unsavedPhase2BracketPrediction, $phase2BracketPrediction, true);
		if (bracketChanged > 0)
			parts.push(`${bracketChanged} bracket ${bracketChanged === 1 ? 'pick' : 'picks'}`);
		return parts;
	})();

	// Hero progress meter: Phase 1 counts group + bracket + bonus picks;
	// Phase 2 counts the 31 knockout BRACKET picks (R16→Winner) — that's what
	// locks at the bracket deadline shown in the same hero countdown. Knockout
	// score cards track their own per-card state below.
	$: phase2BracketFilled = (() => {
		const b = phase2DisplayBracket;
		if (!b) return 0;
		let filled = 0;
		for (const arr of [b.round_of_16, b.quarter_finals, b.semi_finals, b.final]) {
			for (const t of arr || []) if (t) filled++;
		}
		if (b.winner) filled++;
		return filled;
	})();
	$: heroProgress =
		activePhase === 'phase2'
			? phase2Section === 'matches'
				? phase2MatchProgress
				: {
						done: phase2BracketFilled,
						total: BRACKET_TOTAL_SLOTS_PHASE2,
						pct: Math.round((phase2BracketFilled / BRACKET_TOTAL_SLOTS_PHASE2) * 100)
					}
			: phaseProgress;

	// Count filled bracket slots across all knockout stages for the Phase 1
	// progress bar. Phase 1 bracket has 32 R32 winners + 16 R16 + 8 QF + 4 SF
	// + 2 F + 1 W = 63 advancement picks total. Phase 2 bracket skips R32
	// (actual standings already determined R32) so totals 31 — we only use
	// this helper for Phase 1 progress.
	// ---- Bonus questions (real backend) ----------------------------------

	let bonusQuestions: import('$api/bonus').BonusQuestion[] = [];
	let bonusPlayers: import('$api/bonus').BonusPlayer[] = []; // squad list for award dropdowns
	let bonusAnswers: Map<string, string> = new Map(); // question_id → answer
	let bonusInitial: Map<string, string> = new Map(); // for change tracking
	let bonusLoaded = false; // true once the bonus list arrives; gates the progress meter

	$: hasUnsavedBonus = (() => {
		if (bonusQuestions.length === 0) return false;
		if (bonusAnswers.size !== bonusInitial.size) return true;
		for (const [k, v] of bonusAnswers) {
			if (bonusInitial.get(k) !== v) return true;
		}
		return false;
	})();

	async function loadBonus() {
		const bonusApi = await import('$api/bonus');
		const [qs, preds, players] = await Promise.all([
			bonusApi.getBonusQuestions(),
			bonusApi.getMyBonusPredictions(),
			bonusApi.getBonusPlayers()
		]);
		bonusQuestions = qs;
		bonusPlayers = players;
		const map = new Map<string, string>();
		for (const p of preds) map.set(p.question_id, p.answer);
		bonusAnswers = map;
		bonusInitial = new Map(map);
		bonusLoaded = true;
	}

	// Reactive lambda (same pattern as groupProgress / predictionState above):
	// the function reference must be reactive so `{@const answer = bonusAnswer(bq.id)}`
	// in the template re-evaluates when bonusAnswers is reassigned.
	$: bonusAnswer = (qid: string): string => bonusAnswers.get(qid) ?? '';

	function formatLocalTime(d: Date): string {
		return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
	}

	function setBonusAnswer(qid: string, value: string) {
		const next = new Map(bonusAnswers);
		if (value) next.set(qid, value);
		else next.delete(qid);
		bonusAnswers = next;
	}

	// All 48 teams for the team-input dropdown, derived from group fixtures.
	$: allTeams = (() => {
		const set = new Set<string>();
		for (const g of $groupFixtures) {
			for (const f of g.fixtures) {
				if (f.home_team && f.home_team !== 'TBD') set.add(f.home_team);
				if (f.away_team && f.away_team !== 'TBD') set.add(f.away_team);
			}
		}
		return Array.from(set).sort();
	})();
	$: teamOptions = allTeams.map((t) => ({ value: t, label: displayTeamName(t), flag: teamCode(t) }));

	// ---- Award-question player dropdowns ---------------------------------
	// The full squad list (from the players table) feeds the four award
	// questions, each with its own eligibility filter. The stored answer is the
	// canonical full_name so it matches the admin's correct answer exactly.
	// FIFA's Young Player Award is U21: born on/after 2005-01-01 for WC2026.
	const U21_CUTOFF = '2005-01-01';

	function toPlayerOption(p: import('$api/bonus').BonusPlayer): ComboOption {
		return {
			value: p.full_name,
			label: p.full_name,
			sublabel: `${displayTeamName(p.country)} · ${p.position}`,
			// Match on display name, ASCII surname, and country.
			keywords: `${p.full_name} ${p.surname} ${p.country}`,
			flag: p.country_code ?? undefined
		};
	}

	// Per-question option lists. Golden Boot excludes keepers, Golden Glove is
	// keepers only, Golden Boy is U21 only, Golden Ball is everyone.
	$: playerOptionsByQuestion = {
		best_player: bonusPlayers.map(toPlayerOption),
		top_scorer: bonusPlayers.filter((p) => p.position !== 'GK').map(toPlayerOption),
		golden_glove: bonusPlayers.filter((p) => p.position === 'GK').map(toPlayerOption),
		best_young_player: bonusPlayers
			.filter((p) => (p.date_of_birth ?? '') >= U21_CUTOFF)
			.map(toPlayerOption)
	} as Record<string, ComboOption[]>;

	// Selected-player → FIFA code, for the flag shown next to the combobox.
	$: playerByName = new Map(bonusPlayers.map((p) => [p.full_name, p]));
	$: playerFlagFor = (name: string): string => playerByName.get(name)?.country_code ?? '';

	// Group questions by category for layout
	$: bonusByCategory = (() => {
		const groups: Record<string, typeof bonusQuestions> = {
			group_stage: [],
			top_flop: [],
			awards: []
		};
		for (const q of bonusQuestions) {
			(groups[q.category] ?? (groups[q.category] = [])).push(q);
		}
		return groups;
	})();

	const CATEGORY_LABEL: Record<string, string> = {
		group_stage: 'Group stage',
		top_flop: 'Top / Flop',
		awards: 'Awards'
	};

	// Load bonus questions + saved picks on mount (gated on auth via the
	// reactive $isAuthenticated check below).
	$: if ($isAuthenticated && bonusQuestions.length === 0) {
		loadBonus().catch(() => {});
	}
</script>

<svelte:head>
	<title>Predictions — Predictor</title>
</svelte:head>

{#if $isAuthenticated}
	<PnPageShell>
		{#if restorationBanner}
			<!-- Mobile: .pn-restore-banner-wrap provides a navy halo around
			     the cream banner sticker so it sits in a navy context that
			     matches the hero below. On desktop the wrap is invisible. -->
			<div class="pn-restore-banner-wrap" transition:fade={{ duration: 400 }}>
				<div class="pn-restore-banner">
					<div class="content">
						<span class="icon">✦</span>
						<div class="text">
							<b>Drafts restored from your last session.</b>
							{#if restorationBanner.matchCount > 0}
								{restorationBanner.matchCount} unsaved match
								{restorationBanner.matchCount === 1 ? 'pick' : 'picks'}{#if restorationBanner.bracketPhase1Restored || restorationBanner.bracketPhase2Restored},{/if}
							{/if}
							{#if restorationBanner.bracketPhase1Restored}
								Phase I bracket{#if restorationBanner.bracketPhase2Restored},{/if}
							{/if}
							{#if restorationBanner.bracketPhase2Restored}
								Phase II bracket
							{/if}
							— remember to press Save when you're done.
						</div>
					</div>
					<button class="dismiss" aria-label="Dismiss" on:click={() => (restorationBanner = null)}>×</button>
				</div>
			</div>
		{/if}
		{#if pendingBracketPrune}
			<!-- Live warning: unsaved group-score edits reshape the knockout
			     line-up, so saving will clear the picks listed here. Derived
			     state — it disappears by itself when the edits are saved or
			     reverted, so it carries no dismiss button. -->
			<div class="pn-restore-banner-wrap" transition:fade={{ duration: 400 }}>
				<div class="pn-restore-banner">
					<div class="content">
						<span class="icon">⚠</span>
						<div class="text">
							<b>Your group changes reshape the knockout line-up.</b>
							Saving will clear {pendingBracketPrune.length} knockout
							{pendingBracketPrune.length === 1 ? 'pick' : 'picks'}
							({[...new Set(pendingBracketPrune.map((p) => displayTeamName(p.team)))].join(', ')})
							— you can re-pick those slots in the Knockout tab afterwards.
						</div>
					</div>
				</div>
			</div>
		{/if}
		{#if bracketPruneNotice}
			<div class="pn-restore-banner-wrap" transition:fade={{ duration: 400 }}>
				<div class="pn-restore-banner">
					<div class="content">
						<span class="icon">⚠</span>
						<div class="text">
							<b>Knockout picks cleared.</b>
							Your group-stage changes reshaped the bracket, so
							{bracketPruneNotice.length}
							{bracketPruneNotice.length === 1 ? 'pick' : 'picks'}
							({[...new Set(bracketPruneNotice.map((p) => displayTeamName(p.team)))].join(', ')})
							no longer fit and {bracketPruneNotice.length === 1 ? 'was' : 'were'} removed —
							open the Knockout tab to fill the empty slots.
						</div>
					</div>
					<button class="dismiss" aria-label="Dismiss" on:click={() => (bracketPruneNotice = null)}>×</button>
				</div>
			</div>
		{/if}
		<!-- Hero / progress / phase toggle — DESKTOP (≥700px) -->
		<div class="pn-ws-only">
		<section class="pn-wiz-hero">
			<div class="title-block">
				<!-- Your picks ↔ Overview — sibling-page switcher (the overview
				     shows the whole pool's predictions once they lock). -->
				<nav class="pn-ovswitch" aria-label="Predictions view">
					<a href="/predictions?view=picks" class="on" aria-current="page">Your picks</a>
					<a href="/predictions/overview">Overview</a>
				</nav>
				<!-- Section tabs — navigation within content, on the LEFT where
				     users expect navigation. Phase 1: Groups / Knockout / Bonus.
				     Phase 2: Bracket / Matches (the knockout score cards get their
				     own tab, mirroring how groups were split from the bracket). -->
				{#if activePhase === 'phase1'}
					<div class="phase-toggle">
						<button class:on={activeSection === 'groups'} on:click={() => (activeSection = 'groups')}>Groups</button>
						<button
							class:on={activeSection === 'knockout'}
							class:gated={phase1BracketGated}
							on:click={() => (activeSection = 'knockout')}
							title={phase1BracketGated ? 'Complete all group predictions to unlock' : ''}
						>Knockout</button>
						<button class:on={activeSection === 'bonus'} on:click={() => (activeSection = 'bonus')}>Bonus</button>
					</div>
				{:else}
					<div class="phase-toggle">
						<button class:on={phase2Section === 'bracket'} on:click={() => (phase2Section = 'bracket')}>Bracket</button>
						<button class:on={phase2Section === 'matches'} on:click={() => (phase2Section = 'matches')}>Matches</button>
					</div>
				{/if}
			</div>
			<div class="progress-stack">
				<div class="big-num" aria-hidden="true">
					{#if progressReady}<b>{heroProgress.done}</b><span class="slash">/{heroProgress.total}</span>{:else}<b>—</b><span class="slash">/—</span>{/if}
				</div>
				<div class="bar-and-labels">
					<div class="l">
						<span>{activePhase === 'phase2' && phase2Section === 'bracket' ? 'Knockout picks' : 'Matches predicted'}</span>
						<span>{progressReady ? heroProgress.pct : 0}%</span>
					</div>
					<div class="bar"><div class="bar-fill" style="width: {progressReady ? heroProgress.pct : 0}%;"></div></div>
					<div class="l">
						<span>
							{#if activePhase === 'phase1'}
								{#if $isPhase1Locked}Locked{:else}Locks in {$phase1Countdown ?? '—'}{/if}
							{:else}
								{#if phase2Section === 'matches'}Locks per match{:else if $isPhase2BracketLocked}Locked{:else}Locks in {$phase2Countdown ?? '—'}{/if}
							{/if}
						</span>
					</div>
				</div>
			</div>
			<div class="toggle-stack">
				<!-- Phase I/II toggle (only when Phase 2 is active) +
				     primary commit button. Both are 'phase-context' controls:
				     the toggle picks which phase, the button commits within it.
				     RIGHT-aligned because primary CTAs conventionally terminate
				     the eye-scan at the right edge of the page chrome. -->
				{#if $isPhase2Active}
					<div class="phase-toggle">
						<button class:on={activePhase === 'phase1'} on:click={() => (activePhase = 'phase1')}>Phase I</button>
						<button class:on={activePhase === 'phase2'} on:click={() => (activePhase = 'phase2')}>Phase II</button>
					</div>
				{/if}
				<button
					class="pn-hero-save pn-hero-save--prominent"
					class:dirty={(activePhase === 'phase1' ? hasAnyPhase1Unsaved : hasAnyPhase2Unsaved) && saveStatus === 'idle'}
					class:saving={saveStatus === 'saving'}
					class:success={saveStatus === 'saved'}
					class:error={saveStatus === 'error'}
					on:click={handleSaveAll}
					disabled={((activePhase === 'phase1' ? !hasAnyPhase1Unsaved : !hasAnyPhase2Unsaved) && saveStatus === 'idle') || saveStatus === 'saving' || $matchPredictionsLoading}
					title={saveError ??
						(activePhase === 'phase1' && hasAnyPhase1Unsaved
							? `Unsaved: ${phase1DirtySources.join(' · ')}`
							: activePhase === 'phase2' && hasAnyPhase2Unsaved
								? `Unsaved: ${phase2DirtySources.join(' · ')}`
								: $lastLocalSave
									? `All saved · drafts mirrored locally at ${formatLocalTime($lastLocalSave)}`
									: 'All predictions saved')}
				>
					{#if saveStatus === 'saving'}
						Saving…
					{:else if saveStatus === 'saved'}
						✓ Saved
					{:else if saveStatus === 'error'}
						× Retry
					{:else if activePhase === 'phase1' && hasAnyPhase1Unsaved}
						Save Phase I
						<span class="badge">{phase1UnsavedTotal}</span>
					{:else if activePhase === 'phase2' && hasAnyPhase2Unsaved}
						Save Phase II
						<span class="badge">{phase2UnsavedTotal}</span>
					{:else}
						✓ All saved
					{/if}
				</button>
			</div>
		</section>
		</div>

		<!-- Hero / progress / tabs — MOBILE (≤699px) -->
		<div
			class="pn-wm-only pn-wm-wrap"
			class:has-banner={restorationBanner || pendingBracketPrune || bracketPruneNotice}
		>
			<section class="pn-wm-hero">
				<div class="top-row">
					<div class="ttl">Predict</div>
					<a class="pn-ov-minilink" href="/predictions/overview">Overview →</a>
				</div>
				{#if $isPhase2Active}
					<!-- Own row rather than crammed into top-row: title + overview
					     link + a two-button pill don't fit one line on narrow
					     phones (Phase II was clipping off the right edge). -->
					<div class="phase-row">
						<div class="phase-pill">
							<button class:on={activePhase === 'phase1'} on:click={() => (activePhase = 'phase1')}>Phase I</button>
							<button class:on={activePhase === 'phase2'} on:click={() => (activePhase = 'phase2')}>Phase II</button>
						</div>
					</div>
				{/if}
				<div class="progress-row">
					<div class="big-num" aria-hidden="true">
						{#if progressReady}<b>{heroProgress.done}</b><span class="slash">/{heroProgress.total}</span>{:else}<b>—</b><span class="slash">/—</span>{/if}
					</div>
					<div class="bar-and-labels">
						<div class="l">
							<span>{activePhase === 'phase2' && phase2Section === 'bracket' ? 'Knockout picks' : 'Matches predicted'}</span>
							<span>{progressReady ? heroProgress.pct : 0}%</span>
						</div>
						<div class="bar"><div class="bar-fill" style="width: {progressReady ? heroProgress.pct : 0}%;"></div></div>
						<div class="l">
							<span>
								{#if activePhase === 'phase1'}
									{#if $isPhase1Locked}Locked{:else}Locks in {$phase1Countdown ?? '—'}{/if}
								{:else}
									{#if phase2Section === 'matches'}Locks per match{:else if $isPhase2BracketLocked}Locked{:else}Locks in {$phase2Countdown ?? '—'}{/if}
								{/if}
							</span>
						</div>
					</div>
				</div>
				<!-- Mobile save button — full-width below the progress row,
				     above the section tabs. Same state machine as the desktop
				     hero save (see above for comment). -->
				<button
					class="pn-hero-save pn-hero-save--mobile"
					class:dirty={(activePhase === 'phase1' ? hasAnyPhase1Unsaved : hasAnyPhase2Unsaved) && saveStatus === 'idle'}
					class:saving={saveStatus === 'saving'}
					class:success={saveStatus === 'saved'}
					class:error={saveStatus === 'error'}
					on:click={handleSaveAll}
					disabled={((activePhase === 'phase1' ? !hasAnyPhase1Unsaved : !hasAnyPhase2Unsaved) && saveStatus === 'idle') || saveStatus === 'saving' || $matchPredictionsLoading}
					title={activePhase === 'phase1' && hasAnyPhase1Unsaved
						? `Unsaved: ${phase1DirtySources.join(' · ')}`
						: activePhase === 'phase2' && hasAnyPhase2Unsaved
							? `Unsaved: ${phase2DirtySources.join(' · ')}`
							: 'All predictions saved'}
				>
					{#if saveStatus === 'saving'}
						Saving…
					{:else if saveStatus === 'saved'}
						✓ Saved
					{:else if saveStatus === 'error'}
						× Retry
					{:else if activePhase === 'phase1' && hasAnyPhase1Unsaved}
						Save Phase I
						<span class="badge">{phase1UnsavedTotal}</span>
					{:else if activePhase === 'phase2' && hasAnyPhase2Unsaved}
						Save Phase II
						<span class="badge">{phase2UnsavedTotal}</span>
					{:else}
						✓ All saved
					{/if}
				</button>
			</section>
			{#if activePhase === 'phase1'}
				<nav class="pn-wm-tabs">
					<button class:on={activeSection === 'groups'} on:click={() => (activeSection = 'groups')}>Groups</button>
					<button
						class:on={activeSection === 'knockout'}
						class:gated={phase1BracketGated}
						on:click={() => (activeSection = 'knockout')}
						title={phase1BracketGated ? 'Complete all group predictions to unlock' : ''}
					>Knockout</button>
					<button class:on={activeSection === 'bonus'} on:click={() => (activeSection = 'bonus')}>Bonus</button>
				</nav>
			{:else}
				<nav class="pn-wm-tabs">
					<button class:on={phase2Section === 'bracket'} on:click={() => (phase2Section = 'bracket')}>Bracket</button>
					<button class:on={phase2Section === 'matches'} on:click={() => (phase2Section = 'matches')}>Matches</button>
				</nav>
			{/if}
		</div>

		<!-- Phase 1 wizard -->
		{#if activePhase === 'phase1'}
			<!-- Group pills (only when the Groups section is selected) -->
			{#if activeSection === 'groups'}
				<section class="pn-wiz-nav">
					<!-- Desktop layout: 12 groups in a divisor-of-12 grid +
					     3rd Place spanning the full height on the right.
					     Hidden on mobile via CSS media query. -->
					<div class="pn-wiz-nav-desktop">
						<div class="groups-grid">
							{#each $groupFixtures as g (g.group)}
								{@const gp = groupProgress(g)}
								{@const isComplete = gp.total > 0 && gp.done === gp.total}
								{@const hasTie = groupStandingsWarnings.some((w) => w.group === g.group)}
								<button
									class="pn-wiz-gp"
									class:active={activeGroupPill === g.group}
									class:done={isComplete && !hasTie}
									class:tied={isComplete && hasTie}
									on:click={() => (activeGroupPill = g.group)}
								>
									Group {g.group}
									<span class="gp-prog">{gp.done}/{gp.total}</span>
								</button>
							{/each}
						</div>
						<button
							class="pn-wiz-gp special"
							class:active={thirdPlaceModalOpen}
							on:click={openThirdPlace}
							aria-haspopup="dialog"
						>
							3rd<br />Place
						</button>
					</div>

					<!-- Mobile layout: prev/next arrows wrap a Panini-styled
					     dropdown picker. 3rd Place is a separate full-width
					     button below. Hidden on desktop via CSS media query. -->
					<div class="pn-wiz-nav-mobile">
						<div class="picker-row">
							<button
								class="arrow"
								on:click={prevGroup}
								aria-label="Previous group"
							>◀</button>
							<div class="dropdown" use:clickOutside={() => (groupDropdownOpen = false)}>
								<button
									class="trigger"
									class:done={currentIsComplete && !currentHasTie}
									class:tied={currentIsComplete && currentHasTie}
									class:open={groupDropdownOpen}
									on:click={() => (groupDropdownOpen = !groupDropdownOpen)}
								>
									<span class="lbl">Group {activeGroupPill || 'A'}</span>
									{#if currentGp}
										<span class="prog">{currentGp.done}/{currentGp.total}</span>
									{/if}
									<span class="chev">▾</span>
								</button>
								{#if groupDropdownOpen}
									<ul class="menu" transition:fade={{ duration: 120 }}>
										{#each $groupFixtures as g (g.group)}
											{@const gp = groupProgress(g)}
											{@const isComplete = gp.total > 0 && gp.done === gp.total}
											{@const hasTie = groupStandingsWarnings.some((w) => w.group === g.group)}
											<li>
												<button
													class:active={activeGroupPill === g.group}
													class:done={isComplete && !hasTie}
													class:tied={isComplete && hasTie}
													on:click={() => selectGroup(g.group)}
												>
													<span class="lbl">Group {g.group}</span>
													<span class="prog">{gp.done}/{gp.total}</span>
												</button>
											</li>
										{/each}
									</ul>
								{/if}
							</div>
							<button
								class="arrow"
								on:click={nextGroup}
								aria-label="Next group"
							>▶</button>
							<button
								class="third-chip"
								class:active={thirdPlaceModalOpen}
								on:click={openThirdPlace}
								aria-haspopup="dialog"
								aria-label="3rd Place standings"
							>3rd</button>
						</div>
					</div>
				</section>
			{/if}

			<!-- Group view (the 'thirdplace' sub-view was removed — that content
			     now lives in the modal at the bottom of this page; see <dialog
			     class="pn-3rd-modal"> below). -->
			{#if activeSection === 'groups' && selectedGroup && pointsReady}
				{@const group = selectedGroup}
				{@const standings = standingsMap[group.group] ?? []}
				{@const groupWarnings = groupStandingsWarnings.filter((w) => w.group === group.group)}
				{@const groupGp = groupProgress(group)}
				{@const groupComplete = groupGp.total > 0 && groupGp.done === groupGp.total}
				<section class="pn-wiz-group">
					{#if groupComplete && groupWarnings.length > 0}
						<div class="pn-tie-warn">
							<h4>⚠ Tied teams in Group {group.group} · alphabetical fallback in effect</h4>
							{#each groupWarnings as w (w.tiedTeams.join('-'))}
								<p>
									<span class="teams">{w.tiedTeams.join(', ')}</span>
									are tied on points, goal difference, goals-for, and head-to-head — they're
									currently ranked alphabetically. Adjust your predicted scores if you want
									a different ordering.
								</p>
							{/each}
						</div>
					{/if}
					<div class="pn-stnd-col">
					<div class="pn-stnd">
						<div class="h">
							<span>Group {group.group} · Predicted Standings</span>
						</div>
						<table class="pn-stnd-table">
							<thead>
								<tr>
									<th></th>
									<th>Team</th>
									<th class="c">P</th>
									<th class="c">W</th>
									<th class="c">D</th>
									<th class="c">L</th>
									<th class="c">GF</th>
									<th class="c">GA</th>
									<th class="c">GD</th>
									<th>Pts</th>
								</tr>
							</thead>
							<tbody>
								{#each standings as t, i (t.team)}
									{@const directQual = i < 2}
									{@const isThirdSlot = i === 2}
									{@const thirdQual =
										isThirdSlot &&
										allGroupsComplete &&
										thirdPlaceQualifiedSet.has(t.team)}
									{@const tentative = isThirdSlot && !allGroupsComplete}
									{@const qualified = directQual || thirdQual}
									{@const isOut = !qualified && !tentative}
									{@const teamQual = qualByTeam.get(t.team)}
									<tr class:qualifies={qualified}>
										<td>
											<span class="pos" class:adv={qualified} class:maybe={tentative} class:out={isOut}>{i + 1}</span>
										</td>
										<td>
											<span class="team">
												<PnFlag code={teamCode(t.team)} w={20} h={14} />
												<span class="nm-text"><span class="nm-full">{displayTeamName(t.team)}</span><span class="nm-code">{teamCode(t.team)}</span></span>
												{#if teamQual}
													<span
														class="qual-badge"
														class:exact={teamQual.correctPos}
														class:outc={!teamQual.correctPos}
														title={teamQual.correctPos
															? 'Qualified + correct position: +10 advance, +5 position'
															: 'Qualified, wrong position: +10 advance'}>+{teamQual.pts}</span>
												{/if}
											</span>
										</td>
										<td class="stat">{t.played}</td>
										<td class="stat">{t.won}</td>
										<td class="stat">{t.drawn}</td>
										<td class="stat">{t.lost}</td>
										<td class="stat">{t.goalsFor}</td>
										<td class="stat">{t.goalsAgainst}</td>
										<td class="stat gd" class:pos={t.goalDifference >= 0} class:neg={t.goalDifference < 0}>
											{t.goalDifference > 0 ? '+' : ''}{t.goalDifference}
										</td>
										<td>{t.points}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
					<div class="pn-stnd-legend">
						<span><span class="pip green"></span>Qualified</span>
						<span><span class="pip grey"></span>Out</span>
					</div>
					</div><!-- /pn-stnd-col -->

					<!-- Matches -->
					<div class="pn-wiz-matches">
						{#each group.fixtures as f (f.id)}
							{@const state = predictionState(f)}
							{@const mp = matchPts(f)}
							<div
								class="pn-mcard"
								class:locked={state === 'locked'}
								class:empty={state === 'empty'}
								class:editing={editingFixtureId === f.id}
								on:focusin={() => handleMatchCardFocusIn(f.id, f.is_locked)}
								on:focusout={handleMatchCardFocusOut}
							>
								{#if editingFixtureId === f.id}
									<span class="editing-tag">Editing</span>
								{:else if state === 'empty'}
									<span class="empty-tag">Pick</span>
								{/if}
								<div class="meta">
									<span>{new Date(f.kickoff).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })} · {new Date(f.kickoff).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}</span>
								</div>
								<div class="row">
									<div class="team" title={f.home_team}>
										<PnFlag code={teamCode(f.home_team)} w={28} h={20} />
										<span class="nm">{teamCode(f.home_team)}</span>
									</div>
									<div class="pn-score">
										<input
											type="text"
											class="pn-score-cell"
											class:empty={state === 'empty'}
											inputmode="numeric"
											maxlength="2"
											pattern="[0-9]*"
											disabled={state === 'locked'}
											on:focus={selectScoreOnFocus}
											value={scoreValue(f.id, 'home')}
											on:input={(e) => {
												clampScoreInput(e.currentTarget);
												handleScoreInput(f.id, 'home', e.currentTarget.value);
											}}
											aria-label="{f.home_team} score"
										/>
										<span class="dash">–</span>
										<input
											type="text"
											class="pn-score-cell"
											class:empty={state === 'empty'}
											inputmode="numeric"
											maxlength="2"
											pattern="[0-9]*"
											disabled={state === 'locked'}
											on:focus={selectScoreOnFocus}
											value={scoreValue(f.id, 'away')}
											on:input={(e) => {
												clampScoreInput(e.currentTarget);
												handleScoreInput(f.id, 'away', e.currentTarget.value);
											}}
											aria-label="{f.away_team} score"
										/>
									</div>
									<div class="team r" title={f.away_team}>
										<PnFlag code={teamCode(f.away_team)} w={28} h={20} />
										<span class="nm">{teamCode(f.away_team)}</span>
									</div>
								</div>
								<div class="save-row">
									{#if state === 'locked'}
										<span class="save-tag locked">Locked</span>
										{#if mp}
											<span class="match-pts {mp.kind}">{mp.pts > 0 ? `+${mp.pts}` : '0'}</span>
										{:else}
											<span>No edits</span>
										{/if}
									{:else if state === 'draft'}
										<span class="save-tag draft">Draft</span>
										<span>Click Save Phase I to commit</span>
									{:else if state === 'saved'}
										<span class="save-tag saved">✓ Saved</span>
										<span>Submitted</span>
									{:else}
										<span class="save-tag empty">— Empty</span>
										<span>Enter a score to predict</span>
									{/if}
								</div>
							</div>
						{/each}
					</div>
				</section>
			{:else if activeSection === 'groups' && selectedGroup}
				<section class="pn-wiz-group">
					<div class="pn-wiz-loading">Loading group points…</div>
				</section>
			{:else if activeSection === 'knockout'}
				{#if phase1BracketGated}
					<section class="pn-locked">
						<div class="lock-icon">
							<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
								<rect x="5" y="11" width="14" height="10" rx="1" fill="currentColor" />
								<path d="M8 11V7a4 4 0 018 0v4" fill="none" />
							</svg>
						</div>
						<h2>Knockout bracket <em>locked</em></h2>
						<p class="l">
							Predict every group-stage match before opening the bracket. The bracket uses your predicted group standings to seed the Round of 32 — it can't be filled in until those are settled.
						</p>
						<div class="lock-progress">
							<div class="v">{groupOnlyProgress.done}<span class="of">/{groupOnlyProgress.total}</span></div>
							<div class="label">matches predicted · {groupOnlyProgress.pct}%</div>
							<div class="bar"><div class="bar-fill" style="width: {groupOnlyProgress.pct}%;"></div></div>
						</div>
						<button class="pn-btn gold" type="button" on:click={() => (activeSection = 'groups')}>← Back to Groups</button>
					</section>
				{:else}
					<PnKnockoutBracket
						bind:this={bracketComponent}
						prediction={displayBracket}
						groupStandings={standingsMap}
						fifaRankings={$fifaRankings}
						locked={$isPhase1Locked}
						phase="phase_1"
						on:update={handleBracketUpdate}
					/>
				{/if}
			{:else if activeSection === 'bonus'}
				{#if $isPhase1Locked}
					<p style="font-family: var(--mono); font-size: 11px; color: var(--ink-3); letter-spacing: 0.06em; text-transform: uppercase; margin: 14px 0 0;">
						Phase 1 has locked — bonus answers can no longer be changed.
					</p>
				{/if}
				{#each Object.entries(bonusByCategory) as [cat, qs] (cat)}
					{#if qs.length > 0}
						<div class="pn-banner" style="margin-top: 18px;">
							<span class="n">{cat === 'group_stage' ? '01' : cat === 'top_flop' ? '02' : '03'}</span>
							<h2>{CATEGORY_LABEL[cat]}</h2>
							{#if cat === 'group_stage' || cat === 'top_flop'}
								<span class="pn-tie-note" title="If two or more teams tie on the relevant criterion, picking any one of them scores full points.">
									<span class="i" aria-hidden="true">ⓘ</span>
									Ties: any tied team scores full points
								</span>
							{/if}
							<span class="end">{qs.length} question{qs.length === 1 ? '' : 's'}</span>
						</div>
						<section class="pn-bonus-row">
							{#each qs as bq (bq.id)}
								{@const answer = bonusAnswer(bq.id)}
								{@const dashIdx = bq.label.indexOf(' — ')}
								{@const nickname = dashIdx >= 0 ? bq.label.slice(0, dashIdx) : bq.label}
								{@const descriptor = dashIdx >= 0 ? bq.label.slice(dashIdx + 3) : ''}
								<div class="pn-bonus">
									<div class="l"><span class="pip"></span>{CATEGORY_LABEL[cat]}</div>
									<div class="q">
										<div class="q-name">{nickname}</div>
										{#if descriptor}
											<div class="q-desc">{descriptor}</div>
										{/if}
									</div>
									{#if bq.input_type === 'team'}
										{@const elig = bq.eligible_teams}
										{@const opts = elig ? teamOptions.filter((o) => elig.includes(o.value)) : teamOptions}
										<div class="answer-row">
											<PnDropdown
												value={answer}
												options={opts}
												placeholder="— Select a team —"
												disabled={$isPhase1Locked}
												on:change={(e) => setBonusAnswer(bq.id, e.detail)}
											/>
											{#if answer}
												<div class="answer-flag" aria-hidden="true">
													<PnFlag code={teamCode(answer)} w={36} h={26} />
												</div>
											{/if}
										</div>
									{:else}
										{@const popts = playerOptionsByQuestion[bq.id] ?? []}
										<div class="answer-row">
											<PnCombobox
												value={answer}
												options={popts}
												placeholder="Type a player name…"
												disabled={$isPhase1Locked}
												on:change={(e) => setBonusAnswer(bq.id, e.detail)}
											/>
											{#if answer && playerFlagFor(answer)}
												<div class="answer-flag" aria-hidden="true">
													<PnFlag code={playerFlagFor(answer)} w={36} h={26} />
												</div>
											{/if}
										</div>
									{/if}
									<div class="pts-pill">+{bq.points} pts</div>
								</div>
							{/each}
						</section>
					{/if}
				{/each}

				<div style="display: flex; justify-content: flex-end; gap: 10px; margin: 14px 0 22px; align-items: center;">
					<span style="font-family: var(--mono); font-size: 10px; letter-spacing: 0.10em; text-transform: uppercase; color: var(--ink-3);">
						{bonusAnswers.size} of {bonusQuestions.length} answered
					</span>
				</div>
				<p style="font-family: var(--mono); font-size: 11px; color: var(--ink-3); letter-spacing: 0.06em; text-transform: uppercase;">
					★ Bonus picks lock with Phase I · admin will reveal correct answers as the tournament resolves
				</p>
			{/if}

		{/if}

		<!-- Phase 2 — Bracket / Matches (mirrors Phase 1's groups-vs-bracket split) -->
		{#if activePhase === 'phase2'}
			{#if $actualStandingsLoading}
				<p style="font-family: var(--mono); font-size: 11px; color: var(--ink-3); letter-spacing: 0.08em; text-transform: uppercase; padding: 16px;">Loading Phase II data…</p>
			{:else if phase2Section === 'bracket'}
				<!-- Bracket: full R32 → Final wall chart seeded from ACTUAL group
				     standings. Picking each R32 winner seeds R16, so the R32
				     column is shown and interactive (not hidden). -->
				<PnKnockoutBracket
					prediction={phase2DisplayBracket}
					groupStandings={$actualGroupStandingsMap}
					fifaRankings={$fifaRankings}
					locked={$isPhase2BracketLocked}
					phase="phase_2"
					on:update={handlePhase2BracketUpdate}
				/>
			{:else}
				<!-- Matches: a STAGE picker (R32 → Final, prev/next arrows) swaps
				     which round's knockout score cards are shown — the same nav
				     pattern as the Phase 1 group A–L picker. -->
				<section class="pn-wiz-nav">
					<div class="pn-wiz-nav-desktop">
						<div class="groups-grid">
							{#each KO_STAGES as s (s.key)}
								{@const sp = koStageProgress(s.key)}
								<button
									class="pn-wiz-gp"
									class:active={activeKoStage === s.key}
									class:done={sp.total > 0 && sp.done === sp.total}
									on:click={() => (activeKoStage = s.key)}
								>
									{s.short}
									<span class="gp-prog">{sp.total > 0 ? `${sp.done}/${sp.total}` : 'TBD'}</span>
								</button>
							{/each}
						</div>
					</div>
					<div class="pn-wiz-nav-mobile">
						<div class="picker-row">
							<button class="arrow" on:click={prevKoStage} aria-label="Previous round">◀</button>
							<div class="dropdown" use:clickOutside={() => (koStageDropdownOpen = false)}>
								<button
									class="trigger"
									class:done={activeKoProg.total > 0 && activeKoProg.done === activeKoProg.total}
									class:open={koStageDropdownOpen}
									on:click={() => (koStageDropdownOpen = !koStageDropdownOpen)}
								>
									<span class="lbl">{activeKoStageMeta.label}</span>
									<span class="prog">{activeKoProg.total > 0 ? `${activeKoProg.done}/${activeKoProg.total}` : 'TBD'}</span>
									<span class="chev">▾</span>
								</button>
								{#if koStageDropdownOpen}
									<ul class="menu" transition:fade={{ duration: 120 }}>
										{#each KO_STAGES as s (s.key)}
											{@const sp = koStageProgress(s.key)}
											<li>
												<button
													class:active={activeKoStage === s.key}
													class:done={sp.total > 0 && sp.done === sp.total}
													on:click={() => selectKoStage(s.key)}
												>
													<span class="lbl">{s.label}</span>
													<span class="prog">{sp.total > 0 ? `${sp.done}/${sp.total}` : 'TBD'}</span>
												</button>
											</li>
										{/each}
									</ul>
								{/if}
							</div>
							<button class="arrow" on:click={nextKoStage} aria-label="Next round">▶</button>
						</div>
					</div>
				</section>

				<!-- Knockout score cards for the selected stage -->
				<section class="pn-wiz-group pn-ko-scores">
					<h2 style="font-family: var(--display); font-size: 22px; text-transform: uppercase; margin: 0 auto 12px; max-width: 720px;">
						{activeKoStageMeta.label} <em style="color: var(--red); font-style: normal;">scores</em>
					</h2>
					<!-- Knockout SCORES are graded on the 90-minute result; who
					     advances (ET/pens) is scored in the Bracket tab. -->
					<div class="pn-ko-90warn" role="note">
						<span class="ic" aria-hidden="true">⏱</span>
						<span class="tx"><b>Scores are judged on the result after 90 minutes.</b> Extra time &amp; penalties don't count here — predict who goes through in the <strong>Bracket</strong> tab.</span>
					</div>
					<div class="pn-wiz-matches">
						{#each activeKoStageFixtures as f (f.id)}
							{@const state = predictionState(f)}
							{@const cd = koLockCountdown(f.kickoff, $currentTime)}
							<div
								class="pn-mcard"
								class:locked={state === 'locked'}
								class:empty={state === 'empty'}
								class:editing={editingFixtureId === f.id}
								on:focusin={() => handleMatchCardFocusIn(f.id, f.is_locked)}
								on:focusout={handleMatchCardFocusOut}
							>
								{#if editingFixtureId === f.id}
									<span class="editing-tag">Editing</span>
								{:else if state === 'empty'}
									<span class="empty-tag">Pick</span>
								{/if}
								<div class="meta">
									<span>{new Date(f.kickoff).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })} · {new Date(f.kickoff).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}</span>
									<span class="lock-cd" class:soon={cd.soon} class:locked={cd.locked}>{cd.locked ? '🔒 Locked' : `Locks in ${cd.text}`}</span>
								</div>
								<div class="row">
									<div class="team" title={f.home_team}>
										<PnFlag code={teamCode(f.home_team)} w={28} h={20} />
										<span class="nm">{teamCode(f.home_team)}</span>
									</div>
									<div class="pn-score">
										<input
											type="text"
											class="pn-score-cell"
											class:empty={state === 'empty'}
											inputmode="numeric"
											maxlength="2"
											pattern="[0-9]*"
											disabled={state === 'locked'}
											on:focus={selectScoreOnFocus}
											value={scoreValue(f.id, 'home')}
											on:input={(e) => {
												clampScoreInput(e.currentTarget);
												handleScoreInput(f.id, 'home', e.currentTarget.value);
											}}
											aria-label="{f.home_team} score"
										/>
										<span class="dash">–</span>
										<input
											type="text"
											class="pn-score-cell"
											class:empty={state === 'empty'}
											inputmode="numeric"
											maxlength="2"
											pattern="[0-9]*"
											disabled={state === 'locked'}
											on:focus={selectScoreOnFocus}
											value={scoreValue(f.id, 'away')}
											on:input={(e) => {
												clampScoreInput(e.currentTarget);
												handleScoreInput(f.id, 'away', e.currentTarget.value);
											}}
											aria-label="{f.away_team} score"
										/>
									</div>
									<div class="team r" title={f.away_team}>
										<PnFlag code={teamCode(f.away_team)} w={28} h={20} />
										<span class="nm">{teamCode(f.away_team)}</span>
									</div>
								</div>
								<div class="save-row">
									{#if state === 'locked'}
										<span class="save-tag locked">Locked</span>
										<span>No edits</span>
									{:else if state === 'draft'}
										<span class="save-tag draft">Draft</span>
										<span>Save below to commit</span>
									{:else if state === 'saved'}
										<span class="save-tag saved">✓ Saved</span>
										<span>Submitted</span>
									{:else}
										<span class="save-tag empty">— Empty</span>
										<span>Enter a score to predict</span>
									{/if}
								</div>
							</div>
						{:else}
							<div style="padding: 16px; font-family: var(--mono); font-size: 11px; color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.08em;">
								{activeKoStageMeta.label} teams are still to be decided — this round fills in as the previous round completes.
							</div>
						{/each}
					</div>
				</section>
			{/if}

		{/if}

		<!-- Third-place standings modal. Triggered by the gold "3rd Place" pill
		     in the group nav (both desktop and mobile). Uses native <dialog>
		     for free a11y (focus trap, ESC-to-close, top-layer hoisting). The
		     backdrop click handler closes when the user clicks outside the
		     content (e.target === dialog when the click hits the backdrop).
		     a11y warnings suppressed because: (1) the click handler exists
		     specifically to implement the standard backdrop-click-to-dismiss
		     pattern, which has no keyboard equivalent — ESC-to-close is
		     already wired by native <dialog>; (2) <dialog> IS an interactive
		     element when opened via .showModal() but Svelte's linter doesn't
		     model that. -->
		<!-- svelte-ignore a11y-click-events-have-key-events -->
		<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
		<dialog
			class="pn-3rd-modal"
			bind:this={thirdPlaceDialog}
			on:close={() => (thirdPlaceModalOpen = false)}
			on:click={onDialogBackdropClick}
			aria-labelledby="pn-3rd-modal-title"
		>
			<div class="pn-3rd-modal-inner">
				<header class="pn-3rd-modal-h">
					<h2 id="pn-3rd-modal-title">Third-place standings · top 8 advance to R32</h2>
					<button class="close" type="button" on:click={closeThirdPlace} aria-label="Close">×</button>
				</header>
				<div class="pn-3rd-modal-body">
					{#if allGroupsComplete && thirdPlaceWarnings.length > 0}
						<div class="pn-tie-warn">
							<h4>⚠ Tied teams · alphabetical fallback in effect</h4>
							{#each thirdPlaceWarnings as w (w.tiedTeams.join('-'))}
								<p>
									<span class="teams">{w.tiedTeams.join(', ')}</span>
									are tied on points, goal difference and goals-for. Third-place teams
									come from different groups so head-to-head isn't applicable — they're
									currently ranked alphabetically. Adjust your predicted scores if you want
									a different team to qualify.
								</p>
							{/each}
						</div>
					{/if}
					<!-- Bare table — no .pn-stnd card wrapper (the modal box IS
					     the card). The thin scroll wrapper lets the 11-col
					     table scroll horizontally on narrow viewports. -->
					<div class="pn-3rd-table-scroll">
						<table class="pn-stnd-table">
							<thead>
								<tr>
									<th></th>
									<th class="c">Grp</th>
									<th>Team</th>
									<th class="c">P</th>
									<th class="c">W</th>
									<th class="c">D</th>
									<th class="c">L</th>
									<th class="c">GF</th>
									<th class="c">GA</th>
									<th class="c">GD</th>
									<th>Pts</th>
								</tr>
							</thead>
							<tbody>
								{#each thirdPlaceStandings as t, i (t.team)}
									<tr class:qualifies={i < 8}>
										<td>
											<span class="pos" class:adv={i < 8} class:out={i >= 8}>{i + 1}</span>
										</td>
										<td class="grp">{t.group}</td>
										<td>
											<span class="team">
												<PnFlag code={teamCode(t.team)} w={20} h={14} />
												<span class="nm-text">{displayTeamName(t.team)}</span>
											</span>
										</td>
										<td class="stat">{t.played}</td>
										<td class="stat">{t.won}</td>
										<td class="stat">{t.drawn}</td>
										<td class="stat">{t.lost}</td>
										<td class="stat">{t.goalsFor}</td>
										<td class="stat">{t.goalsAgainst}</td>
										<td class="stat gd" class:pos={t.goalDifference >= 0} class:neg={t.goalDifference < 0}>
											{t.goalDifference > 0 ? '+' : ''}{t.goalDifference}
										</td>
										<td>{t.points}</td>
									</tr>
								{:else}
									<tr><td colspan="11" class="empty-row">No third-place standings yet — fill in some group predictions</td></tr>
								{/each}
							</tbody>
						</table>
					</div>
					<p class="footnote">
						★ Top 8 third-placed teams (gold rows) qualify for the Round of 32 under FIFA 2026 format
					</p>
				</div>
			</div>
		</dialog>
	</PnPageShell>
{/if}

<style>
	/* Desktop/mobile hero toggle — inlined here (rather than in the
	 * external panini-wizard.css) so the rule ships with the SSR'd HTML
	 * and there's no first-paint flash in Vite dev mode where the
	 * external stylesheet otherwise loads slightly after the markup. */
	:global(.pn .pn-ws-only) {
		display: block;
	}
	:global(.pn .pn-wm-only) {
		display: none;
	}
	@media (max-width: 699px) {
		:global(.pn .pn-ws-only) {
			display: none;
		}
		:global(.pn .pn-wm-only) {
			display: block;
		}
	}
</style>
