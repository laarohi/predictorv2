<script context="module" lang="ts">
	export type CountdownDigits = { d: number; h: number; m: number; s: number };
	export type Teaser = { label: string; value: string; outOf?: string };
</script>

<script lang="ts">
	/**
	 * Funnel-phase hero (Pre-tournament + Between-phases). Three sections:
	 *
	 *   1. Label + h1 + lede + countdown clock (D / H / M / S digits)
	 *   2. Progress bar + headline value + primary CTA
	 *   3. Three teaser pills (group matches / bracket picks / bonus)
	 *
	 * Countdown digits come pre-formatted as `{ d, h, m, s }`. The parent is
	 * responsible for re-rendering once a second via the existing
	 * `currentTime` readable in `$stores/phase`.
	 */
	export let label: string = '';
	export let titleHtml: string = '';
	export let lede: string = '';
	export let countdown: CountdownDigits = { d: 0, h: 0, m: 0, s: 0 };
	export let progressLabel: string = 'Overall progress';
	export let progressValue: number = 0;
	export let progressTotal: number = 0;
	export let progressUnit: string = 'picks';
	// Hold the headline value + bar (show "—", 0% fill) until the page's data has
	// loaded, so the meter doesn't fill up from 0 as predictions stream in.
	// Defaults true so other callers are unaffected.
	export let progressReady: boolean = true;
	export let ctaLabel: string = '';
	export let ctaHref: string = '#';
	export let teasers: Teaser[] = [];
	/** Half-width column variant (Between-phases): the hero shares a row
	 *  with the KPI grid, so the clock drops below the title and the
	 *  progress + CTA stack vertically and pin to the card's bottom. */
	export let side: boolean = false;

	$: pct = progressReady && progressTotal > 0 ? Math.min(100, (progressValue / progressTotal) * 100) : 0;

	function pad(n: number): string {
		return String(Math.max(0, Math.floor(n))).padStart(2, '0');
	}
</script>

<div class="pn-hero-v4" class:side>
	<div class="hero-row">
		<div>
			{#if label}
				<div class="label"><span class="pip"></span> {label}</div>
			{/if}
			<h1>{@html titleHtml}</h1>
			{#if lede}
				<div class="lede">{@html lede}</div>
			{/if}
		</div>
		<div>
			<div class="clock">
				<div class="digit">{countdown.d}<span class="u">DAYS</span></div>
				<div class="digit">{pad(countdown.h)}<span class="u">HRS</span></div>
				<div class="digit">{pad(countdown.m)}<span class="u">MIN</span></div>
				<div class="digit">{pad(countdown.s)}<span class="u">SEC</span></div>
			</div>
		</div>
	</div>

	<div class="progress-block">
		<div class="bar-wrap">
			<div class="bar-h">
				<span class="l">{progressLabel}</span>
				<span class="v">
					<em>{progressReady ? progressValue : '—'}</em><span class="small"> / {progressTotal} {progressUnit}</span>
				</span>
			</div>
			<div class="bar"><div class="fill" style="width: {pct}%"></div></div>
		</div>
		{#if ctaLabel}
			<a class="cta" href={ctaHref}>{ctaLabel} →</a>
		{/if}
	</div>

	{#if teasers.length}
		<div class="teaser-row">
			{#each teasers as t (t.label)}
				<div class="teaser">
					<div class="l">{t.label}</div>
					<div class="v"><em>{t.value}</em>{#if t.outOf} <span class="small">/ {t.outOf}</span>{/if}</div>
				</div>
			{/each}
		</div>
	{/if}
</div>
