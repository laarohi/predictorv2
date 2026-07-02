<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { isAuthenticated, user, authResolved } from '$stores/auth';
	import { getUserPointsLog } from '$api/users';
	import type { PointsLogEvent, PointsLogResponse } from '$types';
	import { teamCode } from '$lib/utils/teamCodes';
	import PnPageShell from '$components/panini/PnPageShell.svelte';
	import PnFlag from '$components/panini/PnFlag.svelte';

	$: if ($authResolved && !$isAuthenticated) goto('/login');
	$: userId = $page.params.userId;
	$: isOwnLog = userId === $user?.id;

	let log: PointsLogResponse | null = null;
	let loading = true;
	let error: string | null = null;
	let search = '';
	// Misses are hidden by default — the log opens as "where my points came
	// from"; flipping this on answers "why did I get nothing for that one".
	let showMisses = false;

	$: if (userId && $isAuthenticated) loadLog(userId);

	async function loadLog(id: string) {
		loading = true;
		error = null;
		try {
			log = await getUserPointsLog(id);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load points log';
		} finally {
			loading = false;
		}
	}

	const STAGE_LABELS: Record<string, string> = {
		group: 'Group stage',
		round_of_32: 'Round of 32',
		round_of_16: 'Round of 16',
		quarter_final: 'Quarter-final',
		semi_final: 'Semi-final',
		third_place: 'Third-place match',
		final: 'Final',
		winner: 'Champion'
	};
	const PHASE_LABELS: Record<string, string> = {
		phase_1: 'Phase I',
		phase_2: 'Phase II',
		both: 'Phase I+II'
	};
	const KIND_LABELS: Record<PointsLogEvent['kind'], string> = {
		match: 'Score',
		advance: 'Bracket',
		bonus: 'Bonus'
	};

	function stageLabel(stage: string | null): string {
		return stage ? (STAGE_LABELS[stage] ?? stage) : '';
	}
	/** "2-0" → "2–0" (en dash for display). */
	function fmtScore(s: string | null): string {
		return (s ?? '').replace('-', '–');
	}
	function ordinal(n: number): string {
		if (n % 100 >= 11 && n % 100 <= 13) return 'th';
		return { 1: 'st', 2: 'nd', 3: 'rd' }[n % 10] ?? 'th';
	}

	/** Headline for a bracket (advance) event. */
	function advanceTitle(e: PointsLogEvent): string {
		const team = e.team ?? '';
		if (e.is_miss) {
			if (e.elim_stage === 'group') {
				return e.group ? `${team} didn't make it out of Group ${e.group}` : `${team} didn't make it out of the groups`;
			}
			return `${team} knocked out in the ${stageLabel(e.elim_stage)}`;
		}
		if (e.stage === 'round_of_32') {
			return e.third_place
				? `${team} squeezed through as a best third`
				: `${team} qualified from Group ${e.group ?? '?'}`;
		}
		if (e.stage === 'winner') return `${team} won the tournament`;
		return `${team} reached the ${stageLabel(e.stage)}`;
	}

	/** Second line for a bracket event — what the pick was. */
	function advanceSub(e: PointsLogEvent): string {
		const parts: string[] = [];
		if (e.stage === 'round_of_32') {
			if (e.predicted_position != null && e.predicted_position === e.actual_position && !e.is_miss) {
				parts.push(`called ${e.actual_position}${ordinal(e.actual_position)} place exactly`);
			}
			if (e.is_miss) parts.push('was in the R32 bracket');
		} else if (e.is_miss) {
			parts.push(`bracket had them reaching the ${stageLabel(e.stage)}`);
		}
		return parts.join(' · ');
	}

	function eventMeta(e: PointsLogEvent): string {
		const parts: string[] = [];
		if (e.kind === 'match') {
			parts.push(e.group ? `Group ${e.group}` : stageLabel(e.stage));
		}
		if (e.phase) parts.push(PHASE_LABELS[e.phase] ?? e.phase);
		if (e.kind === 'bonus') parts.push('Bonus question');
		return parts.join(' · ');
	}

	function searchable(e: PointsLogEvent): string {
		return [e.home_team, e.away_team, e.team, e.question_label, e.answer, e.group, stageLabel(e.stage)]
			.filter(Boolean)
			.join(' ')
			.toLowerCase();
	}

	function fmtDay(iso: string): string {
		return new Date(iso).toLocaleDateString('en-GB', {
			weekday: 'short',
			day: 'numeric',
			month: 'short'
		});
	}
	function dayKey(iso: string): string {
		const d = new Date(iso);
		return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
	}

	$: visible = (log?.events ?? []).filter((e) => {
		if (!showMisses && e.is_miss) return false;
		const q = search.trim().toLowerCase();
		return !q || searchable(e).includes(q);
	});

	// Day totals come from the FULL event list so filtering rows never
	// changes what a day was actually worth.
	$: dayTotals = (() => {
		const totals = new Map<string, number>();
		for (const e of log?.events ?? []) {
			const k = dayKey(e.ts);
			totals.set(k, (totals.get(k) ?? 0) + e.points);
		}
		return totals;
	})();

	$: days = (() => {
		const out: Array<{ key: string; label: string; total: number; events: PointsLogEvent[] }> = [];
		const idx = new Map<string, number>();
		for (const e of visible) {
			const key = dayKey(e.ts);
			let i = idx.get(key);
			if (i === undefined) {
				i = out.length;
				idx.set(key, i);
				out.push({ key, label: fmtDay(e.ts), total: dayTotals.get(key) ?? 0, events: [] });
			}
			out[i].events.push(e);
		}
		return out;
	})();

	$: missCount = (log?.events ?? []).filter((e) => e.is_miss).length;
</script>

<svelte:head><title>Points log{log ? ` — ${log.user_name}` : ''} — Predictor</title></svelte:head>

{#if $isAuthenticated}
	<PnPageShell>
		<section class="pn-pf-section">
			<div class="h">
				<span>{log ? `Points Log — ${log.user_name}` : 'Points Log'}</span>
				<a class="right back" href={isOwnLog ? '/profile' : `/profile/${userId}`}>← Profile</a>
			</div>
			<div class="body">
				{#if error}
					<div class="pn-pf-alert error">{error}</div>
				{:else if loading}
					<p class="muted">Loading points log…</p>
				{:else if log}
					<div class="ledger-top">
						<div class="total">
							<span class="l">Total banked</span>
							<span class="v">{log.total_points}<em>pts</em></span>
						</div>
						<p class="intro">
							Every point {isOwnLog ? 'you have' : `${log.user_name} has`} earned — match by
							match, team by team, question by question — newest first.
							{#if missCount > 0}Show misses to see the picks that earned nothing.{/if}
						</p>
					</div>

					<div class="tools">
						<input class="srch" type="text" placeholder="Search teams, questions…" bind:value={search} />
						<label class="lk">
							<input type="checkbox" bind:checked={showMisses} />
							Show misses{#if missCount > 0} ({missCount}){/if}
						</label>
					</div>

					{#if log.events.length === 0}
						<p class="muted">Nothing on the board yet — points show up here as soon as results are graded.</p>
					{:else if visible.length === 0}
						<p class="muted">No entries match the current filter.</p>
					{:else}
						{#each days as day (day.key)}
							<div class="dayhead">
								<span class="d">{day.label}</span>
								<span class="rule"></span>
								<span class="sum" class:zero={day.total === 0}>{day.total > 0 ? `+${day.total}` : day.total} pts</span>
							</div>
							<div class="evlist">
								{#each day.events as e (e.id)}
									<div class="ev" class:miss={e.is_miss}>
										<div class="kind kind-{e.kind}">{KIND_LABELS[e.kind]}</div>
										<div class="main">
											{#if e.kind === 'match'}
												<div class="headline">
													<span class="t"><PnFlag code={teamCode(e.home_team ?? '')} w={14} h={10} />{teamCode(e.home_team ?? '')}</span>
													<b class="sc">{fmtScore(e.actual)}</b>
													<span class="t"><PnFlag code={teamCode(e.away_team ?? '')} w={14} h={10} />{teamCode(e.away_team ?? '')}</span>
													<span class="pick">pick {fmtScore(e.predicted)}</span>
												</div>
											{:else if e.kind === 'advance'}
												<div class="headline">
													{#if e.team}<PnFlag code={teamCode(e.team)} w={14} h={10} />{/if}
													<span class="txt">{advanceTitle(e)}</span>
												</div>
												{#if advanceSub(e)}<div class="sub">{advanceSub(e)}</div>{/if}
											{:else}
												<div class="headline"><span class="txt">{e.question_label}</span></div>
												<div class="sub">
													pick: {e.answer}
													{#if e.is_miss && e.correct_answers.length > 0}
														· answer: {e.correct_answers.join(' / ')}
													{/if}
												</div>
											{/if}
											<div class="meta">{eventMeta(e)}</div>
											{#if e.chips.length > 1}
												<div class="chips">
													{#each e.chips as c (c.label)}
														<span
															class="chip"
															title={c.label.includes('carried')
																? 'No Phase II bracket was submitted, so the Phase I picks carry forward at the Phase II point values'
																: null}>{c.label} +{c.points}</span
														>
													{/each}
												</div>
											{/if}
										</div>
										<div class="pts" class:zero={e.points === 0} class:gold={e.result === 'exact'}>
											{e.points > 0 ? `+${e.points}` : '0'}
										</div>
									</div>
								{/each}
							</div>
						{/each}
					{/if}
				{/if}
			</div>
		</section>
	</PnPageShell>
{/if}

<style>
	.back {
		text-decoration: none;
		color: var(--paper-3);
		cursor: pointer;
	}
	.muted {
		font-family: var(--mono);
		font-size: 12px;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--ink-3);
	}
	.ledger-top {
		display: flex;
		gap: 18px;
		align-items: center;
		margin-bottom: 14px;
	}
	.ledger-top .total {
		flex: 0 0 auto;
		border: 2px solid var(--ink);
		background: var(--paper-2);
		box-shadow: 3px 3px 0 var(--ink);
		padding: 8px 14px;
		text-align: center;
	}
	.ledger-top .total .l {
		display: block;
		font-family: var(--mono);
		font-size: 9px;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--ink-3);
	}
	.ledger-top .total .v {
		font-family: var(--display);
		font-size: 26px;
		line-height: 1.1;
		color: var(--ink);
	}
	.ledger-top .total .v em {
		font-style: normal;
		font-size: 11px;
		margin-left: 3px;
		color: var(--ink-2);
	}
	.intro {
		font-family: var(--body);
		font-size: 13px;
		line-height: 1.5;
		color: var(--ink-2);
		margin: 0;
	}
	.tools {
		display: flex;
		gap: 14px;
		align-items: center;
		flex-wrap: wrap;
		margin-bottom: 16px;
	}
	.srch {
		flex: 1 1 200px;
		padding: 8px 12px;
		font-family: var(--body);
		font-size: 13px;
		background: var(--paper-2);
		border: 2px solid var(--ink);
		color: var(--ink);
	}
	.lk {
		font-family: var(--mono);
		font-size: 11px;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--ink-3);
		display: inline-flex;
		align-items: center;
		gap: 6px;
		cursor: pointer;
		white-space: nowrap;
	}

	.dayhead {
		display: flex;
		align-items: center;
		gap: 10px;
		margin: 18px 0 4px;
	}
	.dayhead:first-of-type {
		margin-top: 6px;
	}
	.dayhead .d {
		font-family: var(--mono);
		font-size: 11px;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		font-weight: 700;
		color: var(--ink);
	}
	.dayhead .rule {
		flex: 1;
		border-top: 2px dotted var(--paper-3);
	}
	.dayhead .sum {
		font-family: var(--display);
		font-size: 13px;
		color: var(--green);
	}
	.dayhead .sum.zero {
		color: var(--ink-3);
	}

	.evlist {
		display: flex;
		flex-direction: column;
	}
	.ev {
		display: grid;
		grid-template-columns: 64px 1fr auto;
		gap: 12px;
		align-items: start;
		padding: 10px 0;
		border-top: 1px solid var(--paper-3);
	}
	.ev:first-child {
		border-top: none;
	}
	.ev.miss {
		opacity: 0.55;
	}
	.kind {
		font-family: var(--mono);
		font-size: 9px;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		text-align: center;
		padding: 4px 0;
		border: 1.5px solid var(--ink);
		color: var(--ink);
		background: var(--paper-2);
		margin-top: 2px;
	}
	.kind-match { border-color: var(--green); color: var(--green); }
	.kind-advance { border-color: var(--navy); color: var(--navy); }
	.kind-bonus { border-color: var(--gold); color: var(--gold); }

	.headline {
		font-family: var(--body);
		font-size: 13.5px;
		line-height: 1.4;
		color: var(--ink);
		display: flex;
		align-items: center;
		gap: 6px;
		flex-wrap: wrap;
	}
	.headline .t {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		font-family: var(--mono);
		font-weight: 700;
		font-size: 13px;
	}
	.headline .sc {
		font-family: var(--display);
		font-size: 14px;
	}
	.headline .pick {
		font-family: var(--mono);
		font-size: 11.5px;
		color: var(--ink-2);
		margin-left: 4px;
	}
	.headline .txt {
		display: inline;
	}
	.sub {
		font-family: var(--body);
		font-size: 12px;
		color: var(--ink-2);
		margin-top: 2px;
	}
	.meta {
		font-family: var(--mono);
		font-size: 10px;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--ink-3);
		margin-top: 3px;
		display: flex;
		gap: 8px;
		flex-wrap: wrap;
		align-items: center;
	}
	.chips {
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
		margin-top: 5px;
	}
	.chip {
		font-family: var(--mono);
		font-size: 10px;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		border: 1.5px solid var(--paper-3);
		background: var(--paper-2);
		color: var(--ink-2);
		padding: 2px 7px;
	}
	.pts {
		font-family: var(--display);
		font-size: 19px;
		line-height: 1.2;
		color: var(--green);
		min-width: 44px;
		text-align: right;
		margin-top: 2px;
	}
	.pts.gold {
		color: var(--gold);
	}
	.pts.zero {
		color: var(--ink-3);
	}

	@media (max-width: 460px) {
		.ev {
			grid-template-columns: 52px 1fr auto;
			gap: 8px;
		}
		.kind {
			font-size: 8px;
		}
		.pts {
			font-size: 17px;
			min-width: 36px;
		}
		.ledger-top {
			flex-direction: column;
			align-items: flex-start;
			gap: 10px;
		}
	}
</style>
