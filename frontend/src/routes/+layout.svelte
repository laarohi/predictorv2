<script lang="ts">
	import '../app.css';
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { isAuthenticated, user, logout, initAuth } from '$stores/auth';

	onMount(() => {
		initAuth();
	});

	const navItems = [
		{ href: '/', label: 'Dashboard', icon: '🏠' },
		{ href: '/predictions', label: 'Predictions', icon: '⚽' },
		{ href: '/leaderboard', label: 'Leaderboard', icon: '🏆' }
	];

	$: currentPath = $page.url.pathname;
</script>

<div class="min-h-screen bg-base-100 flex flex-col">
	<!-- Navigation -->
	{#if $isAuthenticated}
		<nav class="navbar bg-base-200 border-b border-base-300 sticky top-0 z-50">
			<div class="navbar-start">
				<a href="/" class="btn btn-ghost text-xl font-bold">Predictor</a>
			</div>

			<div class="navbar-center hidden sm:flex">
				<ul class="menu menu-horizontal px-1 gap-1">
					{#each navItems as item}
						<li>
							<a
								href={item.href}
								class:active={currentPath === item.href ||
									(item.href !== '/' && currentPath.startsWith(item.href))}
							>
								<span class="hidden lg:inline">{item.icon}</span>
								{item.label}
							</a>
						</li>
					{/each}
					{#if $user?.is_admin}
						<li>
							<a href="/admin" class:active={currentPath.startsWith('/admin')}>Admin</a>
						</li>
					{/if}
				</ul>
			</div>

			<div class="navbar-end">
				<div class="dropdown dropdown-end">
					<div tabindex="0" role="button" class="btn btn-ghost btn-circle avatar">
						<div class="w-10 rounded-full bg-primary text-primary-content flex items-center justify-center">
							<span class="text-lg font-bold">{$user?.name?.charAt(0).toUpperCase() || '?'}</span>
						</div>
					</div>
					<ul
						tabindex="0"
						class="menu menu-sm dropdown-content mt-3 z-[1] p-2 shadow bg-base-200 rounded-box w-52"
					>
						<li class="menu-title">
							<span>{$user?.name}</span>
						</li>
						<li><a href="/profile">Profile</a></li>
						<li><button on:click={logout}>Logout</button></li>
					</ul>
				</div>
			</div>
		</nav>

		<!-- Mobile bottom navigation -->
		<nav class="btm-nav sm:hidden bg-base-200 border-t border-base-300">
			{#each navItems as item}
				<a
					href={item.href}
					class:active={currentPath === item.href ||
						(item.href !== '/' && currentPath.startsWith(item.href))}
				>
					<span class="text-xl">{item.icon}</span>
					<span class="btm-nav-label text-xs">{item.label}</span>
				</a>
			{/each}
		</nav>
	{/if}

	<!-- Main content -->
	<main class="flex-1 pb-16 sm:pb-0">
		<slot />
	</main>
</div>
