<script lang="ts">
	/**
	 * Phase 2 — Group Stage dashboard (v4).
	 *
	 * Layout (top-down):
	 *   1. KPI row (rank, total, exact, outcomes, trajectory sparkline)
	 *   2. Group summary strip (per-group point totals, 12 cells)
	 *   3. 3-col grid:
	 *        a. Past 24h — finished match cards (oldest → newest)
	 *        b. Upcoming 24h — live + upcoming match cards
	 *        c. Top 5 leaderboard + pinned "you" row
	 *
	 * All data is real where available; we fall back to defensible empty
	 * states (no widgets render fake numbers in production).
	 */
	import { onMount } from 'svelte';
	import PnPageShell from '$components/panini/PnPageShell.svelte';
	import DwKpiRow from './widgets/DwKpiRow.svelte';
	import DwGroupSummaryTable, {
		type GroupMatchPts
	} from './widgets/DwGroupSummaryTable.svelte';
	import DwMatchTable, { type MatchTableRow, type PtsVariant } from './widgets/DwMatchTable.svelte';
	import DwTop5 from './widgets/DwTop5.svelte';
	import DwBackPageReplay from './widgets/DwBackPageReplay.svelte';

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
	import {
		getAgreements,
		getMyGroupQualification,
		type FixtureAgreement,
		type GroupQualEntry
	} from '$api/predictions';
	import { getScoringConfig, type ScoringConfig } from '$api/competition';
	import { teamCode } from '$lib/utils/teamCodes';
	import { goto } from '$app/navigation';
	import { koChipLabel, computeMatchPoints } from '$lib/utils/matchBreakdown';
	import type { Fixture, MatchPrediction } from '$types';

	let trajectoryData: RankTrajectoryResponse | null = null;
	// Per-fixture predictor counts + scoring config — needed to fold the
	// rarity (hybrid) bonus into the group totals, matching the leaderboard.
	let agreements: FixtureAgreement[] = [];
	let scoringConfig: ScoringConfig | null = null;
	// Per-group qualification breakdown (who got the +10/+5), from the backend
	// ledger so it reconciles with the leaderboard. Empty until a group completes.
	let qualLedger: GroupQualEntry[] = [];
	// Gates the group-summary widget: it stays in a loading state until ALL its
	// inputs (fixtures, predictions, agreements, scoring config, qual ledger)
	// have loaded, so it reveals complete instead of flashing zeros / no stickers.
	let ready = false;

	onMount(async () => {
		const fixturesP = fetchAllFixtures();
		fetchLeaderboard();
		const predsP = fetchMatchPredictions();
		try {
			trajectoryData = await getMyRankTrajectory(5);
		} catch {
			trajectoryData = null;
		}
		try {
			// Independent of the trajectory fetch: a failure here just leaves the
			// group strip on outcome+exact (no rarity) rather than blanking it.
			const [agg, cfg] = await Promise.all([getAgreements(), getScoringConfig()]);
			agreements = agg;
			scoringConfig = cfg;
		} catch {
			/* keep the flat fallback */
		}
		try {
			qualLedger = await getMyGroupQualification();
		} catch {
			/* no qualification breakdown yet (no group complete) */
		}
		// Group points + stickers also depend on fixtures + predictions — wait for
		// them so the summary reveals complete rather than mid-populate.
		try {
			await Promise.all([fixturesP, predsP]);
		} catch {
			/* render with whatever's in the stores */
		}
		ready = true;
	});

	// ---- Scoring constants (kept in sync with config/worldcup2026.yml) ----
	const POINTS_PER_OUTCOME = 5;
	const POINTS_PER_EXACT_BONUS = 10;
	const POINTS_PER_EXACT_TOTAL = POINTS_PER_OUTCOME + POINTS_PER_EXACT_BONUS;

	// ---- Helpers ----------------------------------------------------------
	function ordinal(n: number): string {
		if (n % 100 >= 11 && n % 100 <= 13) return 'th';
		switch (n % 10) {
			case 1: return 'st';
			case 2: return 'nd';
			case 3: return 'rd';
			default: return 'th';
		}
	}
	function outcomeOf(home: number, away: number): '1' | 'X' | '2' {
		if (home > away) return '1';
		if (home < away) return '2';
		return 'X';
	}
	function pickResult(
		f: Fixture
	): 'exact' | 'outc' | 'miss' | null {
		if (f.status !== 'finished' || !f.score) return null;
		const p = $predictionsByFixture.get(f.id);
		if (!p) return null;
		const fh = f.score.home_score;
		const fa = f.score.away_score;
		if (p.home_score === fh && p.away_score === fa) return 'exact';
		if (outcomeOf(p.home_score, p.away_score) === outcomeOf(fh, fa)) return 'outc';
		return 'miss';
	}
	function pointsFor(result: ReturnType<typeof pickResult>): number {
		if (result === 'exact') return POINTS_PER_EXACT_TOTAL;
		if (result === 'outc') return POINTS_PER_OUTCOME;
		return 0;
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

	// Generic pick classifier — used for both finished (actual) and live
	// (projected) match-card colourings.
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

	// ---- buildRow — drive DwMatchTable from a Fixture --------------------
	// Single source of truth that translates each fixture's runtime state
	// into the row shape the table widget consumes. The widget is purely
	// presentational; every status string, pill colour, and CTA choice
	// originates here.
	function buildRow(f: Fixture): MatchTableRow {
		const score = scoreTuple(f);
		const pick = pickTuple(f);
		const id = f.id;
		const home = teamCode(f.home_team);
		const away = teamCode(f.away_team);
		const grpLabel = f.group ?? '?';
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
		// Upcoming. Status cell stays empty (a countdown there was dropped
		// per UX feedback — it squashed the row). Instead the kickoff rides
		// inside the score chip, replacing the "VS" placeholder: that cell
		// is otherwise dead space, so the time costs no width. The CTA in
		// the points column still carries the call-to-action signal.
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

	// ---- Past 4 / Upcoming 4 (fixed-count windows) -------------------------
	// The previous 24h-window filter let the cards' total height swing with
	// kickoff schedules — handy during a busy match day, awkward to design
	// against. Fixed counts (4 each) give the columns a constant height so
	// the rest of the layout can be laid out around them.
	//
	// Live games keep showing up in the upcoming column until they're
	// finished (their kickoff is in the past but their status isn't
	// FINISHED yet), which is why we sort upcoming by kickoff ascending
	// AFTER filtering — live matches sit naturally at the top because their
	// kickoff timestamp is the earliest of the still-running set.
	// Bumped from 4 to 5 in lockstep with the DwMatchTable targetRows={5}
	// prop below — supply (fixtures fetched) and demand (row slots
	// rendered) must match or the table renders padding rows at the
	// bottom. Same number flows through the trajectory KPI's
	// "Last N matches" label and the pastExact/pastOutc deltas.
	const PAST_SHOW = 5;
	const UPCOMING_SHOW = 5;

	$: pastFinished = $fixtures
		.filter((f) => f.stage === 'group' && f.status === 'finished')
		.sort((a, b) => new Date(b.kickoff).getTime() - new Date(a.kickoff).getTime())
		.slice(0, PAST_SHOW);

	$: pastTotalPts = pastFinished.reduce((acc, f) => acc + pointsFor(pickResult(f)), 0);

	$: upcoming = $fixtures
		.filter((f) => f.stage === 'group')
		.filter(
			(f) =>
				f.status === 'live' ||
				f.status === 'halftime' ||
				f.status === 'scheduled'
		)
		.sort((a, b) => new Date(a.kickoff).getTime() - new Date(b.kickoff).getTime())
		.slice(0, UPCOMING_SHOW);

	$: upcomingLive = upcoming.filter((f) => f.status === 'live' || f.status === 'halftime').length;

	// ---- Per-group point totals ------------------------------------------
	// Split each finished group match into outcome / exact / rarity-bonus,
	// then sum per group. The rarity bonus needs per-fixture predictor counts
	// (agreements) + the scoring config, so we route through the SAME
	// `computeMatchPoints` mirror the Results page and the backend use — the
	// group total then equals the user's real leaderboard contribution from
	// the group stage, not a flat outcome+exact approximation.
	$: agreementMap = new Map(agreements.map((a) => [a.fixture_id, a]));
	// Match points per group (incl. rarity) + the per-match detail for the tooltip.
	$: matchRows = buildMatchRows(
		$fixtures,
		$predictionsByFixture,
		scoringConfig,
		agreementMap
	);
	// Merge the authoritative qualification ledger onto each group row: Qual
	// column + per-team detail, and Total = Match + Qual.
	$: qualByGroup = new Map(qualLedger.map((e) => [e.group, e]));
	$: groupRows = matchRows.map((r) => {
		const e = qualByGroup.get(r.group);
		const qual = e?.total ?? 0;
		const qualTeams = (e?.teams ?? []).map((t) => ({
			team: teamCode(t.team),
			position: t.actual_position,
			pts: t.base_points + t.position_points
		}));
		return { ...r, qual, qualTeams, total: r.match + qual };
	});
	// Group-stage advancement haul (qualification + correct-position bonus) and
	// the running Phase-1 total, for the summary table's totline.
	$: qualPts =
		($currentUserPosition?.breakdown?.phase1?.group_advance_points ?? 0) +
		($currentUserPosition?.breakdown?.phase1?.group_position_points ?? 0);
	$: bonusPts = $currentUserPosition?.breakdown?.bonus_question_points ?? 0;
	$: phase1Total = $currentUserPosition?.breakdown?.phase1?.total ?? 0;
	$: finishedGroupCount = $fixtures.filter(
		(f) => f.stage === 'group' && f.status === 'finished'
	).length;

	function matchSplit(
		f: Fixture,
		pred: MatchPrediction | undefined,
		cfg: ScoringConfig | null,
		ag: FixtureAgreement | undefined
	): { outcome: number; exact: number; bonus: number } {
		if (!pred || f.status !== 'finished' || !f.score) {
			return { outcome: 0, exact: 0, bonus: 0 };
		}
		const outcomePts = cfg?.outcome_points ?? POINTS_PER_OUTCOME;
		const exactPts = cfg?.exact_points ?? POINTS_PER_EXACT_BONUS;
		const res = computeMatchPoints({
			// Until the config loads, 'fixed' yields outcome+exact with no
			// rarity — the bonus simply fills in once agreements arrive.
			mode: cfg?.mode ?? 'fixed',
			predictedHome: pred.home_score,
			predictedAway: pred.away_score,
			actualHome: f.score.home_score,
			actualAway: f.score.away_score,
			totalPredictors: ag?.total ?? 0,
			correctPredictors: ag?.agrees_outcome ?? 0,
			outcomePoints: outcomePts,
			exactPoints: exactPts,
			cap: cfg?.rarity_cap ?? 10
		});
		const outcome = res.correctOutcome ? outcomePts : 0;
		const exact = res.exactScore ? exactPts : 0;
		// Whatever's left after outcome+exact IS the rarity bonus — so the
		// three buckets always sum back to the parity-tested total.
		return { outcome, exact, bonus: res.points - outcome - exact };
	}

	function buildMatchRows(
		allFixtures: Fixture[],
		preds: Map<string, MatchPrediction>,
		cfg: ScoringConfig | null,
		agMap: Map<string, FixtureAgreement>
	): Array<{ group: string; match: number; matches: GroupMatchPts[] }> {
		type Acc = { match: number; matches: GroupMatchPts[] };
		const map = new Map<string, Acc>();
		for (const f of allFixtures) {
			if (f.stage !== 'group' || !f.group) continue;
			if (f.status !== 'finished') continue;
			const part = matchSplit(f, preds.get(f.id), cfg, agMap.get(f.id));
			// pts includes the rarity bonus, so the per-match tooltip sums back
			// to the Match total (= the user's real leaderboard contribution).
			const pts = part.outcome + part.exact + part.bonus;
			const kind = (classifyPick(scoreTuple(f), pickTuple(f)) ?? 'miss') as
				| 'exact'
				| 'outc'
				| 'miss';
			const cur = map.get(f.group) ?? { match: 0, matches: [] };
			cur.match += pts;
			cur.matches.push({ home: teamCode(f.home_team), away: teamCode(f.away_team), pts, kind });
			map.set(f.group, cur);
		}
		const groups = Array.from({ length: 12 }, (_, i) =>
			String.fromCharCode('A'.charCodeAt(0) + i)
		);
		return groups.map((g) => {
			const b = map.get(g) ?? { match: 0, matches: [] };
			return { group: g, match: b.match, matches: b.matches };
		});
	}

	// ---- KPI values (real backend data) -----------------------------------
	$: rank = $currentUserPosition?.position ?? null;
	$: rankOf = $totalParticipants || $leaderboard.length || 0;
	$: rankDelta = ($currentUserPosition?.movement ?? 0);
	$: total = $currentUserPosition?.total_points ?? 0;
	$: totalDelta = pastTotalPts;
	$: exactCount = $currentUserPosition?.exact_scores ?? 0;
	$: exactOf = $currentUserPosition?.breakdown?.total_predictions ?? 0;
	$: correctOutcomes = $currentUserPosition?.correct_outcomes ?? 0;
	$: rarityPts = $currentUserPosition?.breakdown?.hybrid_bonus_points ?? 0;

	// Compute outcome / exact gains from the past 4 finished matches
	$: pastExact = pastFinished.filter((f) => pickResult(f) === 'exact').length;
	$: pastOutc = pastFinished.filter((f) => {
		const r = pickResult(f);
		return r === 'exact' || r === 'outc';
	}).length;

	$: trajectoryRanks = trajectoryData?.points.map((p) => p.position) ?? [];

	// ---- Standings rows + you ---------------------------------------------
	// 5 visible rows total: 5 top when user is in the top 5, OR 4 top + 1
	// pinned `you` row when the user is outside. Keeping the total fixed
	// makes the standings card the same height regardless of where the
	// user sits on the leaderboard — which preserves the card-bottom
	// alignment with the 5-row match tables alongside.
	// Hint is empty for top rows — the "X exact · Y outc" detail is busy
	// chrome for what is primarily a rank-and-points readout. The widget
	// hides the hint line when it's empty, so each row collapses to a
	// single line.
	// Ghost entrants (crowd/market bots) are a leaderboard-page feature —
	// the dashboard mini-standings shows ranked humans only.
	$: rankedBoard = humanEntries($leaderboard);
	$: topFive = rankedBoard.slice(0, youRow ? 4 : 5).map((e) => ({
		userId: e.user_id,
		position: e.position,
		name: e.user_name,
		hint: '',
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
		return {
			userId: me.user_id,
			position: me.position,
			name: me.user_name,
			hint: '',
			points: me.total_points,
			isCurrentUser: true
		};
	})();

	// ---- Strip labels (legacy chrome — kept while we have PnStrip) ---------
	$: stripYou = rank
		? `<b>You</b> · ${rank}${ordinal(rank)} of ${rankOf} · ${total} pts${rankDelta !== 0 ? ` · ${rankDelta > 0 ? '▲' : '▼'}${Math.abs(rankDelta)}` : ''}`
		: null;
	$: nextLockFixture = upcoming.find((f) => f.status === 'scheduled');
	$: stripLock = nextLockFixture
		? `<b>Next lock</b> ${teamCode(nextLockFixture.home_team)}–${teamCode(nextLockFixture.away_team)}`
		: null;
	$: stripLive = (() => {
		const f = upcoming.find((x) => x.status === 'live' || x.status === 'halftime');
		if (!f || !f.score) return null;
		return `<b>LIVE</b> · ${teamCode(f.home_team)} ${f.score.home_score}–${f.score.away_score} ${teamCode(f.away_team)} · ${f.minute ?? 0}′`;
	})();
</script>

<svelte:head>
	<title>Dashboard — Group stage</title>
</svelte:head>

<PnPageShell liveLabel={stripLive} lockLabel={stripLock} youLabel={stripYou}>
	<div class="pn-dash-v4">
		<DwBackPageReplay />

		<DwKpiRow
			{rank}
			{rankOf}
			{rankDelta}
			{total}
			{totalDelta}
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

		{#if ready}
			<DwGroupSummaryTable
				rows={groupRows}
				qualPoints={qualPts}
				bonusPoints={bonusPts}
				phaseTotal={phase1Total}
				title="Group stage"
				titleEm="so far"
				meta={`${finishedGroupCount} matches played`}
				footLeft="Total incl. rarity · tap a total for the games"
				footRight="Per-match breakdown →"
				footRightHref="/predictions"
			/>
		{:else}
			<div class="pn-sec-h">
				<span class="ttl"><span class="pip"></span> Group stage <em>so far</em></span>
				<span class="meta">loading…</span>
			</div>
			<div class="pn-summary pn-summary-loading">
				<span class="ld">Loading group points…</span>
			</div>
		{/if}

		<section class="pn-dash-cols spectator">
			<div class="col">
				<div class="pn-sec-h">
					<span class="ttl"><span class="pip"></span> Recent matches</span>
					<span class="meta">{pastFinished.length} matches · <b>+{pastTotalPts} pts</b></span>
				</div>
				<DwMatchTable
					groupColumnLabel="Grp"
					rows={pastFinished.map(buildRow)}
					emptyText="No matches finished yet."
					targetRows={5}
				/>
			</div>

			<div class="col">
				<div class="pn-sec-h">
					<span class="ttl">
						<span class="pip" class:red={upcomingLive > 0}></span>
						Upcoming matches
					</span>
					<span class="meta">
						{upcoming.length} matches{#if upcomingLive > 0} · <b>{upcomingLive} live</b>{/if}
					</span>
				</div>
				<DwMatchTable
					groupColumnLabel="Grp"
					rows={upcoming.map(buildRow)}
					emptyText="No upcoming matches."
					targetRows={5}
				/>
			</div>

			<div class="col">
				<DwTop5
					title="Standings"
					subtitle={`of ${rankOf || $leaderboard.length} players`}
					rows={topFive}
					you={youRow}
				/>
			</div>
		</section>
	</div>
</PnPageShell>
