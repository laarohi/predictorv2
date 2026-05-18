<script lang="ts">
	// Panini-styled custom dropdown. Replaces native <select> so we can
	// theme it (paper body, ink border, hard offset shadow, gold-on-hover
	// options) consistently with the rest of the wizard. Options can carry
	// an optional flag code that renders inline next to the label.
	import { createEventDispatcher, tick } from 'svelte';
	import PnFlag from './PnFlag.svelte';

	export let value: string = '';
	export let options: { value: string; label: string; flag?: string }[] = [];
	export let placeholder: string = 'Select…';

	const dispatch = createEventDispatcher<{ change: string }>();

	let isOpen = false;
	let triggerEl: HTMLButtonElement | undefined;
	let panelEl: HTMLDivElement | undefined;

	$: selected = options.find((o) => o.value === value) ?? null;
	$: isEmpty = !value;

	async function open() {
		if (isOpen) return;
		isOpen = true;
		await tick();
		// Scroll the selected option into view when opening.
		if (panelEl && selected) {
			const node = panelEl.querySelector<HTMLElement>(`[data-value="${CSS.escape(selected.value)}"]`);
			if (node) node.scrollIntoView({ block: 'nearest' });
		}
	}

	function close() {
		isOpen = false;
	}

	function toggle() {
		if (isOpen) close();
		else open();
	}

	function pick(v: string) {
		dispatch('change', v);
		close();
		triggerEl?.focus();
	}

	function handleWindowClick(e: MouseEvent) {
		if (!isOpen) return;
		const t = e.target as Node;
		if (triggerEl?.contains(t)) return;
		if (panelEl?.contains(t)) return;
		close();
	}

	function handleKeydown(e: KeyboardEvent) {
		if (!isOpen) return;
		if (e.key === 'Escape') {
			e.preventDefault();
			close();
			triggerEl?.focus();
		}
	}
</script>

<svelte:window on:click={handleWindowClick} on:keydown={handleKeydown} />

<div class="pn-dd" class:open={isOpen}>
	<button
		type="button"
		bind:this={triggerEl}
		class="pn-dd-trigger"
		class:empty={isEmpty}
		on:click={toggle}
		aria-haspopup="listbox"
		aria-expanded={isOpen}
	>
		<span class="lbl">
			{#if selected}
				{#if selected.flag}
					<PnFlag code={selected.flag} w={18} h={12} />
				{/if}
				<span>{selected.label}</span>
			{:else}
				<span class="ph">{placeholder}</span>
			{/if}
		</span>
		<span class="caret" aria-hidden="true">▾</span>
	</button>
	{#if isOpen}
		<div class="pn-dd-panel" bind:this={panelEl} role="listbox">
			{#each options as opt (opt.value)}
				<button
					type="button"
					class="pn-dd-opt"
					class:selected={opt.value === value}
					role="option"
					aria-selected={opt.value === value}
					data-value={opt.value}
					on:click={() => pick(opt.value)}
				>
					{#if opt.flag}
						<PnFlag code={opt.flag} w={16} h={11} />
					{/if}
					<span>{opt.label}</span>
				</button>
			{/each}
		</div>
	{/if}
</div>
