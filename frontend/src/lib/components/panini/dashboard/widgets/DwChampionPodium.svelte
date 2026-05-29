<script context="module" lang="ts">
	export type Podium = {
		name: string;
		hint: string;
		points: number;
		unit: string;
	};
</script>

<script lang="ts">
	/**
	 * Post-competition hero. Three podium steps:
	 *   left   — Group Stage winner (best Phase 1 perf)
	 *   center — Overall Champion (the trophy)
	 *   right  — Phase 2 / Bracket winner (best re-pick perf)
	 *
	 * Plus a winner-line at the bottom showing who actually won the
	 * tournament + how many players correctly predicted it + a CTA to the
	 * full standings.
	 *
	 * Optional `tournamentWinner.code` renders a PnFlag chip on the line.
	 */
	import PnFlag from '$components/panini/PnFlag.svelte';

	export let title: string = "It's a wrap.";
	export let titleEm: string = 'wrap';
	export let label: string = 'Vol. I · CxF Predictaa';
	export let metaLine1: string = '';
	export let metaLine2: string = '';

	export let champion: Podium | null = null;
	export let groupsWinner: Podium | null = null;
	export let bracketWinner: Podium | null = null;

	/** Country (FIFA 3-letter code) and name of the team that actually won. */
	export let tournamentWinner: { code: string; name: string } | null = null;
	/** Number of players who picked the eventual champion correctly. */
	export let pickedCorrectly: number | null = null;
	export let totalPlayers: number = 0;

	export let ctaLabel: string = 'Full standings →';
	export let ctaHref: string = '/leaderboard';

	function renderTitle(text: string, em: string): string {
		if (em && text.toLowerCase().includes(em.toLowerCase())) {
			const re = new RegExp(em, 'i');
			return text.replace(re, `<em>${em}</em>`);
		}
		return text;
	}
</script>

<div class="pn-podium">
	<div class="pod-h">
		<div>
			<div class="label"><span class="pip"></span> {label}</div>
			<h1>{@html renderTitle(title, titleEm)}</h1>
		</div>
		{#if metaLine1 || metaLine2}
			<div class="meta">
				{metaLine1}
				{#if metaLine2}<b>{metaLine2}</b>{/if}
			</div>
		{/if}
	</div>

	<div class="pod-row">
		{#if groupsWinner}
			<div class="pod-step second">
				<span class="rank-badge">★ GROUPS</span>
				<div class="nm">{groupsWinner.name}</div>
				<div class="h">{groupsWinner.hint}</div>
				<div class="pts">
					<span class="v">{groupsWinner.points}</span>
					<span class="u">{groupsWinner.unit}</span>
				</div>
			</div>
		{:else}
			<div class="pod-step second">
				<span class="rank-badge">★ GROUPS</span>
				<div class="nm">—</div>
				<div class="h">awaiting data</div>
			</div>
		{/if}

		{#if champion}
			<div class="pod-step first">
				<span class="rank-badge">CHAMPION</span>
				<div class="trophy">★</div>
				<div class="nm">{champion.name}</div>
				<div class="h">{champion.hint}</div>
				<div class="pts">
					<span class="v">{champion.points}</span>
					<span class="u">{champion.unit}</span>
				</div>
				<span class="crown-tag">★ Vol. I winner</span>
			</div>
		{:else}
			<div class="pod-step first">
				<span class="rank-badge">CHAMPION</span>
				<div class="nm">—</div>
				<div class="h">awaiting data</div>
			</div>
		{/if}

		{#if bracketWinner}
			<div class="pod-step third">
				<span class="rank-badge">★ BRACKET</span>
				<div class="nm">{bracketWinner.name}</div>
				<div class="h">{bracketWinner.hint}</div>
				<div class="pts">
					<span class="v">{bracketWinner.points}</span>
					<span class="u">{bracketWinner.unit}</span>
				</div>
			</div>
		{:else}
			<div class="pod-step third">
				<span class="rank-badge">★ BRACKET</span>
				<div class="nm">—</div>
				<div class="h">awaiting data</div>
			</div>
		{/if}
	</div>

	{#if tournamentWinner || pickedCorrectly !== null}
		<div class="winner-line">
			<div class="wb">
				{#if tournamentWinner}
					<PnFlag code={tournamentWinner.code} w={42} h={28} />
					<span>Tournament won by <em>{tournamentWinner.name.toUpperCase()}</em></span>
				{/if}
			</div>
			<div style="display: flex; align-items: center; gap: 18px;">
				{#if pickedCorrectly !== null && totalPlayers > 0}
					<span class="picked">Picked correctly · <b>{pickedCorrectly} of {totalPlayers}</b> players</span>
				{/if}
				<a class="pn-pod-cta" href={ctaHref}>{ctaLabel}</a>
			</div>
		</div>
	{/if}
</div>
