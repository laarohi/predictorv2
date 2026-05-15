<script lang="ts">
	// Public rules page. No auth gate — prospective joiners should be able
	// to read this before signing up. Pulls live values from the public
	// /api/competition/info and /api/predictions/bonus/questions endpoints
	// with sensible static fallbacks so the first paint is correct even if
	// the API is unreachable.
	import { onMount } from 'svelte';
	import PnPageShell from '$components/panini/PnPageShell.svelte';
	import { getCompetitionInfo, type CompetitionInfo } from '$api/competition';
	import { getBonusQuestions, type BonusQuestion } from '$api/bonus';

	let info: CompetitionInfo | null = null;
	let bonusQuestions: BonusQuestion[] = [];

	onMount(async () => {
		try {
			[info, bonusQuestions] = await Promise.all([
				getCompetitionInfo(),
				getBonusQuestions()
			]);
		} catch (_e) {
			// Public endpoints — failure usually means backend is down. Page
			// still renders with hardcoded defaults below.
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

	<!-- 01 — The tournament -->
	<section class="pn-rl-section">
		<div class="h"><span>01 · The Tournament</span><span class="right">FIFA 2026 · 48 teams</span></div>
		<div class="body">
			<p>
				FIFA World Cup 2026 features <b>48 teams</b> drawn into <b>12 groups of 4</b>. Each group
				plays a single round-robin of three matches across the group stage.
			</p>
			<p>
				The top two teams from each group <b>advance directly</b> to the Round of 32. The eight
				best-ranked third-placed teams (across all 12 groups) <b>also advance</b>, filling the
				bracket to 32 teams. From there it's straight knockout: R32 → R16 → QF → SF → Final.
			</p>
		</div>
	</section>

	<!-- 02 — Phases -->
	<section class="pn-rl-section">
		<div class="h"><span>02 · Two Phases</span><span class="right">Phase II points at 70% value</span></div>
		<div class="body">
			<p>
				The competition is split into two phases. Phase I is the headline event — everything is
				up for grabs and predictions are made blind, before a ball is kicked. Phase II opens
				after the group stage, gives you a second crack at the bracket with full knowledge of
				who advanced, and is worth less per pick to keep Phase I players in the game.
			</p>
			<div class="pn-rl-phases">
				<div class="pn-rl-phase gold">
					<h3>Phase <em>I</em></h3>
					<div class="when">Locks at tournament start</div>
					<ul>
						<li>Predict every group-stage match score</li>
						<li>Build a full knockout bracket from group winners</li>
						<li>Answer the 9 bonus questions</li>
						<li>All Phase I points are 1× face value</li>
					</ul>
				</div>
				<div class="pn-rl-phase">
					<h3>Phase <em>II</em></h3>
					<div class="when">Opens after group stage · admin-activated</div>
					<ul>
						<li>Re-build the bracket using <b>actual</b> group standings</li>
						<li>Predict the score of each knockout match</li>
						<li>Phase II points are scaled to <b>70%</b> of their face value</li>
						<li>Phase I picks remain frozen — Phase II is additive</li>
					</ul>
				</div>
			</div>
		</div>
	</section>

	<!-- 03 — Match scoring -->
	<section class="pn-rl-section">
		<div class="h"><span>03 · Scoring · Match Predictions</span><span class="right">Per match</span></div>
		<div class="body">
			<p>
				For each match you predict (Phase I group stage, or Phase II knockout matches), three
				things can earn you points. They stack — a perfectly-called exact score that nobody
				else got hits all three at once.
			</p>
			<div class="pn-rl-rows">
				<div class="pn-rl-row">
					<span class="pts">5</span>
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
						<div class="lbl">Rarity bonus (hybrid mode)</div>
						<div class="desc">The fewer players who got the outcome right, the higher this bonus climbs. Capped at +10.</div>
					</div>
				</div>
			</div>
		</div>
	</section>

	<!-- 04 — Bracket scoring -->
	<section class="pn-rl-section">
		<div class="h"><span>04 · Scoring · Bracket Advancements</span><span class="right">Per team-stage pick</span></div>
		<div class="body">
			<p>
				Your bracket awards points for each team you correctly predict to reach a stage —
				cumulative through the bracket. Picking <b>Argentina</b> as champion who beat
				<b>France</b> in the final, for example, awards you the Winner points
				<i>plus</i> the Final points for Argentina, plus their SF / QF / R16 / R32 stage points.
			</p>
			<div class="pn-rl-stages">
				<div class="pn-rl-stage">
					<div class="lbl">Group advance</div>
					<div class="pts">10</div>
				</div>
				<div class="pn-rl-stage">
					<div class="lbl">Group position</div>
					<div class="pts">5</div>
				</div>
				<div class="pn-rl-stage">
					<div class="lbl">Round of 32</div>
					<div class="pts">10</div>
				</div>
				<div class="pn-rl-stage">
					<div class="lbl">Round of 16</div>
					<div class="pts">15</div>
				</div>
				<div class="pn-rl-stage">
					<div class="lbl">Quarter-final</div>
					<div class="pts">20</div>
				</div>
				<div class="pn-rl-stage">
					<div class="lbl">Semi-final</div>
					<div class="pts">40</div>
				</div>
				<div class="pn-rl-stage">
					<div class="lbl">Final</div>
					<div class="pts">60</div>
				</div>
				<div class="pn-rl-stage winner">
					<div class="lbl">Tournament winner</div>
					<div class="pts">100</div>
				</div>
			</div>
		</div>
	</section>

	<!-- 05 — Bonus questions -->
	<section class="pn-rl-section">
		<div class="h">
			<span>05 · Bonus Questions</span>
			<span class="right">{bonusQuestions.length || 9} questions · lock with Phase I</span>
		</div>
		<div class="body">
			<p>
				A small set of pre-tournament wagers on side-stories beyond the bracket. Submit your
				picks before Phase I locks; the admin reveals the correct answer as each question
				resolves (group-stage questions at the end of the group stage, awards at the FIFA
				ceremony, etc.). Player-name answers are matched leniently — capitalisation and
				accents don't matter.
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
		<div class="h"><span>06 · Buy-in & Pool</span><span class="right">Cash, paid pre-tournament</span></div>
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
		<div class="h"><span>07 · The Fine Print</span><span class="right">Read once · then never again</span></div>
		<div class="body">
			<div class="pn-rl-print">
				<div class="rule">
					<div class="pip"></div>
					<div>
						<b>Per-match lock · 5 minutes before kickoff</b>
						Once a match locks you can't change your prediction for it, regardless of phase.
						The countdown timer in the wizard is your friend.
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
						<b>Phase II is optional but recommended</b>
						If the admin activates Phase II, you can re-build the bracket using actual group
						results. You're not penalised for skipping it — but every Phase II point you don't
						earn is one your rivals can.
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
