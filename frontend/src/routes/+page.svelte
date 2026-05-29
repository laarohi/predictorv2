<script lang="ts">
	/**
	 * Landing dashboard dispatcher.
	 *
	 * Handles the only two things that belong at this level:
	 *   1. Auth gate (redirect to /login if not signed in)
	 *   2. Dispatch to the correct Dashboard*.svelte based on $uxPhase
	 *
	 * Each dashboard wraps its own <PnPageShell> with phase-appropriate strip
	 * labels and chrome. Data fetching for each phase happens inside the
	 * dashboard component, so phases that don't need (say) leaderboard data
	 * don't fetch it.
	 *
	 * We use <svelte:component this={...}> rather than {#if}/{:else if} chain
	 * here. With the if-chain, every change in $uxPhase causes Svelte to
	 * re-evaluate each branch's condition. Under svelte-hmr's proxy layer,
	 * that pattern interacted badly with DashGroupStage (the largest moved
	 * component) and produced a recursive proxy-instantiation loop. The
	 * single <svelte:component> mount point avoids the issue and is also
	 * cleaner to read.
	 */
	import { isAuthenticated } from '$stores/auth';
	import { goto } from '$app/navigation';
	import { uxPhase } from '$stores/phase';
	import type { UxPhase } from '$types';

	import DashboardPre from '$components/panini/dashboard/DashboardPre.svelte';
	import DashGroupStage from '$components/panini/dashboard/DashGroupStage.svelte';
	import DashboardBetween from '$components/panini/dashboard/DashboardBetween.svelte';
	import DashboardKO from '$components/panini/dashboard/DashboardKO.svelte';
	import DashboardPost from '$components/panini/dashboard/DashboardPost.svelte';

	const DASHBOARDS: Record<UxPhase, ConstructorOfATypedSvelteComponent> = {
		pre_tournament: DashboardPre,
		group_stage: DashGroupStage,
		between_phases: DashboardBetween,
		knockout_stage: DashboardKO,
		post_competition: DashboardPost
	};

	$: ActiveDashboard = DASHBOARDS[$uxPhase];

	$: if (!$isAuthenticated) {
		goto('/login');
	}
</script>

{#if $isAuthenticated && ActiveDashboard}
	<svelte:component this={ActiveDashboard} />
{/if}
