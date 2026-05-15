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

	// The pill bar shows one tab per group + a Knockout pill + a Bonus pill
	type PillId = string; // e.g. 'group:A' | 'knockout' | 'bonus'
	let activePill: PillId = '';

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

	// Default the active pill to the first group once fixtures load
	$: if (!activePill && $groupFixtures.length > 0) {
		activePill = `group:${$groupFixtures[0].group}`;
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
	$: selectedGroup = activePill.startsWith('group:')
		? $groupFixtures.find((g) => g.group === activePill.slice(6)) ?? null
		: null;

	// ---- Score input handlers --------------------------------------------
	function handleScoreInput(fixtureId: string, side: 'home' | 'away', raw: string) {
		const value = Math.max(0, Math.min(20, parseInt(raw || '0', 10) || 0));
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

	// ---- Bonus questions: 6 stub questions, UI only -----------------------
	// Documented in panini-redesign-decisions.md: no backend persistence yet.
	const BONUS_QUESTIONS = [
		{ id: 'b1', label: 'Tournament winner', points: 50, options: ['ARG', 'BRA', 'FRA', 'ENG', 'ESP', 'GER'] },
		{ id: 'b2', label: 'Top scorer (Golden Boot)', points: 30, options: ['—'] },
		{ id: 'b3', label: 'Surprise team to reach SF', points: 20, options: ['—'] },
		{ id: 'b4', label: 'First red card', points: 15, options: ['—'] },
		{ id: 'b5', label: 'Most goals in a single match', points: 15, options: ['—'] },
		{ id: 'b6', label: 'Player of the Tournament', points: 25, options: ['—'] }
	];
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
			{#if $isPhase2Active}
				<div class="phase-toggle">
					<button class:on={activePhase === 'phase1'} on:click={() => (activePhase = 'phase1')}>Phase I</button>
					<button class:on={activePhase === 'phase2'} on:click={() => (activePhase = 'phase2')}>Phase II</button>
				</div>
			{/if}
		</section>

		<!-- Phase 1 wizard -->
		{#if activePhase === 'phase1'}
			<!-- Pill nav: groups + knockout + bonus -->
			<section class="pn-wiz-nav">
				{#each $groupFixtures as g (g.group)}
					{@const gp = groupProgress(g)}
					<button
						class="pn-wiz-gp"
						class:active={activePill === `group:${g.group}`}
						class:done={gp.done === gp.total && gp.total > 0}
						on:click={() => (activePill = `group:${g.group}`)}
					>
						Group {g.group}
						<span class="gp-prog">{gp.done}/{gp.total}</span>
					</button>
				{/each}
				<button
					class="pn-wiz-gp special"
					class:active={activePill === 'knockout'}
					on:click={() => (activePill = 'knockout')}
				>
					Knockout
				</button>
				<button
					class="pn-wiz-gp special"
					class:active={activePill === 'bonus'}
					on:click={() => (activePill = 'bonus')}
				>
					Bonus
				</button>
			</section>

			<!-- Group view -->
			{#if selectedGroup}
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
												{t.team}
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
											max="20"
											disabled={f.is_locked}
											value={scoreValue(f.id, 'home')}
											on:input={(e) => handleScoreInput(f.id, 'home', e.currentTarget.value)}
											aria-label="{f.home_team} score"
										/>
										<span class="dash">–</span>
										<input
											type="number"
											class="pn-score-cell"
											class:empty={state === 'empty'}
											min="0"
											max="20"
											disabled={f.is_locked}
											value={scoreValue(f.id, 'away')}
											on:input={(e) => handleScoreInput(f.id, 'away', e.currentTarget.value)}
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
			{:else if activePill === 'knockout'}
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
			{:else if activePill === 'bonus'}
				<section class="pn-bonus-row">
					{#each BONUS_QUESTIONS as bq (bq.id)}
						<div class="pn-bonus">
							<div class="l"><span class="pip"></span>Phase I bonus</div>
							<div class="q">{bq.label}</div>
							<div class="answer empty">
								<span>SELECT</span>
								<span style="font-family: var(--mono); color: var(--ink-3);">▼</span>
							</div>
							<div class="pts-pill">+{bq.points} pts</div>
						</div>
					{/each}
				</section>
				<p style="font-family: var(--mono); font-size: 11px; color: var(--ink-3); letter-spacing: 0.06em; text-transform: uppercase;">
					★ Bonus questions are UI-only for now · backend persistence coming soon
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
											max="20"
											disabled={f.is_locked}
											value={scoreValue(f.id, 'home')}
											on:input={(e) => handleScoreInput(f.id, 'home', e.currentTarget.value)}
											aria-label="{f.home_team} score"
										/>
										<span class="dash">–</span>
										<input
											type="number"
											class="pn-score-cell"
											class:empty={state === 'empty'}
											min="0"
											max="20"
											disabled={f.is_locked}
											value={scoreValue(f.id, 'away')}
											on:input={(e) => handleScoreInput(f.id, 'away', e.currentTarget.value)}
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
