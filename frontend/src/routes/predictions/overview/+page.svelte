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
		getGroupsOverview
	} from '$api/predictions';
	import { getLeaderboard, type PhaseFilter } from '$api/leaderboard';
	import { getScoringConfig, type ScoringConfig } from '$api/competition';
	import { buildCells, pickActualScore, toGridPlayer, type GridPlayer } from '$lib/utils/matchDetail';
	import { teamCode } from '$lib/utils/teamCodes';
	import { displayTeamName } from '$lib/utils/teamName';
	import PnPageShell from '$components/panini/PnPageShell.svelte';
	import PnFlag from '$components/panini/PnFlag.svelte';
	import PnScoreHeatmap from '$components/panini/PnScoreHeatmap.svelte';
	import type {
		BracketOverviewResponse,
		BracketOverviewTeamRow,
		CommunityPredictionsResponse,
		GroupsOverviewResponse,
		LeaderboardEntry,
		LeaderboardResponse,
		OverviewFixtureRow
	} from '$types';

	$: if (browser && !$isAuthenticated) goto('/login');

	// ---- Section state (groups | knockout), shareable via ?tab= ------------
	type Section = 'groups' | 'knockout';
	let section: Section = 'groups';
	let sectionInitialised = false;
	$: if (browser && !sectionInitialised && $page.url) {
		section = $page.url.searchParams.get('tab') === 'knockout' ? 'knockout' : 'groups';
		sectionInitialised = true;
	}

	function setSection(s: Section) {
		section = s;
		if (browser) {
			const url = new URL(window.location.href);
			if (s === 'knockout') url.searchParams.set('tab', s);
			else url.searchParams.delete('tab');
			history.replaceState(history.state, '', url);
		}
		if (s === 'knockout') void loadBracket();
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

	onMount(() => {
		if (!$isAuthenticated) return;
		void loadGroups();
		if (section === 'knockout') void loadBracket();
	});
	// Re-attempt once the phase status arrives (stores hydrate async); the
	// in-flight/already-loaded guards inside the loaders make these cheap.
	$: if (browser && $isPhase1Locked) void loadGroups();
	$: if (browser && $isPhase1Locked && section === 'knockout') void loadBracket();

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
			b.winner - a.winner ||
			b.final - a.final ||
			b.semi_final - a.semi_final ||
			b.quarter_final - a.quarter_final ||
			b.round_of_16 - a.round_of_16 ||
			b.round_of_32 - a.round_of_32 ||
			a.team.localeCompare(b.team)
		);
	}
	$: tableRows = bracketData
		? [...bracketData.teams].sort((a, b) => {
				if (sortKey === 'team') return sortDir * a.team.localeCompare(b.team);
				const d = (a[sortKey] as number) - (b[sortKey] as number);
				return d !== 0 ? sortDir * d : cmpDefault(a, b);
			})
		: [];

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
	$: modalCells = buildCells(modalPlayers);
	$: modalYou = modalPlayers.find((p) => p.you) ?? null;
	$: modalActual = pickActualScore(modalCommunity?.actual ?? null);
	$: modalMode = (modalActual ? 'post' : 'pre') as 'pre' | 'post';

	// ---- Small helpers -------------------------------------------------------
	function pct(n: number, total: number): number {
		return (100 * n) / Math.max(1, total);
	}
	/** Hide in-segment counts in slivers (<15%) where they'd overflow. */
	function segLabel(n: number, total: number): string {
		return n > 0 && pct(n, total) >= 15 ? String(n) : '';
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

{#if $isAuthenticated}
	<PnPageShell>
		<!-- ───────────────────────── Hero ───────────────────────── -->
		<section class="pn-ov-hero">
			<div class="lead">
				<nav class="pn-ovswitch" aria-label="Predictions view">
					<a href="/predictions">Your picks</a>
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
					<div class="pn-ovswitch slim" role="group" aria-label="Bracket phase">
						<button class:on={bracketPhase === 1} on:click={() => setBracketPhase(1)}>Phase I</button>
						<button class:on={bracketPhase === 2} on:click={() => setBracketPhase(2)}>Phase II</button>
					</div>
				{/if}
				<div class="pn-ovswitch" role="group" aria-label="Overview section">
					<button class:on={section === 'groups'} on:click={() => setSection('groups')}>
						Group stage
					</button>
					<button class:on={section === 'knockout'} on:click={() => setSection('knockout')}>
						Knockout
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
				<a class="pn-btn" href="/predictions">Back to your picks</a>
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
								<span title="Players whose predicted table puts this team 1st">1st</span>
								<span title="Players who carried this team into their Round of 32">Adv</span>
							</div>
							<div class="teams">
								{#each g.teams as t (t.team)}
									<div class="trow">
										<span class="tname">
											<PnFlag code={teamCode(t.team)} w={20} h={14} />
											<span class="nm">{displayTeamName(t.team)}</span>
										</span>
										<span class="tnum first">{t.first_count > 0 ? t.first_count : '·'}</span>
										<span class="tnum">
											<b>{t.advance_count > 0 ? t.advance_count : '·'}</b>
											<span class="qbar">
												<span style="width:{pct(t.advance_count, groupsData.total_predictors)}%"></span>
											</span>
										</span>
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
		{:else}
			<!-- ──────────────────────── Knockout ──────────────────────── -->
			{#if bracketPhase === 2 && !phase2Viewable}
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
					<span class="key dim">click a column to sort</span>
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
										{@const v = t[c.key]}
										<td class="num" class:sorted={sortKey === c.key}>
											<span class="v" class:zero={v === 0} class:champ={c.key === 'winner' && v > 0}>
												{v > 0 ? v : '·'}
											</span>
											<span class="micro">
												<span style="width:{pct(v, bracketData.total_predictors)}%"></span>
											</span>
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
								youPlayer={modalYou}
								pointsExact={scoringConfig.exact_points}
								pointsOutcome={scoringConfig.outcome_points}
							/>
							<div class="mf">
								<span class="mf-key">
									{#if modalMode === 'pre'}
										<i class="sw home"></i> {teamCode(modalRow.home_team)} win
										<i class="sw draw"></i> draw
										<i class="sw away"></i> {teamCode(modalRow.away_team)} win
									{:else}
										<i class="sw exact"></i> exact
										<i class="sw outcome"></i> outcome
										<i class="sw miss"></i> no pts
									{/if}
								</span>
								<a class="mf-link" href="/results/{modalRow.fixture_id}">Full match page →</a>
							</div>
						{/if}
					</div>
				</div>
			{/if}
		</dialog>
	</PnPageShell>
{/if}
