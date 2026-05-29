<script lang="ts">
	// Desktop masthead: crest + brand + 5-tab nav + user avatar.
	// Substitutes the Panini design's nav labels with the current site's tabs:
	// Dashboard / Predictions / Results / Leaderboard / Admin (admin only).
	//
	// The avatar doubles as a menu trigger — clicking it opens a small
	// sticker-style dropdown anchored below with "My Profile" and "Logout".
	// Closes on outside click, Escape, or item selection.
	import { fade } from 'svelte/transition';
	import { page } from '$app/stores';
	import { user, logout } from '$stores/auth';

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

	let menuOpen = false;

	function toggleMenu() {
		menuOpen = !menuOpen;
	}

	function closeMenu() {
		menuOpen = false;
	}

	function handleLogout() {
		menuOpen = false;
		logout();
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape' && menuOpen) {
			menuOpen = false;
		}
	}

	// Svelte action: close the menu when a mousedown lands outside `node`.
	function clickOutside(node: HTMLElement, callback: () => void) {
		function handle(e: MouseEvent) {
			if (!node.contains(e.target as Node)) callback();
		}
		document.addEventListener('mousedown', handle);
		return {
			destroy() {
				document.removeEventListener('mousedown', handle);
			}
		};
	}
</script>

<svelte:window on:keydown={handleKeydown} />

<header class="pn-mast">
	<a href="/" class="logo" style="text-decoration: none; color: inherit;">
		<div class="crest">CxF</div>
		<div>
			<div class="logo-name">Predict<span class="aa">aa</span></div>
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
	<div class="user" use:clickOutside={closeMenu}>
		<span>{$user?.name ?? 'Guest'}</span>
		<button
			type="button"
			class="av"
			aria-haspopup="menu"
			aria-expanded={menuOpen}
			aria-label="Open account menu"
			on:click={toggleMenu}
		>
			{($user?.name?.[0] ?? '?').toUpperCase()}
		</button>
		{#if menuOpen}
			<div class="user-menu" role="menu" transition:fade={{ duration: 80 }}>
				<a
					href="/profile"
					class="user-menu-item"
					role="menuitem"
					on:click={closeMenu}
				>
					My Profile
				</a>
				<button
					type="button"
					class="user-menu-item danger"
					role="menuitem"
					on:click={handleLogout}
				>
					Logout
				</button>
			</div>
		{/if}
	</div>
</header>
