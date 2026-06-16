<script lang="ts">
	/**
	 * Phase 4 — Knockout-stage dashboard (v4).
	 *
	 * Layout:
	 *   1. Red alert when ≥1 of the next 4 KO matches is unpredicted
	 *   2. KPI row
	 *   3. 2-col matches row: Past 4 finished · Upcoming 4 (entries + locks)
	 *   4. 2-col bottom: Scoring Journey (2fr) + Top 5 (1fr)
	 *
	 * The Scoring Journey is wired with what the backend exposes today: the
	 * bracket-exposure endpoint gives us `alive_per_stage` and the user's
	 * KO predictions per stage, plus stage point values from the scoring
	 * config (configured in worldcup2026.yml — values mirrored as constants
	 * here for the in-play computation). When the backend lands the
	 * per-stage earned/available bucket spec from
	 * `docs/superpowers/dashboard-implementation-guide.md` §6 we'll wire that
	 * through; until then we approximate `earned` from completed KO fixtures
	 * and `available` from picks at stages still in play.
	 */
	import { onMount } from 'svelte';
	import PnPageShell from '$components/panini/PnPageShell.svelte';
	import DwKpiRow from './widgets/DwKpiRow.svelte';
	import DwAlert from './widgets/DwAlert.svelte';
	import DwBackPageReplay from './widgets/DwBackPageReplay.svelte';
	import DwMatchTable, { type MatchTableRow, type PtsVariant } from './widgets/DwMatchTable.svelte';
	import DwTop5 from './widgets/DwTop5.svelte';
	import DwScoringJourney from './widgets/DwScoringJourney.svelte';
	import type { JourneyPhase } from './widgets/DwScoringJourney.svelte';

	import { user } from '$stores/auth';
	import { fetchAllFixtures, fixtures } from '$stores/fixtures';
	import {
		fetchLeaderboard,
		currentUserPosition,
		leaderboard,
		totalParticipants
	} from '$stores/leaderboard';
	import { humanEntries } from '$lib/utils/ghosts';
	import { fetchMatchPredictions, predictionsByFixture } from '$stores/predictions';
	import { getMyRankTrajectory, type RankTrajectoryResponse } from '$api/leaderboard';
	import { getBracketExposure, type BracketExposureResponse } from '$api/predictions';
	import { teamCode } from '$lib/utils/teamCodes';
	import { goto } from '$app/navigation';
	import { koChipLabel } from '$lib/utils/matchBreakdown';
	import type { Fixture } from '$types';

	let trajectoryData: RankTrajectoryResponse | null = null;
	let p1Exposure: BracketExposureResponse | null = null;
	let p2Exposure: BracketExposureResponse | null = null;

	onMount(async () => {
		fetchAllFixtures();
		fetchLeaderboard();
		fetchMatchPredictions();
		try {
			[trajectoryData, p1Exposure, p2Exposure] = await Promise.all([
				getMyRankTrajectory(5),
				getBracketExposure('phase_1').catch(() => null),
				getBracketExposure('phase_2').catch(() => null)
			]);
		} catch {
			trajectoryData = null;
		}
	});

	// ---- Constants ---------------------------------------------------------
	const POINTS_PER_OUTCOME = 5;
	const POINTS_PER_EXACT_TOTAL = 15;
	const STAGE_TO_KEY: Record<string, 'r16' | 'qf' | 'sf' | 'f' | 'w'> = {
		round_of_16: 'r16',
		quarter_final: 'qf',
		semi_final: 'sf',
		final: 'f',
		winner: 'w'
	};

	// ---- Helpers (shared with group dashboard) ----------------------------
	function ordinal(n: number): string {
		if (n % 100 >= 11 && n % 100 <= 13) return 'th';
		switch (n % 10) {
			case 1: return 'st';
			case 2: return 'nd';
			case 3: return 'rd';
			default: return 'th';
		}
	}
	function outcomeOf(h: number, a: number): '1' | 'X' | '2' {
		if (h > a) return '1';
		if (h < a) return '2';
		return 'X';
	}
	function pickResult(f: Fixture): 'exact' | 'outc' | 'miss' | null {
		if (f.status !== 'finished' || !f.score) return null;
		const p = $predictionsByFixture.get(f.id);
		if (!p) return null;
		const fh = f.score.home_score;
		const fa = f.score.away_score;
		if (p.home_score === fh && p.away_score === fa) return 'exact';
		if (outcomeOf(p.home_score, p.away_score) === outcomeOf(fh, fa)) return 'outc';
		return 'miss';
	}
	function pointsFor(r: ReturnType<typeof pickResult>): number {
		if (r === 'exact') return POINTS_PER_EXACT_TOTAL;
		if (r === 'outc') return POINTS_PER_OUTCOME;
		return 0;
	}
	function shortRoundLabel(f: Fixture): string {
		const map: Record<string, string> = {
			round_of_16: 'R16',
			quarter_final: 'QF',
			semi_final: 'SF',
			final: 'F',
			winner: 'W'
		};
		return map[f.stage] ?? f.stage.toUpperCase().slice(0, 3);
	}
	function pickTuple(f: Fixture): [number, number] | null {
		const p = $predictionsByFixture.get(f.id);
		if (!p) return null;
		return [p.home_score, p.away_score];
	}
	function scoreTuple(f: Fixture): [number, number] | null {
		if (!f.score) return null;
		return [f.score.home_score, f.score.away_score];
	}

	function classifyPick(
		score: [number, number] | null,
		pick: [number, number] | null
	): 'exact' | 'outc' | 'miss' | null {
		if (!score || !pick) return null;
		if (pick[0] === score[0] && pick[1] === score[1]) return 'exact';
		if (outcomeOf(pick[0], pick[1]) === outcomeOf(score[0], score[1])) return 'outc';
		return 'miss';
	}

	function pointsForResult(r: 'exact' | 'outc' | 'miss' | null): string {
		if (r === 'exact') return `+${POINTS_PER_EXACT_TOTAL}`;
		if (r === 'outc')  return `+${POINTS_PER_OUTCOME}`;
		return '0';
	}

	// Translate a KO fixture into a DwMatchTable row. Mirrors the helper
	// in DashGroupStage; differs only in the grpLabel (R16/QF/SF/F/W
	// instead of A-L).
	function buildRow(f: Fixture): MatchTableRow {
		const score = scoreTuple(f);
		const pick = pickTuple(f);
		const id = f.id;
		const home = teamCode(f.home_team);
		const away = teamCode(f.away_team);
		const grpLabel = shortRoundLabel(f);
		const navigate = () => void goto(`/results/${id}`);

		if (f.status === 'finished') {
			const result = classifyPick(score, pick);
			return {
				id, kind: 'finished',
				statusText: 'FT', statusVariant: 'ft',
				grpLabel, home, away, score, pick, pickResult: result,
				pointsText: pointsForResult(result),
				pointsVariant: (result ?? 'miss') as PtsVariant,
				onClick: navigate
			};
		}
		if (f.status === 'live' || f.status === 'halftime') {
			const projected = classifyPick(score, pick);
			const showPending = pick !== null && projected !== null;
			return {
				id, kind: 'live',
				statusText: String(f.minute ?? 0),
				statusVariant: 'live',
				grpLabel, home, away, score, pick, pickResult: null,
				pointsText: showPending ? pointsForResult(projected) : null,
				pointsVariant: showPending ? (`pending-${projected}` as PtsVariant) : '',
				onClick: navigate
			};
		}
		// Upcoming. Status cell stays empty (countdown dropped per UX
		// feedback — it squashed the row). The kickoff rides inside the
		// score chip instead, replacing the dead "VS" placeholder; the CTA
		// in the points column does the call-to-action work.
		const lockedNow = f.is_locked;
		const cta = lockedNow ? undefined : (pick ? 'edit' : 'pick') as 'edit' | 'pick' | undefined;
		return {
			id, kind: 'upcoming',
			statusText: '',
			statusVariant: 'cd',
			grpLabel, home, away, score, pick, pickResult: null,
			koLabel: koChipLabel(f.kickoff),
			pointsText: cta ? null : '—',
			pointsVariant: 'dash',
			cta,
			ctaHref: '/predictions',
			onClick: navigate
		};
	}

	// ---- Knockout filter (excludes group stage) ---------------------------
	$: knockoutFixtures = $fixtures.filter((f) => f.stage !== 'group');

	// ---- Past 4 / Upcoming 4 (fixed-count windows) -------------------------
	// Same rationale as DashGroupStage — predictable column height beats a
	// rolling 24h filter for layout planning. Live matches keep showing up
	// in `upcoming` until they're FINISHED, so a KO match that's already
	// kicked off won't disappear from the user's view.
	const PAST_SHOW = 4;
	const UPCOMING_SHOW = 4;

	$: pastFinished = knockoutFixtures
		.filter((f) => f.status === 'finished')
		.sort((a, b) => new Date(b.kickoff).getTime() - new Date(a.kickoff).getTime())
		.slice(0, PAST_SHOW);
	$: pastTotalPts = pastFinished.reduce((acc, f) => acc + pointsFor(pickResult(f)), 0);

	$: upcoming = knockoutFixtures
		.filter(
			(f) =>
				f.status === 'live' ||
				f.status === 'halftime' ||
				f.status === 'scheduled'
		)
		.sort((a, b) => new Date(a.kickoff).getTime() - new Date(b.kickoff).getTime())
		.slice(0, UPCOMING_SHOW);

	// ---- Missing-picks alert: count visible upcoming locks w/o picks ------
	// Note this is now "missing picks among the next 4" rather than "missing
	// picks in the next 24h." For the KO stage that's actually a stronger
	// nudge — KO matches are sparser than group fixtures, so the 4 we show
	// are almost always within the user's planning horizon.
	$: missingPicks = upcoming.filter(
		(f) => f.status === 'scheduled' && !$predictionsByFixture.has(f.id)
	);
	$: nextLockFixture = upcoming.find((f) => f.status === 'scheduled' && !f.is_locked);
	$: nextLockLabel = nextLockFixture
		? `<b>next lock in ${formatDuration(nextLockFixture.time_until_lock)}</b> · ${teamCode(nextLockFixture.home_team)} vs ${teamCode(nextLockFixture.away_team)}`
		: '';

	// time_until_lock is SECONDS until lock (see schemas/fixture.py) — the
	// same contract PnResultsCard.formatLockIn consumes.
	function formatDuration(secs: number | null): string {
		if (!secs || secs <= 0) return '—';
		const totalMin = Math.floor(secs / 60);
		const h = Math.floor(totalMin / 60);
		const m = totalMin % 60;
		if (h >= 48) return `${Math.floor(h / 24)}d ${h % 24}h`;
		if (h > 0) return `${h}h ${m}m`;
		return `${m}m`;
	}

	// ---- KPI values --------------------------------------------------------
	$: rank = $currentUserPosition?.position ?? null;
	$: rankOf = $totalParticipants || $leaderboard.length || 0;
	$: rankDelta = $currentUserPosition?.movement ?? 0;
	$: total = $currentUserPosition?.total_points ?? 0;
	$: exactCount = $currentUserPosition?.exact_scores ?? 0;
	$: exactOf = $currentUserPosition?.breakdown?.total_predictions ?? 0;
	$: correctOutcomes = $currentUserPosition?.correct_outcomes ?? 0;
	$: rarityPts = $currentUserPosition?.breakdown?.hybrid_bonus_points ?? 0;
	$: pastExact = pastFinished.filter((f) => pickResult(f) === 'exact').length;
	$: pastOutc = pastFinished.filter((f) => {
		const r = pickResult(f);
		return r === 'exact' || r === 'outc';
	}).length;
	$: trajectoryRanks = trajectoryData?.points.map((p) => p.position) ?? [];

	// ---- Top 5 + you -------------------------------------------------------
	// Visible row count is fixed at 5: either 5 top rows when the user is
	// already in the top 5, OR 4 top rows + the pinned `you` row when the
	// user is outside. Keeps the standings card at a constant height
	// regardless of where the user sits on the leaderboard.
	// Ghost entrants (crowd/market bots) are a leaderboard-page feature —
	// the dashboard mini-standings shows ranked humans only.
	$: rankedBoard = humanEntries($leaderboard);
	$: topFive = rankedBoard.slice(0, youRow ? 4 : 5).map((e) => ({
		userId: e.user_id,
		position: e.position,
		name: e.user_name,
		hint: `${e.exact_scores} exact · ${e.correct_outcomes} outc${e.movement !== 0 ? ` · ${e.movement > 0 ? '▲' : '▼'}${Math.abs(e.movement)}` : ''}`,
		points: e.total_points,
		isCurrentUser: e.user_id === $user?.id
	}));
	$: youIndex = rankedBoard.findIndex((e) => e.user_id === $user?.id);
	$: youRow = (() => {
		const me = $currentUserPosition;
		if (!me) return null;
		// Gate on ROW index, not position number: ties share a position
		// (competition ranking), so "position <= 5" can be true for a user
		// rendered well below the fifth row — invisible in the 5-row slice.
		if (youIndex >= 0 && youIndex < 5) return null;
		const moveChip = me.movement !== 0 ? ` · ${me.movement > 0 ? '▲' : '▼'}${Math.abs(me.movement)}` : '';
		return {
			userId: me.user_id,
			position: me.position,
			name: me.user_name,
			hint: `YOU${moveChip} · ${pastTotalPts >= 0 ? '+' : ''}${pastTotalPts} last ${PAST_SHOW}`,
			points: me.total_points,
			isCurrentUser: true
		};
	})();

	// ---- Scoring journey buckets ------------------------------------------
	// Backend ships per_stage[{earned|available}] with progressive
	// denominators + team lists, including the per-tbd-match dedup. We
	// only translate the dictionary stage keys to the widget's short
	// keys (r16/qf/sf/f/w).
	function buildPhase(exposure: BracketExposureResponse | null): JourneyPhase {
		if (!exposure?.per_stage) return {};
		const phase: JourneyPhase = {};
		for (const [stage, row] of Object.entries(exposure.per_stage)) {
			const k = STAGE_TO_KEY[stage];
			if (!k) continue;
			phase[k] = {
				earned: { n: row.earned.n, of: row.earned.of, pts: row.earned.pts, teams: row.earned.teams },
				available: { n: row.available.n, of: row.available.of, pts: row.available.pts, teams: row.available.teams }
			};
		}
		return phase;
	}

	$: journeyP1 = buildPhase(p1Exposure);
	$: journeyP2 = buildPhase(p2Exposure);

	// Inline score entry was removed — the dashboard is read-only. The
	// red "N KO matches missing predictions" alert at the top still pushes
	// users to /predictions, and unlocked upcoming matches surface an
	// inline "Edit" button on the row itself that links to the wizard.

	// ---- Strip labels ------------------------------------------------------
	$: stripYou = rank
		? `<b>You</b> · ${rank}${ordinal(rank)} of ${rankOf} · ${total} pts${rankDelta !== 0 ? ` · ${rankDelta > 0 ? '▲' : '▼'}${Math.abs(rankDelta)}` : ''}`
		: null;
	$: stripLock = nextLockFixture
		? `<b>Next KO lock</b> ${teamCode(nextLockFixture.home_team)}–${teamCode(nextLockFixture.away_team)} in ${formatDuration(nextLockFixture.time_until_lock)}`
		: null;
</script>

<svelte:head>
	<title>Dashboard — Knockout stage</title>
</svelte:head>

<PnPageShell lockLabel={stripLock} youLabel={stripYou}>
	<div class="pn-dash-v4">
		<DwBackPageReplay />

		{#if missingPicks.length > 0}
			<DwAlert
				variant="red"
				title={`${missingPicks.length} KO ${missingPicks.length === 1 ? 'match' : 'matches'} missing predictions`}
				meta={`Per-match deadlines · ${nextLockLabel}`}
				ctaLabel="Predict now →"
				ctaHref="/predictions"
			/>
		{/if}

		<DwKpiRow
			{rank}
			{rankOf}
			{rankDelta}
			{total}
			totalDelta={pastTotalPts}
			exact={exactCount}
			{exactOf}
			exactDelta={pastExact}
			outcomes={correctOutcomes}
			outcomesOf={exactOf}
			outcomesDelta={pastOutc}
			rarity={rarityPts}
			rarityShareOf={total}
			trajectory={trajectoryRanks}
			trajectoryMaxRank={rankOf || 30}
			trajectoryTodayPts={pastTotalPts}
			trajectoryNowLabel={`Last ${PAST_SHOW}`}
		/>

		<!-- The journey strip rides ABOVE the match tables: it's the KO
		     stage's signature widget (what's still alive in your bracket)
		     and it bridges naturally from the KPI numbers above it. -->
		<section class="pn-journey-sec">
			<DwScoringJourney p1={journeyP1} p2={journeyP2} footHref="/leaderboard" />
		</section>

		<!-- Same 3-col rhythm as the group-stage dashboard. -->
		<section class="pn-dash-cols spectator">
			<div class="col">
				<div class="pn-sec-h">
					<span class="ttl"><span class="pip"></span> Past <em>{PAST_SHOW}</em> matches</span>
					<span class="meta">{pastFinished.length} matches · <b>+{pastTotalPts} pts</b></span>
				</div>
				<DwMatchTable
					groupColumnLabel="Rnd"
					rows={pastFinished.map(buildRow)}
					emptyText="No KO matches finished yet."
				/>
			</div>

			<div class="col">
				<div class="pn-sec-h">
					<span class="ttl">
						<span class="pip" class:red={missingPicks.length > 0}></span>
						Upcoming <em>{UPCOMING_SHOW}</em> matches
					</span>
					<span class="meta">
						{upcoming.length} matches{#if missingPicks.length > 0} · <b>{missingPicks.length} need picks</b>{/if}
					</span>
				</div>
				<DwMatchTable
					groupColumnLabel="Rnd"
					rows={upcoming.map(buildRow)}
					emptyText="No upcoming KO matches."
				/>
			</div>

			<div class="col">
				<DwTop5
					dense
					title="Top"
					titleEm="5"
					subtitle={`of ${rankOf || $leaderboard.length} players`}
					rows={topFive}
					you={youRow}
				/>
			</div>
		</section>
	</div>
</PnPageShell>
