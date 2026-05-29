<script lang="ts">
	/**
	 * Floating dev-only pill for cycling through the 5 UX phases without
	 * mutating real backend data. Visible only when import.meta.env.DEV.
	 *
	 * Two ways to set the override:
	 *   - URL: ?uxPhase=between_phases (wired in +layout.svelte; one-shot on mount)
	 *   - This pill: click to open menu, click a phase to set it
	 *
	 * Click "Auto" to clear the override and resume backend-derived behavior.
	 */
	import { uxPhase, uxPhaseOverride } from '$stores/phase';
	import type { UxPhase } from '$types';

	const PHASES: UxPhase[] = [
		'pre_tournament',
		'group_stage',
		'between_phases',
		'knockout_stage',
		'post_competition'
	];

	let open = false;

	function set(phase: UxPhase | null) {
		uxPhaseOverride.set(phase);
		open = false;
	}

	function label(p: UxPhase): string {
		return p.replace(/_/g, ' ');
	}
</script>

<div class="dev-pill" class:dev-pill--open={open}>
	{#if open}
		<ul role="menu">
			<li>
				<button
					type="button"
					on:click={() => set(null)}
					class:active={$uxPhaseOverride === null}
				>
					auto-derive
				</button>
			</li>
			{#each PHASES as p}
				<li>
					<button
						type="button"
						on:click={() => set(p)}
						class:active={$uxPhaseOverride === p}
					>
						{label(p)}
					</button>
				</li>
			{/each}
		</ul>
	{/if}
	<button
		type="button"
		class="trigger"
		on:click={() => (open = !open)}
		aria-expanded={open}
	>
		<span class="dot" class:dot--override={$uxPhaseOverride !== null}></span>
		DEV · {label($uxPhase)}
	</button>
</div>

<style>
	.dev-pill {
		position: fixed;
		bottom: 12px;
		right: 12px;
		z-index: 9999;
		font-family: 'IBM Plex Mono', ui-monospace, monospace;
		font-size: 11px;
		line-height: 1;
	}

	.trigger {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		padding: 6px 10px;
		background: #0e1d40;
		color: #f1ebde;
		border: 2px solid #d49a2e;
		border-radius: 999px;
		box-shadow: 3px 3px 0 #0e1d40;
		cursor: pointer;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		font-weight: 600;
	}

	.dot {
		display: inline-block;
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: #1b6c3e;
	}
	.dot--override {
		background: #c8281f;
	}

	ul {
		list-style: none;
		padding: 4px;
		margin: 0 0 6px 0;
		background: #f1ebde;
		border: 2px solid #0e1d40;
		border-radius: 8px;
		box-shadow: 3px 3px 0 #0e1d40;
		min-width: 180px;
	}

	li {
		margin: 0;
	}

	li button {
		display: block;
		width: 100%;
		text-align: left;
		padding: 6px 8px;
		background: transparent;
		color: #0e1d40;
		border: none;
		border-radius: 4px;
		cursor: pointer;
		font: inherit;
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}
	li button:hover {
		background: #e9e1cf;
	}
	li button.active {
		background: #d49a2e;
		color: #0e1d40;
		font-weight: 700;
	}
</style>
