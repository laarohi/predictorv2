<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { handleOAuthCallback } from '$stores/auth';

	let error = '';

	onMount(() => {
		// The backend delivers the token in the URL fragment (#token=...) so it
		// never reaches server access logs. Read from the hash, falling back to
		// the query string for backward compatibility.
		const hash = new URLSearchParams(window.location.hash.slice(1));
		const token = hash.get('token') ?? $page.url.searchParams.get('token');
		const errorParam = hash.get('error') ?? $page.url.searchParams.get('error');
		if (errorParam) {
			error = errorParam;
			return;
		}
		if (token) {
			handleOAuthCallback(token);
			// Strip the token from the address bar / history before navigating.
			history.replaceState(null, '', window.location.pathname);
			goto('/');
		} else {
			error = 'No authentication token received';
		}
	});
</script>

<svelte:head>
	<title>Authenticating… — CxF Predictaa</title>
</svelte:head>

<div class="pn">
	<div class="pn-auth-page">
		{#if error}
			<div class="pn-auth-card" style="text-align: center;">
				<div class="pn-auth-crest">
					<div class="crest">CxF</div>
					<div class="nm">Predict<span class="aa">aa</span></div>
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
