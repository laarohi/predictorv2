<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { isAuthenticated, user, authResolved } from '$stores/auth';
	import {
		getUserAuditHistory,
		type AuditEvent,
		type UserHistoryResponse
	} from '$lib/api/admin';
	import PnPageShell from '$components/panini/PnPageShell.svelte';

	// Wait for auth to resolve before role-redirecting (see admin/+page.svelte).
	$: if ($authResolved && !$isAuthenticated) goto('/login');
	$: if ($authResolved && $isAuthenticated && !$user?.is_admin) goto('/');

	$: userId = $page.params.user_id ?? '';

	let history: UserHistoryResponse | null = null;
	let loading = true;
	let error: string | null = null;

	// Toggles
	type GroupBy = 'prediction' | 'chronological';
	let groupBy: GroupBy = 'prediction';
	type PhaseFilter = 'all' | 'phase_1' | 'phase_2';
	let phaseFilter: PhaseFilter = 'all';
	let showLocks = false;
	let search = '';

	// Per-row expansion state
	let expanded: Record<string, boolean> = {};

	onMount(async () => {
		try {
			history = await getUserAuditHistory(userId);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load history';
		} finally {
			loading = false;
		}
	});

	function fmtTime(iso: string): string {
		const d = new Date(iso);
		return d.toLocaleString(undefined, {
			year: 'numeric',
			month: 'short',
			day: '2-digit',
			hour: '2-digit',
			minute: '2-digit',
			second: '2-digit'
		});
	}

	function actionLabel(a: AuditEvent['action']): string {
		return { insert: 'Added', update: 'Changed', delete: 'Removed', lock: 'Locked' }[a];
	}

	function sourceLabel(s: string): string {
		// Friendly source names — fall back to the raw enum for new sources.
		const map: Record<string, string> = {
			api_single: 'Single save',
			api_batch: 'Batch save',
			api_bracket_rewrite: 'Bracket save',
			api_bonus_batch: 'Bonus save',
			lock_scheduler: 'Server (auto-lock)',
			admin: 'Admin'
		};
		return map[s] ?? s;
	}

	function kindLabel(k: AuditEvent['kind']): string {
		return { match: 'Score', team: 'Bracket', bonus: 'Bonus' }[k];
	}

	function applyFilters(events: AuditEvent[]): AuditEvent[] {
		const q = search.trim().toLowerCase();
		return events.filter((e) => {
			if (!showLocks && e.action === 'lock') return false;
			if (phaseFilter !== 'all' && e.phase && e.phase !== phaseFilter) return false;
			if (q) {
				const haystack = `${e.entity_label} ${e.change_summary} ${e.client_device} ${e.client_ip ?? ''}`.toLowerCase();
				if (!haystack.includes(q)) return false;
			}
			return true;
		});
	}

	// Group-by-prediction view: [{entity_id, entity_label, events: [...]}, ...]
	// ordered by most-recent activity in each group.
	$: filteredEvents = history ? applyFilters(history.events) : [];

	$: grouped = (() => {
		if (groupBy === 'chronological' || !history) return null;
		const map = new Map<string, { label: string; events: AuditEvent[] }>();
		for (const e of filteredEvents) {
			const key = e.entity_id ?? `__no_entity_${e.id}`;
			if (!map.has(key)) map.set(key, { label: e.entity_label, events: [] });
			map.get(key)!.events.push(e);
		}
		const arr = Array.from(map.entries()).map(([k, v]) => ({
			key: k,
			label: v.label,
			events: v.events,
			lastActivity: v.events[0]?.timestamp ?? ''
		}));
		arr.sort((a, b) => b.lastActivity.localeCompare(a.lastActivity));
		return arr;
	})();

	function toggleExpand(id: string) {
		expanded = { ...expanded, [id]: !expanded[id] };
	}
</script>

<PnPageShell activeOverride="admin">
	<div class="pn-au-wrap">
		<header class="pn-au-head">
			<a class="pn-au-back" href="/admin/audit">← All users</a>
			{#if history}
				<h1>{history.user.name}</h1>
				<p class="pn-au-sub">
					<span class="mono">{history.user.email}</span>
					· {history.events.length} recorded change{history.events.length === 1 ? '' : 's'}
				</p>
			{:else}
				<h1>Audit log</h1>
			{/if}
		</header>

		{#if loading}
			<p class="pn-au-info">Loading…</p>
		{:else if error}
			<p class="pn-au-error">{error}</p>
		{:else if history}
			<!-- ── Toggles bar ─────────────────────────────────────────── -->
			<div class="pn-au-controls">
				<div class="pn-au-toggle">
					<span class="lbl">Group by</span>
					<div class="seg">
						<button class:on={groupBy === 'prediction'} on:click={() => (groupBy = 'prediction')}>By prediction</button>
						<button class:on={groupBy === 'chronological'} on:click={() => (groupBy = 'chronological')}>Chronological</button>
					</div>
				</div>
				<div class="pn-au-toggle">
					<span class="lbl">Phase</span>
					<div class="seg">
						<button class:on={phaseFilter === 'all'} on:click={() => (phaseFilter = 'all')}>All</button>
						<button class:on={phaseFilter === 'phase_1'} on:click={() => (phaseFilter = 'phase_1')}>Phase 1</button>
						<button class:on={phaseFilter === 'phase_2'} on:click={() => (phaseFilter = 'phase_2')}>Phase 2</button>
					</div>
				</div>
				<label class="pn-au-checkbox">
					<input type="checkbox" bind:checked={showLocks} />
					<span>Show server locks</span>
				</label>
				<input
					class="pn-au-searchbox"
					type="text"
					bind:value={search}
					placeholder="Search…"
					aria-label="Search history"
				/>
			</div>

			{#if filteredEvents.length === 0}
				<p class="pn-au-info">No events match the current filters.</p>
			{:else if groupBy === 'chronological'}
				<ul class="pn-au-events">
					{#each filteredEvents as e (e.id)}
						<li>
							<button
								type="button"
								class="pn-au-row"
								class:lock={e.action === 'lock'}
								class:expanded={expanded[e.id]}
								on:click={() => toggleExpand(e.id)}
							>
								<div class="time">{fmtTime(e.timestamp)}</div>
								<div class="kind">
									<span class="badge">{kindLabel(e.kind)}</span>
									<span class="act act-{e.action}">{actionLabel(e.action)}</span>
								</div>
								<div class="summary">
									<div class="entity">{e.entity_label}</div>
									<div class="change">{e.change_summary}</div>
								</div>
								<div class="origin">
									<div>{e.client_device}</div>
									{#if e.client_ip}
										<div class="ip mono">{e.client_ip}</div>
									{/if}
								</div>
								<div class="chev">{expanded[e.id] ? '▾' : '▸'}</div>
							</button>
							{#if expanded[e.id]}
								<div class="pn-au-detail">
									<dl>
										<dt>Source</dt>
										<dd>{sourceLabel(e.source)}</dd>
										<dt>Request ID</dt>
										<dd class="mono">{e.request_id ?? '—'}</dd>
										<dt>Full IP</dt>
										<dd class="mono">{e.client_ip ?? '—'}</dd>
										<dt>User agent</dt>
										<dd class="mono ua">{e.user_agent ?? '—'}</dd>
										{#if e.performed_by_user_id && e.performed_by_user_id !== history.user.id}
											<dt>Performed by</dt>
											<dd class="mono">{e.performed_by_user_id}</dd>
										{/if}
										<dt>Old values</dt>
										<dd class="mono"><pre>{JSON.stringify(e.old_values, null, 2)}</pre></dd>
										<dt>New values</dt>
										<dd class="mono"><pre>{JSON.stringify(e.new_values, null, 2)}</pre></dd>
									</dl>
								</div>
							{/if}
						</li>
					{/each}
				</ul>
			{:else if grouped}
				{#each grouped as g (g.key)}
					<section class="pn-au-group">
						<h2>{g.label} <span class="count">· {g.events.length} change{g.events.length === 1 ? '' : 's'}</span></h2>
						<ul class="pn-au-events">
							{#each g.events as e (e.id)}
								<li>
									<button
										type="button"
										class="pn-au-row"
										class:lock={e.action === 'lock'}
										class:expanded={expanded[e.id]}
										on:click={() => toggleExpand(e.id)}
									>
										<div class="time">{fmtTime(e.timestamp)}</div>
										<div class="kind">
											<span class="act act-{e.action}">{actionLabel(e.action)}</span>
										</div>
										<div class="summary">
											<div class="change">{e.change_summary}</div>
										</div>
										<div class="origin">
											<div>{e.client_device}</div>
											{#if e.client_ip}
												<div class="ip mono">{e.client_ip}</div>
											{/if}
										</div>
										<div class="chev">{expanded[e.id] ? '▾' : '▸'}</div>
									</button>
									{#if expanded[e.id]}
										<div class="pn-au-detail">
											<dl>
												<dt>Source</dt>
												<dd>{sourceLabel(e.source)}</dd>
												<dt>Request ID</dt>
												<dd class="mono">{e.request_id ?? '—'}</dd>
												<dt>Full IP</dt>
												<dd class="mono">{e.client_ip ?? '—'}</dd>
												<dt>User agent</dt>
												<dd class="mono ua">{e.user_agent ?? '—'}</dd>
												{#if e.performed_by_user_id && e.performed_by_user_id !== history.user.id}
													<dt>Performed by</dt>
													<dd class="mono">{e.performed_by_user_id}</dd>
												{/if}
												<dt>Old values</dt>
												<dd class="mono"><pre>{JSON.stringify(e.old_values, null, 2)}</pre></dd>
												<dt>New values</dt>
												<dd class="mono"><pre>{JSON.stringify(e.new_values, null, 2)}</pre></dd>
											</dl>
										</div>
									{/if}
								</li>
							{/each}
						</ul>
					</section>
				{/each}
			{/if}
		{/if}
	</div>
</PnPageShell>

<style>
	.pn-au-wrap {
		max-width: 980px;
		margin: 0 auto;
		padding: 18px 16px 80px;
		font-family: var(--body);
		color: var(--ink);
	}
	.mono { font-family: var(--mono); }
	.pn-au-back {
		display: inline-block;
		font-family: var(--mono);
		font-size: 12px;
		color: var(--ink-2);
		text-decoration: none;
		margin-bottom: 10px;
	}
	.pn-au-back:hover { color: var(--red); }
	.pn-au-head h1 {
		font-family: var(--display);
		font-size: 28px;
		margin: 0 0 6px;
		letter-spacing: 0.02em;
	}
	.pn-au-sub {
		color: var(--ink-2);
		font-size: 13px;
		margin: 0 0 14px;
	}

	/* Toggles bar */
	.pn-au-controls {
		display: flex;
		flex-wrap: wrap;
		gap: 12px;
		align-items: center;
		background: var(--paper-2);
		border: 2px solid var(--ink);
		padding: 10px 12px;
		margin-bottom: 14px;
	}
	.pn-au-toggle {
		display: flex;
		align-items: center;
		gap: 8px;
	}
	.pn-au-toggle .lbl {
		font-family: var(--mono);
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--ink-3);
	}
	.pn-au-toggle .seg {
		display: inline-flex;
		border: 1.5px solid var(--ink);
		background: var(--paper);
	}
	.pn-au-toggle .seg button {
		border: 0;
		background: var(--paper);
		font-family: var(--mono);
		font-size: 12px;
		padding: 6px 10px;
		color: var(--ink);
		cursor: pointer;
		border-right: 1.5px solid var(--ink);
	}
	.pn-au-toggle .seg button:last-child { border-right: 0; }
	.pn-au-toggle .seg button.on {
		background: var(--ink);
		color: var(--paper);
	}
	.pn-au-checkbox {
		display: flex;
		align-items: center;
		gap: 6px;
		font-family: var(--mono);
		font-size: 12px;
		color: var(--ink-2);
		cursor: pointer;
	}
	.pn-au-checkbox input { accent-color: var(--ink); }
	.pn-au-searchbox {
		margin-left: auto;
		padding: 6px 10px;
		font-family: var(--mono);
		font-size: 12px;
		border: 1.5px solid var(--ink);
		background: var(--paper);
		color: var(--ink);
		min-width: 180px;
	}

	/* Groups */
	.pn-au-group {
		margin-bottom: 18px;
	}
	.pn-au-group h2 {
		font-family: var(--display2);
		font-size: 16px;
		margin: 0 0 6px;
		letter-spacing: 0.01em;
	}
	.pn-au-group h2 .count {
		font-family: var(--mono);
		font-size: 11px;
		color: var(--ink-3);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin-left: 4px;
	}

	/* Event list */
	.pn-au-events {
		list-style: none;
		padding: 0;
		margin: 0;
		display: grid;
		gap: 4px;
	}
	.pn-au-row {
		display: grid;
		grid-template-columns: 168px 116px 1fr 160px 16px;
		gap: 12px;
		align-items: center;
		text-align: left;
		background: var(--paper);
		border: 1.5px solid var(--ink);
		padding: 8px 12px;
		font-family: var(--body);
		font-size: 13px;
		color: var(--ink);
		cursor: pointer;
		width: 100%;
	}
	.pn-au-row:hover { background: var(--paper-2); }
	.pn-au-row.expanded { background: var(--paper-2); }
	.pn-au-row.lock { opacity: 0.65; }
	.pn-au-row .time {
		font-family: var(--mono);
		font-size: 11px;
		color: var(--ink-3);
	}
	.pn-au-row .badge {
		display: inline-block;
		font-family: var(--mono);
		font-size: 10px;
		letter-spacing: 0.05em;
		text-transform: uppercase;
		background: var(--ink);
		color: var(--paper);
		padding: 2px 6px;
		margin-right: 6px;
	}
	.pn-au-row .act {
		font-family: var(--mono);
		font-size: 11px;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}
	.pn-au-row .act-insert { color: var(--green); }
	.pn-au-row .act-update { color: var(--ink); }
	.pn-au-row .act-delete { color: var(--red); }
	.pn-au-row .act-lock { color: var(--ink-3); }
	.pn-au-row .summary .entity {
		font-size: 11px;
		color: var(--ink-3);
		font-family: var(--mono);
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}
	.pn-au-row .summary .change {
		font-weight: 600;
		font-size: 14px;
	}
	.pn-au-row .origin {
		font-size: 12px;
		color: var(--ink-2);
	}
	.pn-au-row .origin .ip {
		font-size: 11px;
		color: var(--ink-3);
	}
	.pn-au-row .chev {
		color: var(--ink-3);
	}

	/* Expanded detail */
	.pn-au-detail {
		background: var(--paper-3);
		border: 1.5px solid var(--ink);
		border-top: 0;
		padding: 10px 14px;
		font-size: 12px;
	}
	.pn-au-detail dl {
		display: grid;
		grid-template-columns: 140px 1fr;
		gap: 6px 12px;
		margin: 0;
	}
	.pn-au-detail dt {
		font-family: var(--mono);
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--ink-3);
		align-self: start;
		padding-top: 2px;
	}
	.pn-au-detail dd {
		margin: 0;
		color: var(--ink);
		word-break: break-word;
	}
	.pn-au-detail dd.ua { font-size: 11px; }
	.pn-au-detail pre {
		font-family: var(--mono);
		font-size: 11px;
		background: var(--paper);
		border: 1px solid var(--ink-3);
		padding: 6px 8px;
		margin: 0;
		white-space: pre-wrap;
		max-width: 100%;
	}

	.pn-au-info, .pn-au-error {
		font-family: var(--mono);
		font-size: 13px;
		padding: 12px;
		text-align: center;
	}
	.pn-au-error { color: var(--red); }

	/* Mobile: stack cells */
	@media (max-width: 720px) {
		.pn-au-row {
			grid-template-columns: 1fr 16px;
			grid-template-rows: auto auto auto auto;
			gap: 4px;
		}
		.pn-au-row .time, .pn-au-row .kind, .pn-au-row .summary, .pn-au-row .origin {
			grid-column: 1;
		}
		.pn-au-row .chev { grid-column: 2; grid-row: 1; align-self: center; }
		.pn-au-detail dl { grid-template-columns: 1fr; }
		.pn-au-detail dt { padding-top: 6px; }
	}
</style>
