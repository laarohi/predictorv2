<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
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
	import PnPageShell from '$components/panini/PnPageShell.svelte';
	import PnSparkline from '$components/panini/PnSparkline.svelte';
	import { stubRankTrajectory } from '$lib/stubs/panini';

	$: if (!$isAuthenticated) {
		goto('/login');
	}

	onMount(() => {
		if ($isAuthenticated) {
			startPolling(60000);
		}
	});

	onDestroy(() => {
		stopPolling();
	});

	async function handlePhaseChange(phase: LeaderboardPhase) {
		await setPhase(phase);
	}

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
	function bonusPts(b: PointBreakdown, phase: LeaderboardPhase): number {
		if (phase === 'phase_1') return b.phase1.hybrid_bonus_points;
		if (phase === 'phase_2') return b.phase2.hybrid_bonus_points;
		return b.hybrid_bonus_points;
	}
	function bracketPts(b: PointBreakdown, phase: LeaderboardPhase): number {
		if (phase === 'phase_1') return getGroupTotal(b.phase1) + b.phase1.round_of_32_points + b.phase1.round_of_16_points + b.phase1.quarter_final_points + b.phase1.semi_final_points + b.phase1.final_points + b.phase1.winner_points;
		if (phase === 'phase_2') return getGroupTotal(b.phase2) + b.phase2.round_of_32_points + b.phase2.round_of_16_points + b.phase2.quarter_final_points + b.phase2.semi_final_points + b.phase2.final_points + b.phase2.winner_points;
		return b.bracket_total;
	}

	$: yourRank = $currentUserPosition?.position ?? 0;
	$: yourPoints = $currentUserPosition?.total_points ?? 0;
	$: leaderPoints = $leaderboard[0]?.total_points ?? 0;
	$: toFirst = yourRank > 1 ? yourPoints - leaderPoints : 0;
	$: yourMovement = $currentUserPosition?.movement ?? 0;
	$: yourExact = $currentUserPosition?.exact_scores ?? 0;
	$: yourOutcomes = $currentUserPosition?.correct_outcomes ?? 0;

	// Roughly how many points are still in play — sum of remaining bracket
	// stages + estimated unfinished match exact/outcome ceiling. For now
	// use a fixed-ish number; this slot exists in the design.
	$: availablePts = 288;
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
				<div class="pn-lb-tabs">
					<button class:on={$leaderboardPhase === 'overall'} on:click={() => handlePhaseChange('overall')}>Overall</button>
					<button class:on={$leaderboardPhase === 'phase_1'} on:click={() => handlePhaseChange('phase_1')}>Phase I</button>
					<button class:on={$leaderboardPhase === 'phase_2'} on:click={() => handlePhaseChange('phase_2')}>Phase II</button>
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
							{yourExact} exact · {yourOutcomes} outcomes
							{#if yourMovement !== 0}
								· {yourMovement > 0 ? '▲' : '▼'}{Math.abs(yourMovement)} last update
							{/if}
						</div>
					</div>
					<div class="stat"><div class="l">Total</div><div class="v">{yourPoints}</div></div>
					<div class="stat"><div class="l">To #1</div><div class="v">{toFirst < 0 ? toFirst : toFirst === 0 ? '—' : `+${toFirst}`}</div></div>
					<div class="stat"><div class="l">Available</div><div class="v">{availablePts}</div></div>
				</div>
			{/if}

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
								<th class="c">Exact</th>
								<th class="c">Outcome</th>
								<th class="c">Bonus</th>
								<th class="c">Bracket</th>
								<th class="c">Trend · 7d</th>
								<th class="r">Total</th>
								<th class="r">Move</th>
							</tr>
						</thead>
						<tbody>
							{#each $leaderboard as r (r.user_id)}
								{@const isYou = r.user_id === $user?.id}
								{@const traj = stubRankTrajectory(r.user_id, r.position, $totalParticipants || $leaderboard.length || 32)}
								<tr class:you={isYou}>
									<td class="pos" class:gold={r.position <= 3}>{r.position}</td>
									<td class="nm-cell">
										<a href="/profile/{r.user_id}" style="color: inherit; text-decoration: none;">
											{r.user_name}
											<span class="h">{isYou ? 'YOU' : `@${r.user_name.split(' ')[0].toLowerCase()}`}</span>
										</a>
									</td>
									<td class="c exact">{exactPts(r.breakdown, $leaderboardPhase)}</td>
									<td class="c">{outcomePts(r.breakdown, $leaderboardPhase)}</td>
									<td class="c bonus">{bonusPts(r.breakdown, $leaderboardPhase)}</td>
									<td class="c bracket">{bracketPts(r.breakdown, $leaderboardPhase)}</td>
									<td class="c">
										<PnSparkline
											ranks={traj.ranks}
											maxRank={traj.maxRank}
											width={80}
											height={22}
											strokeColor={isYou ? 'var(--red)' : 'var(--ink)'}
											fillColor="transparent"
											markerColor={isYou ? 'var(--red)' : 'var(--ink)'}
										/>
									</td>
									<td class="r total">{#if isYou}<em>{r.total_points}</em>{:else}{r.total_points}{/if}</td>
									<td class="r mv">
										{#if r.movement > 0}<span class="up">▲{r.movement}</span>
										{:else if r.movement < 0}<span class="dn">▼{Math.abs(r.movement)}</span>
										{:else}<span class="eq">—</span>{/if}
									</td>
								</tr>
							{:else}
								<tr><td colspan="9" style="padding: 24px; text-align: center; font-family: var(--mono); color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.08em;">No standings yet</td></tr>
							{/each}
						</tbody>
					</table>
				</div>
			</div>
		</div>

		<!-- ===== MOBILE ===== -->
		<div class="pn-mob">
			<div class="pn-m-lb-h">
				<div class="ttl">THE <em>STANDINGS</em></div>
				<div class="meta">{$totalParticipants || $leaderboard.length} PLAYERS<br />{#if $lastCalculated}UPD {formatLastUpdated($lastCalculated)}{/if}</div>
			</div>

			<div class="pn-m-lb-tabs">
				<button class:on={$leaderboardPhase === 'overall'} on:click={() => handlePhaseChange('overall')}>Overall</button>
				<button class:on={$leaderboardPhase === 'phase_1'} on:click={() => handlePhaseChange('phase_1')}>Phase I</button>
				<button class:on={$leaderboardPhase === 'phase_2'} on:click={() => handlePhaseChange('phase_2')}>Phase II</button>
			</div>

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

			<div class="pn-m-lb-rows">
				{#each $leaderboard as r (r.user_id)}
					{@const isYou = r.user_id === $user?.id}
					<div class="pn-m-lb-row" class:gold={r.position <= 3} class:you={isYou}>
						<div class="pos">{r.position}</div>
						<div>
							<div class="nm">{r.user_name}</div>
							<div class="h">{r.exact_scores} ex · {r.correct_outcomes} outc</div>
						</div>
						<div class="pts">{r.total_points}</div>
						<div class="mv">
							{#if r.movement > 0}<span class="up">▲{r.movement}</span>
							{:else if r.movement < 0}<span class="dn">▼{Math.abs(r.movement)}</span>
							{:else}<span class="eq">—</span>{/if}
						</div>
					</div>
				{:else}
					<div style="padding: 24px; text-align: center; font-family: var(--mono); font-size: 11px; color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.08em;">
						No standings yet
					</div>
				{/each}
			</div>
		</div>
	</PnPageShell>
{/if}
