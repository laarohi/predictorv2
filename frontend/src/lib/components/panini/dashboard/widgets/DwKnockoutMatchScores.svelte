<script lang="ts">
	/**
	 * KO match-SCORE points — the sibling of the bracket Scoring Journey.
	 *
	 * A skinny strip modelled on DwGroupSummaryStrip ("Groups so far"): a navy
	 * label block + one cell per knockout round (R32 → Final). Played rounds
	 * show points BANKED; upcoming rounds show a gold "≤N" best-case ceiling
	 * (gold hatch = provisional). Each cell's tooltip breaks the round into its
	 * per-fixture results. Phase 2 only (KO match scores are Phase 2).
	 */
	import { teamCode } from '$lib/utils/teamCodes';
	import type { KnockoutMatchRoundRow } from '$api/predictions';

	export let rounds: KnockoutMatchRoundRow[] = [];

	const STAGE_LABEL: Record<string, string> = {
		round_of_32: 'R32',
		round_of_16: 'R16',
		quarter_final: 'QF',
		semi_final: 'SF',
		final: 'Final',
		third_place: '3rd'
	};

	$: maxEarned = Math.max(1, ...rounds.map((r) => r.earned_pts));
	$: maxAvail = Math.max(1, ...rounds.map((r) => r.available_pts));
	$: bankedTotal = rounds.reduce((a, r) => a + r.earned_pts, 0);
	$: inplayTotal = rounds.reduce((a, r) => a + r.available_pts, 0);

	function isPlayed(r: KnockoutMatchRoundRow): boolean {
		return r.fixtures.some((f) => f.status === 'finished');
	}

	let openTip: string | null = null;
	function toggle(id: string) {
		openTip = openTip === id ? null : id;
	}
	function handleKey(e: KeyboardEvent, id: string) {
		if (e.key === 'Enter' || e.key === ' ') {
			e.preventDefault();
			toggle(id);
		}
	}
</script>

<svelte:window on:click={() => (openTip = null)} />

<div class="pn-sec-h">
	<span class="ttl"><span class="pip"></span> Knockout <em>match scores</em></span>
	<span class="meta"><a href="/results">All results →</a></span>
</div>

<div class="pn-koms">
	<div class="koms-lbl">
		<div class="t">KO<br />matches <em>so far</em></div>
		<div class="s">phase 2 · ≤ best case</div>
	</div>
	<div class="koms-cells">
		{#each rounds as r (r.stage)}
			{@const played = isPlayed(r)}
			{@const ratio = played ? r.earned_pts / maxEarned : r.available_pts / maxAvail}
			<div
				class="koms-cell"
				class:play={!played}
				class:hi={played && ratio > 0.75}
				role="button"
				tabindex="0"
				aria-label={`${STAGE_LABEL[r.stage] ?? r.stage}: ${played ? `${r.earned_pts} match points banked` : `up to ${r.available_pts} in play`}`}
				class:open={openTip === r.stage}
				on:click|stopPropagation={() => toggle(r.stage)}
				on:keydown={(e) => handleKey(e, r.stage)}
			>
				<div class="r">{STAGE_LABEL[r.stage] ?? r.stage}</div>
				<div class="v">{played ? r.earned_pts : `≤${r.available_pts}`}</div>
				<div class="mini"><div class="fl" style="width:{Math.max(10, ratio * 100)}%"></div></div>
				<div class="koms-tip">
					<div class="th">
						<span>{STAGE_LABEL[r.stage] ?? r.stage} · {played ? 'match' : 'in play'}</span>
						<b>{played ? r.earned_pts : `≤${r.available_pts}`}</b>
					</div>
					<ul>
						{#each r.fixtures as f}
							<li class={f.result ?? ''}>
								<span>{teamCode(f.home_team)}–{teamCode(f.away_team)}</span>
								<span class="p">
									{#if f.status === 'finished'}{f.points && f.points > 0 ? `+${f.points}` : '0'}{:else}{f.predicted}{/if}
								</span>
							</li>
						{/each}
					</ul>
				</div>
			</div>
		{/each}
	</div>
	<div class="koms-cap">
		<div class="k">match pts</div>
		<div class="v">{bankedTotal}<br /><span class="y">≤{inplayTotal}</span></div>
	</div>
</div>
