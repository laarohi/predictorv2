<script lang="ts">
	/**
	 * Banner alert at the top of phase dashboards.
	 *
	 *   variant="gold" — informational, non-urgent (unsaved predictions,
	 *                    bracket has unsaved changes)
	 *   variant="red"  — urgent (KO matches missing predictions; next lock
	 *                    is soon)
	 *
	 * Slot the CTA via the `cta` snippet — the alert lays it out on the
	 * right edge.
	 */
	export let variant: 'gold' | 'red' = 'gold';
	/** Title rendered next to the icon. */
	export let title: string = '';
	/** Meta line below the title (raw HTML allowed for inline <b>). */
	export let meta: string = '';
	/** Icon glyph in the tilted box. Default "!" for either variant. */
	export let icon: string = '!';
	/** CTA button label. Empty string hides the button. */
	export let ctaLabel: string = '';
	export let ctaHref: string | null = null;
	export let onCta: (() => void) | null = null;
</script>

<div class="pn-alert-v4" class:red={variant === 'red'}>
	<div class="ico">{icon}</div>
	<div class="copy">
		<div class="ttl">{title}</div>
		<div class="meta">{@html meta}</div>
	</div>

	{#if ctaLabel}
		{#if ctaHref}
			<a class="pn-btn" class:gold={variant === 'gold'} href={ctaHref}>{ctaLabel}</a>
		{:else}
			<button class="pn-btn" class:gold={variant === 'gold'} on:click={() => onCta?.()}>
				{ctaLabel}
			</button>
		{/if}
	{/if}
</div>
