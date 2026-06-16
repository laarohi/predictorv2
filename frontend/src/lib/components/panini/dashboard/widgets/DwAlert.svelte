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
	 * right edge. Set ctaExternal=true to open the CTA href in a new tab
	 * (used for off-site links like the Revolut payment URL).
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
	/** When true and ctaHref is set, opens the link in a new tab. */
	export let ctaExternal: boolean = false;
	export let onCta: (() => void) | null = null;
	/** When set, render a dismiss (×) button that calls this. */
	export let onDismiss: (() => void) | null = null;
</script>

<div class="pn-alert-v4" class:red={variant === 'red'} class:dismissible={onDismiss}>
	{#if onDismiss}
		<button class="dismiss" on:click={() => onDismiss?.()} aria-label="Dismiss">×</button>
	{/if}
	<div class="ico">{icon}</div>
	<div class="copy">
		<div class="ttl">{title}</div>
		<div class="meta">{@html meta}</div>
	</div>

	{#if ctaLabel}
		{#if ctaHref}
			<a
				class="pn-btn"
				class:gold={variant === 'gold'}
				href={ctaHref}
				target={ctaExternal ? '_blank' : undefined}
				rel={ctaExternal ? 'noopener noreferrer' : undefined}
			>
				{ctaLabel}
			</a>
		{:else}
			<button class="pn-btn" class:gold={variant === 'gold'} on:click={() => onCta?.()}>
				{ctaLabel}
			</button>
		{/if}
	{/if}
</div>

<style>
	/* Dismiss (×) — only present when onDismiss is wired (e.g. the Back Page
	   replay banner). Reserve room on the right so it never overlaps the CTA. */
	.pn-alert-v4.dismissible {
		padding-right: 2.6rem;
	}
	.dismiss {
		position: absolute;
		top: 5px;
		right: 8px;
		width: 1.5rem;
		height: 1.5rem;
		display: grid;
		place-items: center;
		border: none;
		background: transparent;
		cursor: pointer;
		font-size: 1.3rem;
		line-height: 1;
		color: var(--ink-3, #8a826f);
		border-radius: 4px;
	}
	.dismiss:hover {
		color: var(--ink, #0e1d40);
		background: rgba(14, 29, 64, 0.06);
	}
</style>
