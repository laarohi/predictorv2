<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { isAuthenticated, user } from '$stores/auth';
	import { getUserProfile, getUserPredictions } from '$api/users';
	import { teamCode } from '$lib/utils/teamCodes';
	import type { PublicProfile, UserPredictionsResponse, UserMatchPredictionView } from '$types';
	import PnPageShell from '$components/panini/PnPageShell.svelte';
	import PnFlag from '$components/panini/PnFlag.svelte';

	$: if (!$isAuthenticated) goto('/login');
	$: userId = $page.params.userId;
	$: isOwnProfile = userId === $user?.id;

	let profile: PublicProfile | null = null;
	let predictions: UserPredictionsResponse | null = null;
	let loading = true;
	let error: string | null = null;

	$: if (userId && $isAuthenticated) loadData(userId);

	async function loadData(id: string) {
		loading = true;
		error = null;
		try {
			const [p, preds] = await Promise.all([getUserProfile(id), getUserPredictions(id)]);
			profile = p;
			predictions = preds;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load profile';
		} finally {
			loading = false;
		}
	}

	function fmtDate(s: string): string {
		return new Date(s).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
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

	const STAGE_LABELS: Record<string, string> = {
		group: 'Group winners',
		round_of_32: 'R32',
		round_of_16: 'R16',
		quarter_finals: 'QF',
		quarter_final: 'QF',
		semi_finals: 'SF',
		semi_final: 'SF',
		final: 'Final',
		winner: 'Tournament Winner'
	};

	function predictionResult(p: UserMatchPredictionView): 'exact' | 'outcome' | 'wrong' | 'pending' {
		if (p.is_exact) return 'exact';
		if (p.is_correct_outcome) return 'outcome';
		if (p.actual_home !== null && p.actual_away !== null) return 'wrong';
		return 'pending';
	}
</script>

<svelte:head>
	<title>{profile?.name ?? 'Profile'} — Predictor</title>
</svelte:head>

{#if $isAuthenticated}
	<PnPageShell>
		{#if loading}
			<p style="font-family: var(--mono); font-size: 11px; color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.08em;">Loading profile…</p>
		{:else if error}
			<div class="pn-pf-alert error">{error}</div>
		{:else if profile}
			<!-- Hero -->
			<section class="pn-pf-hero">
				<div class="av">{profile.name.charAt(0).toUpperCase()}</div>
				<div class="nm-block">
					<div class="nm">{profile.name}{#if isOwnProfile} <em>· YOU</em>{/if}</div>
					<div class="sub">
						<b>Member since</b> {fmtDate(profile.created_at)}
					</div>
				</div>
				<div class="rank-block">
					<div class="l">Leaderboard</div>
					<div class="v">
						{#if profile.stats.leaderboard_position}
							{profile.stats.leaderboard_position}<span class="sx">{ordinal(profile.stats.leaderboard_position)}</span>
						{:else}
							—
						{/if}
					</div>
					<div class="of">of {profile.stats.total_participants}</div>
				</div>
			</section>

			<!-- Stats -->
			<section class="pn-pf-stats">
				<div class="pn-pf-stat">
					<div class="l">Total points</div>
					<div class="v">{profile.stats.total_points}</div>
				</div>
				<div class="pn-pf-stat">
					<div class="l">Accuracy</div>
					<div class="v">{profile.stats.accuracy_pct}%</div>
				</div>
				<div class="pn-pf-stat">
					<div class="l">Predictions</div>
					<div class="v">{profile.stats.total_predictions}</div>
					<div class="sub">{profile.stats.total_match_predictions} match · {profile.stats.total_team_predictions} team</div>
				</div>
				<div class="pn-pf-stat">
					<div class="l">Exact scores</div>
					<div class="v exact">{profile.stats.exact_scores}</div>
				</div>
				<div class="pn-pf-stat">
					<div class="l">Correct outcomes</div>
					<div class="v">{profile.stats.correct_outcomes}</div>
				</div>
				<div class="pn-pf-stat">
					<div class="l">Bonus haul</div>
					<div class="v bonus">{profile.stats.breakdown.hybrid_bonus_points}</div>
				</div>
			</section>

			<!-- Bracket summary -->
			{#if predictions && (Object.keys(predictions.bracket_summary.stages).length > 0 || Object.keys(predictions.bracket_summary.phase1_stages ?? {}).length > 0)}
				{@const bs = predictions.bracket_summary}
				{@const stages = (bs.phase1_stages && Object.keys(bs.phase1_stages).length > 0) ? bs.phase1_stages : bs.stages}
				<section class="pn-pf-section">
					<div class="h"><span>Bracket picks · Phase I</span><span class="right">Locked predictions</span></div>
					<div class="body">
						<div style="display: flex; flex-wrap: wrap; gap: 18px;">
							{#each Object.entries(STAGE_LABELS) as [stageKey, label]}
								{#if stages[stageKey] && stages[stageKey].length > 0}
									<div style="display: flex; flex-direction: column; gap: 6px;">
										<div style="font-family: var(--mono); font-size: 10px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--ink-3);">{label}</div>
										<div style="display: flex; flex-wrap: wrap; gap: 4px; max-width: 220px;">
											{#each stages[stageKey] as team}
												<span class="pn-tag {stageKey === 'winner' ? 'gold' : ''}" style="padding: 3px 8px; font-size: 10px; display: inline-flex; align-items: center; gap: 4px;">
													<PnFlag code={teamCode(team)} w={12} h={9} />{teamCode(team)}
												</span>
											{/each}
										</div>
									</div>
								{/if}
							{/each}
						</div>
					</div>
				</section>
			{/if}

			<!-- Recent predictions -->
			{#if predictions && predictions.match_predictions.length > 0}
				<section class="pn-pf-section">
					<div class="h"><span>Recent match predictions</span><span class="right">{predictions.match_predictions.length} total</span></div>
					<div class="body">
						<div class="pn-pf-prediction-list">
							{#each predictions.match_predictions.slice(0, 12) as p (p.fixture_id)}
								{@const result = predictionResult(p)}
								<div class="pn-pf-prediction" class:exact={result === 'exact'} class:outcome={result === 'outcome'}>
									<div class="team">
										<PnFlag code={teamCode(p.home_team)} w={14} h={10} />
										{teamCode(p.home_team)}
									</div>
									<div class="score">{p.predicted_home}–{p.predicted_away}</div>
									<div class="team r">
										<PnFlag code={teamCode(p.away_team)} w={14} h={10} />
										{teamCode(p.away_team)}
									</div>
									<div class="meta">
										<span>{new Date(p.kickoff).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })} · {p.group ? `Group ${p.group}` : p.stage}</span>
										<span class="actual {result}">
											{#if p.actual_home !== null && p.actual_away !== null}
												ACTUAL <b>{p.actual_home}–{p.actual_away}</b>
												{#if result === 'exact'}✓ EXACT{:else if result === 'outcome'}● OUTCOME{:else if result === 'wrong'}× MISSED{/if}
											{:else}
												PENDING
											{/if}
										</span>
									</div>
								</div>
							{/each}
						</div>
					</div>
				</section>
			{/if}
		{/if}
	</PnPageShell>
{/if}
