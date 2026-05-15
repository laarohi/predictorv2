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
	<title>Authenticating… — Predictor</title>
</svelte:head>

<div class="pn">
	<div class="pn-auth-page">
		{#if error}
			<div class="pn-auth-card" style="text-align: center;">
				<div class="pn-auth-crest">
					<div class="crest">P</div>
					<div class="nm">The Predictor</div>
				</div>
				<h1 class="pn-auth-h" style="color: var(--red);">Authentication <em>failed</em></h1>
				<p style="font-family: var(--mono); font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase; color: var(--ink-3); margin-bottom: 22px;">
					{error}
				</p>
				<a class="pn-btn" href="/login">Back to Sign In</a>
			</div>
		{:else}
			<div style="text-align: center; font-family: var(--mono); font-size: 12px; letter-spacing: 0.10em; text-transform: uppercase; color: var(--ink-3);">
				Completing authentication…
			</div>
		{/if}
	</div>
</div>
