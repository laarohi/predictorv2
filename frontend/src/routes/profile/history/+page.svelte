<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { isAuthenticated, user, authResolved } from '$stores/auth';
	import { getMyHistory } from '$api/users';
	import type { AuditEvent } from '$api/admin';
	import PnPageShell from '$components/panini/PnPageShell.svelte';

	// Same auth-resolved guard pattern as the rest of the app — don't bounce
	// before /auth/me has populated $user on a cold load.
	$: if ($authResolved && !$isAuthenticated) goto('/login');

	let events: AuditEvent[] = [];
	let loading = true;
	let error: string | null = null;
	let search = '';
	let showLocks = false;

	onMount(async () => {
		if (!$isAuthenticated) return;
		try {
			const res = await getMyHistory();
			events = res.events;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load your history';
		} finally {
			loading = false;
		}
	});

	function fmtTime(iso: string): string {
		return new Date(iso).toLocaleString(undefined, {
			month: 'short',
			day: '2-digit',
			hour: '2-digit',
			minute: '2-digit'
		});
	}
	function actionLabel(a: AuditEvent['action']): string {
		return { insert: 'Added', update: 'Changed', delete: 'Removed', lock: 'Locked' }[a];
	}
	function kindLabel(k: AuditEvent['kind']): string {
		return { match: 'Score', team: 'Bracket', bonus: 'Bonus' }[k];
	}
	function sourceLabel(s: string): string {
		const map: Record<string, string> = {
			api_single: 'Single save',
			api_batch: 'Batch save',
			api_bracket_rewrite: 'Bracket save',
			api_bonus_batch: 'Bonus save',
			lock_scheduler: 'Auto-lock',
			admin: 'Admin'
		};
		return map[s] ?? s;
	}
	// An event a player didn't make themselves — i.e. an admin (or the auto-lock
	// scheduler) touched their predictions. Surfaced so tampering is visible.
	function byOther(e: AuditEvent): boolean {
		return e.performed_by_user_id != null && e.performed_by_user_id !== $user?.id;
	}

	$: filtered = events.filter((e) => {
		if (!showLocks && e.action === 'lock') return false;
		const q = search.trim().toLowerCase();
		if (!q) return true;
		return (
			e.entity_label.toLowerCase().includes(q) ||
			e.change_summary.toLowerCase().includes(q) ||
			kindLabel(e.kind).toLowerCase().includes(q)
		);
	});
</script>

<svelte:head><title>My history — Predictor</title></svelte:head>

{#if $isAuthenticated}
	<PnPageShell>
		<section class="pn-pf-section">
			<div class="h">
				<span>My Prediction History</span>
				<a class="right back" href="/profile">← Profile</a>
			</div>
			<div class="body">
				<p class="intro">
					Every change to your predictions is recorded here — scores, bracket picks
					and bonus answers, with timestamps. Anything an admin or the auto-lock
					changed on your behalf is flagged.
				</p>

				<div class="tools">
					<input class="srch" type="text" placeholder="Search teams, picks…" bind:value={search} />
					<label class="lk"><input type="checkbox" bind:checked={showLocks} /> Show auto-locks</label>
				</div>

				{#if error}
					<div class="pn-pf-alert error">{error}</div>
				{:else if loading}
					<p class="muted">Loading your history…</p>
				{:else if events.length === 0}
					<p class="muted">No changes recorded yet — once you save predictions they'll show up here.</p>
				{:else if filtered.length === 0}
					<p class="muted">No events match your filter.</p>
				{:else}
					<div class="evlist">
						{#each filtered as e (e.id)}
							<div class="ev" class:other={byOther(e)} class:lock={e.action === 'lock'}>
								<div class="kind kind-{e.kind}">{kindLabel(e.kind)}</div>
								<div class="main">
									<div class="summary">
										<span class="act">{actionLabel(e.action)}</span>
										{e.entity_label}
										{#if e.change_summary}<span class="chg">{e.change_summary}</span>{/if}
									</div>
									<div class="meta">
										{fmtTime(e.timestamp)} · {sourceLabel(e.source)}
										{#if e.phase}· {e.phase === 'phase_1' ? 'Phase I' : 'Phase II'}{/if}
										{#if byOther(e)}<span class="flag">⚑ Changed by admin</span>{/if}
									</div>
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</div>
		</section>
	</PnPageShell>
{/if}

<style>
	.back {
		text-decoration: none;
		color: var(--paper-3);
		cursor: pointer;
	}
	.intro {
		font-family: var(--body);
		font-size: 13px;
		line-height: 1.5;
		color: var(--ink-2);
		margin: 0 0 14px;
	}
	.tools {
		display: flex;
		gap: 14px;
		align-items: center;
		flex-wrap: wrap;
		margin-bottom: 14px;
	}
	.srch {
		flex: 1 1 220px;
		padding: 8px 12px;
		font-family: var(--body);
		font-size: 13px;
		background: var(--paper-2);
		border: 2px solid var(--ink);
		color: var(--ink);
	}
	.lk {
		font-family: var(--mono);
		font-size: 11px;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--ink-3);
		display: inline-flex;
		align-items: center;
		gap: 6px;
		cursor: pointer;
	}
	.muted {
		font-family: var(--mono);
		font-size: 12px;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--ink-3);
	}
	.evlist {
		display: flex;
		flex-direction: column;
	}
	.ev {
		display: grid;
		grid-template-columns: 72px 1fr;
		gap: 12px;
		align-items: start;
		padding: 10px 0;
		border-top: 1px solid var(--paper-3);
	}
	.ev:first-child {
		border-top: none;
	}
	.ev.other {
		background: rgba(200, 40, 31, 0.06);
		border-left: 4px solid var(--red);
		padding-left: 10px;
		margin-left: -10px;
	}
	.ev.lock {
		opacity: 0.62;
	}
	.kind {
		font-family: var(--mono);
		font-size: 9px;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		text-align: center;
		padding: 4px 0;
		border: 1.5px solid var(--ink);
		color: var(--ink);
		background: var(--paper-2);
	}
	.kind-match { border-color: var(--green); color: var(--green); }
	.kind-team { border-color: var(--navy); color: var(--navy); }
	.kind-bonus { border-color: var(--gold); color: var(--gold); }
	.summary {
		font-family: var(--body);
		font-size: 13.5px;
		line-height: 1.4;
		color: var(--ink);
	}
	.summary .act {
		font-family: var(--display);
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--ink-3);
		margin-right: 4px;
	}
	.summary .chg {
		font-family: var(--mono);
		font-size: 12px;
		color: var(--ink-2);
		margin-left: 4px;
	}
	.meta {
		font-family: var(--mono);
		font-size: 10px;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--ink-3);
		margin-top: 3px;
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
		align-items: center;
	}
	.meta .flag {
		color: var(--red);
		font-weight: 700;
	}
</style>
