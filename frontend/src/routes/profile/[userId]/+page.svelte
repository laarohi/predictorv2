<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { isAuthenticated, user } from '$stores/auth';
	import { getUserProfile, getUserPredictions, getUserPointsLog } from '$api/users';
	import { getAllFixtures } from '$api/fixtures';
	import { teamCode } from '$lib/utils/teamCodes';
	import { computeTeamFate } from '$lib/utils/bracketFate';
	import type {
		Fixture,
		PointsLogEvent,
		PublicProfile,
		UserPredictionsResponse,
		UserMatchPredictionView
	} from '$types';
	import PnPageShell from '$components/panini/PnPageShell.svelte';
	import PnBracketRuns from '$components/panini/PnBracketRuns.svelte';
	import PnFlag from '$components/panini/PnFlag.svelte';

	$: if (!$isAuthenticated) goto('/login');
	$: userId = $page.params.userId;
	$: isOwnProfile = userId === $user?.id;

	let profile: PublicProfile | null = null;
	let predictions: UserPredictionsResponse | null = null;
	let allFixtures: Fixture[] = [];
	let advanceEvents: PointsLogEvent[] | null = null;
	let loading = true;
	let error: string | null = null;

	$: if (userId && $isAuthenticated) loadData(userId);

	async function loadData(id: string) {
		loading = true;
		error = null;
		try {
			// Fixtures feed the bracket fate colouring (which teams actually
			// reached each round) and the points log feeds the per-team banked
			// points on the bracket runs; a failure in either only loses that
			// enrichment, so both degrade instead of failing the whole page.
			const [p, preds, fx, plog] = await Promise.all([
				getUserProfile(id),
				getUserPredictions(id),
				getAllFixtures().catch(() => [] as Fixture[]),
				getUserPointsLog(id).catch(() => null)
			]);
			profile = p;
			predictions = preds;
			allFixtures = fx;
			advanceEvents = plog ? plog.events.filter((e) => e.kind === 'advance') : null;
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

	// Actual tournament fate per team, derived from the real fixture list.
	// Crucially this reads ADVANCEMENT from match results (a finished match's
	// winner has reached the next round) — not from fixture structure — so a
	// team that's already through shows green even before its next match is
	// drawn. See bracketFate.ts for the full rationale.
	$: teamFate = computeTeamFate(allFixtures);

	// Knockout rounds in play order — drives the KO predictions tables.
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

	// Whether any bracket picks are visible to this viewer (blind-pool gated
	// server-side) — drives both the bracket-runs section and the empty state.
	$: hasBracket = (() => {
		const bs = predictions?.bracket_summary;
		if (!bs) return false;
		return (
			Object.keys(bs.phase1_stages ?? {}).length > 0 ||
			Object.keys(bs.phase2_stages ?? {}).length > 0
		);
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

			<!-- Points log entry point -->
			<section class="pn-pf-section">
				<div class="h">
					<span>Points Log</span>
					<span class="right">{profile.stats.total_points} pts itemised</span>
				</div>
				<div class="body">
					<p style="font-family: var(--body); font-size: 13px; line-height: 1.5; color: var(--ink-2); margin: 0 0 12px;">
						Where {isOwnProfile ? 'your' : `${profile.name}'s`} points came from, day by day — every match, qualifier, bracket call and bonus question.
					</p>
					<a class="pn-btn" href="/profile/{userId}/points">View points log →</a>
				</div>
			</section>

			<!-- Bracket picks — team run bars, Phase I over Phase II -->
			{#if predictions && hasBracket}
				<section class="pn-pf-section">
					<div class="h">
						<span>Bracket picks</span>
						<span class="right">One row per team · deepest pick first</span>
					</div>
					<div class="body">
						<PnBracketRuns
							phase1Stages={predictions.bracket_summary.phase1_stages}
							phase2Stages={predictions.bracket_summary.phase2_stages}
							fate={teamFate}
							{advanceEvents}
							qualLedger={predictions.group_qualification}
						/>
					</div>
				</section>
			{/if}

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
									<div class="hd"><span class="gname">Group {group}</span><span class="cl">pick</span><span></span><span></span></div>
									{#each preds as p (p.fixture_id)}
										{@const result = predictionResult(p)}
										<div class="row {result}">
											<span class="t"><PnFlag code={teamCode(p.home_team)} w={14} h={10} />{teamCode(p.home_team)}</span>
											<span class="pick">{p.predicted_home}–{p.predicted_away}</span>
											<span class="t r">{teamCode(p.away_team)}<PnFlag code={teamCode(p.away_team)} w={14} h={10} /></span>
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
									<div class="hd"><span class="gname">{block.label}</span><span class="cl">pick</span><span></span><span></span></div>
									{#each block.preds as p (p.fixture_id)}
										{@const result = predictionResult(p)}
										<div class="row {result}">
											<span class="t"><PnFlag code={teamCode(p.home_team)} w={14} h={10} />{teamCode(p.home_team)}</span>
											<span class="pick">{p.predicted_home}–{p.predicted_away}</span>
											<span class="t r">{teamCode(p.away_team)}<PnFlag code={teamCode(p.away_team)} w={14} h={10} /></span>
											<span class="mk {result}">{RESULT_MARK[result]}</span>
										</div>
									{/each}
								</div>
							{/each}
						</div>
					</div>
				</section>
			{/if}

			<!-- Bonus picks — question → answer, coloured by resolution -->
			{#if predictions && predictions.bonus_predictions.length > 0}
				<section class="pn-pf-section">
					<div class="h">
						<span>Bonus picks</span>
						<span class="right">{predictions.bonus_predictions.length} questions · border: in green · out red</span>
					</div>
					<div class="body">
						<div class="pn-pf-bracket">
							{#each predictions.bonus_predictions as bp (bp.question_id)}
								{@const fate = bp.is_correct === null ? 'tbd' : bp.is_correct ? 'in' : 'out'}
								{@const isTeam = bp.category !== 'awards'}
								<div class="strow">
									<!-- Question labels are "Nickname — long description";
									     the narrow column takes the nickname, the title
									     attribute carries the full wording. -->
									<div class="lbl" title={bp.label}>{bp.label.split('—')[0].trim()}<span class="n">+{bp.points}</span></div>
									<div class="tags">
										<span class="pn-tag pick-tag fate-{fate}">
											{#if isTeam}<PnFlag code={teamCode(bp.answer)} w={12} h={9} />{/if}
											{bp.answer}
										</span>
										{#if bp.is_correct === false && bp.correct_answers.length > 0}
											<span class="pn-tag pick-tag fate-tbd">
												→
												{#each bp.correct_answers as correct, i (correct)}
													{#if isTeam}<PnFlag code={teamCode(correct)} w={12} h={9} />{/if}
													{correct}{i < bp.correct_answers.length - 1 ? ' / ' : ''}
												{/each}
											</span>
										{/if}
									</div>
								</div>
							{/each}
						</div>
					</div>
				</section>
			{/if}

			<!-- Blind-pool empty state: nothing visible yet for this viewer -->
			{#if predictions && predictions.match_predictions.length === 0 && !hasBracket && predictions.bonus_predictions.length === 0}
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
