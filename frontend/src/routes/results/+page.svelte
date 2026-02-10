<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { isAuthenticated } from '$stores/auth';
	import { fetchAllFixtures, finishedFixtures } from '$stores/fixtures';
	import { fetchMatchPredictions, predictionsByFixture } from '$stores/predictions';
	import { getPredictionResult, type PredictionResult } from '$lib/utils/predictionResult';
	import ResultCard from '$lib/components/ResultCard.svelte';
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

	// Filters
	let groupFilter = 'all';
	let resultFilter: 'all' | PredictionResult = 'all';

	// Derive sorted finished fixtures (newest first)
	$: sorted = [...$finishedFixtures].sort(
		(a, b) => new Date(b.kickoff).getTime() - new Date(a.kickoff).getTime()
	);

	// Collect available groups for filter
	$: availableGroups = (() => {
		const groups = new Set<string>();
		for (const f of $finishedFixtures) {
			if (f.group) groups.add(f.group);
			else groups.add('knockout');
		}
		return Array.from(groups).sort();
	})();

	// Apply filters
	$: filtered = sorted.filter((f) => {
		// Group filter
		if (groupFilter !== 'all') {
			if (groupFilter === 'knockout') {
				if (f.group) return false;
			} else {
				if (f.group !== groupFilter) return false;
			}
		}

		// Result filter
		if (resultFilter !== 'all') {
			const pred = $predictionsByFixture.get(f.id);
			const result = getPredictionResult(f, pred);
			if (result !== resultFilter) return false;
		}

		return true;
	});

	// Stats
	$: stats = (() => {
		let exact = 0;
		let outcome = 0;
		let wrong = 0;
		let pending = 0;
		for (const f of $finishedFixtures) {
			const pred = $predictionsByFixture.get(f.id);
			const result = getPredictionResult(f, pred);
			if (result === 'exact') exact++;
			else if (result === 'outcome') outcome++;
			else if (result === 'wrong') wrong++;
			else pending++;
		}
		return { exact, outcome, wrong, pending, total: $finishedFixtures.length };
	})();
</script>

<svelte:head>
	<title>Results - Predictor v2</title>
</svelte:head>

{#if $isAuthenticated}
	<div class="container mx-auto mobile-padding py-6">
		<!-- Header -->
		<div class="mb-6">
			<h1 class="text-3xl sm:text-4xl font-display tracking-wide">Results</h1>
			<p class="text-sm text-base-content/50 mt-1">
				{stats.total} finished matches — tap any match to see everyone's predictions
			</p>
		</div>

		{#if loading}
			<div class="flex justify-center py-16">
				<span class="loading loading-spinner loading-lg text-primary"></span>
			</div>
		{:else if $finishedFixtures.length === 0}
			<div class="stadium-card no-glow p-8 text-center">
				<svg class="w-16 h-16 mx-auto mb-4 text-base-content/20" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
					<path stroke-linecap="round" stroke-linejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
				</svg>
				<p class="text-base-content/50">No finished matches yet.</p>
				<p class="text-base-content/30 text-sm mt-1">Results will appear here as matches are completed.</p>
			</div>
		{:else}
			<!-- Stats summary -->
			<div class="grid grid-cols-4 gap-2 sm:gap-3 mb-6">
				<div class="stat-card !p-3">
					<div class="stat-title text-[10px]">Exact</div>
					<div class="stat-value !text-2xl text-success">{stats.exact}</div>
				</div>
				<div class="stat-card !p-3">
					<div class="stat-title text-[10px]">Correct</div>
					<div class="stat-value !text-2xl text-warning">{stats.outcome}</div>
				</div>
				<div class="stat-card !p-3">
					<div class="stat-title text-[10px]">Wrong</div>
					<div class="stat-value !text-2xl text-error/70">{stats.wrong}</div>
				</div>
				<div class="stat-card !p-3">
					<div class="stat-title text-[10px]">No Pred</div>
					<div class="stat-value !text-2xl text-base-content/40">{stats.pending}</div>
				</div>
			</div>

			<!-- Filters -->
			<div class="flex flex-wrap gap-2 mb-6">
				<!-- Group filter -->
				<select
					class="select select-sm bg-base-200 border-base-300/50 text-sm"
					bind:value={groupFilter}
				>
					<option value="all">All Stages</option>
					{#each availableGroups as g}
						<option value={g}>{g === 'knockout' ? 'Knockout' : `Group ${g}`}</option>
					{/each}
				</select>

				<!-- Result filter -->
				<div class="flex gap-1 p-0.5 bg-base-300/30 rounded-lg">
					<button
						class="px-3 py-1 rounded-md text-xs font-medium transition-all {resultFilter === 'all'
							? 'bg-primary text-primary-content'
							: 'hover:bg-base-300/50 text-base-content/70'}"
						on:click={() => (resultFilter = 'all')}
					>
						All
					</button>
					<button
						class="px-3 py-1 rounded-md text-xs font-medium transition-all {resultFilter === 'exact'
							? 'bg-success text-success-content'
							: 'hover:bg-base-300/50 text-base-content/70'}"
						on:click={() => (resultFilter = 'exact')}
					>
						Exact
					</button>
					<button
						class="px-3 py-1 rounded-md text-xs font-medium transition-all {resultFilter === 'outcome'
							? 'bg-warning text-warning-content'
							: 'hover:bg-base-300/50 text-base-content/70'}"
						on:click={() => (resultFilter = 'outcome')}
					>
						Correct
					</button>
					<button
						class="px-3 py-1 rounded-md text-xs font-medium transition-all {resultFilter === 'wrong'
							? 'bg-error text-error-content'
							: 'hover:bg-base-300/50 text-base-content/70'}"
						on:click={() => (resultFilter = 'wrong')}
					>
						Wrong
					</button>
				</div>
			</div>

			<!-- Results list -->
			{#if filtered.length === 0}
				<div class="text-center py-8 text-base-content/40 text-sm">
					No matches match your filters.
				</div>
			{:else}
				<div class="space-y-2">
					{#each filtered as fixture (fixture.id)}
						<ResultCard
							{fixture}
							prediction={$predictionsByFixture.get(fixture.id)}
						/>
					{/each}
				</div>
			{/if}
		{/if}
	</div>
{/if}
