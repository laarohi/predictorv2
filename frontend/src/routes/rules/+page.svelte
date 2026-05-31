<script lang="ts">
	// Public rules page. No auth gate — prospective joiners should be able
	// to read this before signing up. Pulls live values from the public
	// /api/competition/info, /api/competition/scoring-config and
	// /api/predictions/bonus/questions endpoints with sensible static
	// fallbacks so the first paint is correct even if the API is unreachable.
	import { onMount } from 'svelte';
	import PnPageShell from '$components/panini/PnPageShell.svelte';
	import {
		getCompetitionInfo,
		getScoringConfig,
		type CompetitionInfo,
		type ScoringConfig
	} from '$api/competition';
	import { getBonusQuestions, type BonusQuestion } from '$api/bonus';
	import { logarithmicRarityBonus } from '$lib/utils/matchBreakdown';

	let info: CompetitionInfo | null = null;
	let scoring: ScoringConfig | null = null;
	let bonusQuestions: BonusQuestion[] = [];

	// Static fallbacks mirror config/worldcup2026.yml — used only for first
	// paint and if the public /scoring-config call fails. Once `scoring`
	// loads, the endpoint (YAML-backed) is the single source of truth, so
	// these can't silently drift from the real scoring values.
	const RARITY_CAP_FALLBACK = 10;
	const ADVANCEMENT_FALLBACK: Record<string, number> = {
		group_position: 5,
		round_of_32: 10,
		round_of_16: 15,
		quarter_final: 25,
		semi_final: 55,
		final: 85,
		winner: 150
	};
	const ADVANCEMENT_PHASE2_FALLBACK: Record<string, number> = {
		round_of_32: 0,
		round_of_16: 5,
		quarter_final: 15,
		semi_final: 40,
		final: 60,
		winner: 100
	};

	/** Display order + labels for the bracket-points table. `phase1Only`
	 *  rounds (group position) show "—" in the Phase II column: group standings
	 *  aren't re-predicted in Phase II. R32 in Phase II is a real 0 (the line-up
	 *  is published before Phase II opens), so it renders as a number, not "—". */
	const BRACKET_ROUNDS: Array<{ key: string; label: string; phase1Only?: boolean }> = [
		{ key: 'group_position', label: 'Group position', phase1Only: true },
		{ key: 'round_of_32', label: 'Round of 32' },
		{ key: 'round_of_16', label: 'Round of 16' },
		{ key: 'quarter_final', label: 'Quarter-final' },
		{ key: 'semi_final', label: 'Semi-final' },
		{ key: 'final', label: 'Final' },
		{ key: 'winner', label: 'Tournament winner' }
	];

	$: RARITY_CAP = scoring?.rarity_cap ?? RARITY_CAP_FALLBACK;

	// Phase 1 round table + the standalone group-position bonus (the endpoint
	// keeps group_position separate from the round table). Phase 2 round table.
	// Annotated as Record so the string-keyed lookups below typecheck — the
	// object-spread otherwise narrows the inferred type and drops the index
	// signature.
	let adv1: Record<string, number> = ADVANCEMENT_FALLBACK;
	let adv2: Record<string, number> = ADVANCEMENT_PHASE2_FALLBACK;
	$: adv1 = {
		...(scoring?.advancement ?? ADVANCEMENT_FALLBACK),
		group_position: scoring?.group_position ?? ADVANCEMENT_FALLBACK.group_position
	};
	$: adv2 = scoring?.advancement_phase2 ?? ADVANCEMENT_PHASE2_FALLBACK;
	$: bracketPoints = BRACKET_ROUNDS.map((r) => ({
		round: r.label,
		p1: adv1[r.key] ?? null,
		p2: r.phase1Only ? null : (adv2[r.key] ?? null)
	}));

	onMount(async () => {
		try {
			[info, scoring, bonusQuestions] = await Promise.all([
				getCompetitionInfo(),
				getScoringConfig(),
				getBonusQuestions()
			]);
		} catch (_e) {
			// Public endpoints — failure usually means backend is down. Page
			// still renders with the static fallbacks above.
		}
	});

	function fmtCurrency(n: number): string {
		// Single-currency for now — Euros. Swap to Intl.NumberFormat keyed
		// off a Competition.currency_code field if a future pool ever runs
		// in a different currency.
		if (!n || n === 0) return '—';
		return `€${n.toFixed(0)}`;
	}

	function fmtDate(iso: string | null): string {
		if (!iso) return '—';
		return new Date(iso).toLocaleDateString('en-GB', {
			weekday: 'short',
			day: 'numeric',
			month: 'short',
			year: 'numeric'
		});
	}

	$: poolTotal =
		info && info.entry_fee && info.paid_players
			? info.entry_fee * info.paid_players
			: 0;

	/** Group consecutive agreement counts (1..P) that yield the same rarity
	 * bonus into bands, so the table is compact (e.g. "5–6 of 30 → +3"). */
	function rarityBands(
		totalPredictors: number,
		cap: number
	): Array<{ countLabel: string; bonus: number }> {
		if (totalPredictors <= 0) return [];
		const bands: Array<{ countLabel: string; bonus: number }> = [];
		let bandStart = 1;
		let bandBonus = logarithmicRarityBonus(totalPredictors, 1, cap);
		for (let k = 2; k <= totalPredictors; k++) {
			const r = logarithmicRarityBonus(totalPredictors, k, cap);
			if (r !== bandBonus) {
				bands.push({
					countLabel: bandStart === k - 1 ? `${bandStart}` : `${bandStart}–${k - 1}`,
					bonus: bandBonus
				});
				bandStart = k;
				bandBonus = r;
			}
		}
		bands.push({
			countLabel:
				bandStart === totalPredictors ? `${bandStart}` : `${bandStart}–${totalPredictors}`,
			bonus: bandBonus
		});
		return bands;
	}

	// Fall back to 30 (the design anchor) before info loads, so the table
	// renders something sensible on first paint.
	$: rarityPredictorCount = info?.total_players ?? 30;
	$: rarityRows = rarityBands(rarityPredictorCount, RARITY_CAP);

	const CATEGORY_LABEL: Record<string, string> = {
		group_stage: 'Group stage',
		top_flop: 'Top / Flop',
		awards: 'Awards'
	};
	$: bonusByCategory = (() => {
		const groups: Record<string, BonusQuestion[]> = {
			group_stage: [],
			top_flop: [],
			awards: []
		};
		for (const q of bonusQuestions) {
			(groups[q.category] ?? (groups[q.category] = [])).push(q);
		}
		return groups;
	})();
</script>

<svelte:head>
	<title>Rules — Predictor</title>
</svelte:head>

<PnPageShell>
	<!-- Hero -->
	<section class="pn-rl-hero">
		<div>
			<div class="ttl">THE <em>RULES</em></div>
			<div class="sub">
				How predictions, points and prizes work in {info?.name ?? 'FIFA World Cup 2026'}. Read the
				short version below — the long version is in the comments of every Sunday morning text
				thread you've ever been part of.
			</div>
		</div>
		<div class="meta">
			Entry fee<b>{info ? fmtCurrency(info.entry_fee) : '—'}</b>
			Players signed up<b>{info?.total_players ?? '—'}</b>
			Phase I lock<b>{info ? fmtDate(info.phase1_deadline) : '—'}</b>
		</div>
	</section>

	<!-- 01 — Phases -->
	<section class="pn-rl-section">
		<div class="h"><span>01 · Two Phases</span><span class="right">Overall score = Phase I + Phase II</span></div>
		<div class="body">
			<p>
				The competition is split into two phases, and your <b>overall score is simply Phase I
				plus Phase II added together</b>. Phase I is the blind event — you make every pick before
				a ball is kicked. Phase II opens once the group stage is done: now that the real bracket
				is set, everyone predicts the knockout rounds from the <b>actual</b> line-up. It's also a
				second chance — a strong Phase II can claw back ground for anyone who had a rough Phase I.
			</p>
			<div class="pn-rl-phases">
				<div class="pn-rl-phase gold">
					<h3>Phase <em>I</em></h3>
					<div class="when">Locks at tournament start</div>
					<ul>
						<li>Predict every group-stage match score</li>
						<li>Build a full knockout bracket from group winners</li>
						<li>Answer the 10 bonus questions</li>
						<li>Full advancement rewards — Phase I carries the heaviest weight</li>
					</ul>
				</div>
				<div class="pn-rl-phase">
					<h3>Phase <em>II</em></h3>
					<div class="when">Opens after group stage · admin-activated</div>
					<ul>
						<li>Re-build the bracket using the <b>actual</b> group standings</li>
						<li>Predict the score of each knockout match — these <b>lock 15 minutes before the start of each match</b></li>
						<li>Advancement points are set <b>per stage</b> — R32 picks pay nothing (the bracket is published) and R16 picks pay a token amount; deeper rounds carry most of the Phase II reward</li>
						<li>Phase I picks stay frozen — Phase II points are added on top</li>
					</ul>
				</div>
			</div>
		</div>
	</section>

	<!-- 02 — Match scoring -->
	<section class="pn-rl-section">
		<div class="h"><span>02 · Scoring · Match Predictions</span><span class="right">Per match</span></div>
		<div class="body">
			<p>
				For each match you predict (Phase I group stage, or Phase II knockout matches), three
				things can earn you points. They stack — a perfectly-called exact score that nobody
				else got hits all three at once.
			</p>
			<div class="pn-rl-rows">
				<div class="pn-rl-row">
					<span class="pts">+5</span>
					<div>
						<div class="lbl">Correct outcome</div>
						<div class="desc">Picking the right side (1/X/2). Awarded even if the exact score is wrong.</div>
					</div>
				</div>
				<div class="pn-rl-row">
					<span class="pts green">+10</span>
					<div>
						<div class="lbl">Exact score bonus</div>
						<div class="desc">Stacks on top of the outcome — 15 pts total if you nail the result.</div>
					</div>
				</div>
				<div class="pn-rl-row">
					<span class="pts gold">up to +10</span>
					<div>
						<div class="lbl">Rarity bonus</div>
						<div class="desc">
							Reward for being right when most people were wrong. The fewer
							friends who picked the same outcome as you, the bigger the bonus.
							Popular picks that everyone got right pay nothing extra; a lone
							correct call earns the full +10.
						</div>
					</div>
				</div>
			</div>

			<!-- Rarity bonus table: count → bonus mapping for the current pool size. -->
			<div class="pn-rl-rarity">
				<div class="pn-rl-rarity-head">
					<span>How many friends picked the same outcome as you</span>
					<span class="right">Bonus</span>
				</div>
				{#each rarityRows as band}
					<div class="pn-rl-rarity-row" class:cap={band.bonus === RARITY_CAP} class:zero={band.bonus === 0}>
						<span class="count">
							{band.countLabel} of {rarityPredictorCount}
						</span>
						<span class="pts">
							{band.bonus > 0 ? `+${band.bonus}` : '—'}
						</span>
					</div>
				{/each}
				<div class="pn-rl-rarity-foot">
					Scales with how many friends predicted that fixture. Numbers shown
					assume all {rarityPredictorCount} of you submitted — bands shift if
					fewer predictors are in.
				</div>
			</div>
		</div>
	</section>

	<!-- 03 — Bracket scoring -->
	<section class="pn-rl-section">
		<div class="h"><span>03 · Scoring · Bracket Advancements</span><span class="right">Per team-stage pick</span></div>
		<div class="body">
			<p>
				Your bracket awards points for each team you correctly predict to reach a stage —
				cumulative through the bracket. Picking <b>Argentina</b> as champion who beat
				<b>France</b> in the final, for example, awards you the Winner points
				<i>plus</i> the Final points for Argentina, plus their SF / QF / R16 / R32 stage points.
				Each round pays differently in the two phases:
			</p>
			<div class="pn-rl-bracket">
				<div class="pn-rl-bracket-head">
					<span class="rnd">Round</span>
					<span class="p">Phase I</span>
					<span class="p">Phase II</span>
				</div>
				{#each bracketPoints as row}
					<div class="pn-rl-bracket-row" class:winner={row.round === 'Tournament winner'}>
						<span class="rnd">{row.round}</span>
						<span class="p1">{row.p1 ?? '—'}</span>
						<span class="p2">{row.p2 === null ? '—' : row.p2}</span>
					</div>
				{/each}
				<div class="pn-rl-bracket-foot">
					Phase II Round of 32 pays 0 — the line-up is already published when Phase II opens,
					so there's no advancement to predict. Group position isn't re-scored in Phase II.
				</div>
			</div>
		</div>
	</section>

	<!-- 04 — Bonus questions -->
	<section class="pn-rl-section">
		<div class="h">
			<span>04 · Bonus Questions</span>
			<span class="right">{bonusQuestions.length || 10} questions · lock with Phase I</span>
		</div>
		<div class="body">
			<p>
				A small set of pre-tournament wagers on side-stories beyond the bracket. Submit your
				picks before Phase I locks; the admin reveals the correct answer as each question
				resolves (group-stage questions at the end of the group stage, awards at the FIFA
				ceremony, etc.).
			</p>
			{#each ['group_stage', 'top_flop', 'awards'] as cat (cat)}
				{@const qs = bonusByCategory[cat] ?? []}
				{#if qs.length > 0}
					<div class="pn-rl-bonus-cat">{CATEGORY_LABEL[cat]}</div>
					<div class="pn-rl-bonus-list">
						{#each qs as q (q.id)}
							<div class="pn-rl-bonus-item">
								<div class="q">{q.label}</div>
								<div class="pts">+{q.points}</div>
							</div>
						{/each}
					</div>
				{/if}
			{/each}
			{#if bonusQuestions.length === 0}
				<p style="font-family: var(--mono); font-size: 11px; color: var(--ink-3); letter-spacing: 0.06em; text-transform: uppercase;">
					Loading bonus questions…
				</p>
			{/if}
		</div>
	</section>

	<!-- 06 — Buy-in & pool -->
	<section class="pn-rl-section">
		<div class="h"><span>05 · Buy-in & Pool</span><span class="right">Cash, paid pre-tournament</span></div>
		<div class="body">
			<p>
				Entry to the competition costs <b>{info ? fmtCurrency(info.entry_fee) : 'tbd'}</b> per
				player, payable to the admin before the tournament starts. Anyone who hasn't paid by
				Phase I lock can still play, but isn't eligible for the prize pool. The admin tracks
				paid status in the admin panel.
			</p>
			<div class="pn-rl-pool">
				<div class="cell">
					<div class="l">Entry fee</div>
					<div class="v">{info ? fmtCurrency(info.entry_fee) : '—'}</div>
					<div class="sub">per player</div>
				</div>
				<div class="cell">
					<div class="l">Players paid</div>
					<div class="v">{info?.paid_players ?? '—'}</div>
					<div class="sub">of {info?.total_players ?? '—'} signed up</div>
				</div>
				<div class="cell">
					<div class="l">Pool (so far)</div>
					<div class="v">{poolTotal > 0 ? fmtCurrency(poolTotal) : '—'}</div>
					<div class="sub">grows as buy-ins land</div>
				</div>
			</div>
			<p style="margin-top: 14px;">
				<b>Prize distribution</b> is decided by the admin pre-tournament and announced in the
				competition group chat. A common split: <b>60 / 25 / 15</b> for 1st / 2nd / 3rd, or
				winner-takes-all for small pools. Final split is fixed before Phase I locks and won't
				change after kick-off.
			</p>
		</div>
	</section>

	<!-- 07 — Fine print -->
	<section class="pn-rl-section">
		<div class="h"><span>06 · The Fine Print</span><span class="right">Read once · then never again</span></div>
		<div class="body">
			<div class="pn-rl-print">
				<div class="rule">
					<div class="pip"></div>
					<div>
						<b>Knockout per-match lock · 15 minutes before kickoff</b>
						This per-match lock applies to the <b>Phase II knockout matches only</b> — each one
						locks 15 minutes before its own kickoff. Phase I group-stage scores all lock together
						at the Phase I deadline, not match-by-match. The countdown timer in the wizard is your
						friend.
					</div>
				</div>
				<div class="rule">
					<div class="pip"></div>
					<div>
						<b>Blind pool</b>
						You can't see anyone else's pick for a match until that match locks. Rarity bonuses
						are computed once the field is set, not during entry.
					</div>
				</div>
				<div class="rule">
					<div class="pip"></div>
					<div>
						<b>Score cap · 15 goals per side</b>
						The wizard caps any single team's score at 15. Yes, even when picking the 7-1 you
						saw in 2014.
					</div>
				</div>
				<div class="rule">
					<div class="pip"></div>
					<div>
						<b>Phase I bracket gate</b>
						The Phase I knockout bracket only opens once all 72 group-stage matches have been
						predicted. The bracket needs your predicted standings to seed R32, so it can't
						work earlier.
					</div>
				</div>
				<div class="rule">
					<div class="pip"></div>
					<div>
						<b>Disputes</b>
						If a fixture's score is corrected after the fact (e.g. a goal disallowed in
						post-match review), the admin can manually update the result via the admin panel
						and the leaderboard recomputes on the next request.
					</div>
				</div>
				<div class="rule">
					<div class="pip"></div>
					<div>
						<b>Have fun</b>
						This is a friend competition, not Vegas. Trash talk is encouraged. Lording an
						18-place lead over your group chat is exactly the point.
					</div>
				</div>
			</div>
		</div>
	</section>
</PnPageShell>
