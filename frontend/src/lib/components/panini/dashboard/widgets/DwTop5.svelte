<script context="module" lang="ts">
	export type Top5Row = {
		/** Stable identity for keyed-each reconciliation. Required to be
		 * unique across `rows`. Falls back to "{name}|{position}|{idx}" if
		 * omitted, but ties on `position` then trigger Svelte's duplicate-
		 * key error — always pass `userId` when binding from a leaderboard. */
		userId?: string;
		position: number;
		name: string;
		hint: string;
		points: number;
		isCurrentUser?: boolean;
	};
</script>

<script lang="ts">
	/**
	 * Compact Top-5 leaderboard column (v4). Used in the right column of
	 * Group and KO dashboards, and as the "final standings" widget on
	 * Between-phases.
	 *
	 * Two flavours:
	 *   - Just the top N rows (`rows`) — when the current user is already
	 *     inside the top N.
	 *   - Top N rows + a "you" row pinned at the bottom separated by a
	 *     dashed divider — when the user is outside the top.
	 *
	 * Section header is rendered above the card so the spacing matches the
	 * sibling `pn-sec-h` headers in the dash columns.
	 */
	export let title: string = 'Top 5';
	export let titleEm: string = '';
	export let subtitle: string = '';
	export let rows: Top5Row[] = [];
	export let you: Top5Row | null = null;
	export let footHref: string = '/leaderboard';
	export let footLabel: string = 'See full standings →';
	/** Single-line rows (hint inline after the name, ellipsized) for
	 *  dashboards that need the column ~80px shorter to fit one screen. */
	export let dense: boolean = false;
	/** Render the standings link as a foot BAR inside the card (mirrors
	 *  .pn-summary .foot) instead of a bare link below it. Used when the
	 *  card sits beside another footed card and the bottom edges must
	 *  align (Between-phases summary + final standings). */
	export let footInside: boolean = false;
	/** Left-hand caption of the inside foot bar. */
	export let footLeft: string = '';
</script>

<!--
	Three sibling root elements (header, card, foot link). The widget
	intentionally has no wrapper so the parent `.col` directly contains
	them — that keeps the standings card aligned with the sibling match-
	table cards (which are also direct children of their own .col) while
	letting the "See full standings" link sit below the card without
	taking height away from it.
-->
<div class="pn-sec-h">
	<span class="ttl">
		<span class="pip"></span>
		{title}{#if titleEm} <em>{titleEm}</em>{/if}
	</span>
	<span class="meta">{subtitle}</span>
</div>

<div class="pn-top5" class:dense>
	<!-- Internal navy header bar with column labels — mirrors .mtab-head
	     in the sibling match-table card so the two cards share the same
	     structure (section header outside, column-labels bar inside, data
	     rows below) and align bottom-to-bottom. -->
	<div class="head">
		<span class="c-pos">Rank</span>
		<span class="c-nm">Player</span>
		<span class="c-pts">Points</span>
	</div>

	{#each rows as r, i (r.userId ?? `${r.name}|${r.position}|${i}`)}
		<div
			class="row"
			class:gold={r.position === 1}
			class:you={r.isCurrentUser}
		>
			<div class="pos">{r.position}</div>
			<div class="ident">
				<div class="nm">{r.name}</div>
				{#if r.hint}<div class="h">{r.hint}</div>{/if}
			</div>
			<div class="pts">{r.points}</div>
		</div>
	{/each}

	{#if you}
		<div class="row you you-pinned">
			<div class="pos">{you.position}</div>
			<div class="ident">
				<div class="nm">{you.name}</div>
				{#if you.hint}<div class="h">{you.hint}</div>{/if}
			</div>
			<div class="pts">{you.points}</div>
		</div>
	{/if}

	{#if footInside}
		<div class="foot">
			<span>{footLeft}</span>
			<a href={footHref}>{footLabel}</a>
		</div>
	{/if}
</div>

{#if !footInside}
	<div class="pn-top5-foot"><a href={footHref}>{footLabel}</a></div>
{/if}
