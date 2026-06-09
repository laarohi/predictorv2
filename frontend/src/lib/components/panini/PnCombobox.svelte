<script lang="ts" context="module">
	/** One selectable option. `value` is what gets emitted/stored; `label` is
	 *  shown; `sublabel` is the muted second line; `keywords` is the haystack
	 *  searched (defaults to label); `flag` is an optional FIFA code. */
	export interface ComboOption {
		value: string;
		label: string;
		sublabel?: string;
		keywords?: string;
		flag?: string;
	}

	/** NFD-strip diacritics + lowercase, so "mbappe"/"mbappé"/"MBAPPE" all
	 *  match — mirrors the backend bonus scoring's _normalize(). */
	function norm(s: string): string {
		return s
			.normalize('NFKD')
			.replace(/[̀-ͯ]/g, '')
			.toLowerCase()
			.trim();
	}
</script>

<script lang="ts">
	// Panini-styled searchable combobox: type to filter, options appear in a
	// dropdown, pick one to emit its value. Styling mirrors PnDropdown (paper
	// panel, ink border, gold-on-hover options) but the trigger is a text input.
	import { createEventDispatcher, tick } from 'svelte';
	import PnFlag from './PnFlag.svelte';

	export let value: string = '';
	export let options: ComboOption[] = [];
	export let placeholder: string = 'Type to search…';
	/** Cap on rendered results — large lists (~1.2k players) stay snappy and
	 *  the user is nudged to keep typing to narrow down. */
	export let limit: number = 50;
	export let disabled: boolean = false;

	const dispatch = createEventDispatcher<{ change: string }>();

	let isOpen = false;
	let query = '';
	let activeIndex = 0;
	let inputEl: HTMLInputElement | undefined;
	let panelEl: HTMLDivElement | undefined;

	// Label of the currently-selected value (shown in the input when not editing).
	$: selected = options.find((o) => o.value === value) ?? null;

	// Pre-compute the normalized haystack once per option.
	$: haystacks = options.map((o) => norm(o.keywords ?? `${o.label} ${o.sublabel ?? ''}`));

	$: filtered = (() => {
		const q = norm(query);
		if (!q) return options.slice(0, limit);
		const out: ComboOption[] = [];
		for (let i = 0; i < options.length && out.length < limit; i++) {
			if (haystacks[i].includes(q)) out.push(options[i]);
		}
		return out;
	})();
	$: totalMatches = (() => {
		const q = norm(query);
		if (!q) return options.length;
		let n = 0;
		for (const h of haystacks) if (h.includes(q)) n++;
		return n;
	})();

	async function open() {
		if (isOpen || disabled) return;
		isOpen = true;
		query = '';
		activeIndex = 0;
		await tick();
		scrollActiveIntoView();
	}

	function close() {
		isOpen = false;
		query = '';
	}

	function pick(opt: ComboOption) {
		dispatch('change', opt.value);
		close();
		inputEl?.blur();
	}

	function clear() {
		dispatch('change', '');
		close();
	}

	async function scrollActiveIntoView() {
		await tick();
		const node = panelEl?.querySelectorAll<HTMLElement>('.pn-cb-opt')[activeIndex];
		node?.scrollIntoView({ block: 'nearest' });
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'ArrowDown') {
			e.preventDefault();
			if (!isOpen) open();
			else {
				activeIndex = Math.min(activeIndex + 1, filtered.length - 1);
				scrollActiveIntoView();
			}
		} else if (e.key === 'ArrowUp') {
			e.preventDefault();
			activeIndex = Math.max(activeIndex - 1, 0);
			scrollActiveIntoView();
		} else if (e.key === 'Enter') {
			if (isOpen && filtered[activeIndex]) {
				e.preventDefault();
				pick(filtered[activeIndex]);
			}
		} else if (e.key === 'Escape') {
			if (isOpen) {
				e.preventDefault();
				close();
				inputEl?.blur();
			}
		}
	}

	function onInput() {
		if (!isOpen) isOpen = true;
		activeIndex = 0;
	}

	function handleWindowClick(e: MouseEvent) {
		if (!isOpen) return;
		const t = e.target as Node;
		if (inputEl?.contains(t) || panelEl?.contains(t)) return;
		close();
	}
</script>

<svelte:window on:click={handleWindowClick} />

<div class="pn-cb" class:open={isOpen}>
	<div class="pn-cb-field" class:empty={!selected}>
		<input
			bind:this={inputEl}
			class="pn-cb-input"
			type="text"
			autocomplete="off"
			placeholder={selected ? selected.label : placeholder}
			value={isOpen ? query : selected ? selected.label : ''}
			on:input={(e) => {
				query = e.currentTarget.value;
				onInput();
			}}
			{disabled}
			on:focus={open}
			on:keydown={handleKeydown}
			role="combobox"
			aria-expanded={isOpen}
			aria-controls="pn-cb-list"
			aria-autocomplete="list"
		/>
		{#if selected && !isOpen && !disabled}
			<button type="button" class="pn-cb-clear" title="Clear" on:click={clear}>×</button>
		{:else}
			<span class="caret" aria-hidden="true">▾</span>
		{/if}
	</div>

	{#if isOpen}
		<div class="pn-cb-panel" bind:this={panelEl} id="pn-cb-list" role="listbox">
			{#if filtered.length === 0}
				<div class="pn-cb-empty">No matches</div>
			{:else}
				{#each filtered as opt, i (opt.value)}
					<button
						type="button"
						class="pn-cb-opt"
						class:active={i === activeIndex}
						class:selected={opt.value === value}
						role="option"
						aria-selected={opt.value === value}
						on:mouseenter={() => (activeIndex = i)}
						on:click={() => pick(opt)}
					>
						{#if opt.flag}
							<PnFlag code={opt.flag} w={18} h={12} />
						{/if}
						<span class="txt">
							<span class="lbl">{opt.label}</span>
							{#if opt.sublabel}<span class="sub">{opt.sublabel}</span>{/if}
						</span>
					</button>
				{/each}
				{#if totalMatches > filtered.length}
					<div class="pn-cb-more">+{totalMatches - filtered.length} more — keep typing…</div>
				{/if}
			{/if}
		</div>
	{/if}
</div>

<style>
	.pn-cb {
		position: relative;
		width: 100%;
	}
	.pn-cb-field {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		background: var(--paper);
		border: 2px solid var(--ink);
		box-shadow: 3px 3px 0 var(--ink);
		padding: 0 0.5rem;
	}
	.pn-cb.open .pn-cb-field {
		box-shadow: 3px 3px 0 var(--gold);
		border-color: var(--gold);
	}
	.pn-cb-input {
		flex: 1;
		min-width: 0;
		background: transparent;
		border: none;
		outline: none;
		font-family: var(--body);
		font-size: 0.95rem;
		color: var(--ink);
		padding: 0.5rem 0;
	}
	.pn-cb-input::placeholder {
		color: var(--ink-3);
	}
	.pn-cb-field.empty .pn-cb-input::placeholder {
		color: var(--ink-3);
	}
	.caret {
		color: var(--ink-2);
		font-size: 0.7rem;
		pointer-events: none;
	}
	.pn-cb-clear {
		border: none;
		background: transparent;
		color: var(--ink-2);
		font-size: 1.2rem;
		line-height: 1;
		cursor: pointer;
		padding: 0 0.2rem;
	}
	.pn-cb-clear:hover {
		color: var(--red);
	}
	.pn-cb-panel {
		position: absolute;
		z-index: 40;
		top: calc(100% + 4px);
		left: 0;
		right: 0;
		max-height: 280px;
		overflow-y: auto;
		background: var(--paper);
		border: 2px solid var(--ink);
		box-shadow: 5px 5px 0 var(--ink);
	}
	.pn-cb-opt {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		width: 100%;
		text-align: left;
		border: none;
		background: transparent;
		padding: 0.5rem 0.6rem;
		cursor: pointer;
		font-family: var(--body);
		color: var(--ink);
		border-bottom: 1px solid var(--paper-3);
	}
	.pn-cb-opt.active {
		background: var(--gold);
		color: var(--ink);
	}
	.pn-cb-opt.selected {
		font-weight: 700;
	}
	.pn-cb-opt .txt {
		display: flex;
		flex-direction: column;
		min-width: 0;
	}
	.pn-cb-opt .lbl {
		font-size: 0.95rem;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.pn-cb-opt .sub {
		font-family: var(--mono);
		font-size: 0.7rem;
		color: var(--ink-3);
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}
	.pn-cb-opt.active .sub {
		color: var(--ink-2);
	}
	.pn-cb-empty,
	.pn-cb-more {
		padding: 0.6rem;
		font-family: var(--mono);
		font-size: 0.75rem;
		color: var(--ink-3);
		text-align: center;
	}
	.pn-cb-more {
		border-top: 1px solid var(--paper-3);
	}
</style>
