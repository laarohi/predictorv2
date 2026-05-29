<script lang="ts">
	/**
	 * Conditional urgency nudge. Renders one of two visual states depending
	 * on whether the user is behind AND the deadline is close.
	 *
	 *   - Calm:   pn-card with progress bar + link. Default when not urgent.
	 *   - Urgent: pn-banner with large countdown + primary CTA. Triggered
	 *             when unfilledCount > 0 AND msUntilDeadline < 12h.
	 *
	 * Used at the top of DashboardPre (phase_1_open), DashboardBetween
	 * (phase_2_bracket), and conditionally inside DashboardKO
	 * (phase_2_scores, only when next KO is within 12h).
	 */
	import { currentTime } from '$stores/phase';

	export let scope: 'phase_1_open' | 'phase_2_bracket' | 'phase_2_scores';
	export let unfilledCount: number;
	export let totalCount: number;
	export let deadlineISO: string | null;
	export let ctaHref = '/predictions';

	const URGENT_THRESHOLD_MS = 12 * 60 * 60 * 1000;

	const SCOPE_LABELS: Record<typeof scope, string> = {
		phase_1_open: 'Phase 1 predictions',
		phase_2_bracket: 'Phase 2 bracket',
		phase_2_scores: 'Knockout scores'
	};

	$: msUntilDeadline = deadlineISO
		? new Date(deadlineISO).getTime() - $currentTime.getTime()
		: null;

	$: urgent =
		unfilledCount > 0 &&
		msUntilDeadline !== null &&
		msUntilDeadline > 0 &&
		msUntilDeadline < URGENT_THRESHOLD_MS;

	$: filledCount = Math.max(0, totalCount - unfilledCount);
	$: progressPct = totalCount > 0 ? Math.round((filledCount / totalCount) * 100) : 0;

	function fmtCountdown(ms: number | null): string {
		if (ms === null || ms <= 0) return '—';
		const totalMin = Math.floor(ms / 60000);
		const h = Math.floor(totalMin / 60);
		const m = totalMin % 60;
		const s = Math.floor((ms % 60000) / 1000);
		if (h > 0) return `${h}h ${String(m).padStart(2, '0')}m`;
		if (m > 0) return `${m}m ${String(s).padStart(2, '0')}s`;
		return `${s}s`;
	}

	function fmtDeadline(iso: string | null): string {
		if (!iso) return 'No deadline set';
		const d = new Date(iso);
		return d.toLocaleString('en-GB', {
			weekday: 'short',
			day: 'numeric',
			month: 'short',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	$: scopeLabel = SCOPE_LABELS[scope];
</script>

{#if urgent}
	<aside class="pn-nudge pn-nudge--urgent" role="alert">
		<div class="urgent-head">
			<span class="urgent-tag">PICKS LEFT</span>
			<span class="urgent-scope">{scopeLabel}</span>
		</div>
		<div class="urgent-body">
			<div class="urgent-count">
				<span class="count-n">{unfilledCount}</span>
				<span class="count-l">unfilled</span>
			</div>
			<div class="urgent-meta">
				<div class="when">Locks in</div>
				<div class="cd">{fmtCountdown(msUntilDeadline)}</div>
			</div>
			<a class="urgent-cta" href={ctaHref}>Finish predictions →</a>
		</div>
	</aside>
{:else}
	<aside class="pn-nudge pn-nudge--calm">
		<div class="calm-head">
			<span class="calm-l">YOUR PICKS · {scopeLabel}</span>
			<span class="calm-deadline">Locks {fmtDeadline(deadlineISO)}</span>
		</div>
		<div class="calm-progress">
			<div class="bar"><div class="fill" style="width: {progressPct}%"></div></div>
			<div class="counts"><b>{filledCount}</b>/{totalCount} done</div>
		</div>
		<div class="calm-foot">
			{#if msUntilDeadline !== null && msUntilDeadline > 0}
				<span class="calm-cd">in {fmtCountdown(msUntilDeadline)}</span>
			{/if}
			<a class="calm-link" href={ctaHref}>Open predictions →</a>
		</div>
	</aside>
{/if}

<style>
	.pn-nudge {
		font-family: 'IBM Plex Sans', system-ui, sans-serif;
		margin: 0 0 16px;
	}

	/* ---- Calm ---- */
	.pn-nudge--calm {
		background: var(--paper-2, #e9e1cf);
		border: 2px solid var(--ink, #0e1d40);
		box-shadow: 5px 5px 0 var(--ink, #0e1d40);
		padding: 12px 14px;
	}
	.calm-head {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 12px;
		margin-bottom: 8px;
		font-family: 'IBM Plex Mono', ui-monospace, monospace;
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}
	.calm-l {
		color: var(--ink, #0e1d40);
		font-weight: 600;
	}
	.calm-deadline {
		color: var(--ink-3, #8a826f);
	}
	.calm-progress {
		display: flex;
		align-items: center;
		gap: 12px;
		margin-bottom: 6px;
	}
	.bar {
		flex: 1;
		height: 8px;
		background: var(--paper-3, #dfd4ba);
		border: 1.5px solid var(--ink, #0e1d40);
		position: relative;
		overflow: hidden;
	}
	.fill {
		position: absolute;
		inset: 0 auto 0 0;
		background: var(--green, #1b6c3e);
	}
	.counts {
		font-family: 'IBM Plex Mono', ui-monospace, monospace;
		font-size: 12px;
		color: var(--ink, #0e1d40);
	}
	.counts b {
		font-size: 14px;
	}
	.calm-foot {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		font-family: 'IBM Plex Mono', ui-monospace, monospace;
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}
	.calm-cd {
		color: var(--ink-2, #514a3d);
	}
	.calm-link {
		color: var(--red, #c8281f);
		text-decoration: none;
		font-weight: 700;
	}
	.calm-link:hover {
		text-decoration: underline;
	}

	/* ---- Urgent ---- */
	.pn-nudge--urgent {
		background: var(--red, #c8281f);
		color: var(--paper, #f1ebde);
		border: 2px solid var(--ink, #0e1d40);
		box-shadow: 5px 5px 0 var(--ink, #0e1d40);
		padding: 14px 16px;
	}
	.urgent-head {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 12px;
		margin-bottom: 12px;
		font-family: 'IBM Plex Mono', ui-monospace, monospace;
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}
	.urgent-tag {
		background: var(--paper, #f1ebde);
		color: var(--red, #c8281f);
		padding: 3px 8px;
		font-weight: 700;
	}
	.urgent-body {
		display: grid;
		grid-template-columns: auto 1fr auto;
		gap: 16px;
		align-items: center;
	}
	.urgent-count {
		display: flex;
		flex-direction: column;
		align-items: center;
	}
	.count-n {
		font-family: 'Archivo Black', system-ui, sans-serif;
		font-size: 44px;
		line-height: 1;
	}
	.count-l {
		font-family: 'IBM Plex Mono', ui-monospace, monospace;
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		margin-top: 2px;
	}
	.urgent-meta {
		display: flex;
		flex-direction: column;
	}
	.when {
		font-family: 'IBM Plex Mono', ui-monospace, monospace;
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		opacity: 0.85;
	}
	.cd {
		font-family: 'Archivo Black', system-ui, sans-serif;
		font-size: 28px;
		line-height: 1.1;
	}
	.urgent-cta {
		background: var(--paper, #f1ebde);
		color: var(--ink, #0e1d40);
		padding: 10px 14px;
		font-family: 'IBM Plex Mono', ui-monospace, monospace;
		font-size: 12px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		text-decoration: none;
		border: 2px solid var(--ink, #0e1d40);
		box-shadow: 3px 3px 0 var(--ink, #0e1d40);
	}
	.urgent-cta:hover {
		background: var(--gold, #d49a2e);
	}

	@media (max-width: 640px) {
		.urgent-body {
			grid-template-columns: 1fr;
			gap: 10px;
		}
		.urgent-count {
			flex-direction: row;
			gap: 10px;
			align-items: baseline;
		}
	}
</style>
