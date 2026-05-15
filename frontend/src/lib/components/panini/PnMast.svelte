<script lang="ts">
	// Desktop masthead: crest + brand + 5-tab nav + user avatar.
	// Substitutes the Panini design's nav labels with the current site's tabs:
	// Dashboard / Predictions / Results / Leaderboard / Admin (admin only).
	import { page } from '$app/stores';
	import { user } from '$stores/auth';

	export let activeOverride: string | null = null;

	type NavItem = { href: string; label: string; key: string };

	const items: NavItem[] = [
		{ href: '/', label: 'Dashboard', key: 'dash' },
		{ href: '/predictions', label: 'Predictions', key: 'pred' },
		{ href: '/results', label: 'Results', key: 'res' },
		{ href: '/leaderboard', label: 'Leaderboard', key: 'ldb' },
		{ href: '/rules', label: 'Rules', key: 'rules' }
	];

	$: currentPath = $page.url.pathname;
	$: isActive = (href: string, key: string) => {
		if (activeOverride !== null) return activeOverride === key;
		return currentPath === href || (href !== '/' && currentPath.startsWith(href));
	};
</script>

<header class="pn-mast">
	<a href="/" class="logo" style="text-decoration: none; color: inherit;">
		<div class="crest">P</div>
		<div>
			<div class="logo-name">The Predictor</div>
			<div class="logo-vol">Vol. I — World Cup 2026</div>
		</div>
	</a>
	<nav class="nav">
		{#each items as item (item.key)}
			<a href={item.href} class:on={isActive(item.href, item.key)}>{item.label}</a>
		{/each}
		{#if $user?.is_admin}
			<a href="/admin" class:on={isActive('/admin', 'adm')}>Admin</a>
		{/if}
	</nav>
	<div class="user">
		<span>{$user?.name ?? 'Guest'}</span>
		<div class="av">{($user?.name?.[0] ?? '?').toUpperCase()}</div>
	</div>
</header>
