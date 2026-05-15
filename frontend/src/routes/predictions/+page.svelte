<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
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
		hasUnsavedPhase2BracketChanges
	} from '$stores/predictions';
	import {
		fetchGroupFixtures,
		groupFixtures,
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
		phase2Countdown
	} from '$stores/phase';
	import { computeGroupStandingsMap } from '$lib/utils/standings';
	import { teamCode } from '$lib/utils/teamCodes';
	import type { Fixture, MatchPrediction, BracketPrediction, TeamAdvancementPrediction } from '$types';

	import PnPageShell from '$components/panini/PnPageShell.svelte';
	import PnFlag from '$components/panini/PnFlag.svelte';
	import PnKnockoutBracket from '$components/panini/PnKnockoutBracket.svelte';

	$: if (!$isAuthenticated) {
		goto('/login');
	}

	// Phase + pill selection state
	let activePhase: 'phase1' | 'phase2' = 'phase1';
	let initialPhaseSet = false;
	$: if (!initialPhaseSet && $isPhase2Active !== undefined) {
		activePhase = $isPhase2Active ? 'phase2' : 'phase1';
		initialPhaseSet = true;
	}

	// Section toggle controls the outer mode (Groups / Knockout / Bonus).
	// Group pills are a sub-selection that only appears in the Groups section.
	type Section = 'groups' | 'knockout' | 'bonus';
	let activeSection: Section = 'groups';
	// Active group pill — either a group letter (e.g. 'A') or 'thirdplace'.
	let activeGroupPill: string = '';

	let saveStatus: 'idle' | 'saving' | 'saved' | 'error' = 'idle';

	onMount(async () => {
		if ($isAuthenticated) {
			await Promise.all([
				fetchMatchPredictions(),
				fetchGroupFixtures(),
				fetchBracketPredictions()
			]);
			if ($isPhase2Active) {
				await Promise.all([
					fetchActualKnockoutFixtures(),
					fetchActualStandings(),
					fetchPhase2BracketPredictions()
				]);
			}
		}
		window.addEventListener('beforeunload', handleBeforeUnload);
	});

	onDestroy(() => {
		if (typeof window !== 'undefined') {
			window.removeEventListener('beforeunload', handleBeforeUnload);
		}
	});

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
	$: standingsMap = computeGroupStandingsMap($groupFixtures, livePredictionMap);

	// Per-group progress: count of fixtures that have a saved or unsaved pick
	function groupProgress(g: { group: string; fixtures: Fixture[] }): { done: number; total: number } {
		let done = 0;
		for (const f of g.fixtures) {
			if (livePredictionMap.has(f.id)) done++;
		}
		return { done, total: g.fixtures.length };
	}

	// Phase 1 knockout bracket is gated on completing every group prediction.
	// Phase 2 uses real standings so doesn't need the gate.
	$: phase1BracketGated =
		activePhase === 'phase1' &&
		!(
			phaseProgress.total > 0 &&
			phaseProgress.done === phaseProgress.total
		);

	$: phaseProgress = (() => {
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

	// ---- Selected group's fixtures ---------------------------------------
	$: selectedGroup =
		activeGroupPill && activeGroupPill !== 'thirdplace'
			? $groupFixtures.find((g) => g.group === activeGroupPill) ?? null
			: null;

	// ---- Third-place qualifying standings (top 8 of 12 advance to R32) ----
	$: thirdPlaceStandings = (() => {
		const thirds = [];
		for (const std of Object.values(standingsMap)) {
			if (std[2]) thirds.push(std[2]);
		}
		return thirds.sort((a, b) => {
			if (b.points !== a.points) return b.points - a.points;
			if (b.goalDifference !== a.goalDifference) return b.goalDifference - a.goalDifference;
			if (b.goalsFor !== a.goalsFor) return b.goalsFor - a.goalsFor;
			return a.team.localeCompare(b.team);
		});
	})();

	// Maximum goals allowed in a single match's score input. Enforced both in
	// the handler and via clampScoreInput on every keystroke so the user
	// sees the cap immediately — typing "16" instantly becomes "15".
	const MAX_GOALS = 15;

	function clampScoreInput(el: HTMLInputElement): void {
		const n = parseInt(el.value || '0', 10);
		if (Number.isNaN(n) || n < 0) {
			el.value = '0';
		} else if (n > MAX_GOALS) {
			el.value = String(MAX_GOALS);
		}
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

	function scoreValue(fixtureId: string, side: 'home' | 'away'): string {
		const u = $unsavedChanges[fixtureId];
		if (u) return String(side === 'home' ? u.home_score : u.away_score);
		const p = $predictionsByFixture.get(fixtureId);
		if (p) return String(side === 'home' ? p.home_score : p.away_score);
		return '';
	}

	function predictionState(f: Fixture): 'locked' | 'saved' | 'draft' | 'empty' {
		if (f.is_locked) return 'locked';
		if ($unsavedChanges[f.id]) return 'draft';
		if ($predictionsByFixture.get(f.id)) return 'saved';
		return 'empty';
	}

	// ---- Bracket (Phase 1) ------------------------------------------------
	let bracketComponent: PnKnockoutBracket;
	$: displayBracket = $unsavedBracketPrediction || $bracketPrediction;

	function bracketToPredictions(b: BracketPrediction): TeamAdvancementPrediction[] {
		const out: TeamAdvancementPrediction[] = [];
		const push = (stage: string, teams: (string | undefined)[] | undefined) => {
			if (!teams) return;
			for (const t of teams) if (t) out.push({ team: t, stage, group_position: null });
		};
		push('round_of_32', b.round_of_32);
		push('round_of_16', b.round_of_16);
		push('quarter_finals', b.quarter_finals);
		push('semi_finals', b.semi_finals);
		push('final', b.final);
		if (b.winner) out.push({ team: b.winner, stage: 'winner', group_position: null });
		return out;
	}

	let bracketSaveStatus: 'idle' | 'saving' | 'saved' | 'error' = 'idle';
	function handleBracketUpdate(event: CustomEvent<BracketPrediction>) {
		unsavedBracketPrediction.set(event.detail);
	}
	async function handleSaveBracket() {
		const b = $unsavedBracketPrediction;
		if (!b) return;
		bracketSaveStatus = 'saving';
		const ok = await saveBracketPredictions(bracketToPredictions(b));
		bracketSaveStatus = ok ? 'saved' : 'error';
		if (ok) {
			unsavedBracketPrediction.set(null);
			setTimeout(() => (bracketSaveStatus = 'idle'), 2000);
		}
	}

	// ---- Phase 2 wiring ---------------------------------------------------
	let phase2BracketComponent: PnKnockoutBracket;
	let phase2BracketSaveStatus: 'idle' | 'saving' | 'saved' | 'error' = 'idle';
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
	async function handleSavePhase2Bracket() {
		const b = $unsavedPhase2BracketPrediction;
		if (!b) return;
		phase2BracketSaveStatus = 'saving';
		const preds = bracketToPredictions(b).filter((p) => p.stage !== 'round_of_32');
		const ok = await saveBracketPredictions(preds);
		phase2BracketSaveStatus = ok ? 'saved' : 'error';
		if (ok) {
			unsavedPhase2BracketPrediction.set(null);
			setTimeout(() => (phase2BracketSaveStatus = 'idle'), 2000);
		}
	}
	function handleClearPhase2Bracket() {
		if (confirm('Clear all Phase 2 knockout selections?')) {
			phase2BracketComponent?.clearAllSelections();
		}
	}

	// ---- Unified save -----------------------------------------------------
	$: hasAnyUnsaved = $hasUnsavedChanges || $hasUnsavedBracketChanges || $hasUnsavedPhase2BracketChanges;
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
		const ok = await saveAllPredictions();
		saveStatus = ok ? 'saved' : 'error';
		if (ok) setTimeout(() => (saveStatus = 'idle'), 2000);
	}

	// ---- Bonus questions (real backend) ----------------------------------

	let bonusQuestions: import('$api/bonus').BonusQuestion[] = [];
	let bonusAnswers: Map<string, string> = new Map(); // question_id → answer
	let bonusInitial: Map<string, string> = new Map(); // for change tracking
	let bonusSaveStatus: 'idle' | 'saving' | 'saved' | 'error' = 'idle';

	$: hasUnsavedBonus = (() => {
		if (bonusQuestions.length === 0) return false;
		if (bonusAnswers.size !== bonusInitial.size) return true;
		for (const [k, v] of bonusAnswers) {
			if (bonusInitial.get(k) !== v) return true;
		}
		return false;
	})();

	async function loadBonus() {
		const [qs, preds] = await Promise.all([
			(await import('$api/bonus')).getBonusQuestions(),
			(await import('$api/bonus')).getMyBonusPredictions()
		]);
		bonusQuestions = qs;
		const map = new Map<string, string>();
		for (const p of preds) map.set(p.question_id, p.answer);
		bonusAnswers = map;
		bonusInitial = new Map(map);
	}

	async function handleSaveBonus() {
		bonusSaveStatus = 'saving';
		try {
			const { saveBonusPredictions } = await import('$api/bonus');
			const preds = Array.from(bonusAnswers.entries()).map(([question_id, answer]) => ({
				question_id,
				answer
			}));
			const saved = await saveBonusPredictions(preds);
			// Reset baseline to whatever the backend returned.
			const fresh = new Map<string, string>();
			for (const p of saved) fresh.set(p.question_id, p.answer);
			bonusAnswers = fresh;
			bonusInitial = new Map(fresh);
			bonusSaveStatus = 'saved';
			setTimeout(() => (bonusSaveStatus = 'idle'), 2000);
		} catch (_e) {
			bonusSaveStatus = 'error';
		}
	}

	function bonusAnswer(qid: string): string {
		return bonusAnswers.get(qid) ?? '';
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
		<!-- Hero / progress / phase toggle -->
		<section class="pn-wiz-hero">
			<div class="title-block">
				<div class="l">
					{activePhase === 'phase1' ? 'Phase I · Group Stage' : 'Phase II · Knockout'}
				</div>
				<div class="ttl"><em>Predict</em></div>
			</div>
			<div class="progress-stack">
				<div class="l">
					<span><b>{phaseProgress.done}</b> of {phaseProgress.total} matches</span>
					<span>{phaseProgress.pct}%</span>
				</div>
				<div class="bar"><div class="bar-fill" style="width: {phaseProgress.pct}%;"></div></div>
				<div class="l">
					<span>
						{#if activePhase === 'phase1'}
							{#if $isPhase1Locked}Locked{:else}Locks in {$phase1Countdown ?? '—'}{/if}
						{:else}
							{#if $isPhase2BracketLocked}Locked{:else}Locks in {$phase2Countdown ?? '—'}{/if}
						{/if}
					</span>
					<span>{$unsavedChangesCount} unsaved</span>
				</div>
			</div>
			<div class="toggle-stack">
				{#if $isPhase2Active}
					<div class="phase-toggle">
						<button class:on={activePhase === 'phase1'} on:click={() => (activePhase = 'phase1')}>Phase I</button>
						<button class:on={activePhase === 'phase2'} on:click={() => (activePhase = 'phase2')}>Phase II</button>
					</div>
				{/if}
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
			</div>
		</section>

		<!-- Phase 1 wizard -->
		{#if activePhase === 'phase1'}
			<!-- Group pills (only when the Groups section is selected) -->
			{#if activeSection === 'groups'}
				<section class="pn-wiz-nav">
					{#each $groupFixtures as g (g.group)}
						{@const gp = groupProgress(g)}
						<button
							class="pn-wiz-gp"
							class:active={activeGroupPill === g.group}
							class:done={gp.done === gp.total && gp.total > 0}
							on:click={() => (activeGroupPill = g.group)}
						>
							Group {g.group}
							<span class="gp-prog">{gp.done}/{gp.total}</span>
						</button>
					{/each}
					<button
						class="pn-wiz-gp special"
						class:active={activeGroupPill === 'thirdplace'}
						on:click={() => (activeGroupPill = 'thirdplace')}
					>
						3rd Place
					</button>
				</section>
			{/if}

			<!-- Group view -->
			{#if activeSection === 'groups' && activeGroupPill === 'thirdplace'}
				<section class="pn-wiz-group">
					<div class="pn-stnd">
						<div class="h">
							<span>Third-place standings · top 8 advance to R32</span>
							<span class="live">LIVE</span>
						</div>
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
												<span class="nm-text">{t.team}</span>
											</span>
										</td>
										<td class="stat">{t.played}</td>
										<td class="stat">{t.won}</td>
										<td class="stat">{t.drawn}</td>
										<td class="stat">{t.lost}</td>
										<td class="stat gd" class:pos={t.goalDifference >= 0} class:neg={t.goalDifference < 0}>
											{t.goalDifference > 0 ? '+' : ''}{t.goalDifference}
										</td>
										<td>{t.points}</td>
									</tr>
								{:else}
									<tr><td colspan="9" style="padding: 24px; text-align: center; font-family: var(--mono); color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.08em;">No third-place standings yet — fill in some group predictions</td></tr>
								{/each}
							</tbody>
						</table>
					</div>
					<p style="font-family: var(--mono); font-size: 11px; color: var(--ink-3); letter-spacing: 0.06em; text-transform: uppercase; margin-top: 10px;">
						★ Top 8 third-placed teams (gold rows) qualify for the Round of 32 under FIFA 2026 format
					</p>
				</section>
			{:else if activeSection === 'groups' && selectedGroup}
				{@const group = selectedGroup}
				{@const standings = standingsMap[group.group] ?? []}
				<section class="pn-wiz-group">
					<div class="pn-stnd">
						<div class="h">
							<span>Group {group.group} · Predicted Standings</span>
							<span class="live">LIVE</span>
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
									<th class="c">GD</th>
									<th>Pts</th>
								</tr>
							</thead>
							<tbody>
								{#each standings as t, i (t.team)}
									<tr>
										<td>
											<span class="pos" class:adv={i < 2} class:out={i >= 2}>{i + 1}</span>
										</td>
										<td>
											<span class="team">
												<PnFlag code={teamCode(t.team)} w={20} h={14} />
												<span class="nm-text">{t.team}</span>
											</span>
										</td>
										<td class="stat">{t.played}</td>
										<td class="stat">{t.won}</td>
										<td class="stat">{t.drawn}</td>
										<td class="stat">{t.lost}</td>
										<td class="stat gd" class:pos={t.goalDifference >= 0} class:neg={t.goalDifference < 0}>
											{t.goalDifference > 0 ? '+' : ''}{t.goalDifference}
										</td>
										<td>{t.points}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>

					<!-- Matches -->
					<div class="pn-wiz-matches">
						{#each group.fixtures as f (f.id)}
							{@const state = predictionState(f)}
							<div class="pn-mcard" class:locked={state === 'locked'} class:empty={state === 'empty'}>
								<div class="meta">
									<span><b>{teamCode(f.home_team)} vs {teamCode(f.away_team)}</b></span>
									<span>{new Date(f.kickoff).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })} · {new Date(f.kickoff).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}</span>
								</div>
								<div class="row">
									<div class="team">
										<PnFlag code={teamCode(f.home_team)} w={28} h={20} />
										<span class="nm">{f.home_team}</span>
									</div>
									<div class="pn-score">
										<input
											type="number"
											class="pn-score-cell"
											class:empty={state === 'empty'}
											min="0"
											max={MAX_GOALS}
											inputmode="numeric"
											disabled={f.is_locked}
											value={scoreValue(f.id, 'home')}
											on:input={(e) => {
												clampScoreInput(e.currentTarget);
												handleScoreInput(f.id, 'home', e.currentTarget.value);
											}}
											aria-label="{f.home_team} score"
										/>
										<span class="dash">–</span>
										<input
											type="number"
											class="pn-score-cell"
											class:empty={state === 'empty'}
											min="0"
											max={MAX_GOALS}
											inputmode="numeric"
											disabled={f.is_locked}
											value={scoreValue(f.id, 'away')}
											on:input={(e) => {
												clampScoreInput(e.currentTarget);
												handleScoreInput(f.id, 'away', e.currentTarget.value);
											}}
											aria-label="{f.away_team} score"
										/>
									</div>
									<div class="team r">
										<PnFlag code={teamCode(f.away_team)} w={28} h={20} />
										<span class="nm">{f.away_team}</span>
									</div>
								</div>
								<div class="save-row">
									{#if state === 'locked'}
										<span class="save-tag locked">Locked</span>
										<span>No edits</span>
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
			{:else if activeSection === 'knockout'}
				{#if phase1BracketGated}
					{@const pct = phaseProgress.total > 0 ? Math.round((phaseProgress.done / phaseProgress.total) * 100) : 0}
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
							<div class="v">{phaseProgress.done}<span class="of">/{phaseProgress.total}</span></div>
							<div class="label">matches predicted · {pct}%</div>
							<div class="bar"><div class="bar-fill" style="width: {pct}%;"></div></div>
						</div>
						<button class="pn-btn gold" type="button" on:click={() => (activeSection = 'groups')}>← Back to Groups</button>
					</section>
				{:else}
					<PnKnockoutBracket
						bind:this={bracketComponent}
						prediction={displayBracket}
						groupStandings={standingsMap}
						locked={$isPhase1Locked}
						phase="phase_1"
						on:update={handleBracketUpdate}
					/>
					<div style="display: flex; gap: 12px; justify-content: flex-end; margin-top: 12px; margin-bottom: 22px;">
						{#if $hasUnsavedBracketChanges}
							<button class="pn-btn gold" on:click={handleSaveBracket} disabled={bracketSaveStatus === 'saving'}>
								{bracketSaveStatus === 'saving' ? 'Saving…' : bracketSaveStatus === 'saved' ? '✓ Saved' : 'Save bracket'}
							</button>
						{/if}
					</div>
				{/if}
			{:else if activeSection === 'bonus'}
				{#each Object.entries(bonusByCategory) as [cat, qs] (cat)}
					{#if qs.length > 0}
						<div class="pn-banner" style="margin-top: 18px;">
							<span class="n">{cat === 'group_stage' ? '06' : cat === 'top_flop' ? '07' : '08'}</span>
							<h2>{CATEGORY_LABEL[cat]}</h2>
							<span class="end">{qs.length} question{qs.length === 1 ? '' : 's'}</span>
						</div>
						<section class="pn-bonus-row">
							{#each qs as bq (bq.id)}
								{@const answer = bonusAnswer(bq.id)}
								<div class="pn-bonus">
									<div class="l"><span class="pip"></span>{CATEGORY_LABEL[cat]}</div>
									<div class="q">{bq.label}</div>
									{#if bq.input_type === 'team'}
										<select
											class="answer"
											class:empty={!answer}
											value={answer}
											on:change={(e) => setBonusAnswer(bq.id, e.currentTarget.value)}
											style="cursor: pointer;"
										>
											<option value="">— Select a team —</option>
											{#each allTeams as t (t)}
												<option value={t}>{t}</option>
											{/each}
										</select>
									{:else}
										<input
											type="text"
											class="answer"
											class:empty={!answer}
											value={answer}
											on:input={(e) => setBonusAnswer(bq.id, e.currentTarget.value)}
											placeholder="Type a player name…"
										/>
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
					<button
						class="pn-btn gold"
						on:click={handleSaveBonus}
						disabled={!hasUnsavedBonus || bonusSaveStatus === 'saving'}
					>
						{bonusSaveStatus === 'saving'
							? 'Saving…'
							: bonusSaveStatus === 'saved'
								? '✓ Saved'
								: bonusSaveStatus === 'error'
									? '× Error — retry'
									: 'Save bonus picks'}
					</button>
				</div>
				<p style="font-family: var(--mono); font-size: 11px; color: var(--ink-3); letter-spacing: 0.06em; text-transform: uppercase;">
					★ Bonus picks lock with Phase I · admin will reveal correct answers as the tournament resolves
				</p>
			{/if}

			<!-- Sticky save bar -->
			<section class="pn-wiz-foot">
				<div class="stats">
					<b>{$unsavedChangesCount}</b> match · <b>{$hasUnsavedBracketChanges ? 'YES' : 'no'}</b> bracket unsaved
				</div>
				<button
					class="submit-btn"
					class:success={saveStatus === 'saved'}
					class:error={saveStatus === 'error'}
					on:click={handleSaveAll}
					disabled={!$hasUnsavedChanges || saveStatus === 'saving' || $matchPredictionsLoading}
				>
					{#if saveStatus === 'saving'}Saving…
					{:else if saveStatus === 'saved'}✓ Saved
					{:else if saveStatus === 'error'}× Error — retry
					{:else}Save Phase I ({$unsavedChangesCount}){/if}
				</button>
			</section>
		{/if}

		<!-- Phase 2 — Panini bracket + knockout match score cards -->
		{#if activePhase === 'phase2'}
			{#if $actualStandingsLoading}
				<p style="font-family: var(--mono); font-size: 11px; color: var(--ink-3); letter-spacing: 0.08em; text-transform: uppercase; padding: 16px;">Loading Phase II data…</p>
			{:else}
				<PnKnockoutBracket
					bind:this={phase2BracketComponent}
					prediction={phase2DisplayBracket}
					groupStandings={$actualGroupStandingsMap}
					locked={$isPhase2BracketLocked}
					phase="phase_2"
					hideR32
					on:update={handlePhase2BracketUpdate}
				/>
				<div style="display: flex; gap: 12px; justify-content: flex-end; margin-top: 12px; margin-bottom: 22px;">
					{#if $hasUnsavedPhase2BracketChanges}
						<button class="pn-btn gold" on:click={handleSavePhase2Bracket} disabled={phase2BracketSaveStatus === 'saving'}>
							{phase2BracketSaveStatus === 'saving' ? 'Saving…' : phase2BracketSaveStatus === 'saved' ? '✓ Saved' : 'Save bracket'}
						</button>
					{/if}
				</div>

				<!-- Knockout fixture score predictions (Phase 2 only) -->
				<section class="pn-wiz-group">
					<h2 style="font-family: var(--display); font-size: 22px; text-transform: uppercase; margin: 0 0 12px;">
						Knockout <em style="color: var(--red); font-style: normal;">scores</em>
					</h2>
					<div class="pn-wiz-matches">
						{#each $actualKnockoutFixtures as f (f.id)}
							{@const state = predictionState(f)}
							<div class="pn-mcard" class:locked={state === 'locked'} class:empty={state === 'empty'}>
								<div class="meta">
									<span><b>{teamCode(f.home_team)} vs {teamCode(f.away_team)}</b></span>
									<span>{new Date(f.kickoff).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })} · {new Date(f.kickoff).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}</span>
								</div>
								<div class="row">
									<div class="team">
										<PnFlag code={teamCode(f.home_team)} w={28} h={20} />
										<span class="nm">{f.home_team}</span>
									</div>
									<div class="pn-score">
										<input
											type="number"
											class="pn-score-cell"
											class:empty={state === 'empty'}
											min="0"
											max={MAX_GOALS}
											inputmode="numeric"
											disabled={f.is_locked}
											value={scoreValue(f.id, 'home')}
											on:input={(e) => {
												clampScoreInput(e.currentTarget);
												handleScoreInput(f.id, 'home', e.currentTarget.value);
											}}
											aria-label="{f.home_team} score"
										/>
										<span class="dash">–</span>
										<input
											type="number"
											class="pn-score-cell"
											class:empty={state === 'empty'}
											min="0"
											max={MAX_GOALS}
											inputmode="numeric"
											disabled={f.is_locked}
											value={scoreValue(f.id, 'away')}
											on:input={(e) => {
												clampScoreInput(e.currentTarget);
												handleScoreInput(f.id, 'away', e.currentTarget.value);
											}}
											aria-label="{f.away_team} score"
										/>
									</div>
									<div class="team r">
										<PnFlag code={teamCode(f.away_team)} w={28} h={20} />
										<span class="nm">{f.away_team}</span>
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
								No knockout fixtures yet — Phase II starts once groups conclude.
							</div>
						{/each}
					</div>
				</section>
			{/if}

			<!-- Sticky save bar for phase 2 match score picks -->
			<section class="pn-wiz-foot">
				<div class="stats">
					<b>{$unsavedChangesCount}</b> match unsaved
				</div>
				<button
					class="submit-btn"
					class:success={saveStatus === 'saved'}
					class:error={saveStatus === 'error'}
					on:click={handleSaveAll}
					disabled={!$hasUnsavedChanges || saveStatus === 'saving' || $matchPredictionsLoading}
				>
					{#if saveStatus === 'saving'}Saving…
					{:else if saveStatus === 'saved'}✓ Saved
					{:else if saveStatus === 'error'}× Error — retry
					{:else}Save Phase II ({$unsavedChangesCount}){/if}
				</button>
			</section>
		{/if}
	</PnPageShell>
{/if}
