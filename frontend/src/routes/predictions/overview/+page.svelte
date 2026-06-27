<script lang="ts">
	/**
	 * Prediction overview — "who picked what" across the whole pool.
	 *
	 * Sibling of the prediction wizard (the Your picks ↔ Overview switcher
	 * in both heroes navigates between them). Two sections:
	 *   - Group stage: one panel per group — how many players put each team
	 *     1st / through to the R32, plus the 1/X/2 split behind every
	 *     fixture. Clicking a fixture opens the scoreline heatmap modal.
	 *   - Knockout: forecast table — how many players carried each team to
	 *     each knockout round. Sortable; Phase I/II toggle once Phase 2 is live.
	 *
	 * Blind pool: the backend 403s until Phase 1 locks; this page mirrors
	 * the same gate from the phase store so the lock card renders without a
	 * failed round-trip.
	 */
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { isAuthenticated, user } from '$stores/auth';
	import {
		isPhase1Locked,
		isPhase2Active,
		isPhase2BracketLocked,
		phase1Countdown,
		phase2Countdown
	} from '$stores/phase';
	import {
		getBracketOverview,
		getCommunityPredictions,
		getGroupsOverview,
		getKnockoutScoresOverview
	} from '$api/predictions';
	import { getLeaderboard, type PhaseFilter } from '$api/leaderboard';
	import { getScoringConfig, type ScoringConfig } from '$api/competition';
	import { getBonusOverview, type BonusOverviewResponse } from '$api/bonus';
	import { buildCells, gridAxes, pickActualScore, toGridPlayer, type GridPlayer } from '$lib/utils/matchDetail';
	import { teamCode } from '$lib/utils/teamCodes';
	import { displayTeamName } from '$lib/utils/teamName';
	import PnPageShell from '$components/panini/PnPageShell.svelte';
	import PnFlag from '$components/panini/PnFlag.svelte';
	import PnPointsBar from '$components/panini/PnPointsBar.svelte';
	import PnScoreHeatmap from '$components/panini/PnScoreHeatmap.svelte';
	import type {
		BracketOverviewResponse,
		BracketOverviewTeamRow,
		CommunityPredictionsResponse,
		GroupsOverviewResponse,
		KnockoutScoreFixtureRow,
		KnockoutScoresOverviewResponse,
		LeaderboardEntry,
		LeaderboardResponse,
		OverviewCountCell,
		OverviewFixtureRow
	} from '$types';

	$: if (browser && !$isAuthenticated) goto('/login');

	// ---- Section state (groups | knockout | bonus), shareable via ?tab= -----
	type Section = 'groups' | 'knockout' | 'bonus';
	let section: Section = 'groups';
	let sectionInitialised = false;
	$: if (browser && !sectionInitialised && $page.url) {
		const tab = $page.url.searchParams.get('tab');
		section = tab === 'knockout' || tab === 'bonus' ? tab : 'groups';
		sectionInitialised = true;
	}

	// Within the Knockout section: the existing per-round advancement
	// forecast, or (Phase 2 only) the pool's knockout match-SCORE splits.
	type KnockoutView = 'advancement' | 'scores';
	let knockoutView: KnockoutView = 'advancement';

	function setSection(s: Section) {
		section = s;
		if (browser) {
			const url = new URL(window.location.href);
			if (s !== 'groups') url.searchParams.set('tab', s);
			else url.searchParams.delete('tab');
			history.replaceState(history.state, '', url);
		}
		if (s === 'knockout') {
			void loadBracket();
			if (knockoutView === 'scores') void loadKnockoutScores();
		}
		if (s === 'bonus') void loadBonus();
	}

	function setKnockoutView(v: KnockoutView) {
		knockoutView = v;
		if (v === 'scores') void loadKnockoutScores();
		else void loadBracket();
	}

	// ---- Data ---------------------------------------------------------------
	let groupsData: GroupsOverviewResponse | null = null;
	let groupsError: string | null = null;
	let groupsLoading = false;

	// Bracket data cached per phase so toggling I ↔ II doesn't refetch.
	let bracketByPhase: Record<number, BracketOverviewResponse> = {};
	let bracketError: string | null = null;
	let bracketLoading = false;
	let bracketPhase: 1 | 2 = 1;
	let bracketPhaseInitialised = false;
	// Default the toggle to the live phase once known.
	$: if (!bracketPhaseInitialised && $isPhase2Active !== undefined) {
		bracketPhase = $isPhase2Active && $isPhase2BracketLocked ? 2 : 1;
		bracketPhaseInitialised = true;
	}

	$: phase2Viewable = $isPhase2Active && $isPhase2BracketLocked;
	$: bracketData = bracketByPhase[bracketPhase] ?? null;
	// Your own name, used to gold-flag the counts your bracket is part of.
	$: youName = $user?.name ?? null;

	async function loadGroups() {
		if (!$isPhase1Locked || groupsData || groupsLoading) return;
		groupsLoading = true;
		groupsError = null;
		try {
			groupsData = await getGroupsOverview();
		} catch (e) {
			groupsError = e instanceof Error ? e.message : 'Failed to load the overview.';
		} finally {
			groupsLoading = false;
		}
	}

	async function loadBracket() {
		const phase = bracketPhase;
		if (phase === 1 && !$isPhase1Locked) return;
		if (phase === 2 && !phase2Viewable) return;
		if (bracketByPhase[phase] || bracketLoading) return;
		bracketLoading = true;
		bracketError = null;
		try {
			const resp = await getBracketOverview(phase);
			bracketByPhase = { ...bracketByPhase, [phase]: resp };
		} catch (e) {
			bracketError = e instanceof Error ? e.message : 'Failed to load the overview.';
		} finally {
			bracketLoading = false;
		}
	}

	function setBracketPhase(p: 1 | 2) {
		bracketPhase = p;
		void loadBracket();
	}

	// Knockout match-SCORE distribution (Phase 2). Per-match blind pool: the
	// backend only returns a fixture's split once it individually locks, so
	// this can change between visits as more knockout matches kick off — we
	// refetch each time the Scores sub-view is opened rather than caching.
	let koScoresData: KnockoutScoresOverviewResponse | null = null;
	let koScoresError: string | null = null;
	let koScoresLoading = false;

	async function loadKnockoutScores() {
		if (!$isPhase2Active) return;
		if (koScoresLoading) return;
		koScoresLoading = true;
		koScoresError = null;
		try {
			koScoresData = await getKnockoutScoresOverview();
		} catch (e) {
			koScoresError = e instanceof Error ? e.message : 'Failed to load the overview.';
		} finally {
			koScoresLoading = false;
		}
	}

	// Round label + ordering for the knockout-scores panels.
	const KO_ROUND_LABELS: Record<string, string> = {
		round_of_32: 'Round of 32',
		round_of_16: 'Round of 16',
		quarter_final: 'Quarter-finals',
		semi_final: 'Semi-finals',
		third_place: 'Third place',
		final: 'Final'
	};
	const KO_ROUND_ORDER = ['round_of_32', 'round_of_16', 'quarter_final', 'semi_final', 'third_place', 'final'];

	interface KnockoutRound {
		stage: string;
		label: string;
		fixtures: KnockoutScoreFixtureRow[];
	}
	// Group the (already round-then-kickoff ordered) fixtures into round panels.
	$: koRounds = (() => {
		if (!koScoresData) return [] as KnockoutRound[];
		const byStage = new Map<string, KnockoutScoreFixtureRow[]>();
		for (const fx of koScoresData.fixtures) {
			const list = byStage.get(fx.stage) ?? [];
			list.push(fx);
			byStage.set(fx.stage, list);
		}
		return KO_ROUND_ORDER.filter((s) => byStage.has(s)).map((s) => ({
			stage: s,
			label: KO_ROUND_LABELS[s] ?? s,
			fixtures: byStage.get(s) ?? []
		}));
	})();

	// Bonus-question answer distribution.
	let bonusData: BonusOverviewResponse | null = null;
	let bonusError: string | null = null;
	let bonusLoading = false;

	async function loadBonus() {
		if (!$isPhase1Locked || bonusData || bonusLoading) return;
		bonusLoading = true;
		bonusError = null;
		try {
			bonusData = await getBonusOverview();
		} catch (e) {
			bonusError = e instanceof Error ? e.message : 'Failed to load the overview.';
		} finally {
			bonusLoading = false;
		}
	}

	onMount(() => {
		if (!$isAuthenticated) return;
		void loadGroups();
		if (section === 'knockout') void loadBracket();
		if (section === 'bonus') void loadBonus();
	});
	// Re-attempt once the phase status arrives (stores hydrate async); the
	// in-flight/already-loaded guards inside the loaders make these cheap.
	$: if (browser && $isPhase1Locked) void loadGroups();
	$: if (browser && $isPhase1Locked && section === 'knockout') void loadBracket();
	$: if (browser && $isPhase1Locked && section === 'bonus') void loadBonus();
	$: if (
		browser &&
		$isPhase2Active &&
		section === 'knockout' &&
		knockoutView === 'scores' &&
		!koScoresData &&
		!koScoresLoading
	)
		void loadKnockoutScores();

	// ---- Forecast table sorting --------------------------------------------
	type SortKey = keyof Pick<
		BracketOverviewTeamRow,
		'team' | 'round_of_32' | 'round_of_16' | 'quarter_final' | 'semi_final' | 'final' | 'winner'
	>;
	type NumKey = Exclude<SortKey, 'team'>;
	const COLS: { key: NumKey; label: string; hint: string }[] = [
		{ key: 'round_of_32', label: 'R32', hint: 'Picked to reach the Round of 32' },
		{ key: 'round_of_16', label: 'R16', hint: 'Picked to reach the Round of 16' },
		{ key: 'quarter_final', label: 'QF', hint: 'Picked to reach the Quarter-finals' },
		{ key: 'semi_final', label: 'SF', hint: 'Picked to reach the Semi-finals' },
		{ key: 'final', label: 'Final', hint: 'Picked to reach the Final' },
		{ key: 'winner', label: 'Champ', hint: 'Picked to win the World Cup' }
	];
	let sortKey: SortKey = 'winner';
	let sortDir: 1 | -1 = -1;

	function setSort(k: SortKey) {
		if (sortKey === k) {
			sortDir = (sortDir * -1) as 1 | -1;
		} else {
			sortKey = k;
			sortDir = k === 'team' ? 1 : -1;
		}
	}
	const arrow = (k: SortKey, sk: SortKey, sd: 1 | -1) => (sk === k ? (sd === 1 ? '↑' : '↓') : '');

	// Stable composite ordering under any header: ties resolved champion-first
	// (the backend's default ordering), so sorting by R16 doesn't shuffle
	// equal-count teams randomly.
	function cmpDefault(a: BracketOverviewTeamRow, b: BracketOverviewTeamRow): number {
		return (
			b.winner.count - a.winner.count ||
			b.final.count - a.final.count ||
			b.semi_final.count - a.semi_final.count ||
			b.quarter_final.count - a.quarter_final.count ||
			b.round_of_16.count - a.round_of_16.count ||
			b.round_of_32.count - a.round_of_32.count ||
			a.team.localeCompare(b.team)
		);
	}
	$: tableRows = bracketData
		? [...bracketData.teams].sort((a, b) => {
				if (sortKey === 'team') return sortDir * a.team.localeCompare(b.team);
				const d = a[sortKey].count - b[sortKey].count;
				return d !== 0 ? sortDir * d : cmpDefault(a, b);
			})
		: [];

	// ---- Who-is-behind-a-count popover ---------------------------------------
	// One floating card for every clickable count on the page (group position
	// cells, advance cells, forecast-table cells). Anchored under the count,
	// clamped to the viewport; dismissed on outside press / Escape / re-click.
	interface Pop {
		title: string;
		sub: string;
		users: string[];
		left: number;
		top: number;
		anchor: HTMLElement;
	}
	let pop: Pop | null = null;
	const POP_W = 210;

	function openPop(e: MouseEvent, title: string, sub: string, cell: OverviewCountCell) {
		const anchor = e.currentTarget as HTMLElement;
		if (pop?.anchor === anchor) {
			pop = null; // second click on the same count toggles it off
			return;
		}
		const r = anchor.getBoundingClientRect();
		pop = {
			title,
			sub,
			users: cell.users,
			left: Math.min(window.innerWidth - POP_W - 8, Math.max(8, r.left + r.width / 2 - POP_W / 2)),
			top: r.bottom + 6,
			anchor
		};
	}
	function onWindowPress(e: MouseEvent) {
		if (!pop) return;
		const t = e.target as Node;
		if (pop.anchor.contains(t)) return; // openPop's toggle handles this
		const popEl = document.querySelector('.pn-ov-pop');
		if (popEl && popEl.contains(t)) return;
		pop = null;
	}
	function onWindowKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') pop = null;
	}
	// Page scroll would drag a fixed-position popover away from its anchor —
	// dismiss. But the popover's own name list is scrollable, and scroll
	// events are observed in the capture phase, so scrolls that originate
	// INSIDE the popover must be ignored or the list closes itself the
	// moment the user scrolls it.
	function onAnyScroll(e: Event) {
		if (!pop) return;
		const t = e.target as Node | null;
		const popEl = document.querySelector('.pn-ov-pop');
		if (t && popEl && popEl.contains(t)) return;
		pop = null;
	}

	// ---- Heatmap modal -------------------------------------------------------
	let modalDialog: HTMLDialogElement;
	let modalRow: OverviewFixtureRow | null = null;
	let modalCommunity: CommunityPredictionsResponse | null = null;
	let modalLoading = false;
	let modalError: string | null = null;

	// Leaderboard + scoring config are fetched once, lazily, for tooltip
	// labels (season points pre-match, +pts post-match).
	let leaderboardEntries: LeaderboardEntry[] = [];
	let scoringConfig: ScoringConfig = {
		mode: 'logarithmic',
		outcome_points: 5,
		exact_points: 10,
		rarity_cap: 10
	};
	let modalDepsLoaded = false;

	async function openFixture(row: OverviewFixtureRow) {
		modalRow = row;
		modalCommunity = null;
		modalError = null;
		modalLoading = true;
		modalDialog?.showModal();
		try {
			if (!modalDepsLoaded) {
				const [lb, cfg] = await Promise.all([
					getLeaderboard(null as PhaseFilter).catch(
						() => ({ entries: [] }) as Partial<LeaderboardResponse> as LeaderboardResponse
					),
					getScoringConfig().catch(() => scoringConfig)
				]);
				leaderboardEntries = lb.entries ?? [];
				scoringConfig = cfg;
				modalDepsLoaded = true;
			}
			modalCommunity = await getCommunityPredictions(row.fixture_id);
		} catch (e) {
			modalError = e instanceof Error ? e.message : 'Failed to load predictions.';
		} finally {
			modalLoading = false;
		}
	}
	function closeModal() {
		modalDialog?.close();
		modalRow = null;
	}
	function onModalBackdropClick(e: MouseEvent) {
		if (e.target === modalDialog) closeModal();
	}

	$: modalPlayers = (() => {
		if (!modalCommunity) return [] as GridPlayer[];
		const lbByName = new Map(leaderboardEntries.map((e) => [e.user_name, e]));
		const youName = $user?.name ?? null;
		return modalCommunity.predictions.map((cp) => {
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
	$: modalGridMax = gridAxes(modalPlayers, modalActual);
	$: modalCells = buildCells(modalPlayers, modalGridMax.homeMax, modalGridMax.awayMax);
	$: modalYou = modalPlayers.find((p) => p.you) ?? null;
	$: modalActual = pickActualScore(modalCommunity?.actual ?? null);
	$: modalMode = (modalActual ? 'post' : 'pre') as 'pre' | 'post';

	// ---- Small helpers -------------------------------------------------------
	const POSITION_LABELS = ['1st', '2nd', '3rd', '4th'];

	function pct(n: number, total: number): number {
		return (100 * n) / Math.max(1, total);
	}
	/** Hide in-segment counts in slivers (<15%) where they'd overflow. */
	function segLabel(n: number, total: number): string {
		return n > 0 && pct(n, total) >= 15 ? String(n) : '';
	}
	/** Bonus labels are "Nickname — long description"; split for display. */
	function bonusNick(label: string): string {
		return label.split('—')[0].trim();
	}
	function bonusDesc(label: string): string {
		const i = label.indexOf('—');
		return i >= 0 ? label.slice(i + 1).trim() : '';
	}

	function statusChip(row: OverviewFixtureRow): { label: string; cls: string } | null {
		if (row.actual_home === null || row.actual_away === null) return null;
		const live = row.status === 'live' || row.status === 'halftime';
		return {
			label: `${row.actual_home}–${row.actual_away}`,
			cls: live ? 'live' : 'ft'
		};
	}
</script>

<svelte:head>
	<title>Overview — Predictor</title>
</svelte:head>

<svelte:window
	on:mousedown={onWindowPress}
	on:keydown={onWindowKeydown}
	on:scroll|capture={onAnyScroll}
/>

{#if $isAuthenticated}
	<PnPageShell>
		<!-- ───────────────────────── Hero ───────────────────────── -->
		<section class="pn-ov-hero">
			<div class="lead">
				<nav class="pn-ovswitch" aria-label="Predictions view">
					<!-- ?view=picks marks an explicit choice — the wizard would
					     otherwise bounce straight back here once Phase 1 locks
					     and nothing is left to fill in. -->
					<a href="/predictions?view=picks">Your picks</a>
					<a href="/predictions/overview" class="on" aria-current="page">Overview</a>
				</nav>
				<p class="sub">
					{#if groupsData}
						How all <b>{groupsData.total_predictors}</b> players called it — picks are sealed
						until they lock, then the whole pool opens up.
					{:else}
						How the whole pool called it — picks are sealed until they lock.
					{/if}
				</p>
			</div>
			<div class="controls">
				{#if section === 'knockout' && $isPhase2Active}
					<!-- Advancement (forecast) vs Scores (match-score splits). Only
					     meaningful once Phase 2 is live, where knockout scores exist. -->
					<div class="pn-ovswitch slim" role="group" aria-label="Knockout view">
						<button
							class:on={knockoutView === 'advancement'}
							on:click={() => setKnockoutView('advancement')}>Advancement</button
						>
						<button
							class:on={knockoutView === 'scores'}
							on:click={() => setKnockoutView('scores')}>Scores</button
						>
					</div>
				{/if}
				{#if section === 'knockout' && $isPhase2Active && knockoutView === 'advancement'}
					<div class="pn-ovswitch slim" role="group" aria-label="Bracket phase">
						<button class:on={bracketPhase === 1} on:click={() => setBracketPhase(1)}>Phase I</button>
						<button class:on={bracketPhase === 2} on:click={() => setBracketPhase(2)}>Phase II</button>
					</div>
				{/if}
				<div class="pn-ovswitch" role="group" aria-label="Overview section">
					<!-- One-word label: three equal-width segments share the strip
					     and "Group stage" clips at mobile widths. -->
					<button class:on={section === 'groups'} on:click={() => setSection('groups')}>
						Groups
					</button>
					<button class:on={section === 'knockout'} on:click={() => setSection('knockout')}>
						Knockout
					</button>
					<button class:on={section === 'bonus'} on:click={() => setSection('bonus')}>
						Bonus
					</button>
				</div>
			</div>
		</section>

		{#if !$isPhase1Locked}
			<!-- ─────────────────── Blind-pool lock card ─────────────────── -->
			<section class="pn-ov-locked">
				<div class="lock-badge">SEALED</div>
				<h2>Everyone's picks stay hidden until Phase 1 locks</h2>
				<p>
					No peeking — the full pool of predictions opens up the moment the deadline passes
					{#if $phase1Countdown}(in <b>{$phase1Countdown}</b>){/if}. Until then, get your own picks in.
				</p>
				<a class="pn-btn" href="/predictions?view=picks">Back to your picks</a>
			</section>
		{:else if section === 'groups'}
			<!-- ─────────────────────── Group stage ─────────────────────── -->
			{#if groupsLoading}
				<p class="pn-ov-note">Loading the pool's picks…</p>
			{:else if groupsError}
				<p class="pn-ov-note error">{groupsError}</p>
			{:else if groupsData}
				<div class="pn-ov-legend">
					<span class="cap">Every fixture's pool split</span>
					<span class="key">
						<i class="sw home"></i> home win
						<i class="sw draw"></i> draw
						<i class="sw away"></i> away win
						<span class="dim">· tap a match for the score heatmap</span>
					</span>
				</div>
				<div class="pn-ov-groups">
					{#each groupsData.groups as g (g.group)}
						<div class="pn-ov-group">
							<div class="ghd">
								<span class="gletter">{g.group}</span>
								<span class="glabel">Group {g.group}</span>
							</div>
							<div class="thead">
								<span>Team</span>
								{#each POSITION_LABELS as p (p)}
									<span title="Players whose predicted table puts this team {p}">{p}</span>
								{/each}
								<span title="Players who carried this team into their Round of 32">Adv</span>
							</div>
							<div class="teams">
								{#each g.teams as t (t.team)}
									<div class="trow">
										<span class="tname">
											<PnFlag code={teamCode(t.team)} w={20} h={14} />
											<span class="nm">{displayTeamName(t.team)}</span>
										</span>
										{#each t.positions as cell, i (i)}
											{#if cell.count > 0}
												<button
													class="tnum pos pn-ov-cnt"
													class:lead={i === 0}
													on:click={(e) =>
														openPop(
															e,
															displayTeamName(t.team),
															`Predicted ${POSITION_LABELS[i]} · ${cell.count} of ${groupsData?.total_predictors}`,
															cell
														)}
												>{cell.count}</button>
											{:else}
												<span class="tnum pos zero">·</span>
											{/if}
										{/each}
										{#if t.advance.count > 0}
											<button
												class="tnum adv pn-ov-cnt"
												on:click={(e) =>
													openPop(
														e,
														displayTeamName(t.team),
														`In the R32 · ${t.advance.count} of ${groupsData?.total_predictors}`,
														t.advance
													)}
											>
												<b>{t.advance.count}</b>
												<span class="qbar">
													<span style="width:{pct(t.advance.count, groupsData.total_predictors)}%"></span>
												</span>
											</button>
										{:else}
											<span class="tnum adv zero">·</span>
										{/if}
									</div>
								{/each}
							</div>
							<div class="fixtures">
								{#each g.fixtures as fx (fx.fixture_id)}
									{@const chip = statusChip(fx)}
									{@const fxTotal = fx.home_count + fx.draw_count + fx.away_count}
									<button
										class="fx"
										on:click={() => openFixture(fx)}
										title="{fx.home_team} v {fx.away_team} — see everyone's scores"
									>
										<span class="fxteam">
											<PnFlag code={teamCode(fx.home_team)} w={20} h={14} />
											<span class="code">{teamCode(fx.home_team)}</span>
										</span>
										<span class="fxbar" class:empty={fxTotal === 0}>
											{#if fxTotal > 0}
												<span class="seg home" style="width:{pct(fx.home_count, fxTotal)}%"
													>{segLabel(fx.home_count, fxTotal)}</span
												>
												<span class="seg draw" style="width:{pct(fx.draw_count, fxTotal)}%"
													>{segLabel(fx.draw_count, fxTotal)}</span
												>
												<span class="seg away" style="width:{pct(fx.away_count, fxTotal)}%"
													>{segLabel(fx.away_count, fxTotal)}</span
												>
											{:else}
												<span class="none">no picks</span>
											{/if}
											{#if chip}
												<span class="result {chip.cls}">{chip.label}</span>
											{/if}
										</span>
										<span class="fxteam right">
											<span class="code">{teamCode(fx.away_team)}</span>
											<PnFlag code={teamCode(fx.away_team)} w={20} h={14} />
										</span>
									</button>
								{/each}
							</div>
						</div>
					{/each}
				</div>
			{/if}
		{:else if section === 'bonus'}
			<!-- ──────────────────────── Bonus questions ──────────────────────── -->
			{#if bonusLoading}
				<p class="pn-ov-note">Loading the pool's bonus picks…</p>
			{:else if bonusError}
				<p class="pn-ov-note error">{bonusError}</p>
			{:else if bonusData}
				<div class="pn-ov-legend">
					<span class="cap">
						Every bonus question's answer split across <b>{bonusData.total_predictors}</b> players
					</span>
					<span class="key dim">tap a row to see who picked it · ✓ marks a resolved answer</span>
				</div>
				<div class="pn-ov-bonus">
					{#each bonusData.questions as q (q.id)}
						<div class="pn-ov-bq">
							<div class="bqh">
								<span class="bqtitle">{bonusNick(q.label)}</span>
								<span class="bqpts">+{q.points}</span>
							</div>
							<div class="bqsub">{bonusDesc(q.label)}</div>
							<div class="bqrows">
								{#each q.answers as a (a.answer)}
									<button
										class="bqrow pn-ov-cnt"
										class:hit={a.is_correct === true}
										class:miss={a.is_correct === false}
										on:click={(e) =>
											openPop(
												e,
												a.answer,
												`${bonusNick(q.label)} · ${a.count} of ${bonusData?.total_predictors}`,
												{ count: a.count, users: a.users }
											)}
									>
										<span class="bqname">
											{#if q.input_type === 'team'}
												<PnFlag code={teamCode(a.answer)} w={16} h={11} />
											{/if}
											<span class="nm">{a.answer}</span>
											{#if a.is_correct === true}<i class="mk hit">✓</i>{:else if a.is_correct === false}<i class="mk miss">×</i>{/if}
										</span>
										<span class="bqbar">
											<span style="width:{pct(a.count, bonusData.total_predictors)}%"></span>
										</span>
										<span class="bqct">{a.count}</span>
									</button>
								{:else}
									<p class="pn-ov-note">No picks for this question.</p>
								{/each}
							</div>
							{#if q.correct_answers.length > 0}
								<div class="bqans">
									Answer: <b>{q.correct_answers.join(' / ')}</b>
								</div>
							{/if}
						</div>
					{/each}
				</div>
			{/if}
		{:else}
			<!-- ──────────────────────── Knockout ──────────────────────── -->
			{#if $isPhase2Active && knockoutView === 'scores'}
				<!-- Knockout match-score splits (Phase 2, per-match blind pool) -->
				{#if koScoresLoading}
					<p class="pn-ov-note">Loading the pool's knockout scores…</p>
				{:else if koScoresError}
					<p class="pn-ov-note error">{koScoresError}</p>
				{:else if koScoresData}
					<div class="pn-ov-legend">
						<span class="cap">
							Every knockout fixture's pool split — once a match locks, how all
							<b>{koScoresData.total_predictors}</b> players scored it
						</span>
						<span class="key">
							<i class="sw home"></i> home win
							<i class="sw draw"></i> draw
							<i class="sw away"></i> away win
							<span class="dim">· tap a match for the score heatmap</span>
						</span>
					</div>
					{#if koRounds.length === 0}
						<section class="pn-ov-locked">
							<div class="lock-badge">SEALED</div>
							<h2>No knockout matches have locked yet</h2>
							<p>
								Knockout scores stay hidden per match until 15 minutes before each kickoff.
								The pool's picks for a fixture open up the moment it locks — check back once
								the knockouts get under way.
							</p>
						</section>
					{:else}
						<div class="pn-ov-groups">
							{#each koRounds as r (r.stage)}
								<div class="pn-ov-group">
									<div class="ghd">
										<span class="gletter">{r.fixtures.length}</span>
										<span class="glabel">{r.label}</span>
									</div>
									<div class="fixtures bare">
										{#each r.fixtures as fx (fx.fixture_id)}
											{@const chip = statusChip(fx)}
											{@const fxTotal = fx.home_count + fx.draw_count + fx.away_count}
											<button
												class="fx"
												on:click={() => openFixture(fx)}
												title="{fx.home_team} v {fx.away_team} — see everyone's scores"
											>
												<span class="fxteam">
													<PnFlag code={teamCode(fx.home_team)} w={20} h={14} />
													<span class="code">{teamCode(fx.home_team)}</span>
												</span>
												<span class="fxbar" class:empty={fxTotal === 0}>
													{#if fxTotal > 0}
														<span class="seg home" style="width:{pct(fx.home_count, fxTotal)}%"
															>{segLabel(fx.home_count, fxTotal)}</span
														>
														<span class="seg draw" style="width:{pct(fx.draw_count, fxTotal)}%"
															>{segLabel(fx.draw_count, fxTotal)}</span
														>
														<span class="seg away" style="width:{pct(fx.away_count, fxTotal)}%"
															>{segLabel(fx.away_count, fxTotal)}</span
														>
													{:else}
														<span class="none">no picks</span>
													{/if}
													{#if chip}
														<span class="result {chip.cls}">{chip.label}</span>
													{/if}
												</span>
												<span class="fxteam right">
													<span class="code">{teamCode(fx.away_team)}</span>
													<PnFlag code={teamCode(fx.away_team)} w={20} h={14} />
												</span>
											</button>
										{/each}
									</div>
								</div>
							{/each}
						</div>
					{/if}
				{/if}
			{:else if bracketPhase === 2 && !phase2Viewable}
				<section class="pn-ov-locked">
					<div class="lock-badge">SEALED</div>
					<h2>Phase II picks stay hidden until the bracket locks</h2>
					<p>
						Everyone's updated brackets open up when the Phase 2 deadline passes
						{#if $phase2Countdown}(in <b>{$phase2Countdown}</b>){/if}.
					</p>
				</section>
			{:else if bracketLoading}
				<p class="pn-ov-note">Loading the pool's brackets…</p>
			{:else if bracketError}
				<p class="pn-ov-note error">{bracketError}</p>
			{:else if bracketData}
				<div class="pn-ov-legend">
					<span class="cap">
						The pool's forecast — players (of <b>{bracketData.total_predictors}</b>) backing each
						team per round
					</span>
					<span class="key">
						<i class="sw mine"></i> your call
						<span class="dim">· click a column to sort</span>
					</span>
				</div>
				<div class="pn-ov-tablewrap">
					<table class="pn-ov-table">
						<thead>
							<tr>
								<th class="rank">#</th>
								<th class="team">
									<button on:click={() => setSort('team')}
										>Team <span class="ar">{arrow('team', sortKey, sortDir)}</span></button
									>
								</th>
								{#each COLS as c (c.key)}
									<th class="num" class:sorted={sortKey === c.key} title={c.hint}>
										<button on:click={() => setSort(c.key)}
											>{c.label} <span class="ar">{arrow(c.key, sortKey, sortDir)}</span></button
										>
									</th>
								{/each}
							</tr>
						</thead>
						<tbody>
							{#each tableRows as t, i (t.team)}
								<tr>
									<td class="rank">{i + 1}</td>
									<td class="team">
										<span class="teamcell">
											<PnFlag code={teamCode(t.team)} w={22} h={15} />
											<span class="nm">{displayTeamName(t.team)}</span>
											{#if t.group}<span class="gchip">{t.group}</span>{/if}
										</span>
									</td>
									{#each COLS as c (c.key)}
										{@const cell = t[c.key]}
										{@const mine = youName !== null && cell.users.includes(youName)}
										<td class="num" class:sorted={sortKey === c.key}>
											{#if cell.count > 0}
												<button
													class="pn-ov-cnt"
													class:mine
													on:click={(e) =>
														openPop(
															e,
															displayTeamName(t.team),
															`${c.hint.replace('Picked to ', '')} · ${cell.count} of ${bracketData?.total_predictors}`,
															cell
														)}
												>
													<span class="v" class:champ={c.key === 'winner'}>{cell.count}</span>
													<span class="micro">
														<span style="width:{pct(cell.count, bracketData.total_predictors)}%"></span>
													</span>
												</button>
											{:else}
												<span class="v zero">·</span>
												<span class="micro"></span>
											{/if}
										</td>
									{/each}
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		{/if}

		<!-- ─────────────────── Scoreline heatmap modal ─────────────────── -->
		<!-- svelte-ignore a11y-click-events-have-key-events -->
		<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
		<dialog
			class="pn-ov-modal"
			bind:this={modalDialog}
			on:close={() => (modalRow = null)}
			on:click={onModalBackdropClick}
			aria-labelledby="pn-ov-modal-title"
		>
			{#if modalRow}
				<div class="pn-ov-modal-inner">
					<header class="mh">
						<div class="mh-teams" id="pn-ov-modal-title">
							<span class="side">
								<PnFlag code={teamCode(modalRow.home_team)} w={26} h={18} />
								{teamCode(modalRow.home_team)}
							</span>
							{#if modalActual}
								<span class="mid score">{modalActual.home_score}–{modalActual.away_score}</span>
							{:else}
								<span class="mid">v</span>
							{/if}
							<span class="side">
								{teamCode(modalRow.away_team)}
								<PnFlag code={teamCode(modalRow.away_team)} w={26} h={18} />
							</span>
						</div>
						<button class="close" type="button" on:click={closeModal} aria-label="Close">×</button>
					</header>
					<div class="mb">
						{#if modalLoading}
							<p class="pn-ov-note">Loading everyone's scores…</p>
						{:else if modalError}
							<p class="pn-ov-note error">{modalError}</p>
						{:else if modalCommunity}
							<PnScoreHeatmap
								mode={modalMode}
								homeCode={teamCode(modalRow.home_team)}
								awayCode={teamCode(modalRow.away_team)}
								actual={modalActual}
								cells={modalCells}
								homeMax={modalGridMax.homeMax}
								awayMax={modalGridMax.awayMax}
								youPlayer={modalYou}
								pointsExact={scoringConfig.exact_points}
								pointsOutcome={scoringConfig.outcome_points}
								rarityCap={scoringConfig.rarity_cap}
							/>
							<!-- Same W/D/L distribution + rarity underbraces as the
							     match detail page — one canonical component. -->
							<PnPointsBar
								mode={modalMode}
								homeCode={teamCode(modalRow.home_team)}
								awayCode={teamCode(modalRow.away_team)}
								actual={modalActual}
								players={modalPlayers}
								pointsExact={scoringConfig.exact_points}
								pointsOutcome={scoringConfig.outcome_points}
								rarityCap={scoringConfig.rarity_cap}
							/>
							<div class="mf">
								<a class="mf-link" href="/results/{modalRow.fixture_id}">Full match page →</a>
							</div>
						{/if}
					</div>
				</div>
			{/if}
		</dialog>

		<!-- ─────────────── Who-is-behind-a-count popover ─────────────── -->
		{#if pop}
			<div class="pn-ov-pop" style="left: {pop.left}px; top: {pop.top}px; width: {POP_W}px;">
				<div class="pp-h">
					<span class="pp-t">{pop.title}</span>
					<button class="pp-x" on:click={() => (pop = null)} aria-label="Close">×</button>
				</div>
				<div class="pp-sub">{pop.sub}</div>
				<ul>
					{#each pop.users as name (name)}
						<li class:you={name === ($user?.name ?? null)}>{name}</li>
					{/each}
				</ul>
			</div>
		{/if}
	</PnPageShell>
{/if}
