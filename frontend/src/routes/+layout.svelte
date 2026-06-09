<script lang="ts">
	import '../app.css';
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { isAuthenticated, initAuth } from '$stores/auth';
	import { fetchPhaseStatus, startPhaseStatusRefresh, uxPhaseOverride } from '$stores/phase';
	import type { ComponentType } from 'svelte';
	import type { UxPhase } from '$types';

	let hasLoadedPhase = false;

	// Dev phase pill — lazy-loaded in dev only (see onMount). Typed as a Svelte
	// ComponentType (no `any`); null until its chunk arrives in dev, always null
	// in prod where the loader below is compiled away entirely.
	let DevPhasePill: ComponentType | null = null;

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
		// Long-lived tabs: keep lock/phase state honest across the deadline.
		const stopPhaseRefresh = startPhaseStatusRefresh();
		if (import.meta.env.DEV) {
			const param = $page.url.searchParams.get('uxPhase');
			if (param && VALID_UX_PHASES.has(param as UxPhase)) {
				uxPhaseOverride.set(param as UxPhase);
			}
			// Load the dev phase pill in dev ONLY. The dynamic import lives inside
			// this import.meta.env.DEV guard, so a production build folds the guard
			// to `false`, dead-code-eliminates the whole branch (the import() call
			// included), and never emits the pill's chunk — zero JS/CSS in prod. A
			// static top-level import can't achieve this: Rollup keeps it because
			// the component injects CSS (a module side effect tree-shaking won't drop).
			import('$components/panini/PnDevPhasePill.svelte').then((m) => {
				DevPhasePill = m.default;
			});
		}
		return stopPhaseRefresh;
	});

	$: if ($isAuthenticated && !hasLoadedPhase) {
		hasLoadedPhase = true;
		fetchPhaseStatus();
	}
</script>

{#if import.meta.env.DEV && DevPhasePill && $isAuthenticated}
	<svelte:component this={DevPhasePill} />
{/if}

<slot />
