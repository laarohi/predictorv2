<script lang="ts">
	/**
	 * Phase 1 — Pre-tournament dashboard (v4).
	 *
	 * Layout:
	 *   1. Unsaved-predictions alert (gold, when there are local but un-saved
	 *      prediction edits — TODO: wire to unsavedPersistence store)
	 *   2. Funnel hero (countdown to Phase 1 lock + progress bar + CTA)
	 *   3. 3-col equal: scoring peek · structure peek · player roster
	 *
	 * The roster currently shows whatever rows the leaderboard exposes. A
	 * future backend endpoint that lists registered users with their
	 * prediction-count progress would let us show the full ~30-player
	 * roster the design calls for; until then we pad with the current user
	 * so the layout doesn't collapse on first paint.
	 */
	import { onMount } from 'svelte';
	import PnPageShell from '$components/panini/PnPageShell.svelte';
	import DwAlert from './widgets/DwAlert.svelte';
	import DwFunnelHero from './widgets/DwFunnelHero.svelte';
	import DwPeek from './widgets/DwPeek.svelte';
	import DwRoster from './widgets/DwRoster.svelte';

	import { user } from '$stores/auth';
	import { fetchAllFixtures, fixtures } from '$stores/fixtures';
	import {
		fetchMatchPredictions,
		fetchBracketPredictions,
		predictionsByFixture,
		workingBracketPrediction
	} from '$stores/predictions';
	import {
		phase1Deadline,
		currentTime
	} from '$stores/phase';
	import { getRoster, type RosterResponse } from '$api/users';
	import { getBonusQuestions, getMyBonusPredictions } from '$api/bonus';
	import { getCompetitionInfo, type CompetitionInfo } from '$api/competition';
	import { countBracketSlotsFilled, BRACKET_TOTAL_SLOTS } from '$lib/utils/bracketProgress';

	let rosterResp: RosterResponse | null = null;
	let info: CompetitionInfo | null = null;
	// Bonus questions + the user's saved bonus answers come from two separate
	// endpoints (questions are config-driven, answers are per-user). We store
	// the counts only — the dashboard never renders the question prompts, so
	// holding the full payloads in memory would be wasteful.
	let bonusQuestionsCount: number | null = null;
	let bonusFilled = 0;
	// Gate the progress meter until all inputs (fixtures, match preds, bracket,
	// bonus) have loaded — see onMount — so the bar doesn't fill up from 0/0%.
	let dashReady = false;

	onMount(async () => {
		// Progress-data fetches fire immediately (the banner/roster don't wait on
		// them) but are captured so dashReady can flip once they resolve.
		const progressData = Promise.all([
			fetchAllFixtures(),
			fetchMatchPredictions(),
			fetchBracketPredictions()
		]);
		// Roster + competition info fetched in parallel — they're independent
		// requests and the banner can render without the roster.
		const [rosterResult, infoResult] = await Promise.allSettled([
			getRoster(),
			getCompetitionInfo(),
		]);
		rosterResp = rosterResult.status === 'fulfilled' ? rosterResult.value : null;
		info = infoResult.status === 'fulfilled' ? infoResult.value : null;
		try {
			const [questions, preds] = await Promise.all([
				getBonusQuestions(),
				getMyBonusPredictions()
			]);
			bonusQuestionsCount = questions.length;
			// A saved bonus prediction with an empty `answer` shouldn't count
			// as filled — the wizard's own logic uses the Map size only, but
			// the backend echo can include skipped entries; defensive trim.
			bonusFilled = preds.filter((p) => p.answer && p.answer.length > 0).length;
		} catch {
			bonusQuestionsCount = null;
		}
		// All progress inputs are in — reveal the real numbers so the meter
		// doesn't visibly fill from 0% as data streamed in.
		await progressData.catch(() => {});
		dashReady = true;
	});

	$: groupFixtures = $fixtures.filter((f) => f.stage === 'group');
	// FIFA 2026 has 72 group matches (12 groups × 6 each). The `|| 72`
	// fallback only matters during the first paint before fixtures arrive
	// — after that the live value rules.
	$: totalGroupMatches = groupFixtures.length || 72;
	$: filledGroup = groupFixtures.filter((f) => $predictionsByFixture.has(f.id)).length;

	// Bracket: 63 KO slots; reused from the same helper the wizard uses, so
	// the dashboard's "you're 88% there" and the wizard's progress bar can
	// never disagree by construction.
	$: bracketSlotsFilled = countBracketSlotsFilled($workingBracketPrediction).done;

	// Bonus question count is dynamic — config can add/remove questions
	// without a code change. While the bonus fetch is in flight we fall back
	// to the known YAML count of 10 so the hero doesn't read 72/72 (which
	// would look like the user has finished when they haven't).
	$: totalBonusQuestions = bonusQuestionsCount ?? 10;

	$: overallTotal = totalGroupMatches + BRACKET_TOTAL_SLOTS + totalBonusQuestions;
	$: overallFilled = filledGroup + bracketSlotsFilled + bonusFilled;

	// Entry fee comes from /competition/info (YAML-backed). Fall back to 30
	// before the fetch resolves so the banner copy and the Revolut URL stay
	// sensible during the first render. EUR is the only supported currency.
	$: entryFee = info?.entry_fee ?? 30;
	$: revolutUrl = `https://revolut.me/laarohi?currency=EUR&amount=${Math.round(entryFee * 100)}&note=World%20Cup%20Predictor`;

	$: countdown = (() => {
		if (!$phase1Deadline) return { d: 0, h: 0, m: 0, s: 0 };
		const target = new Date($phase1Deadline).getTime();
		const diff = target - $currentTime.getTime();
		if (diff <= 0) return { d: 0, h: 0, m: 0, s: 0 };
		const d = Math.floor(diff / (1000 * 60 * 60 * 24));
		const h = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
		const m = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
		const s = Math.floor((diff % (1000 * 60)) / 1000);
		return { d, h, m, s };
	})();

	// Roster comes from the public /users/roster endpoint (returns ALL active
	// registered users, alphabetical). Until it loads we fall back to a
	// single-row "you" placeholder so the layout doesn't collapse.
	$: rosterRows = (() => {
		if (rosterResp) {
			return rosterResp.entries.map((e, i) => ({
				position: String(i + 1).padStart(2, '0'),
				name: e.name,
				handle: e.is_current_user
					? 'YOU'
					: `@${e.name.split(' ')[0].toLowerCase()}`,
				filled: e.match_predictions_filled + e.bracket_picks_filled + e.bonus_picks_filled,
				total: overallTotal,
				isCurrentUser: e.is_current_user,
				paid: e.paid
			}));
		}
		if ($user) {
			return [
				{
					position: '01',
					name: $user.name ?? 'You',
					handle: 'YOU',
					filled: overallFilled,
					total: overallTotal,
					isCurrentUser: true,
					paid: $user.paid
				}
			];
		}
		return [];
	})();

	$: playerCount = rosterResp?.total_active_users ?? rosterRows.length;
	$: stripLock = $phase1Deadline
		? `<b>Phase 1 locks</b> · ${countdown.d}d ${countdown.h}h ${countdown.m}m`
		: null;

	// Hero greeting + state-aware lede.
	// First name only — "Welcome back, Luke" reads warmer than the full
	// name. Same split(' ')[0] convention the roster handles use above.
	// Greeting flips on whether the user has any picks yet: 0 picks means
	// they're effectively new to the prediction flow even if they've
	// logged in before.
	$: firstName = $user?.name?.split(' ')[0] ?? 'predictor';
	// When both alerts fire they share one row — stacked, the pair alone
	// would eat ~165px of a one-screen page.
	$: showUnpaid = $user !== null && $user.paid === false;
	$: showUnfilled = dashReady && overallFilled < overallTotal && overallFilled > 0;

	$: heroGreeting = overallFilled === 0 ? 'Welcome' : 'Welcome back';
	$: heroTitleHtml = `${heroGreeting}, <em>${firstName}</em>.`;
	$: heroLede =
		overallFilled === overallTotal
			? "You're all set, no edits after the start of the tournament — so any last tweaks, get them in now."
			: `The World Cup is back bigger than ever and so is the CxF Predictaa, ${overallTotal} picks to make before the start of the tournament, let's get cracking.`;
</script>

<svelte:head>
	<title>Predictor — Sign up &amp; predict</title>
</svelte:head>

<PnPageShell lockLabel={stripLock}>
	<div class="pn-dash-v4">
		{#if showUnpaid || showUnfilled}
			<div class="pn-alert-pair" class:both={showUnpaid && showUnfilled}>
				{#if showUnpaid}
					<DwAlert
						variant="red"
						icon="€"
						title="Entry fee unpaid"
						meta={`Send <b>€${entryFee}</b> to <b>+356 9929 0197</b> on Revolut before the competition starts.`}
						ctaLabel={`Pay €${entryFee} now`}
						ctaHref={revolutUrl}
						ctaExternal
					/>
				{/if}
				{#if showUnfilled}
					<DwAlert
						variant="gold"
						title={`${overallTotal - overallFilled} predictions still to fill`}
						meta="Lock in before the whistle · <b>switch devices &amp; partial drafts are gone</b>"
						ctaLabel="Open predictions →"
						ctaHref="/predictions"
					/>
				{/if}
			</div>
		{/if}

		<DwFunnelHero
			label="Phase 1 — Predictions due"
			titleHtml={heroTitleHtml}
			lede={heroLede}
			{countdown}
			progressLabel="Overall progress"
			progressValue={overallFilled}
			progressTotal={overallTotal}
			progressUnit="picks"
			progressReady={dashReady}
			ctaLabel="Open predictions"
			ctaHref="/predictions"
			teasers={[
				{ label: 'Group matches', value: dashReady ? String(filledGroup) : '—', outOf: String(totalGroupMatches) },
				{ label: 'Bracket picks', value: dashReady ? String(bracketSlotsFilled) : '—', outOf: String(BRACKET_TOTAL_SLOTS) },
				{ label: 'Bonus questions', value: dashReady ? String(bonusFilled) : '—', outOf: String(totalBonusQuestions) }
			]}
		/>

		<!-- Two columns, not three: the old "Tournament structure" card was
		     rules-page content (the hero teasers already enumerate the
		     Phase 1 duties); its Phase II awareness survives as the last
		     rules row. The roster pins to the rules card's height. -->
		<section class="pn-dash-cols two">
			<div class="col">
				<DwPeek
					mode="rules"
					title="How"
					titleEm="points work"
					meta="phase 1"
					rules={[
						{
							pts: '+5',
							ptsUnit: 'pts',
							ptsTone: 'gold',
							name: 'Correct outcome',
							desc: 'Right side (1/X/2), even if the scoreline is off — per match.'
						},
						{
							pts: '+10',
							ptsUnit: 'pts',
							ptsTone: 'green',
							name: 'Exact-score bonus',
							desc: 'Stacks on the outcome — 15 pts when you nail both goals.'
						},
						{
							pts: '+0–10',
							ptsUnit: 'pts',
							ptsTone: 'red',
							name: 'Rarity bonus',
							desc: 'Picks the room missed pay more; consensus earns no extra.'
						},
						{
							pts: '10–150',
							ptsUnit: 'pts',
							ptsTone: 'navy',
							name: 'Bracket advance',
							desc: 'Each team reaching its predicted round — R32 (10) to Winner (150).'
						},
						{
							pts: '5–100',
							ptsUnit: 'pts',
							ptsTone: 'red',
							name: 'Phase II — re-pick after groups',
							desc: 'Re-pick the bracket with the real R32, plus KO match scores.'
						}
					]}
					footLabel="Read full rules →"
					footHref="/rules"
				/>
			</div>
			<div class="col">
				<DwRoster
					title={`★ Players · ${playerCount} ${playerCount === 1 ? 'player' : 'of 30'}`}
					meta={playerCount >= 30 ? 'waitlist at 30' : 'registration open'}
					rows={rosterRows}
				/>
			</div>
		</section>
	</div>
</PnPageShell>
