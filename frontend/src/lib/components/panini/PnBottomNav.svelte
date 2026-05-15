<script lang="ts">
	// Mobile bottom 5-tab nav. Renders below 700px only (the page shell handles
	// the responsive show/hide). Matches the current site's 5 routes:
	// Dashboard / Predictions / Results / Leaderboard / Admin (admin only).
	import { page } from '$app/stores';
	import { user } from '$stores/auth';
	import PnIcon from './PnIcon.svelte';
	import type { IconName } from '$types/panini';

	type NavItem = { href: string; label: string; icon: IconName; key: string };

	const items: NavItem[] = [
		{ href: '/', label: 'Home', icon: 'home', key: 'dash' },
		{ href: '/predictions', label: 'Predict', icon: 'predict', key: 'pred' },
		{ href: '/results', label: 'Results', icon: 'whistle', key: 'res' },
		{ href: '/leaderboard', label: 'Standings', icon: 'trophy', key: 'ldb' }
	];

	$: currentPath = $page.url.pathname;
	$: isActive = (href: string) =>
		currentPath === href || (href !== '/' && currentPath.startsWith(href));
</script>

<nav class="pn-mob-tab" style="position: fixed; bottom: 0; left: 0; right: 0;">
	{#each items as item (item.key)}
		{@const active = isActive(item.href)}
		<a href={item.href} class:on={active}>
			<PnIcon name={item.icon} size={20} color={active ? '#d49a2e' : '#8a826f'} />
			{item.label}
		</a>
	{/each}
	{#if $user?.is_admin}
		{@const active = isActive('/admin')}
		<a href="/admin" class:on={active}>
			<PnIcon name="cog" size={20} color={active ? '#d49a2e' : '#8a826f'} />
			Admin
		</a>
	{/if}
</nav>
