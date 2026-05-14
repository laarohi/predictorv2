<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { isAuthenticated } from '$stores/auth';
	import { fetchAllFixtures, finishedFixtures } from '$stores/fixtures';
	import { fetchMatchPredictions, predictionsByFixture } from '$stores/predictions';
	import { getPredictionResult, type PredictionResult } from '$lib/utils/predictionResult';
	import { teamCode } from '$lib/utils/teamCodes';
	import PnPageShell from '$components/panini/PnPageShell.svelte';
	import PnFlag from '$components/panini/PnFlag.svelte';
	import type { Fixture } from '$types';

	$: if (!$isAuthenticated) {
		goto('/login');
	}

	let loading = true;

	onMount(async () => {
		if ($isAuthenticated) {
			await Promise.all([fetchAllFixtures(), fetchMatchPredictions()]);
			loading = false;
		}
	});

	let groupFilter = 'all';
	let resultFilter: 'all' | PredictionResult = 'all';

	$: sorted = [...$finishedFixtures].sort(
		(a, b) => new Date(b.kickoff).getTime() - new Date(a.kickoff).getTime()
	);

	$: availableGroups = (() => {
		const groups = new Set<string>();
		for (const f of $finishedFixtures) {
			if (f.group) groups.add(f.group);
			else groups.add('knockout');
		}
		return Array.from(groups).sort();
	})();

	$: filtered = sorted.filter((f) => {
		if (groupFilter !== 'all') {
			if (groupFilter === 'knockout') {
				if (f.group) return false;
			} else if (f.group !== groupFilter) return false;
		}
		if (resultFilter !== 'all') {
			const pred = $predictionsByFixture.get(f.id);
			if (getPredictionResult(f, pred) !== resultFilter) return false;
		}
		return true;
	});

	$: stats = (() => {
		let exact = 0, outcome = 0, wrong = 0, pending = 0;
		for (const f of $finishedFixtures) {
			const pred = $predictionsByFixture.get(f.id);
			const result = getPredictionResult(f, pred);
			if (result === 'exact') exact++;
			else if (result === 'outcome') outcome++;
			else if (result === 'wrong') wrong++;
			else pending++;
		}
		return { exact, outcome, wrong, pending };
	})();

	interface DayGroup {
		date: string;
		matches: Fixture[];
		exact: number;
		outcome: number;
		wrong: number;
	}
	$: groupedByDate = (() => {
		const groups: DayGroup[] = [];
		let current: DayGroup | null = null;
		for (const f of filtered) {
			const date = new Date(f.kickoff).toLocaleDateString('en-GB', {
				weekday: 'short',
				day: 'numeric',
				month: 'short'
			});
			if (!current || current.date !== date) {
				current = { date, matches: [], exact: 0, outcome: 0, wrong: 0 };
				groups.push(current);
			}
			current.matches.push(f);
			const pred = $predictionsByFixture.get(f.id);
			const result = getPredictionResult(f, pred);
			if (result === 'exact') current.exact++;
			else if (result === 'outcome') current.outcome++;
			else if (result === 'wrong') current.wrong++;
		}
		return groups;
	})();

	function fmtTime(iso: string): string {
		return new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
	}

	function resultLabel(r: PredictionResult): string {
		if (r === 'exact') return 'Exact';
		if (r === 'outcome') return 'Outcome';
		if (r === 'wrong') return 'Missed';
		return 'No pick';
	}
</script>

<svelte:head>
	<title>Results — Predictor</title>
</svelte:head>

{#if $isAuthenticated}
	<PnPageShell>
		<div class="pn-res-h">
			<div class="ttl">THE <em>RESULTS</em></div>
			<div class="meta">
				{$finishedFixtures.length} finished<br />
				{stats.exact + stats.outcome + stats.wrong} scored
			</div>
		</div>

		<!-- Stats -->
		<div class="pn-res-stats">
			<div class="pn-res-stat">
				<div class="l">Exact scores</div>
				<div class="v exact">{stats.exact}</div>
			</div>
			<div class="pn-res-stat">
				<div class="l">Outcomes</div>
				<div class="v outcome">{stats.outcome}</div>
			</div>
			<div class="pn-res-stat">
				<div class="l">Missed</div>
				<div class="v wrong">{stats.wrong}</div>
			</div>
			<div class="pn-res-stat">
				<div class="l">No pick</div>
				<div class="v pending">{stats.pending}</div>
			</div>
		</div>

		<!-- Filters -->
		<div class="pn-res-filters">
			<span class="l">Group</span>
			<button class="pn-res-filter" class:on={groupFilter === 'all'} on:click={() => (groupFilter = 'all')}>All</button>
			{#each availableGroups as g}
				<button class="pn-res-filter" class:on={groupFilter === g} on:click={() => (groupFilter = g)}>
					{g === 'knockout' ? 'Knockout' : `Group ${g}`}
				</button>
			{/each}
			<span class="l" style="margin-left: 16px;">Result</span>
			<button class="pn-res-filter" class:on={resultFilter === 'all'} on:click={() => (resultFilter = 'all')}>All</button>
			<button class="pn-res-filter" class:on={resultFilter === 'exact'} on:click={() => (resultFilter = 'exact')}>Exact</button>
			<button class="pn-res-filter" class:on={resultFilter === 'outcome'} on:click={() => (resultFilter = 'outcome')}>Outcome</button>
			<button class="pn-res-filter" class:on={resultFilter === 'wrong'} on:click={() => (resultFilter = 'wrong')}>Missed</button>
		</div>

		<!-- Day groups -->
		{#if loading}
			<p style="font-family: var(--mono); font-size: 11px; color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.08em;">Loading…</p>
		{:else if groupedByDate.length === 0}
			<p style="font-family: var(--mono); font-size: 11px; color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.08em; padding: 24px; text-align: center;">
				No finished matches yet
			</p>
		{:else}
			{#each groupedByDate as day (day.date)}
				<section class="pn-res-day">
					<div class="day-h">
						<span class="date">{day.date}</span>
						<span class="summary">
							{#if day.exact}<span class="exact">{day.exact} exact</span> · {/if}
							{#if day.outcome}<span class="outcome">{day.outcome} outcome</span> · {/if}
							{#if day.wrong}<span class="wrong">{day.wrong} missed</span>{/if}
						</span>
					</div>
					<div class="pn-res-grid">
						{#each day.matches as f (f.id)}
							{@const pred = $predictionsByFixture.get(f.id)}
							{@const result = getPredictionResult(f, pred)}
							<div class="pn-res-card" class:exact={result === 'exact'} class:outcome={result === 'outcome'} class:wrong={result === 'wrong'}>
								<span class="badge {result}">{resultLabel(result)}</span>
								<div class="meta">
									<span><b>{teamCode(f.home_team)} vs {teamCode(f.away_team)}</b></span>
									<span>{fmtTime(f.kickoff)} · {f.group ? `Group ${f.group}` : f.stage}</span>
								</div>
								<div class="body">
									<div class="team">
										<PnFlag code={teamCode(f.home_team)} w={28} h={20} />
										<span class="nm">{f.home_team}</span>
									</div>
									<div class="scores">
										<div class="actual">
											{#if f.score}{f.score.home_score}–{f.score.away_score}{:else}—{/if}
										</div>
										<div class="your-pick">
											{#if pred}
												YOUR PICK · <b>{pred.home_score}–{pred.away_score}</b>
											{:else}
												NO PICK SUBMITTED
											{/if}
										</div>
									</div>
									<div class="team r">
										<PnFlag code={teamCode(f.away_team)} w={28} h={20} />
										<span class="nm">{f.away_team}</span>
									</div>
								</div>
							</div>
						{/each}
					</div>
				</section>
			{/each}
		{/if}
	</PnPageShell>
{/if}
