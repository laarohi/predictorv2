<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { isAuthenticated } from '$stores/auth';
	import {
		fetchMatchPredictions,
		fetchBracketPredictions,
		matchPredictions,
		unsavedChanges,
		hasUnsavedChanges,
		saveAllPredictions,
		matchPredictionsLoading
	} from '$stores/predictions';
	import { fetchGroupFixtures, groupFixtures } from '$stores/fixtures';
	import MatchCard from '$components/MatchCard.svelte';
	import SaveButton from '$components/SaveButton.svelte';

	$: if (!$isAuthenticated) {
		goto('/login');
	}

	let activeTab: 'groups' | 'bracket' = 'groups';
	let saveStatus: 'idle' | 'saving' | 'saved' | 'error' = 'idle';

	onMount(async () => {
		if ($isAuthenticated) {
			await Promise.all([fetchMatchPredictions(), fetchGroupFixtures()]);
		}
	});

	async function handleSaveAll() {
		saveStatus = 'saving';
		const success = await saveAllPredictions();
		saveStatus = success ? 'saved' : 'error';

		if (success) {
			setTimeout(() => {
				saveStatus = 'idle';
			}, 2000);
		}
	}

	// Create a map of predictions by fixture ID
	$: predictionMap = new Map($matchPredictions.map((p) => [p.fixture_id, p]));
</script>

<svelte:head>
	<title>Predictions - Predictor v2</title>
</svelte:head>

{#if $isAuthenticated}
	<div class="container mx-auto mobile-padding py-6">
		<!-- Header with tabs -->
		<div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
			<h1 class="text-2xl font-bold">My Predictions</h1>

			<div class="tabs tabs-boxed bg-base-200">
				<button
					class="tab"
					class:tab-active={activeTab === 'groups'}
					on:click={() => (activeTab = 'groups')}
				>
					Groups
				</button>
				<button
					class="tab"
					class:tab-active={activeTab === 'bracket'}
					on:click={() => (activeTab = 'bracket')}
				>
					Bracket
				</button>
			</div>
		</div>

		<!-- Floating save button -->
		{#if $hasUnsavedChanges}
			<div class="fixed bottom-20 sm:bottom-6 right-6 z-40">
				<SaveButton
					status={saveStatus}
					count={$unsavedChanges.size}
					on:save={handleSaveAll}
				/>
			</div>
		{/if}

		<!-- Groups Tab -->
		{#if activeTab === 'groups'}
			{#if $matchPredictionsLoading && $groupFixtures.length === 0}
				<div class="flex justify-center py-12">
					<span class="loading loading-spinner loading-lg text-primary"></span>
				</div>
			{:else if $groupFixtures.length === 0}
				<div class="text-center py-12 text-base-content/50">
					<p>No group stage fixtures available yet.</p>
				</div>
			{:else}
				<div class="space-y-8">
					{#each $groupFixtures as group}
						<div class="card bg-base-200">
							<div class="card-body">
								<h2 class="card-title text-lg">Group {group.group}</h2>
								<div class="grid gap-4 md:grid-cols-2">
									{#each group.fixtures as fixture}
										<MatchCard
											{fixture}
											prediction={predictionMap.get(fixture.id)}
										/>
									{/each}
								</div>
							</div>
						</div>
					{/each}
				</div>
			{/if}
		{/if}

		<!-- Bracket Tab -->
		{#if activeTab === 'bracket'}
			<div class="card bg-base-200">
				<div class="card-body text-center py-12">
					<h2 class="text-xl font-bold mb-2">Knockout Bracket</h2>
					<p class="text-base-content/50">
						The knockout bracket will be available after the group stage ends.
					</p>
				</div>
			</div>
		{/if}
	</div>
{/if}
