<script lang="ts">
	// Foundation sandbox — renders every Panini primitive at once so we can
	// eyeball the design system at 1440px and 375px. Not linked from nav.
	// Note: while logged in, the legacy dark navbar still shows above us
	// because the root +layout.svelte renders it. Log out for a clean view.
	import PnPageShell from '$components/panini/PnPageShell.svelte';
	import PnFlag from '$components/panini/PnFlag.svelte';
	import PnIcon from '$components/panini/PnIcon.svelte';
	import type { IconName } from '$types/panini';

	const icons: IconName[] = [
		'ball',
		'home',
		'predict',
		'bracket',
		'trophy',
		'list',
		'flag',
		'target',
		'chevron-right',
		'chevron-left',
		'arrow-up',
		'arrow-down',
		'minus',
		'star',
		'lock',
		'clock',
		'whistle',
		'cog'
	];

	const flags: string[] = [
		'ARG',
		'BRA',
		'FRA',
		'ESP',
		'GER',
		'ITA',
		'POR',
		'NED',
		'ENG',
		'MEX',
		'USA',
		'JPN'
	];
</script>

<PnPageShell
	liveLabel="<b>LIVE</b> · ARG 2–1 CRO · 41′"
	lockLabel="<b>Next lock</b> MEX–POL in 04:32"
	youLabel="<b>You</b> · 8th of 32 · 147 pts · ▲4"
>
	<section class="pn-banner">
		<span class="n">01</span>
		<h2>Foundation <em>sandbox</em></h2>
		<span class="end">Verify chrome · 1440 + 375</span>
	</section>

	<div
		style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; margin-bottom: 24px;"
	>
		<div class="pn-sticker">
			<div class="l"><span class="pip"></span>Rank</div>
			<div class="v"><em>8</em><span class="small">/32</span></div>
			<div class="sub"><b>▲ 4</b> · last 7d</div>
		</div>
		<div class="pn-sticker">
			<div class="l"><span class="pip"></span>Total</div>
			<div class="v">147</div>
			<div class="sub"><b>+42</b> · MD2</div>
		</div>
		<div class="pn-sticker">
			<div class="l"><span class="pip"></span>Exact</div>
			<div class="v"><span class="green">3</span><span class="small">/16</span></div>
			<div class="sub"><b>+45 pts</b></div>
			<div class="corner-tag">Hot</div>
		</div>
	</div>

	<section class="pn-banner">
		<span class="n">02</span>
		<h2>Icons & <em>flags</em></h2>
	</section>

	<div
		style="display: flex; flex-wrap: wrap; gap: 14px; padding: 18px; background: var(--paper-2); border: 2px solid var(--ink); margin-bottom: 18px;"
	>
		{#each icons as name (name)}
			<div
				style="display: flex; flex-direction: column; align-items: center; gap: 6px; font-family: var(--mono); font-size: 10px; color: var(--ink-3); min-width: 60px;"
			>
				<PnIcon {name} size={28} color="#0e1d40" />
				{name}
			</div>
		{/each}
	</div>

	<div
		style="display: flex; flex-wrap: wrap; gap: 10px; padding: 18px; background: var(--paper-2); border: 2px solid var(--ink); margin-bottom: 24px;"
	>
		{#each flags as code (code)}
			<div
				style="display: flex; align-items: center; gap: 8px; font-family: var(--display); font-size: 14px;"
			>
				<PnFlag {code} w={28} h={20} />
				{code}
			</div>
		{/each}
	</div>

	<section class="pn-banner">
		<span class="n">03</span>
		<h2>Buttons & <em>tags</em></h2>
	</section>

	<div style="display: flex; gap: 12px; margin-bottom: 14px; flex-wrap: wrap;">
		<button class="pn-btn">Primary</button>
		<button class="pn-btn gold">Gold</button>
		<button class="pn-btn ghost">Ghost</button>
		<button class="pn-btn navy">Navy</button>
	</div>

	<div style="display: flex; gap: 10px; flex-wrap: wrap;">
		<span class="pn-tag">Plain</span>
		<span class="pn-tag gold">Gold</span>
		<span class="pn-tag got">Got it</span>
		<span class="pn-tag red">Locked</span>
	</div>

	<section class="pn-banner" style="margin-top: 24px;">
		<span class="n">04</span>
		<h2>Card with <em>header</em></h2>
	</section>

	<div class="pn-card">
		<div class="pn-card-h">
			<span><span class="live-dot"></span>LIVE NOW · 2 IN PROGRESS</span>
			<span class="right">MATCH DAY 03</span>
		</div>
		<div class="pn-card-body">
			Cards combine a heavy outline, offset hard shadow, and an inverted header band.
			They're the workhorse container for tables, fixtures, and grouped content.
		</div>
	</div>
</PnPageShell>
