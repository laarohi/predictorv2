<script lang="ts">
	import '../app.css';
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { isAuthenticated, initAuth } from '$stores/auth';
	import { fetchPhaseStatus, uxPhaseOverride } from '$stores/phase';
	import PnDevPhasePill from '$components/panini/PnDevPhasePill.svelte';
	import type { UxPhase } from '$types';

	let hasLoadedPhase = false;

	// Dev-only: seed uxPhaseOverride from ?uxPhase=... once on mount so each
	// phase's dashboard can be visually QA'd without mutating backend data.
	// The PnDevPhasePill component (below) lets you cycle phases interactively
	// after the initial load. Production builds never read the param.
	const VALID_UX_PHASES = new Set<UxPhase>([
		'pre_tournament',
		'group_stage',
		'between_phases',
		'knockout_stage',
		'post_competition'
	]);

	onMount(() => {
		// Remove the cold-load splash (app.html) now that the app has mounted.
		document.getElementById('app-splash')?.remove();
		initAuth();
		if (import.meta.env.DEV) {
			const param = $page.url.searchParams.get('uxPhase');
			if (param && VALID_UX_PHASES.has(param as UxPhase)) {
				uxPhaseOverride.set(param as UxPhase);
			}
		}
	});

	$: if ($isAuthenticated && !hasLoadedPhase) {
		hasLoadedPhase = true;
		fetchPhaseStatus();
	}
</script>

{#if import.meta.env.DEV && $isAuthenticated}
	<PnDevPhasePill />
{/if}

<slot />
