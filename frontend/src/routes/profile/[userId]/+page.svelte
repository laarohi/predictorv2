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
		third_place: '3rd place',
		final: 'Final',
		winner: 'Tournament Winner'
	};

	// Knockout rounds in play order — drives both the KO predictions tables
	// and the per-phase bracket tag sections.
	const KO_ROUNDS: Array<[string, string]> = [
		['round_of_32', 'Round of 32'],
		['round_of_16', 'Round of 16'],
		['quarter_final', 'Quarter-finals'],
		['semi_final', 'Semi-finals'],
		['third_place', 'Third place'],
		['final', 'Final']
	];

	function predictionResult(p: UserMatchPredictionView): 'exact' | 'outcome' | 'wrong' | 'pending' {
		if (p.is_exact) return 'exact';
		if (p.is_correct_outcome) return 'outcome';
		if (p.actual_home !== null && p.actual_away !== null) return 'wrong';
		return 'pending';
	}

	const RESULT_MARK: Record<string, string> = {
		exact: '✓',
		outcome: '●',
		wrong: '×',
		pending: '—'
	};

	// Group-stage picks bucketed by group letter (A…L), kickoff order within.
	// The backend already sorts by kickoff, so buckets stay ordered for free.
	$: groupBlocks = (() => {
		const blocks = new Map<string, UserMatchPredictionView[]>();
		for (const p of predictions?.match_predictions ?? []) {
			if (p.stage !== 'group') continue;
			const key = p.group ?? '?';
			if (!blocks.has(key)) blocks.set(key, []);
			blocks.get(key)!.push(p);
		}
		return [...blocks.entries()].sort(([a], [b]) => a.localeCompare(b));
	})();

	// Knockout match-score picks (Phase 2) bucketed by round, in play order.
	$: koBlocks = (() => {
		const byStage = new Map<string, UserMatchPredictionView[]>();
		for (const p of predictions?.match_predictions ?? []) {
			if (p.stage === 'group') continue;
			if (!byStage.has(p.stage)) byStage.set(p.stage, []);
			byStage.get(p.stage)!.push(p);
		}
		return KO_ROUNDS.filter(([key]) => byStage.has(key)).map(([key, label]) => ({
			key,
			label,
			preds: byStage.get(key)!
		}));
	})();

	// Bracket tag sections, one per phase that has visible picks.
	$: bracketPhases = (() => {
		const bs = predictions?.bracket_summary;
		if (!bs) return [];
		const out: Array<{ label: string; sub: string; stages: Record<string, string[]> }> = [];
		if (bs.phase1_stages && Object.keys(bs.phase1_stages).length > 0) {
			out.push({ label: 'Bracket picks · Phase I', sub: 'Pre-tournament', stages: bs.phase1_stages });
		}
		if (bs.phase2_stages && Object.keys(bs.phase2_stages).length > 0) {
			out.push({ label: 'Bracket picks · Phase II', sub: 'Knockout re-pick', stages: bs.phase2_stages });
		}
		// Legacy fallback: phase-tagged maps empty but the merged map isn't.
		if (out.length === 0 && Object.keys(bs.stages).length > 0) {
			out.push({ label: 'Bracket picks', sub: 'Locked predictions', stages: bs.stages });
		}
		return out;
	})();

	$: groupPickCount = groupBlocks.reduce((n, [, preds]) => n + preds.length, 0);
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

			<!-- Bracket picks, one section per visible phase -->
			{#each bracketPhases as bp (bp.label)}
				<section class="pn-pf-section">
					<div class="h"><span>{bp.label}</span><span class="right">{bp.sub}</span></div>
					<div class="body">
						<div style="display: flex; flex-wrap: wrap; gap: 18px;">
							{#each Object.entries(STAGE_LABELS) as [stageKey, label]}
								{#if bp.stages[stageKey] && bp.stages[stageKey].length > 0}
									<div style="display: flex; flex-direction: column; gap: 6px;">
										<div style="font-family: var(--mono); font-size: 10px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--ink-3);">{label}</div>
										<div style="display: flex; flex-wrap: wrap; gap: 4px; max-width: 220px;">
											{#each bp.stages[stageKey] as team}
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
			{/each}

			<!-- Group stage predictions — compact per-group tables -->
			{#if groupBlocks.length > 0}
				<section class="pn-pf-section">
					<div class="h">
						<span>Group stage predictions</span>
						<span class="right">{groupPickCount} picks · ✓ exact · ● outcome · × missed</span>
					</div>
					<div class="body">
						<div class="pn-pf-predgrid">
							{#each groupBlocks as [group, preds] (group)}
								<div class="pn-pf-predblock">
									<div class="hd"><span>Group {group}</span><span class="n">pick · ft</span></div>
									{#each preds as p (p.fixture_id)}
										{@const result = predictionResult(p)}
										<div class="row {result}">
											<span class="t"><PnFlag code={teamCode(p.home_team)} w={14} h={10} />{teamCode(p.home_team)}</span>
											<span class="pick">{p.predicted_home}–{p.predicted_away}</span>
											<span class="t r">{teamCode(p.away_team)}<PnFlag code={teamCode(p.away_team)} w={14} h={10} /></span>
											<span class="ft">
												{#if p.actual_home !== null && p.actual_away !== null}{p.actual_home}–{p.actual_away}{:else}·{/if}
											</span>
											<span class="mk {result}">{RESULT_MARK[result]}</span>
										</div>
									{/each}
								</div>
							{/each}
						</div>
					</div>
				</section>
			{/if}

			<!-- Knockout predictions — Phase 2 match-score picks by round -->
			{#if koBlocks.length > 0}
				<section class="pn-pf-section">
					<div class="h">
						<span>Knockout predictions</span>
						<span class="right">Phase II match picks</span>
					</div>
					<div class="body">
						<div class="pn-pf-predgrid">
							{#each koBlocks as block (block.key)}
								<div class="pn-pf-predblock">
									<div class="hd"><span>{block.label}</span><span class="n">pick · ft</span></div>
									{#each block.preds as p (p.fixture_id)}
										{@const result = predictionResult(p)}
										<div class="row {result}">
											<span class="t"><PnFlag code={teamCode(p.home_team)} w={14} h={10} />{teamCode(p.home_team)}</span>
											<span class="pick">{p.predicted_home}–{p.predicted_away}</span>
											<span class="t r">{teamCode(p.away_team)}<PnFlag code={teamCode(p.away_team)} w={14} h={10} /></span>
											<span class="ft">
												{#if p.actual_home !== null && p.actual_away !== null}{p.actual_home}–{p.actual_away}{:else}·{/if}
											</span>
											<span class="mk {result}">{RESULT_MARK[result]}</span>
										</div>
									{/each}
								</div>
							{/each}
						</div>
					</div>
				</section>
			{/if}

			<!-- Blind-pool empty state: nothing visible yet for this viewer -->
			{#if predictions && predictions.match_predictions.length === 0 && bracketPhases.length === 0}
				<section class="pn-pf-section">
					<div class="h"><span>Predictions</span><span class="right">Blind pool</span></div>
					<div class="body">
						<p style="font-family: var(--mono); font-size: 11px; color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.08em; margin: 0;">
							{isOwnProfile
								? 'No predictions saved yet — head to the predictions page to get started.'
								: 'Picks stay hidden until they lock — match picks reveal 15 minutes before each kickoff, bracket picks when the phase deadline passes.'}
						</p>
					</div>
				</section>
			{/if}
		{/if}
	</PnPageShell>
{/if}
