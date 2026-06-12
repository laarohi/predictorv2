<script lang="ts">
	/**
	 * Phase 3 — Between-phases dashboard (v4).
	 *
	 * Layout:
	 *   1. Unsaved-bracket alert (gold, if user has local bracket edits pending)
	 *   2. Funnel hero (Phase 2 bracket deadline countdown + progress) — the
	 *      "you just finished Phase 1 with N pts, real groups are in" beat
	 *   3. KPI row (Phase 1 final values + group-stage trajectory)
	 *   4. 2-col bottom:
	 *        - Group stage summary table (12 groups × Outc/Exact/Qual/Total)
	 *        - Phase 1 "final" leaderboard (Top 5 + you)
	 */
	import { onMount } from 'svelte';
	import PnPageShell from '$components/panini/PnPageShell.svelte';
	import DwAlert from './widgets/DwAlert.svelte';
	import DwFunnelHero from './widgets/DwFunnelHero.svelte';
	import DwKpiRow from './widgets/DwKpiRow.svelte';
	import DwGroupSummaryTable from './widgets/DwGroupSummaryTable.svelte';
	import DwTop5 from './widgets/DwTop5.svelte';
	import type { GroupSummaryRow } from './widgets/DwGroupSummaryTable.svelte';

	import { user } from '$stores/auth';
	import { fetchAllFixtures, fixtures } from '$stores/fixtures';
	import {
		fetchMatchPredictions,
		predictionsByFixture,
		fetchPhase2BracketPredictions,
		workingPhase2BracketPrediction,
		hasUnsavedPhase2BracketChanges
	} from '$stores/predictions';
	import { countBracketSlotsFilled, BRACKET_TOTAL_SLOTS_PHASE2 } from '$lib/utils/bracketProgress';
	import {
		phase2BracketDeadline,
		currentTime
	} from '$stores/phase';
	import {
		fetchLeaderboard,
		currentUserPosition,
		leaderboard,
		totalParticipants,
		setPhase
	} from '$stores/leaderboard';
	import { humanEntries } from '$lib/utils/ghosts';
	import { getMyRankTrajectory, type RankTrajectoryResponse } from '$api/leaderboard';
	import type { Fixture } from '$types';

	let trajectoryData: RankTrajectoryResponse | null = null;

	onMount(async () => {
		fetchAllFixtures();
		fetchMatchPredictions();
		fetchPhase2BracketPredictions();
		// Pull the Phase 1 (final) leaderboard for the right column — between
		// phases it represents the locked-in groups standings.
		await setPhase('phase_1');
		try {
			trajectoryData = await getMyRankTrajectory(30);
		} catch {
			trajectoryData = null;
		}
	});

	// ---- Constants ---------------------------------------------------------
	const POINTS_PER_OUTCOME = 5;
	const POINTS_PER_EXACT_BONUS = 10;

	// ---- Helpers -----------------------------------------------------------
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

	// ---- Countdown digits --------------------------------------------------
	$: countdown = (() => {
		if (!$phase2BracketDeadline) return { d: 0, h: 0, m: 0, s: 0 };
		const target = new Date($phase2BracketDeadline).getTime();
		const diff = target - $currentTime.getTime();
		if (diff <= 0) return { d: 0, h: 0, m: 0, s: 0 };
		const d = Math.floor(diff / (1000 * 60 * 60 * 24));
		const h = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
		const m = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
		const s = Math.floor((diff % (1000 * 60)) / 1000);
		return { d, h, m, s };
	})();

	// ---- Phase 1 group-by-group breakdown ---------------------------------
	$: groupRows = (() => {
		const groups = Array.from({ length: 12 }, (_, i) =>
			String.fromCharCode('A'.charCodeAt(0) + i)
		);
		const map = new Map<string, { outcome: number; exact: number }>();
		groups.forEach((g) => map.set(g, { outcome: 0, exact: 0 }));
		for (const f of $fixtures) {
			if (f.stage !== 'group' || !f.group) continue;
			const r = pickResult(f);
			if (!r) continue;
			const bucket = map.get(f.group);
			if (!bucket) continue;
			if (r === 'exact') {
				bucket.outcome += POINTS_PER_OUTCOME;
				bucket.exact += POINTS_PER_EXACT_BONUS;
			} else if (r === 'outc') {
				bucket.outcome += POINTS_PER_OUTCOME;
			}
		}
		const rows: GroupSummaryRow[] = groups.map((g) => {
			const b = map.get(g)!;
			return {
				group: g,
				outcome: b.outcome,
				exact: b.exact,
				total: b.outcome + b.exact
			};
		});
		return rows;
	})();

	$: qualPts =
		($currentUserPosition?.breakdown?.phase1?.group_advance_points ?? 0) +
		($currentUserPosition?.breakdown?.phase1?.group_position_points ?? 0);

	$: groupOutcomeTotal = groupRows.reduce((acc, r) => acc + r.outcome, 0);
	$: groupExactTotal = groupRows.reduce((acc, r) => acc + r.exact, 0);
	$: bonusPts = $currentUserPosition?.breakdown?.bonus_question_points ?? 0;
	$: phaseTotal = $currentUserPosition?.breakdown?.phase1?.total ?? (groupOutcomeTotal + groupExactTotal + bonusPts);

	// ---- KPI values --------------------------------------------------------
	$: rank = $currentUserPosition?.position ?? null;
	$: rankOf = $totalParticipants || $leaderboard.length || 0;
	$: rankDelta = $currentUserPosition?.movement ?? 0;
	$: total = $currentUserPosition?.total_points ?? 0;
	$: exactCount = $currentUserPosition?.exact_scores ?? 0;
	$: exactOf = $currentUserPosition?.breakdown?.total_predictions ?? 0;
	$: correctOutcomes = $currentUserPosition?.correct_outcomes ?? 0;
	$: rarityPts = $currentUserPosition?.breakdown?.hybrid_bonus_points ?? 0;
	$: trajectoryRanks = trajectoryData?.points.map((p) => p.position) ?? [];

	// ---- Top 5 (Phase 1 final) + you --------------------------------------
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
		hint: `${e.exact_scores} exact · ${e.correct_outcomes} outc`,
		points: e.total_points,
		isCurrentUser: e.user_id === $user?.id
	}));
	$: youIndex = rankedBoard.findIndex((e) => e.user_id === $user?.id);
	$: youRow = (() => {
		const me = $currentUserPosition;
		// Gate on ROW index, not position number: ties share a position
		// (competition ranking), so "position <= 5" can be true for a user
		// rendered well below the fifth row — invisible in the 5-row slice.
		if (!me || (youIndex >= 0 && youIndex < 5)) return null;
		const gap = me.position > 1 ? ` · −${($leaderboard[0]?.total_points ?? me.total_points) - me.total_points} to #1` : '';
		return {
			userId: me.user_id,
			position: me.position,
			name: me.user_name,
			hint: `YOU${gap}`,
			points: me.total_points,
			isCurrentUser: true
		};
	})();

	// ---- Bracket progress — real Phase 2 bracket fill, same helper the wizard
	// and DashboardPre use, so the funnel can't disagree with them.
	$: bracketFilled = countBracketSlotsFilled($workingPhase2BracketPrediction).done;
	$: stripLock = $phase2BracketDeadline
		? `<b>Phase 2 bracket locks</b> · ${countdown.d}d ${countdown.h}h ${countdown.m}m`
		: null;
</script>

<svelte:head>
	<title>Predictor — Redo your bracket</title>
</svelte:head>

<PnPageShell lockLabel={stripLock}>
	<div class="pn-dash-v4">
		{#if $hasUnsavedPhase2BracketChanges}
			<DwAlert
				variant="gold"
				title="Bracket has unsaved changes"
				meta="You've re-picked your bracket on this device — <b>save before the deadline</b>"
				ctaLabel="Save bracket"
				ctaHref="/predictions"
			/>
		{/if}

		<!-- Top band: half-width hero beside a 2×3 KPI grid. The hero keeps
		     its drama at half width (clock under the title, progress + CTA
		     pinned to the card bottom) and the KPI cells stay the SAME size
		     as every other dashboard — the grid shape changes, not the
		     sticker. Both stretch to the same band height. -->
		<section class="pn-between-top">
			<DwFunnelHero
				side
				label="Phase 2 — Re-pick bracket"
				titleHtml="Real groups are in. Re-pick the <em>knockout</em>."
				lede={`Phase 1 ended. Group stage scored you <b style="color: var(--gold);">${phaseTotal} pts</b>. Your original bracket carries over until you update it — but the real R32 matchups are now set.`}
				{countdown}
				progressLabel="Phase 2 bracket"
				progressValue={bracketFilled}
				progressTotal={BRACKET_TOTAL_SLOTS_PHASE2}
				progressUnit="set"
				ctaLabel="Update bracket"
				ctaHref="/predictions"
			/>

			<DwKpiRow
				columns={3}
				{rank}
				{rankOf}
				{rankDelta}
				{total}
				totalDelta={0}
				totalSub={'<b>pts</b> · phase 1 final'}
				exact={exactCount}
				{exactOf}
				exactDelta={0}
				outcomes={correctOutcomes}
				outcomesOf={exactOf}
				outcomesDelta={0}
				rarity={rarityPts}
				rarityShareOf={total}
				trajectory={trajectoryRanks}
				trajectoryMaxRank={rankOf || 30}
				trajectoryTodayPts={0}
			/>
		</section>

		<!-- Bottom band: both columns share the pn-sec-h header treatment
		     and close with the same internal foot bar, so the two cards
		     align top edge to bottom edge. -->
		<section class="pn-dash-cols between">
			<div class="col">
				<DwGroupSummaryTable
					rows={groupRows}
					bonusPoints={bonusPts}
					qualPoints={qualPts}
					phaseTotal={phaseTotal}
					title="Group stage"
					titleEm="summary"
					meta="final · all matches played"
				/>
			</div>
			<div class="col">
				<DwTop5
					footInside
					footLeft="phase 1 standings carry into phase 2"
					title="Phase 1"
					titleEm="final"
					subtitle="where it stands"
					rows={topFive}
					you={youRow}
					footLabel="See full standings →"
				/>
			</div>
		</section>
	</div>
</PnPageShell>
