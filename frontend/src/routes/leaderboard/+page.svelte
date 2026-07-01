<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { isAuthenticated, user } from '$stores/auth';
	import {
		fetchLeaderboard,
		setPhase,
		startPolling,
		stopPolling,
		leaderboard,
		leaderboardLoading,
		lastCalculated,
		totalParticipants,
		currentUserPosition,
		leaderboardPhase,
		type LeaderboardPhase
	} from '$stores/leaderboard';
	import { getGroupTotal, type PhaseBreakdown, type PointBreakdown } from '$types';
	import { getProgression, type ProgressionResponse } from '$lib/api/leaderboard';
	import PnPageShell from '$components/panini/PnPageShell.svelte';
	import PnBumpChart from '$components/panini/PnBumpChart.svelte';
	import PnIcon from '$components/panini/PnIcon.svelte';

	$: if (!$isAuthenticated) {
		goto('/login');
	}

	onMount(() => {
		if ($isAuthenticated) {
			startPolling(60000);
			if ($page.url.searchParams.get('view') === 'progression') {
				void setView('progression');
			}
		}
	});

	onDestroy(() => {
		stopPolling();
	});

	async function handlePhaseChange(phase: LeaderboardPhase) {
		await setPhase(phase);
	}

	// Show the form chip (🔥/🧊) only once a run reaches this length — a single
	// result isn't a streak, and 2+ is the point where it's worth ribbing.
	const STREAK_MIN = 2;

	function ordinal(n: number): string {
		if (n % 100 >= 11 && n % 100 <= 13) return 'th';
		switch (n % 10) {
			case 1: return 'st';
			case 2: return 'nd';
			case 3: return 'rd';
			default: return 'th';
		}
	}

	function formatLastUpdated(date: string | null): string {
		if (!date) return '';
		return new Date(date).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
	}

	// Match-cell value for the current phase filter
	function matchPts(b: PointBreakdown, phase: LeaderboardPhase): number {
		if (phase === 'phase_1') return b.phase1.match_outcome_points + b.phase1.exact_score_points + b.phase1.hybrid_bonus_points;
		if (phase === 'phase_2') return b.phase2.match_outcome_points + b.phase2.exact_score_points + b.phase2.hybrid_bonus_points;
		return b.match_total;
	}
	function exactPts(b: PointBreakdown, phase: LeaderboardPhase): number {
		if (phase === 'phase_1') return b.phase1.exact_score_points;
		if (phase === 'phase_2') return b.phase2.exact_score_points;
		return b.exact_score_points;
	}
	function outcomePts(b: PointBreakdown, phase: LeaderboardPhase): number {
		if (phase === 'phase_1') return b.phase1.match_outcome_points;
		if (phase === 'phase_2') return b.phase2.match_outcome_points;
		return b.match_outcome_points;
	}
	// "Rarity" column = the match rarity (hybrid) bonus ONLY — per-phase in the
	// phase tabs, the cross-phase aggregate in Overall. This is the reward for a
	// correct outcome few others picked; it lives inside the match score.
	function rarityPts(b: PointBreakdown, phase: LeaderboardPhase): number {
		if (phase === 'phase_1') return b.phase1.hybrid_bonus_points;
		if (phase === 'phase_2') return b.phase2.hybrid_bonus_points;
		return b.hybrid_bonus_points;
	}
	// "Bonus" column = bonus-question points (Golden Ball / group / top-flop) —
	// a SEPARATE mechanism from the rarity bonus. They're cross-phase (locked
	// with Phase I, scored when the admin reveals answers) and sit OUTSIDE both
	// phases' match/bracket totals, so they only populate the Overall column —
	// where Total includes them. In the phase tabs they're 0, keeping each
	// phase's visible columns reconciled with that phase's total.
	function questionPts(b: PointBreakdown, phase: LeaderboardPhase): number {
		return phase === 'overall' ? b.bonus_question_points : 0;
	}
	function bracketPts(b: PointBreakdown, phase: LeaderboardPhase): number {
		if (phase === 'phase_1') return getGroupTotal(b.phase1) + b.phase1.round_of_32_points + b.phase1.round_of_16_points + b.phase1.quarter_final_points + b.phase1.semi_final_points + b.phase1.final_points + b.phase1.winner_points;
		if (phase === 'phase_2') return getGroupTotal(b.phase2) + b.phase2.round_of_32_points + b.phase2.round_of_16_points + b.phase2.quarter_final_points + b.phase2.semi_final_points + b.phase2.final_points + b.phase2.winner_points;
		return b.bracket_total;
	}

	// Standings table vs Progression bump chart
	type View = 'table' | 'progression';
	let view: View = 'table';
	let progression: ProgressionResponse | null = null;
	let progressionLoading = false;
	async function setView(v: View) {
		view = v;
		if (v === 'progression' && !progression && !progressionLoading) {
			progressionLoading = true;
			try {
				progression = await getProgression();
			} finally {
				progressionLoading = false;
			}
		}
	}

	// Row expansion state
	let expanded = new Set<string>();
	function toggle(userId: string) {
		if (expanded.has(userId)) expanded.delete(userId);
		else expanded.add(userId);
		expanded = expanded; // trigger reactivity
	}

	// Phases listed in the per-row expander, in order
	const DETAIL_PHASES: Array<{ k: 'phase1' | 'phase2'; name: string }> = [
		{ k: 'phase1', name: 'Phase I' },
		{ k: 'phase2', name: 'Phase II' }
	];

	// Per-phase breakdown helpers
	function phaseTotal(p: PhaseBreakdown): number {
		return (
			p.match_outcome_points +
			p.exact_score_points +
			p.hybrid_bonus_points +
			getGroupTotal(p) +
			p.round_of_32_points +
			p.round_of_16_points +
			p.quarter_final_points +
			p.semi_final_points +
			p.final_points +
			p.winner_points
		);
	}
	function phaseBracketSum(p: PhaseBreakdown): number {
		return (
			getGroupTotal(p) +
			p.round_of_32_points +
			p.round_of_16_points +
			p.quarter_final_points +
			p.semi_final_points +
			p.final_points +
			p.winner_points
		);
	}

	// Bracket sub-stages shown in the expander, in tournament order. group_advance
	// is intentionally omitted (always 0 — group qualification is scored as
	// round_of_32_points). 'Qual' = got out of the group; 'Pos' = correct group
	// position bonus (Phase 1 only).
	const STAGE_DEFS: Array<{ key: string; label: string; get: (p: PhaseBreakdown) => number }> = [
		{ key: 'qual', label: 'Qual', get: (p) => p.round_of_32_points },
		{ key: 'pos', label: 'Pos', get: (p) => p.group_position_points },
		{ key: 'r16', label: 'R16', get: (p) => p.round_of_16_points },
		{ key: 'qf', label: 'QF', get: (p) => p.quarter_final_points },
		{ key: 'sf', label: 'SF', get: (p) => p.semi_final_points },
		{ key: 'final', label: 'Final', get: (p) => p.final_points },
		{ key: 'champ', label: 'Champ', get: (p) => p.winner_points }
	];

	// Auto-hide: a phase card / bracket stage chip is shown only if SOMEONE on the
	// board has non-zero points there. So "no Phase II yet" or "no R16 yet" simply
	// vanish instead of showing a wall of zeros. Because a stage is hidden only
	// when it's zero for everyone, the visible chips still sum to the Bracket total.
	$: phaseVisible = {
		phase1: $leaderboard.some((r) => phaseTotal(r.breakdown.phase1) > 0),
		phase2: $leaderboard.some((r) => phaseTotal(r.breakdown.phase2) > 0)
	};
	$: stageVisible = {
		phase1: STAGE_DEFS.filter((s) => $leaderboard.some((r) => s.get(r.breakdown.phase1) > 0)),
		phase2: STAGE_DEFS.filter((s) => $leaderboard.some((r) => s.get(r.breakdown.phase2) > 0))
	};
	// Same auto-hide rule for the cross-phase Bonus Questions card: shown in the
	// expander only once someone on the board has scored a bonus question.
	$: bonusQVisible = $leaderboard.some((r) => r.breakdown.bonus_question_points > 0);

	// Row-expander scope follows the active standings tab: Overall shows both
	// phases + Bonus Questions (as today); Phase I shows only Phase I + Bonus
	// Questions (bonus locks with Phase 1); Phase II shows ONLY Phase II — no
	// cross-phase bonus card, since Bonus Questions aren't part of "Phase 2 only".
	$: expanderPhases =
		$leaderboardPhase === 'phase_1'
			? DETAIL_PHASES.filter((p) => p.k === 'phase1')
			: $leaderboardPhase === 'phase_2'
				? DETAIL_PHASES.filter((p) => p.k === 'phase2')
				: DETAIL_PHASES;
	$: expanderShowsBonus = bonusQVisible && $leaderboardPhase !== 'phase_2';

	$: yourRank = $currentUserPosition?.position ?? 0;
	$: yourPoints = $currentUserPosition?.total_points ?? 0;
	$: leaderPoints = $leaderboard[0]?.total_points ?? 0;
	$: toFirst = yourRank > 1 ? yourPoints - leaderPoints : 0;
	$: yourMovement = $currentUserPosition?.movement ?? 0;
	$: yourExact = $currentUserPosition?.exact_scores ?? 0;
	$: yourOutcomes = $currentUserPosition?.correct_outcomes ?? 0;
</script>

<svelte:head>
	<title>Standings — Predictor</title>
</svelte:head>

{#if $isAuthenticated}
	<PnPageShell>
		<!-- ===== DESKTOP ===== -->
		<div class="pn-desk">
			<div class="pn-lb-h">
				<div class="ttl">THE <em>STANDINGS</em></div>
				<div style="display: flex; flex-direction: column; align-items: flex-end; gap: 8px;">
					<div class="pn-lb-view" style="margin-bottom: 0;">
						<button class:on={view === 'table'} on:click={() => setView('table')}>Standings</button>
						<button class:on={view === 'progression'} on:click={() => setView('progression')}>Progression</button>
					</div>
					{#if view === 'table'}
						<div class="pn-lb-tabs">
							<button class:on={$leaderboardPhase === 'overall'} on:click={() => handlePhaseChange('overall')}>Overall</button>
							<button class:on={$leaderboardPhase === 'phase_1'} on:click={() => handlePhaseChange('phase_1')}>Phase I</button>
							<button class:on={$leaderboardPhase === 'phase_2'} on:click={() => handlePhaseChange('phase_2')}>Phase II</button>
						</div>
					{/if}
				</div>
			</div>

			{#if $currentUserPosition}
				<div class="pn-lb-self">
					<div class="num">
						{yourRank}<span style="font-size: 24px; color: rgba(255,255,255,0.65); vertical-align: top;">{ordinal(yourRank)}</span>
					</div>
					<div>
						<div class="nm">
							{$currentUserPosition.user_name}
							<span style="background: var(--paper); color: var(--red); padding: 2px 6px; font-size: 11px; margin-left: 8px;">YOU</span>
						</div>
						<div class="sub">
							{yourOutcomes} outcomes · {yourExact} exact
							{#if yourMovement !== 0}
								· {yourMovement > 0 ? '▲' : '▼'}{Math.abs(yourMovement)} since yesterday
							{/if}
						</div>
					</div>
					<div class="stat"><div class="l">Total</div><div class="v">{yourPoints}</div></div>
					<div class="stat"><div class="l">To #1</div><div class="v">{toFirst < 0 ? toFirst : toFirst === 0 ? '—' : `+${toFirst}`}</div></div>
				</div>
			{/if}

			{#if view === 'progression'}
				<div class="pn-card pn-lb-card">
					<div class="pn-card-h">
						<span>★ PROGRESSION · RANK BY DAY</span>
						<span class="right">{#if progressionLoading}LOADING…{/if}</span>
					</div>
					<div class="pn-card-body" style="padding: 16px 20px 20px;">
						{#if progression}
							<PnBumpChart users={progression.users} youId={$user?.id ?? null} />
						{:else if !progressionLoading}
							<div style="padding: 24px; text-align: center; font-family: var(--mono); color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.08em;">No history yet</div>
						{/if}
					</div>
				</div>
			{:else}
			<div class="pn-card pn-lb-card">
				<div class="pn-card-h">
					<span>★ STANDINGS · {$totalParticipants || $leaderboard.length} PLAYERS</span>
					<span class="right">
						{#if $leaderboardLoading}LOADING…{:else if $lastCalculated}Updated {formatLastUpdated($lastCalculated)}{/if}
					</span>
				</div>
				<div class="pn-card-body">
					<table class="pn-lb-table">
						<thead>
							<tr>
								<th>#</th>
								<th>Player</th>
								<th class="c">Outcome</th>
								<th class="c">Exact</th>
								<th class="c">Rarity</th>
								<th class="c">Bonus</th>
								<th class="c">Bracket</th>
								<th class="r">Total</th>
								<th class="r">Move</th>
								<th></th>
							</tr>
						</thead>
						<tbody>
							{#each $leaderboard as r (r.user_id)}
								{@const isYou = r.user_id === $user?.id}
								{@const isOpen = expanded.has(r.user_id)}
								<tr class:you={isYou} class:ghost={r.is_ghost} class:open={isOpen} on:click={() => toggle(r.user_id)} style="cursor: pointer;">
									<td class="pos" class:gold={!r.is_ghost && r.position <= 3}>
										{#if r.is_ghost}
											<span class="ghost-chip" role="img" aria-label="Unranked bot entry" title="Unranked bot — for reference only">
												<PnIcon name="ghost" size={14} color="var(--paper)" />
											</span>
										{:else}{r.position}{/if}
									</td>
									<td class="nm-cell">
										<a href="/profile/{r.user_id}" style="color: inherit; text-decoration: none;" on:click|stopPropagation>
											{r.user_name}{#if !r.is_ghost && r.hot_streak >= STREAK_MIN}<span class="streak hot" title="{r.hot_streak} correct outcomes in a row">🔥{r.hot_streak}</span>{:else if !r.is_ghost && r.cold_streak >= STREAK_MIN}<span class="streak cold" title="{r.cold_streak} wrong in a row">🧊{r.cold_streak}</span>{/if}
											<span class="h">{isYou ? 'YOU' : r.is_ghost ? 'UNRANKED' : `@${r.user_name.split(' ')[0].toLowerCase()}`}</span>
										</a>
									</td>
									<td class="c">{outcomePts(r.breakdown, $leaderboardPhase)}</td>
									<td class="c exact">{exactPts(r.breakdown, $leaderboardPhase)}</td>
									<td class="c rarity">{rarityPts(r.breakdown, $leaderboardPhase)}</td>
									<td class="c bonusq">{questionPts(r.breakdown, $leaderboardPhase)}</td>
									<td class="c bracket">{bracketPts(r.breakdown, $leaderboardPhase)}</td>
									<td class="r total">{#if isYou}<em>{r.total_points}</em>{:else}{r.total_points}{/if}</td>
									<td class="r mv">
										{#if r.movement > 0}<span class="up">▲{r.movement}</span>
										{:else if r.movement < 0}<span class="dn">▼{Math.abs(r.movement)}</span>
										{:else}<span class="eq">—</span>{/if}
									</td>
									<td class="expand"><span class="chev">▾</span></td>
								</tr>
								{#if isOpen}
									<tr class="detail">
										<td colspan="10">
											<div class="pn-lb-detail">
												{#each expanderPhases as ph (ph.k)}
													{#if phaseVisible[ph.k]}
														{@const p = r.breakdown[ph.k]}
														<div class="phase">
															<div class="ph-h">
																<span>{ph.name}</span>
																<b>{phaseTotal(p)} pts</b>
															</div>
															<div class="grid">
																<div class="cell"><div class="l">Outcome</div><div class="v">{p.match_outcome_points}</div></div>
																<div class="cell"><div class="l">Exact</div><div class="v exact">{p.exact_score_points}</div></div>
																<div class="cell"><div class="l">Rarity</div><div class="v rarity">{p.hybrid_bonus_points}</div></div>
															</div>
															{#if stageVisible[ph.k].length}
																<div class="brk">
																	<div class="brk-h"><span>Bracket</span><b>{phaseBracketSum(p)}</b></div>
																	<div class="brk-strip">
																		{#each stageVisible[ph.k] as s (s.key)}
																			<div class="chip"><div class="cl">{s.label}</div><div class="cv">{s.get(p)}</div></div>
																		{/each}
																	</div>
																</div>
															{/if}
														</div>
													{/if}
												{/each}
												{#if expanderShowsBonus}
													<div class="phase bonusq">
														<div class="ph-h">
															<span>Bonus Questions</span>
															<b>{r.breakdown.bonus_question_points} pts</b>
														</div>
														<div class="bq-note">Golden Ball · group · top/flop</div>
													</div>
												{/if}
											</div>
										</td>
									</tr>
								{/if}
							{:else}
								<tr><td colspan="10" style="padding: 24px; text-align: center; font-family: var(--mono); color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.08em;">No standings yet</td></tr>
							{/each}
						</tbody>
					</table>
				</div>
			</div>
			{/if}
		</div>

		<!-- ===== MOBILE ===== -->
		<div class="pn-mob">
			<div class="pn-m-lb-h">
				<div class="ttl">THE <em>STANDINGS</em></div>
				<div class="meta">{$totalParticipants || $leaderboard.length} PLAYERS<br />{#if $lastCalculated}UPD {formatLastUpdated($lastCalculated)}{/if}</div>
			</div>

			<div class="pn-lb-view">
				<button class:on={view === 'table'} on:click={() => setView('table')}>Standings</button>
				<button class:on={view === 'progression'} on:click={() => setView('progression')}>Progression</button>
			</div>

			{#if view === 'table'}
			<div class="pn-m-lb-tabs">
				<button class:on={$leaderboardPhase === 'overall'} on:click={() => handlePhaseChange('overall')}>Overall</button>
				<button class:on={$leaderboardPhase === 'phase_1'} on:click={() => handlePhaseChange('phase_1')}>Phase I</button>
				<button class:on={$leaderboardPhase === 'phase_2'} on:click={() => handlePhaseChange('phase_2')}>Phase II</button>
			</div>
			{/if}

			{#if $currentUserPosition}
				<div class="pn-m-lb-self">
					<div class="num">
						{yourRank}<span style="font-size: 16px; color: rgba(255,255,255,0.7); vertical-align: top;">{ordinal(yourRank)}</span>
					</div>
					<div>
						<div class="nm">{$currentUserPosition.user_name}</div>
						<div class="sub">{yourExact} ex · {yourOutcomes} outc {#if yourMovement !== 0}· {yourMovement > 0 ? '▲' : '▼'}{Math.abs(yourMovement)}{/if}</div>
					</div>
					<div class="pts">
						<div class="v">{yourPoints}</div>
						<div class="l">{toFirst === 0 ? 'LEADER' : `${toFirst} to #1`}</div>
					</div>
				</div>
			{/if}

			{#if view === 'progression'}
				<div class="pn-card" style="padding: 12px;">
					{#if progression}
						<PnBumpChart users={progression.users} youId={$user?.id ?? null} />
					{:else}
						<div style="padding: 24px; text-align: center; font-family: var(--mono); font-size: 11px; color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.08em;">
							{progressionLoading ? 'Loading…' : 'No history yet'}
						</div>
					{/if}
				</div>
			{:else}
			<div class="pn-m-lb-rows">
				{#each $leaderboard as r (r.user_id)}
					{@const isYou = r.user_id === $user?.id}
					{@const isOpen = expanded.has(r.user_id)}
					<div
						class="pn-m-lb-row"
						class:gold={!r.is_ghost && r.position <= 3}
						class:you={isYou}
						class:ghost={r.is_ghost}
						class:open={isOpen}
						role="button"
						tabindex="0"
						on:click={() => toggle(r.user_id)}
						on:keydown={(e) => (e.key === 'Enter' || e.key === ' ') && toggle(r.user_id)}
					>
						<div class="pos">
							{#if r.is_ghost}
								<span class="ghost-chip" role="img" aria-label="Unranked bot entry">
									<PnIcon name="ghost" size={13} color="var(--paper)" />
								</span>
							{:else}{r.position}{/if}
						</div>
						<div>
							<div class="nm">
								<!-- Name navigates to the profile; the rest of the row still toggles. -->
								<a href="/profile/{r.user_id}" style="color: inherit; text-decoration: none;" on:click|stopPropagation>
									{r.user_name}
								</a>
							</div>
							<div class="h">{r.correct_outcomes} outc · {r.exact_scores} ex{#if !r.is_ghost && r.hot_streak >= STREAK_MIN} · <span class="streak hot" title="{r.hot_streak} correct outcomes in a row">🔥{r.hot_streak}</span>{:else if !r.is_ghost && r.cold_streak >= STREAK_MIN} · <span class="streak cold" title="{r.cold_streak} wrong in a row">🧊{r.cold_streak}</span>{/if} · <span class="chev">▾</span></div>
						</div>
						<div class="pts">{r.total_points}</div>
						<div class="mv">
							{#if r.movement > 0}<span class="up">▲{r.movement}</span>
							{:else if r.movement < 0}<span class="dn">▼{Math.abs(r.movement)}</span>
							{:else}<span class="eq">—</span>{/if}
						</div>
					</div>
					{#if isOpen}
						<div class="pn-m-lb-detail">
							{#each expanderPhases as ph (ph.k)}
								{#if phaseVisible[ph.k]}
									{@const p = r.breakdown[ph.k]}
									<div class="phase">
										<div class="ph-h">
											<span>{ph.name}</span>
											<b>{phaseTotal(p)} pts</b>
										</div>
										<div class="grid">
											<div class="cell"><div class="l">Out</div><div class="v">{p.match_outcome_points}</div></div>
											<div class="cell"><div class="l">Exact</div><div class="v exact">{p.exact_score_points}</div></div>
											<div class="cell"><div class="l">Rarity</div><div class="v rarity">{p.hybrid_bonus_points}</div></div>
										</div>
										{#if stageVisible[ph.k].length}
											<div class="brk">
												<div class="brk-h"><span>Bracket</span><b>{phaseBracketSum(p)}</b></div>
												<div class="brk-strip">
													{#each stageVisible[ph.k] as s (s.key)}
														<div class="chip"><div class="cl">{s.label}</div><div class="cv">{s.get(p)}</div></div>
													{/each}
												</div>
											</div>
										{/if}
									</div>
								{/if}
							{/each}
							{#if expanderShowsBonus}
								<div class="phase bonusq">
									<div class="ph-h">
										<span>Bonus Questions</span>
										<b>{r.breakdown.bonus_question_points} pts</b>
									</div>
									<div class="bq-note">Golden Ball · group · top/flop</div>
								</div>
							{/if}
						</div>
					{/if}
				{:else}
					<div style="padding: 24px; text-align: center; font-family: var(--mono); font-size: 11px; color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.08em;">
						No standings yet
					</div>
				{/each}
			</div>
			{/if}
		</div>
	</PnPageShell>
{/if}
