<script lang="ts">
	/**
	 * Phase 5 — Post-competition dashboard (v4).
	 *
	 * Layout:
	 *   1. Champion podium (Groups winner · Overall champion · Bracket winner)
	 *   2. 2-col: Points by source · Highlights (retrospective cards)
	 *
	 * No KPI row here: the competition is over, so live deltas/hit-rates are
	 * noise. The user's final rank/points/peak ride the masthead strip, and
	 * Points-by-source carries the total — the podium gets the vertical
	 * room instead.
	 *
	 * Data:
	 *   - leaderboard (overall + phase_1 + phase_2 winners)
	 *   - /leaderboard/tournament-winner — who lifted the trophy and how
	 *     many predicted it correctly
	 *   - /leaderboard/me/highlights — personal retrospective
	 *   - $currentUserPosition.breakdown — for points-by-source split
	 */
	import { onMount } from 'svelte';
	import PnPageShell from '$components/panini/PnPageShell.svelte';
	import DwChampionPodium from './widgets/DwChampionPodium.svelte';
	import DwPointsBySource, { type Source } from './widgets/DwPointsBySource.svelte';
	import DwHighlights from './widgets/DwHighlights.svelte';

	import { user } from '$stores/auth';
	import { fetchAllFixtures, fixtures } from '$stores/fixtures';
	import {
		fetchLeaderboard,
		currentUserPosition,
		leaderboard,
		totalParticipants
	} from '$stores/leaderboard';
	import { getLeaderboard } from '$api/leaderboard';
	import {
		getMyRankTrajectory,
		getTournamentWinnerPickers,
		getMyHighlights,
		type RankTrajectoryResponse,
		type TournamentWinnerPickers,
		type MyHighlights
	} from '$api/leaderboard';
	import { teamCode } from '$lib/utils/teamCodes';
	import { displayTeamName } from '$lib/utils/teamName';
	import type { LeaderboardEntry } from '$types';

	let trajectoryData: RankTrajectoryResponse | null = null;
	let phase1Top: LeaderboardEntry[] = [];
	let phase2Top: LeaderboardEntry[] = [];
	let winners: TournamentWinnerPickers | null = null;
	let highlights: MyHighlights | null = null;

	onMount(async () => {
		fetchAllFixtures();
		fetchLeaderboard();
		try {
			const [p1, p2, traj, win, hl] = await Promise.all([
				getLeaderboard('phase_1').catch(() => null),
				getLeaderboard('phase_2').catch(() => null),
				getMyRankTrajectory(365).catch(() => null),
				getTournamentWinnerPickers().catch(() => null),
				getMyHighlights().catch(() => null)
			]);
			if (p1) phase1Top = p1.entries.slice(0, 5);
			if (p2) phase2Top = p2.entries.slice(0, 5);
			trajectoryData = traj;
			winners = win;
			highlights = hl;
		} catch {
			// degrade gracefully on backend errors
		}
	});

	// ---- Podium composition ------------------------------------------------
	$: champion = $leaderboard[0]
		? {
				name: $leaderboard[0].user_name,
				hint: `${$leaderboard[0].exact_scores} exact · ${$leaderboard[0].correct_outcomes} outcomes`,
				points: $leaderboard[0].total_points,
				unit: 'pts'
			}
		: null;

	$: groupsWinner = phase1Top[0]
		? {
				name: phase1Top[0].user_name,
				hint: `@${phase1Top[0].user_name.split(' ')[0].toLowerCase()} · best Phase 1 · ${phase1Top[0].exact_scores} exact`,
				points: phase1Top[0].total_points,
				unit: 'GS pts'
			}
		: null;

	$: bracketWinner = phase2Top[0]
		? {
				name: phase2Top[0].user_name,
				hint: `@${phase2Top[0].user_name.split(' ')[0].toLowerCase()} · best Phase 2 re-pick`,
				points: phase2Top[0].total_points,
				unit: 'P2 pts'
			}
		: null;

	$: tournamentWinner = (() => {
		if (!winners?.actual_winner) {
			// Fallback: read winner from finished final fixture
			const final = $fixtures.find((f) => f.stage === 'final' && f.status === 'finished');
			if (!final || !final.score) return null;
			const winnerTeam =
				final.score.home_score > final.score.away_score
					? final.home_team
					: final.score.home_score < final.score.away_score
						? final.away_team
						: null;
			return winnerTeam
				? { code: teamCode(winnerTeam), name: displayTeamName(winnerTeam) }
				: null;
		}
		return {
			code: teamCode(winners.actual_winner),
			name: displayTeamName(winners.actual_winner)
		};
	})();

	$: pickedCorrectly = winners?.phase1_picker_count ?? null;

	// ---- Final figures (masthead strip + meta lines) ------------------------
	$: rank = $currentUserPosition?.position ?? null;
	$: rankOf = $totalParticipants || $leaderboard.length || 0;
	$: total = $currentUserPosition?.total_points ?? 0;
	$: trajectoryRanks = trajectoryData?.points.map((p) => p.position) ?? [];
	$: peakRank = trajectoryRanks.length ? Math.min(...trajectoryRanks) : rank ?? 0;

	// ---- Points by source --------------------------------------------------
	$: pointsSources = ((): Source[] => {
		const b = $currentUserPosition?.breakdown;
		if (!b) return [];
		const matchTotal = b.match_outcome_points + b.exact_score_points + b.hybrid_bonus_points;
		const p1Bracket = b.phase1
			? b.phase1.group_advance_points +
				b.phase1.group_position_points +
				b.phase1.round_of_32_points +
				b.phase1.round_of_16_points +
				b.phase1.quarter_final_points +
				b.phase1.semi_final_points +
				b.phase1.final_points +
				b.phase1.winner_points
			: 0;
		const p2Bracket = b.phase2
			? b.phase2.group_advance_points +
				b.phase2.group_position_points +
				b.phase2.round_of_32_points +
				b.phase2.round_of_16_points +
				b.phase2.quarter_final_points +
				b.phase2.semi_final_points +
				b.phase2.final_points +
				b.phase2.winner_points
			: 0;
		const bonus = b.bonus_question_points;
		return [
			{ key: 'match', name: 'Match scores', points: matchTotal },
			{ key: 'p1', name: 'P1 bracket', points: p1Bracket },
			{ key: 'p2', name: 'P2 bracket', points: p2Bracket },
			{ key: 'bonus', name: 'Bonus questions', points: bonus }
		];
	})();

	// ---- Highlights composition -------------------------------------------
	$: highlightCards = (() => {
		const cards: Array<{
			label: string;
			valueHtml: string;
			valueTone?: 'gold' | 'red';
			desc: string;
			tag?: { label: string; tone?: 'gold' | 'red' | 'green' };
		}> = [];
		if (highlights?.best_exact_streak) {
			const s = highlights.best_exact_streak;
			cards.push({
				label: 'Best exact streak',
				valueHtml: `<em>${s.count}</em> ${s.count === 1 ? 'match' : 'matches'}`,
				desc: `Run of ${s.count} consecutive exact${s.count === 1 ? '' : 's'} · <b>+${s.count * 15} pts</b>`,
				tag: { label: '★ STREAK', tone: 'green' }
			});
		}
		if (highlights?.biggest_climb) {
			const c = highlights.biggest_climb;
			cards.push({
				label: 'Biggest single-day climb',
				valueHtml: `▲<em>${c.places}</em> places`,
				desc: `${new Date(c.captured_date).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })} · from ${c.from_position} → ${c.to_position}`,
				tag: { label: '▲ CLIMB' }
			});
		}
		if (highlights?.most_contrarian_correct) {
			const m = highlights.most_contrarian_correct;
			cards.push({
				label: 'Most contrarian win',
				valueHtml: `${teamCode(m.home_team)} <em>${m.user_pick}</em> ${teamCode(m.away_team)}`,
				valueTone: 'gold',
				desc: `You + ${m.agrees_exact - 1} of ${m.total} picked it · <b>rarity bonus</b>`,
				tag: { label: '⭐ RARE' }
			});
		}
		if (highlights?.best_phase) {
			const p = highlights.best_phase;
			const label = p.phase === 'phase_1' ? 'Phase 1' : 'Phase 2';
			cards.push({
				label: 'Best phase',
				valueHtml: `<em>${label}</em>`,
				valueTone: 'gold',
				desc: `${p.points} pts came from this phase`,
				tag: { label: '🔥 PEAK', tone: 'red' }
			});
		}
		return cards;
	})();

	// ---- Sign-off (podium header meta) -------------------------------------
	// Was a standalone DwMemorialStrip below the fold; folded into the
	// podium's top-right meta. null (no finished final yet) just drops the
	// segment — falling back to "Vol. I closed" would duplicate metaLine2.
	$: signoffLine = (() => {
		const final = $fixtures.find((f) => f.stage === 'final' && f.status === 'finished');
		if (!final || !final.score) return null;
		const ko = new Date(final.kickoff);
		const dateStr = ko.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
		return `Final · ${teamCode(final.home_team)} ${final.score.home_score}–${final.score.away_score} ${teamCode(final.away_team)} · ${dateStr}`;
	})();

	$: podiumMetaLine1 = [`${rankOf} players`, `${$fixtures.length} matches`, signoffLine]
		.filter(Boolean)
		.join(' · ');

	$: stripYou = rank
		? `<b>You</b> · ${rank} of ${rankOf} · ${total} pts · peak ${peakRank}`
		: null;
</script>

<svelte:head>
	<title>Predictor — Final standings</title>
</svelte:head>

<PnPageShell youLabel={stripYou} showStrip={true}>
	<div class="pn-dash-v4">
		<DwChampionPodium
			title="It's a wrap."
			titleEm="wrap"
			label="Vol. I · CxF Predictaa"
			metaLine1={podiumMetaLine1}
			metaLine2="Vol. I closed · next edition 2030"
			{champion}
			{groupsWinner}
			{bracketWinner}
			{tournamentWinner}
			{pickedCorrectly}
			totalPlayers={rankOf}
		/>

		<section class="pn-dash-cols two">
			<div class="col">
				{#if pointsSources.length > 0}
					<DwPointsBySource sources={pointsSources} total={total} meta="final" />
				{/if}
			</div>
			<div class="col">
				{#if highlightCards.length > 0}
					<DwHighlights highlights={highlightCards} />
				{/if}
			</div>
		</section>

	</div>
</PnPageShell>
