<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { browser } from '$app/environment';
	import { goto } from '$app/navigation';
	import { isAuthenticated } from '$stores/auth';
	import { fetchAllFixtures, fixtures } from '$stores/fixtures';
	import { fetchMatchPredictions, predictionsByFixture } from '$stores/predictions';
	import { getAgreements, type FixtureAgreement } from '$api/predictions';
	import { getScoringConfig, type ScoringConfig } from '$api/competition';
	import {
		computeBreakdown,
		matchState,
		wizardHref,
		stageLabel,
		stageShort,
		type MatchState,
		type MatchBreakdown
	} from '$lib/utils/matchBreakdown';
	import { teamCode } from '$lib/utils/teamCodes';
	import PnPageShell from '$components/panini/PnPageShell.svelte';
	import PnFlag from '$components/panini/PnFlag.svelte';
	import PnResultsCard from '$components/panini/PnResultsCard.svelte';
	import PnResultsCardMobile from '$components/panini/PnResultsCardMobile.svelte';
	import type { Fixture } from '$types';

	$: if (!$isAuthenticated) {
		goto('/login');
	}

	let loading = true;
	let agreementsByFixture = new Map<string, FixtureAgreement>();
	let scoringConfig: ScoringConfig = {
		mode: 'logarithmic',
		outcome_points: 5,
		exact_points: 10,
		rarity_cap: 10
	};

	onMount(async () => {
		if (!$isAuthenticated) return;
		const [, , agreements, cfg] = await Promise.all([
			fetchAllFixtures(),
			fetchMatchPredictions(),
			getAgreements().catch(() => [] as FixtureAgreement[]),
			getScoringConfig().catch(() => scoringConfig)
		]);
		const m = new Map<string, FixtureAgreement>();
		for (const a of agreements) m.set(a.fixture_id, a);
		agreementsByFixture = m;
		scoringConfig = cfg;
		loading = false;
	});

	type SortMode = 'date' | 'group';
	type FilterMode = 'all' | MatchState;

	let sort: SortMode = 'date';
	let filter: FilterMode = 'all';

	$: filtered = $fixtures.filter((f) => {
		if (filter === 'all') return true;
		return matchState(f) === filter;
	});

	$: counts = (() => {
		const c = { all: $fixtures.length, finished: 0, live: 0, locked: 0, open: 0 };
		for (const f of $fixtures) c[matchState(f)]++;
		return c;
	})();

	// Precompute every fixture's MatchBreakdown ONCE per data change. Cards,
	// KPIs, and day/group tallies all read from this Map — they were
	// previously calling computeBreakdown() inline per render, which
	// recomputed identical work every time sort/filter/searchTerm flipped.
	// Dependencies: $fixtures, $predictionsByFixture, agreementsByFixture,
	// scoringConfig — anything else can change without rebuilding the map.
	$: breakdownsByFixture = (() => {
		const map = new Map<string, MatchBreakdown>();
		for (const f of $fixtures) {
			map.set(
				f.id,
				computeBreakdown(
					f,
					$predictionsByFixture.get(f.id),
					agreementsByFixture.get(f.id),
					scoringConfig
				)
			);
		}
		return map;
	})();

	$: kpis = (() => {
		let banked = 0;
		let exactHits = 0;
		let outcomeHits = 0;
		for (const f of $fixtures) {
			if (matchState(f) !== 'finished') continue;
			const bd = breakdownsByFixture.get(f.id);
			if (!bd) continue;
			banked += bd.totalPts;
			if (bd.outcomePill.state === 'hit-outcome') {
				if (bd.scorePill.state === 'hit-exact') exactHits++;
				else outcomeHits++;
			}
		}
		const upcomingPicked = $fixtures.filter((f) => {
			const s = matchState(f);
			return (s === 'open' || s === 'locked') && $predictionsByFixture.get(f.id);
		}).length;
		const upcomingTotal = counts.open + counts.locked;
		return {
			banked,
			exactHits,
			outcomeHits,
			playedTotal: counts.finished,
			liveTotal: counts.live,
			upcomingPicked,
			upcomingTotal,
			ahead: upcomingTotal // alias used in mobile hero
		};
	})();

	// ───────────────── Date buckets ─────────────────
	interface DayBucket {
		key: string;
		dow: string;
		dateLabel: string;
		isToday: boolean;
		items: Fixture[];
	}

	function dayKey(iso: string): string {
		const d = new Date(iso);
		return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
	}
	function dayDow(iso: string): string {
		return new Date(iso).toLocaleDateString('en-GB', { weekday: 'short' }).toUpperCase();
	}
	function dayDateLabel(iso: string): string {
		return new Date(iso)
			.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
			.toUpperCase();
	}
	function isSameDay(a: Date, b: Date): boolean {
		return (
			a.getFullYear() === b.getFullYear() &&
			a.getMonth() === b.getMonth() &&
			a.getDate() === b.getDate()
		);
	}

	$: dayBuckets = (() => {
		const today = new Date();
		const buckets = new Map<string, DayBucket>();
		for (const f of filtered) {
			const key = dayKey(f.kickoff);
			let b = buckets.get(key);
			if (!b) {
				b = {
					key,
					dow: dayDow(f.kickoff),
					dateLabel: dayDateLabel(f.kickoff),
					isToday: isSameDay(new Date(f.kickoff), today),
					items: []
				};
				buckets.set(key, b);
			}
			b.items.push(f);
		}
		const sorted = Array.from(buckets.values()).sort((a, b) => a.key.localeCompare(b.key));
		for (const b of sorted) {
			b.items.sort((x, y) => new Date(x.kickoff).getTime() - new Date(y.kickoff).getTime());
		}
		return sorted;
	})();

	// ───────────────── Group/Stage buckets ─────────────────
	interface GroupBucket {
		key: string;
		kind: 'group' | 'stage';
		letter: string;
		ttl: string;
		teams: string[];
		items: Fixture[];
	}

	const STAGE_ORDER: Record<string, number> = {
		round_of_32: 100,
		round_of_16: 101,
		quarter_final: 102,
		semi_final: 103,
		third_place: 104,
		final: 105
	};

	$: groupBuckets = (() => {
		const buckets = new Map<string, GroupBucket>();
		for (const f of filtered) {
			let key: string;
			let kind: 'group' | 'stage';
			let letter: string;
			let ttl: string;
			if (f.group) {
				key = f.group;
				kind = 'group';
				letter = f.group;
				ttl = `Group ${f.group}`;
			} else {
				key = f.stage || 'other';
				kind = 'stage';
				letter = stageShort(f.stage || '');
				ttl = stageLabel(f.stage || 'Other');
			}
			let b = buckets.get(key);
			if (!b) {
				b = { key, kind, letter, ttl, teams: [], items: [] };
				buckets.set(key, b);
			}
			b.items.push(f);
		}
		for (const b of buckets.values()) {
			if (b.kind !== 'group') continue;
			const seen = new Set<string>();
			for (const f of b.items) {
				if (f.home_team) seen.add(f.home_team);
				if (f.away_team) seen.add(f.away_team);
			}
			b.teams = Array.from(seen).sort();
		}
		return Array.from(buckets.values()).sort((a, b) => {
			const aw = a.kind === 'group' ? a.letter.charCodeAt(0) : STAGE_ORDER[a.key] ?? 999;
			const bw = b.kind === 'group' ? b.letter.charCodeAt(0) : STAGE_ORDER[b.key] ?? 999;
			return aw - bw;
		});
	})();

	// ───────────────── Helpers ─────────────────
	function fmtTime(iso: string): string {
		return new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
	}
	function ptsForDay(items: Fixture[]): { live: number; pts: number } {
		let live = 0;
		let pts = 0;
		for (const f of items) {
			const s = matchState(f);
			if (s === 'live') live++;
			if (s !== 'finished') continue;
			const bd = breakdownsByFixture.get(f.id);
			if (bd) pts += bd.totalPts;
		}
		return { live, pts };
	}
	function ptsForGroup(items: Fixture[]): { earned: number; potential: number } {
		let earned = 0;
		for (const f of items) {
			if (matchState(f) !== 'finished') continue;
			const bd = breakdownsByFixture.get(f.id);
			if (bd) earned += bd.totalPts;
		}
		const potential = items.length * (scoringConfig.outcome_points + scoringConfig.exact_points);
		return { earned, potential };
	}

	// Per-card pieces (shared by desktop + mobile). bdFor reads from the
	// precomputed map — falls back to a one-off compute only if the map
	// hasn't been populated yet (shouldn't happen in practice).
	function bdFor(f: Fixture): MatchBreakdown {
		return (
			breakdownsByFixture.get(f.id) ??
			computeBreakdown(
				f,
				$predictionsByFixture.get(f.id),
				agreementsByFixture.get(f.id),
				scoringConfig
			)
		);
	}
	function predFor(f: Fixture) {
		return $predictionsByFixture.get(f.id);
	}
	function dateMetaShort(iso: string): string {
		return new Date(iso)
			.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
			.toUpperCase();
	}

	// ───────────────── Auto-scroll to nearest matchday ─────────────────
	// On first render after data lands, scroll the page to the most relevant
	// day bucket — today if it has fixtures, otherwise the next future day,
	// otherwise the last past day. The day headers carry scroll-margin-top:
	// calc(var(--results-ribbon-h) + breathing-room), so the browser offsets
	// the scroll target below the sticky ribbon automatically.
	const desktopDayRefs: Record<string, HTMLElement> = {};
	const mobileDayRefs: Record<string, HTMLElement> = {};
	let stickyRibbonEl: HTMLElement | null = null;
	let mobileStickyRibbonEl: HTMLElement | null = null;
	let didAutoScroll = false;

	function updateRibbonHeight() {
		if (!browser) return;
		// One of the two ribbons is display:none at any given viewport — its
		// offsetHeight is 0. Math.max picks whichever is currently visible.
		const dh = stickyRibbonEl?.offsetHeight ?? 0;
		const mh = mobileStickyRibbonEl?.offsetHeight ?? 0;
		const h = Math.max(dh, mh);
		document.documentElement.style.setProperty('--results-ribbon-h', `${h}px`);
	}

	// Re-align the auto-scroll target if its position drifts shortly after
	// the initial scroll — match cards above it (flags lazily code-split via
	// utils/flagSvgs.ts swap a placeholder box for the real SVG a beat after
	// mount) can still be growing, which shifts the target's position in the
	// document without moving scrollTop, sliding it out from under the
	// sticky ribbon. Stops once it's held still for ~15 frames, or after a
	// ~3s budget in case something never truly settles.
	function watchAndRealign(el: HTMLElement): void {
		let lastTop = el.getBoundingClientRect().top;
		let stableFrames = 0;
		let totalFrames = 0;
		function check() {
			totalFrames++;
			const top = el.getBoundingClientRect().top;
			if (Math.abs(top - lastTop) > 0.5) {
				el.scrollIntoView({ block: 'start', behavior: 'auto' });
				lastTop = el.getBoundingClientRect().top;
				stableFrames = 0;
			} else {
				stableFrames++;
			}
			if (stableFrames < 15 && totalFrames < 180) {
				requestAnimationFrame(check);
			}
		}
		requestAnimationFrame(check);
	}

	onMount(() => {
		if (!browser) return;
		const ro = new ResizeObserver(updateRibbonHeight);
		// Defer observing until after the ribbons are bound (they live inside
		// `{#if $isAuthenticated}` so they aren't always in the tree).
		const id = setInterval(() => {
			if (stickyRibbonEl || mobileStickyRibbonEl) {
				if (stickyRibbonEl) ro.observe(stickyRibbonEl);
				if (mobileStickyRibbonEl) ro.observe(mobileStickyRibbonEl);
				updateRibbonHeight();
				clearInterval(id);
			}
		}, 50);
		const onResize = () => updateRibbonHeight();
		window.addEventListener('resize', onResize);
		return () => {
			clearInterval(id);
			ro.disconnect();
			window.removeEventListener('resize', onResize);
		};
	});

	$: nearestMatchDay = (() => {
		if (!dayBuckets.length) return null;
		const today = new Date();
		const todayK = dayKey(today.toISOString());
		const todays = dayBuckets.find((b) => b.key === todayK);
		if (todays) return todays;
		const future = dayBuckets.find((b) => b.key > todayK);
		if (future) return future;
		return dayBuckets[dayBuckets.length - 1];
	})();

	$: if (
		browser &&
		!loading &&
		!didAutoScroll &&
		sort === 'date' &&
		nearestMatchDay
	) {
		didAutoScroll = true;
		const key = nearestMatchDay.key;
		tick().then(() => {
			// Make sure the ribbon height is fresh BEFORE the browser
			// resolves the scroll-margin-top calc().
			updateRibbonHeight();
			// Calling scrollIntoView on the hidden one (display:none via the
			// .pn-rs-only / .pn-rm-only toggle) is a no-op, so calling both
			// is safe and avoids viewport-detection code.
			desktopDayRefs[key]?.scrollIntoView({ block: 'start', behavior: 'auto' });
			mobileDayRefs[key]?.scrollIntoView({ block: 'start', behavior: 'auto' });
			// Whichever one is actually visible — see watchAndRealign for why.
			const target = desktopDayRefs[key]?.offsetParent ? desktopDayRefs[key] : mobileDayRefs[key];
			if (target) watchAndRealign(target);
		});
	}
</script>

<svelte:head>
	<title>Results & Fixtures — Predictor</title>
</svelte:head>

{#if $isAuthenticated}
	<PnPageShell>
		<!-- ══════════════════ DESKTOP LAYOUT ══════════════════ -->
		<div class="pn-rs-only">
		<div class="pn-rs-sticky" bind:this={stickyRibbonEl}>
			<section class="pn-rs-hero">
				<div class="title">Results <em>&amp;</em> Fixtures</div>
				<div class="kpis">
					<span class="k">
						<b class="green">{kpis.banked}</b>
						<span class="l">pts</span>
					</span>
					<span class="sep">·</span>
					<span class="k">
						<b class="gold">{kpis.exactHits}·{kpis.outcomeHits}</b>
						<span class="l">ex·out</span>
					</span>
					<span class="sep">·</span>
					<span class="k">
						<b class="red">{kpis.liveTotal}</b>
						<span class="l">live</span>
					</span>
					<span class="sep">·</span>
					<span class="k">
						<b>{kpis.upcomingPicked}<span class="of">/{kpis.upcomingTotal}</span></b>
						<span class="l">picked</span>
					</span>
				</div>
			</section>

			<section class="pn-rs-tools">
				<div class="pn-rs-segtitle">SORT <b>BY</b></div>
				<div class="pn-rs-seg">
					<button class={sort === 'date' ? 'on' : ''} on:click={() => (sort = 'date')}>
						Date <span class="ch">{counts.all}</span>
					</button>
					<button class={sort === 'group' ? 'on' : ''} on:click={() => (sort = 'group')}>
						Group/Stage <span class="ch">A–F</span>
					</button>
				</div>
				<div class="pn-rs-chips">
					<button
						data-k="all"
						class={'pn-rs-chip' + (filter === 'all' ? ' on' : '')}
						on:click={() => (filter = 'all')}
					>
						All <span class="ct">{counts.all}</span>
					</button>
					<button
						data-k="played"
						class={'pn-rs-chip' + (filter === 'finished' ? ' on' : '')}
						on:click={() => (filter = 'finished')}
					>
						Played <span class="ct">{counts.finished}</span>
					</button>
					<button
						data-k="live"
						class={'pn-rs-chip' + (filter === 'live' ? ' on' : '')}
						on:click={() => (filter = 'live')}
					>
						Live <span class="ct">{counts.live}</span>
					</button>
					<button
						data-k="locked"
						class={'pn-rs-chip' + (filter === 'locked' ? ' on' : '')}
						on:click={() => (filter = 'locked')}
					>
						Locked <span class="ct">{counts.locked}</span>
					</button>
					<button
						data-k="open"
						class={'pn-rs-chip' + (filter === 'open' ? ' on' : '')}
						on:click={() => (filter = 'open')}
					>
						Open <span class="ct">{counts.open}</span>
					</button>
				</div>
			</section>
		</div>

			{#if loading}
				<p class="pn-rs-empty">Loading…</p>
			{:else if filtered.length === 0}
				<p class="pn-rs-empty">No matches for the current filter.</p>
			{:else if sort === 'date'}
				{#each dayBuckets as day (day.key)}
					{@const tally = ptsForDay(day.items)}
					<div>
						<div
							class="pn-rs-head"
							class:is-today={day.isToday}
							bind:this={desktopDayRefs[day.key]}
						>
							<div class="dow">
								{day.dow}
								<span class="dt">· {day.dateLabel}</span>
							</div>
							{#if day.isToday}
								<span class="today-tag">● Today</span>
							{:else}
								<div />
							{/if}
							<div class="ct">
								<b>{day.items.length}</b>
								{day.items.length === 1 ? 'match' : 'matches'}
								{#if tally.live > 0}
									· <span class="live"><b>{tally.live}</b> LIVE</span>
								{/if}
								{#if tally.pts > 0}
									· <span class="got">+<b>{tally.pts}</b> pts banked</span>
								{/if}
							</div>
						</div>
						<div class="pn-rs-grid">
							{#each day.items as f (f.id)}
								{#if matchState(f) === 'open'}
									<a class="pn-md-card-link" href={wizardHref(f)} title="Make your prediction →">
										<PnResultsCard
											fixture={f}
											prediction={predFor(f)}
											breakdown={bdFor(f)}
											config={scoringConfig}
											metaRight={(f.group ? 'GROUPS' : 'KO') + ' · ' + fmtTime(f.kickoff)}
										/>
									</a>
								{:else}
									<a class="pn-md-card-link" href={`/results/${f.id}`}>
										<PnResultsCard
											fixture={f}
											prediction={predFor(f)}
											breakdown={bdFor(f)}
											config={scoringConfig}
											metaRight={(f.group ? 'GROUPS' : 'KO') + ' · ' + fmtTime(f.kickoff)}
										/>
									</a>
								{/if}
							{/each}
						</div>
					</div>
				{/each}
			{:else}
				{#each groupBuckets as grp (grp.key)}
					{@const tally = ptsForGroup(grp.items)}
					<div class="pn-rs-group-panel">
						<div class="gh">
							<div class={'lt ' + (grp.kind === 'group' ? 'g-' + grp.letter : 'stage')}>
								{grp.letter}
							</div>
							<div class="meta">
								<div class="ttl">{grp.ttl}</div>
								{#if grp.kind === 'group' && grp.teams.length}
									<div class="teams">
										{#each grp.teams as t}
											<span class="t">
												<PnFlag code={teamCode(t)} w={18} h={12} />
												<b>{teamCode(t)}</b>
											</span>
										{/each}
									</div>
								{/if}
							</div>
							<div class="pts-tally">
								<div class="l">Points · this {grp.kind === 'group' ? 'group' : 'stage'}</div>
								<div class="v">
									+{tally.earned}<span class="of">/{tally.potential}</span>
								</div>
								<div class="l">
									{grp.items.filter((f) => matchState(f) === 'finished').length} played ·
									{grp.items.filter(
										(f) => matchState(f) !== 'finished' && matchState(f) !== 'live'
									).length} ahead
								</div>
							</div>
						</div>
						<div class="pn-rs-grid">
							{#each grp.items as f (f.id)}
								{#if matchState(f) === 'open'}
									<a class="pn-md-card-link" href={wizardHref(f)} title="Make your prediction →">
										<PnResultsCard
											fixture={f}
											prediction={predFor(f)}
											breakdown={bdFor(f)}
											config={scoringConfig}
											metaRight={dateMetaShort(f.kickoff)}
										/>
									</a>
								{:else}
									<a class="pn-md-card-link" href={`/results/${f.id}`}>
										<PnResultsCard
											fixture={f}
											prediction={predFor(f)}
											breakdown={bdFor(f)}
											config={scoringConfig}
											metaRight={dateMetaShort(f.kickoff)}
										/>
									</a>
								{/if}
							{/each}
						</div>
					</div>
				{/each}
			{/if}
		</div>

		<!-- ══════════════════ MOBILE LAYOUT ══════════════════ -->
		<div class="pn-rm-only pn-rm">
			<!-- Intro block (title + sub) — scrolls away on its own; the
			     KPI tiles + tools below stick to viewport top. -->
			<div class="pn-rm-hero pn-rm-intro">
				<div class="ttl">Results <em>&amp;</em> Fixtures</div>
				<div class="sub">Every score, every pick · <b>{counts.all}</b> matches</div>
			</div>
		<div class="pn-rm-sticky" bind:this={mobileStickyRibbonEl}>
			<div class="pn-rm-hero pn-rm-stats-block">
				<div class="stats">
					<div class="stat green">
						<div class="v">{kpis.banked}</div>
						<div class="l">Pts</div>
					</div>
					<div class="stat gold">
						<div class="v">{kpis.exactHits}</div>
						<div class="l">Exact</div>
					</div>
					<div class="stat red">
						<div class="v">{kpis.liveTotal}</div>
						<div class="l">Live</div>
					</div>
					<div class="stat">
						<div class="v">{kpis.ahead}</div>
						<div class="l">Ahead</div>
					</div>
				</div>
			</div>

			<div class="pn-rm-tools">
				<div class="pn-rm-seg">
					<button class={sort === 'date' ? 'on' : ''} on:click={() => (sort = 'date')}>
						Date
					</button>
					<button class={sort === 'group' ? 'on' : ''} on:click={() => (sort = 'group')}>
						Group/Stage
					</button>
				</div>
				<div class="pn-rm-chips">
					<button class={filter === 'all' ? 'on' : ''} on:click={() => (filter = 'all')}>
						All <span class="ct">{counts.all}</span>
					</button>
					<button
						class={filter === 'finished' ? 'on' : ''}
						on:click={() => (filter = 'finished')}
					>
						Played <span class="ct">{counts.finished}</span>
					</button>
					<button class={filter === 'live' ? 'on' : ''} on:click={() => (filter = 'live')}>
						Live <span class="ct">{counts.live}</span>
					</button>
					<button class={filter === 'locked' ? 'on' : ''} on:click={() => (filter = 'locked')}>
						Locked <span class="ct">{counts.locked}</span>
					</button>
					<button class={filter === 'open' ? 'on' : ''} on:click={() => (filter = 'open')}>
						Open <span class="ct">{counts.open}</span>
					</button>
				</div>
			</div>
		</div>

			<div class="pn-rm-body">
				{#if loading}
					<p class="pn-rs-empty">Loading…</p>
				{:else if filtered.length === 0}
					<p class="pn-rs-empty">No matches for the current filter.</p>
				{:else if sort === 'date'}
					{#each dayBuckets as day (day.key)}
						{@const tally = ptsForDay(day.items)}
						<div
							class="pn-rm-day"
							class:is-today={day.isToday}
							bind:this={mobileDayRefs[day.key]}
						>
							<div class="dow">
								{day.dow}
								<span class="dt">{day.dateLabel}</span>
							</div>
							{#if day.isToday}
								<span class="today-tag">● Today</span>
							{/if}
							<div class="ct">
								<b>{day.items.length}</b>
								{day.items.length === 1 ? 'match' : 'matches'}
								{#if tally.live > 0}· <span class="live"><b>{tally.live}</b> LIVE</span>{/if}
								{#if tally.pts > 0}· <span class="got">+<b>{tally.pts}</b></span>{/if}
							</div>
						</div>
						<div class="pn-rm-list">
							{#each day.items as f (f.id)}
								{#if matchState(f) === 'open'}
									<a class="pn-md-card-link" href={wizardHref(f)} title="Make your prediction →">
										<PnResultsCardMobile
											fixture={f}
											prediction={predFor(f)}
											breakdown={bdFor(f)}
											config={scoringConfig}
											metaRight={fmtTime(f.kickoff)}
										/>
									</a>
								{:else}
									<a class="pn-md-card-link" href={`/results/${f.id}`}>
										<PnResultsCardMobile
											fixture={f}
											prediction={predFor(f)}
											breakdown={bdFor(f)}
											config={scoringConfig}
											metaRight={fmtTime(f.kickoff)}
										/>
									</a>
								{/if}
							{/each}
						</div>
					{/each}
				{:else}
					{#each groupBuckets as grp (grp.key)}
						{@const tally = ptsForGroup(grp.items)}
						<div class="pn-rm-grp">
							<div class={'lt ' + (grp.kind === 'group' ? 'g-' + grp.letter : 'stage')}>
								{grp.letter}
							</div>
							<div class="info">
								<div class="ttl">{grp.ttl}</div>
								{#if grp.kind === 'group' && grp.teams.length}
									<div class="teams">
										{#each grp.teams as t, idx}
											{idx ? ' · ' : ''}<b>{teamCode(t)}</b>
										{/each}
									</div>
								{/if}
							</div>
							<div class="pts">
								+{tally.earned}
								<div class="of">{grp.items.length} matches</div>
							</div>
						</div>
						<div class="pn-rm-list">
							{#each grp.items as f (f.id)}
								{#if matchState(f) === 'open'}
									<a class="pn-md-card-link" href={wizardHref(f)} title="Make your prediction →">
										<PnResultsCardMobile
											fixture={f}
											prediction={predFor(f)}
											breakdown={bdFor(f)}
											config={scoringConfig}
											metaRight={dateMetaShort(f.kickoff)}
										/>
									</a>
								{:else}
									<a class="pn-md-card-link" href={`/results/${f.id}`}>
										<PnResultsCardMobile
											fixture={f}
											prediction={predFor(f)}
											breakdown={bdFor(f)}
											config={scoringConfig}
											metaRight={dateMetaShort(f.kickoff)}
										/>
									</a>
								{/if}
							{/each}
						</div>
					{/each}
				{/if}
			</div>
		</div>
	</PnPageShell>
{/if}

<style>
	/* Desktop/mobile layout toggle — inlined here (rather than in the
	 * external panini-results.css) so the rule ships with the SSR'd HTML
	 * and there's no first-paint flash in Vite dev mode where the
	 * external stylesheet otherwise loads slightly after the markup. */
	:global(.pn .pn-rs-only) {
		display: none;
	}
	:global(.pn .pn-rm-only) {
		display: block;
	}
	@media (min-width: 700px) {
		:global(.pn .pn-rs-only) {
			display: block;
		}
		:global(.pn .pn-rm-only) {
			display: none;
		}
	}
</style>
