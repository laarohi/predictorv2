<script lang="ts">
	/**
	 * /results/[fixture_id] — Match Detail page.
	 *
	 * Pulls together the existing per-fixture data and renders the design
	 * handoff's "Match Detail" surface: hero + score-breakdown strip +
	 * 5×5 bubble plot + per-match leaderboard.
	 *
	 * State → mode mapping:
	 *   - finished → post  (actual score drives colouring)
	 *   - live     → post  (live score acts as "if FT now" result)
	 *   - locked   → pre   (no score yet; bubbles coloured by W/D/L)
	 *   - open     → blocked  (community endpoint refuses; show placeholder)
	 *
	 * Data sources:
	 *   - fixtures store           — for the Fixture itself
	 *   - getMatchPredictions      — for the caller's own pick
	 *   - getCommunityPredictions  — every player's pick (gated to locked/finished)
	 *   - getLeaderboard           — current Comp pts + rank per player
	 *   - getAgreements            — for rarity in the user's breakdown strip
	 *   - getScoringConfig         — outcome/exact/cap values
	 */
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { isAuthenticated, user } from '$stores/auth';
	import { fetchAllFixtures, fixtureById } from '$stores/fixtures';
	import { fetchMatchPredictions, predictionsByFixture } from '$stores/predictions';
	import {
		getAgreements,
		getCommunityPredictions,
		type FixtureAgreement
	} from '$api/predictions';
	import { getLeaderboard, type PhaseFilter } from '$api/leaderboard';
	import { getScoringConfig, type ScoringConfig } from '$api/competition';
	import {
		computeBreakdown,
		stageLabel,
		stageShort,
		matchState
	} from '$lib/utils/matchBreakdown';
	import {
		buildCells,
		toGridPlayer,
		fmtKickoff,
		pickActualScore,
		type GridPlayer
	} from '$lib/utils/matchDetail';
	import { teamCode } from '$lib/utils/teamCodes';
	import { displayTeamName } from '$lib/utils/teamName';
	import PnPageShell from '$components/panini/PnPageShell.svelte';
	import PnFlag from '$components/panini/PnFlag.svelte';
	import PnBubbleGrid from '$components/panini/PnBubbleGrid.svelte';
	import PnPointsBar from '$components/panini/PnPointsBar.svelte';
	import PnMatchLeaderboard from '$components/panini/PnMatchLeaderboard.svelte';
	import PnMatchLeaderboardMobile from '$components/panini/PnMatchLeaderboardMobile.svelte';
	import type {
		CommunityPredictionsResponse,
		Fixture,
		LeaderboardEntry,
		LeaderboardResponse
	} from '$types';

	$: if (browser && !$isAuthenticated) goto('/login');

	$: fixtureId = $page.params.fixture_id ?? '';
	$: fixture = $fixtureById.get(fixtureId) as Fixture | undefined;

	let loading = true;
	let loadError: string | null = null;
	let community: CommunityPredictionsResponse | null = null;
	let agreement: FixtureAgreement | undefined = undefined;
	let leaderboardEntries: LeaderboardEntry[] = [];
	let scoringConfig: ScoringConfig = {
		mode: 'logarithmic',
		outcome_points: 5,
		exact_points: 10,
		rarity_cap: 10
	};
	let blocked = false;

	onMount(async () => {
		if (!$isAuthenticated) return;
		try {
			// Make sure fixtures + own predictions are loaded.
			await Promise.all([fetchAllFixtures(), fetchMatchPredictions()]);

			const f = $fixtureById.get(fixtureId);
			if (!f) {
				loadError = 'Fixture not found.';
				loading = false;
				return;
			}

			const state = matchState(f);
			if (state === 'open') {
				blocked = true;
				const [cfg, ags] = await Promise.all([
					getScoringConfig().catch(() => scoringConfig),
					getAgreements([fixtureId]).catch(() => [] as FixtureAgreement[])
				]);
				scoringConfig = cfg;
				agreement = ags.find((a) => a.fixture_id === fixtureId);
				loading = false;
				return;
			}

			const [comm, cfg, ags, lb] = await Promise.all([
				getCommunityPredictions(fixtureId),
				getScoringConfig().catch(() => scoringConfig),
				getAgreements([fixtureId]).catch(() => [] as FixtureAgreement[]),
				getLeaderboard(null as PhaseFilter).catch(
					() => ({ entries: [] } as Partial<LeaderboardResponse> as LeaderboardResponse)
				)
			]);
			community = comm;
			scoringConfig = cfg;
			agreement = ags.find((a) => a.fixture_id === fixtureId);
			leaderboardEntries = lb.entries ?? [];
		} catch (e) {
			loadError = e instanceof Error ? e.message : 'Failed to load match.';
		} finally {
			loading = false;
		}
	});

	// Build the GridPlayer[] for the bubble grid + leaderboard.
	$: gridPlayers = (() => {
		if (!community) return [] as GridPlayer[];
		const lbByName = new Map<string, LeaderboardEntry>();
		for (const e of leaderboardEntries) lbByName.set(e.user_name, e);
		const youName = $user?.name ?? null;
		return community.predictions.map((cp) => {
			const lb = lbByName.get(cp.user_name);
			return toGridPlayer(
				cp,
				youName !== null && cp.user_name === youName,
				lb?.position ?? null,
				lb?.total_points ?? null,
				lb?.movement ?? null
			);
		});
	})();

	$: cells = buildCells(gridPlayers);
	$: youPlayer = gridPlayers.find((p) => p.you) ?? null;

	$: state = fixture ? matchState(fixture) : null;
	$: phase = (state === 'finished' || state === 'live' ? 'post' : 'pre') as 'pre' | 'post';
	$: actualScore = pickActualScore(fixture?.score ?? null);

	// Own prediction + breakdown — reuses the existing helper, so behaviour
	// matches the Results & Fixtures card exactly.
	$: ownPrediction = $predictionsByFixture.get(fixtureId);
	$: breakdown = fixture
		? computeBreakdown(fixture, ownPrediction, agreement, scoringConfig)
		: null;

	$: homeCode = fixture ? teamCode(fixture.home_team) : '';
	$: awayCode = fixture ? teamCode(fixture.away_team) : '';
	$: homeFull = fixture ? displayTeamName(fixture.home_team) : '';
	$: awayFull = fixture ? displayTeamName(fixture.away_team) : '';

	$: homeWon = !!(state === 'finished' && actualScore && actualScore.home_score > actualScore.away_score);
	$: awayWon = !!(state === 'finished' && actualScore && actualScore.away_score > actualScore.home_score);

	$: kickoff = fixture ? fmtKickoff(fixture.kickoff) : { dow: '', date: '', time: '' };

	function statePillLabel(): string {
		if (state === 'finished') return 'FULL TIME';
		if (state === 'live')
			return fixture?.minute != null ? `LIVE · ${fixture.minute}'` : 'LIVE';
		if (state === 'locked') return 'PRE-MATCH · LOCKED';
		return 'PRE-MATCH';
	}
	function statePillClass(): string {
		if (state === 'finished') return 'ft';
		if (state === 'live') return 'live';
		if (state === 'locked') return 'locked';
		return 'pre';
	}

	function pillIcon(s: string): string {
		if (s.startsWith('hit-rarity')) return '★';
		if (s === 'miss') return '✗';
		if (s.startsWith('potential')) return '?';
		if (s === 'none') return '–';
		return '✓';
	}
	function pillPts(p: number): string {
		if (p === 0) return '0';
		return p > 0 ? '+' + p : String(p);
	}
</script>

<svelte:head>
	<title>
		{fixture ? `${homeCode} vs ${awayCode} — Match Detail` : 'Match Detail'} · Predictor
	</title>
</svelte:head>

{#if $isAuthenticated}
	<PnPageShell>
		{#if loading}
			<p class="pn-md-empty">Loading match…</p>
		{:else if loadError || !fixture}
			<p class="pn-md-empty">{loadError ?? 'Match not found.'}</p>
			<p class="pn-md-empty"><a href="/results">← Back to results &amp; fixtures</a></p>
		{:else}
			<!-- ══════════════════ DESKTOP LAYOUT ══════════════════
			 * Two rows in a 3fr/2fr grid:
			 *   row 1 — hero (left) + score-strip (right), full-bleed; blends
			 *           with the masthead via negative top/side margins.
			 *   row 2 — plot (left) + leaderboard (right), stretched to the
			 *           plot's natural height; leaderboard scrolls internally.
			 * Breadcrumb dropped — top-nav "Results" link covers navigation;
			 * the match identifier sits in the hero's centre meta line. -->
			<div class="pn-md-only">
				<div class="pn-md-top">
					<!-- Hero -->
					<div class="pn-md-hero">
						<div class={'team-side' + (homeWon ? ' won' : awayWon ? ' lost' : '')}>
							<span class="flag-wrap">
								<PnFlag code={homeCode} w={56} h={38} />
							</span>
							<div class="meta">
								<span class="role">
									Home · {fixture.group ? 'Group ' + fixture.group : stageLabel(fixture.stage)}
								</span>
								<span class="nm">{homeFull}</span>
							</div>
						</div>

						<div class="centre">
							<span class={'state ' + statePillClass()}>{statePillLabel()}</span>
							{#if phase === 'post' && actualScore}
								<div class="score">
									<span class={'n' + (awayWon ? ' lose' : '')}>{actualScore.home_score}</span>
									<span class="dash">–</span>
									<span class={'n' + (homeWon ? ' lose' : '')}>{actualScore.away_score}</span>
								</div>
							{:else}
								<div class="score pre"><span class="vs">VS</span></div>
							{/if}
							<div class="meta-line">
								<span>KO <b>{kickoff.time}</b></span>
								<span class="pip">·</span>
								<span>{kickoff.dow} <b>{kickoff.date}</b></span>
								<span class="pip">·</span>
								<span>
									{#if fixture.group}
										GROUP <b>{fixture.group}</b>
									{:else}
										<b>{stageShort(fixture.stage)}</b>
									{/if}
								</span>
							</div>
						</div>

						<div class={'team-side right' + (awayWon ? ' won' : homeWon ? ' lost' : '')}>
							<span class="flag-wrap">
								<PnFlag code={awayCode} w={56} h={38} />
							</span>
							<div class="meta">
								<span class="role">
									Away · {fixture.group ? 'Group ' + fixture.group : stageLabel(fixture.stage)}
								</span>
								<span class="nm">{awayFull}</span>
							</div>
						</div>
					</div>

					<!-- Score-strip — your potential / banked haul -->
					{#if breakdown}
						{@const tierLabel = breakdown.tier === 'tier-exact'
							? '★ Exact'
							: breakdown.tier === 'tier-outcome'
								? 'Outcome'
								: breakdown.tier === 'tier-miss'
									? 'No points'
									: state === 'live'
										? 'In play'
										: 'Pending'}
						<div class={'pn-md-score-strip ' + breakdown.tier}>
							<div class="head">
								<span class="caption">
									{#if state === 'finished'}
										Your score · banked
									{:else if state === 'live'}
										Your score · if FT now
									{:else}
										Your score · potential
									{/if}
								</span>
								<span class="tier-tag">{tierLabel}</span>
							</div>
							<div class={'pn-md-bd ' + breakdown.tier}>
								<div class={'pill ' + breakdown.outcomePill.state}>
									<span class="pts">
										<span class="ic">{pillIcon(breakdown.outcomePill.state)}</span>{pillPts(
											breakdown.outcomePill.pts
										)}
									</span>
									<span class="lab">{breakdown.outcomePill.lab}</span>
								</div>
								<div class={'pill ' + breakdown.scorePill.state}>
									<span class="pts">
										<span class="ic">{pillIcon(breakdown.scorePill.state)}</span>{pillPts(
											breakdown.scorePill.pts
										)}
									</span>
									<span class="lab">{breakdown.scorePill.lab}</span>
								</div>
								{#if scoringConfig.mode === 'logarithmic'}
									<div class={'pill ' + breakdown.rarityPill.state}>
										<span class="pts">
											<span class="ic">{pillIcon(breakdown.rarityPill.state)}</span>{pillPts(
												breakdown.rarityPill.pts
											)}
										</span>
										<span class="lab">{breakdown.rarityPill.lab}</span>
									</div>
								{/if}
								<div class="total">
									<span class="v">{breakdown.totalDisplay}</span>
									<span class="lab">{breakdown.totalLabel}</span>
								</div>
							</div>
						</div>
					{/if}
				</div>

				{#if blocked}
					<div class="pn-md-blocked">
						<div class="h">Predictions are blind until lock</div>
						<div class="b">
							Community predictions become visible <b>15 minutes before kickoff</b>. Come back when
							the match locks to see the full pool, the score-distribution plot, and the per-match
							leaderboard.
						</div>
					</div>
				{:else}
					<div class="pn-md-bottom">
						<!-- LEFT — bubble plate -->
						<section class="pn-md-plate">
							<div class="ph">
								<span>
									{phase === 'pre'
										? 'Predicted scoreline distribution'
										: 'Match result · scoreline distribution'}
								</span>
								<div class="pn-md-legend">
									{#if phase === 'pre'}
										<span class="it"><span class="sw pre-home" /> {homeCode} win</span>
										<span class="it"><span class="sw pre-draw" /> Draw</span>
										<span class="it"><span class="sw pre-away" /> {awayCode} win</span>
										<span class="it you"><span class="ring" /> Your pick</span>
									{:else}
										<span class="it"><span class="sw exact" /> Exact <span class="star">★</span></span>
										<span class="it"><span class="sw outcome" /> Outcome</span>
										<span class="it"><span class="sw miss" /> No pts</span>
										<span class="it you"><span class="ring" /> You</span>
									{/if}
								</div>
							</div>
							<div class="pb">
								<PnBubbleGrid
									mode={phase}
									homeCode={homeCode}
									awayCode={awayCode}
									actual={actualScore}
									cells={cells}
									youPlayer={youPlayer}
									pointsExact={scoringConfig.exact_points}
									pointsOutcome={scoringConfig.outcome_points}
								/>
								<PnPointsBar
									mode={phase}
									homeCode={homeCode}
									awayCode={awayCode}
									actual={actualScore}
									players={gridPlayers}
									pointsExact={scoringConfig.exact_points}
									pointsOutcome={scoringConfig.outcome_points}
								/>
							</div>
						</section>

						<!-- RIGHT — leaderboard. Wrapped so the inner panel can be
						 * position:absolute, taking it out of the grid row's height
						 * calculation; the row then sizes to the plate alone and
						 * the leaderboard fills its cell with internal scrolling. -->
						<div class="pn-md-lb-wrap">
							<PnMatchLeaderboard
								mode={phase}
								actual={actualScore}
								players={gridPlayers}
								pointsExact={scoringConfig.exact_points}
								pointsOutcome={scoringConfig.outcome_points}
							/>
						</div>
					</div>
				{/if}
			</div>

			<!-- ══════════════════ MOBILE LAYOUT ══════════════════ -->
			<div class="pn-mm-only">
				<div class="pn-mm-back">
					<a href="/results">← Results</a>
					<span class="crumb-cur">
						{fixture.group ? 'GROUP ' + fixture.group : stageShort(fixture.stage)} · <b>{homeCode} v {awayCode}</b>
					</span>
				</div>

				<div class="pn-mm-summary">
					<div class={'team' + (homeWon ? ' won' : awayWon ? ' lost' : '')}>
						<span class="fl"><PnFlag code={homeCode} w={42} h={28} /></span>
						<span class="nm">{homeCode}</span>
					</div>
					<div class="centre">
						<span class={'state-pill ' + statePillClass()}>{statePillLabel()}</span>
						{#if phase === 'post' && actualScore}
							<div class="score">
								<span class={awayWon ? 'lose' : ''}>{actualScore.home_score}</span>
								<span class="dash">–</span>
								<span class={homeWon ? 'lose' : ''}>{actualScore.away_score}</span>
							</div>
						{:else}
							<div class="score pre-vs">VS</div>
						{/if}
					</div>
					<div class={'team' + (awayWon ? ' won' : homeWon ? ' lost' : '')}>
						<span class="fl"><PnFlag code={awayCode} w={42} h={28} /></span>
						<span class="nm">{awayCode}</span>
					</div>
					<div class="meta-line">
						{fixture.group ? 'Group ' : ''}<b>{fixture.group ?? stageShort(fixture.stage)}</b>
						· <b>{kickoff.date}</b> · KO <b>{kickoff.time}</b>
					</div>
				</div>

				{#if blocked}
					<div class="pn-md-blocked" style="margin: 14px 12px 0;">
						<div class="h">Predictions are blind until lock</div>
						<div class="b">
							Community predictions become visible <b>15 minutes before kickoff</b>.
						</div>
					</div>
				{:else}
					<!-- Mobile breakdown strip -->
					{#if breakdown}
						<div class={'pn-mm-score ' + breakdown.tier}>
							<div class="head">
								<span class="lbl">
									{#if state === 'finished'}
										Your score
									{:else if state === 'live'}
										Score · live
									{:else}
										Score potential
									{/if}
								</span>
								<span class="tier-tag">
									{#if state === 'finished'}
										{breakdown.tier === 'tier-exact'
											? '★ Exact'
											: breakdown.tier === 'tier-outcome'
												? 'Outcome'
												: breakdown.tier === 'tier-miss'
													? 'No pts'
													: '—'}
									{:else if state === 'live'}
										{breakdown.totalLabel}
									{:else}
										Potential
									{/if}
									· {breakdown.totalDisplay} pts
								</span>
							</div>
							<div class="body">
								<div class={'pill ' + breakdown.outcomePill.state}>
									<span class="pts">{pillIcon(breakdown.outcomePill.state)} {pillPts(breakdown.outcomePill.pts)}</span>
									<span class="lab">{breakdown.outcomePill.lab}</span>
								</div>
								<div class={'pill ' + breakdown.scorePill.state}>
									<span class="pts">{pillIcon(breakdown.scorePill.state)} {pillPts(breakdown.scorePill.pts)}</span>
									<span class="lab">{breakdown.scorePill.lab}</span>
								</div>
								{#if scoringConfig.mode === 'logarithmic'}
									<div class={'pill ' + breakdown.rarityPill.state}>
										<span class="pts">{pillIcon(breakdown.rarityPill.state)} {pillPts(breakdown.rarityPill.pts)}</span>
										<span class="lab">{breakdown.rarityPill.lab}</span>
									</div>
								{/if}
								<div class="total">
									<span class="v">{breakdown.totalDisplay}</span>
									<span class="lab">{breakdown.totalLabel.slice(0, 8)}</span>
								</div>
							</div>
						</div>
					{/if}

					<!-- Mobile plate (bubble grid + bar) -->
					<div class="pn-mm-plate">
						<div class="ph">
							<div class="ttl">
								<span>
									{phase === 'pre'
										? 'Predicted scoreline distribution'
										: 'Match result · distribution'}
								</span>
								<span class="right">5×5</span>
							</div>
							<div class="legend">
								{#if phase === 'pre'}
									<span class="it"><span class="sw pre-home" /> {homeCode} win</span>
									<span class="it"><span class="sw pre-draw" /> Draw</span>
									<span class="it"><span class="sw pre-away" /> {awayCode} win</span>
									<span class="it"><span class="ring" /> You</span>
								{:else}
									<span class="it"><span class="sw exact" /> Exact★</span>
									<span class="it"><span class="sw outcome" /> Outcome</span>
									<span class="it"><span class="sw miss" /> No pts</span>
									<span class="it"><span class="ring" /> You</span>
								{/if}
							</div>
						</div>
						<div class="pb">
							<PnBubbleGrid
								mode={phase}
								homeCode={homeCode}
								awayCode={awayCode}
								actual={actualScore}
								cells={cells}
								youPlayer={youPlayer}
								compact={true}
								pointsExact={scoringConfig.exact_points}
								pointsOutcome={scoringConfig.outcome_points}
							/>
							<PnPointsBar
								mode={phase}
								homeCode={homeCode}
								awayCode={awayCode}
								actual={actualScore}
								players={gridPlayers}
								pointsExact={scoringConfig.exact_points}
								pointsOutcome={scoringConfig.outcome_points}
							/>
						</div>
					</div>

					<!-- Mobile leaderboard — compact layout (own component) -->
					<PnMatchLeaderboardMobile
						mode={phase}
						actual={actualScore}
						players={gridPlayers}
						pointsExact={scoringConfig.exact_points}
						pointsOutcome={scoringConfig.outcome_points}
					/>
				{/if}
			</div>
		{/if}
	</PnPageShell>
{/if}
