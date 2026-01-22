<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { handleOAuthCallback } from '$stores/auth';

	let error = '';

	onMount(() => {
		const token = $page.url.searchParams.get('token');
		const errorParam = $page.url.searchParams.get('error');

		if (errorParam) {
			error = errorParam;
			return;
		}

		if (token) {
			handleOAuthCallback(token);
			goto('/');
		} else {
			error = 'No authentication token received';
		}
	});
</script>

<svelte:head>
	<title>Authenticating... - Predictor v2</title>
</svelte:head>

<div class="min-h-screen flex items-center justify-center bg-base-100">
	{#if error}
		<div class="card bg-base-200 shadow-xl">
			<div class="card-body text-center">
				<h2 class="text-xl font-bold text-error">Authentication Failed</h2>
				<p class="text-base-content/70">{error}</p>
				<div class="mt-4">
					<a href="/login" class="btn btn-primary">Back to Login</a>
				</div>
			</div>
		</div>
	{:else}
		<div class="text-center">
			<span class="loading loading-spinner loading-lg text-primary"></span>
			<p class="mt-4 text-base-content/70">Completing authentication...</p>
		</div>
	{/if}
</div>
