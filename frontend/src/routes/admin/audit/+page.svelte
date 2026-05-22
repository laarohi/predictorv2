<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { isAuthenticated, user } from '$stores/auth';
	import { getAllUsers, type UserAdminView } from '$lib/api/admin';
	import PnPageShell from '$components/panini/PnPageShell.svelte';

	$: if ($isAuthenticated && !$user?.is_admin) goto('/');
	$: if (!$isAuthenticated) goto('/login');

	let users: UserAdminView[] = [];
	let loading = true;
	let error: string | null = null;
	let search = '';

	$: filtered = users.filter((u) => {
		if (!search.trim()) return true;
		const q = search.toLowerCase();
		return u.name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q);
	});

	onMount(async () => {
		try {
			users = await getAllUsers();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load users';
		} finally {
			loading = false;
		}
	});
</script>

<PnPageShell activeOverride="admin">
	<div class="pn-au-wrap">
		<header class="pn-au-head">
			<a class="pn-au-back" href="/admin">← Admin</a>
			<h1>Audit log</h1>
			<p class="pn-au-sub">
				Pick a user to view their prediction-change history. Use this for
				dispute resolution — the page renders one row per recorded change,
				with the option to expand for full IP / user-agent / raw JSON.
			</p>
		</header>

		<div class="pn-au-search">
			<input
				type="text"
				bind:value={search}
				placeholder="Search by name or email…"
				aria-label="Search users"
			/>
		</div>

		{#if loading}
			<p class="pn-au-info">Loading users…</p>
		{:else if error}
			<p class="pn-au-error">{error}</p>
		{:else}
			<ul class="pn-au-userlist">
				{#each filtered as u (u.id)}
					<li>
						<a class="pn-au-userrow" href={`/admin/audit/${u.id}`}>
							<span class="name">{u.name}</span>
							<span class="email">{u.email}</span>
							<span class="count">{u.prediction_count} predictions</span>
							<span class="chev">›</span>
						</a>
					</li>
				{:else}
					<li class="pn-au-info">No users match.</li>
				{/each}
			</ul>
		{/if}
	</div>
</PnPageShell>

<style>
	.pn-au-wrap {
		max-width: 920px;
		margin: 0 auto;
		padding: 18px 16px 80px;
		font-family: var(--body);
		color: var(--ink);
	}
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
		font-size: 32px;
		margin: 0 0 6px;
		letter-spacing: 0.02em;
	}
	.pn-au-sub {
		color: var(--ink-2);
		font-size: 14px;
		max-width: 60ch;
		margin: 0 0 16px;
	}
	.pn-au-search input {
		width: 100%;
		padding: 10px 12px;
		font-family: var(--mono);
		font-size: 14px;
		border: 2px solid var(--ink);
		background: var(--paper);
		color: var(--ink);
		margin-bottom: 12px;
	}
	.pn-au-userlist {
		list-style: none;
		padding: 0;
		margin: 0;
		display: grid;
		gap: 6px;
	}
	.pn-au-userrow {
		display: grid;
		grid-template-columns: 1fr 1fr auto 16px;
		gap: 12px;
		align-items: center;
		background: var(--paper);
		border: 1.5px solid var(--ink);
		padding: 10px 14px;
		text-decoration: none;
		color: var(--ink);
		transition: background 80ms ease;
	}
	.pn-au-userrow:hover { background: var(--paper-2); }
	.pn-au-userrow .name { font-weight: 600; }
	.pn-au-userrow .email { color: var(--ink-2); font-family: var(--mono); font-size: 12px; }
	.pn-au-userrow .count {
		font-family: var(--mono);
		font-size: 11px;
		color: var(--ink-3);
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}
	.pn-au-userrow .chev { color: var(--ink-3); font-size: 18px; }
	.pn-au-info, .pn-au-error {
		font-family: var(--mono);
		font-size: 13px;
		padding: 12px;
		text-align: center;
	}
	.pn-au-error { color: var(--red); }

	@media (max-width: 640px) {
		.pn-au-userrow {
			grid-template-columns: 1fr auto;
			grid-template-rows: auto auto;
		}
		.pn-au-userrow .email { grid-column: 1; grid-row: 2; }
		.pn-au-userrow .count { grid-column: 2; grid-row: 2; }
		.pn-au-userrow .chev { grid-column: 2; grid-row: 1; }
	}
</style>
