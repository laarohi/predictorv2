<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { verifyMagicLink } from '$api/auth';
	import { token, fetchUser } from '$stores/auth';

	type State = 'verifying' | 'success' | 'error';

	let state: State = 'verifying';
	let errorMessage = '';

	onMount(async () => {
		const rawToken = $page.url.searchParams.get('token');
		if (!rawToken) {
			// No token = user landed here without a link; send them to
			// the request form instead of showing a dead-end error.
			goto('/auth/magic/request');
			return;
		}

		try {
			const result = await verifyMagicLink(rawToken);
			token.set(result.access_token);
			await fetchUser();
			state = 'success';
			// Brief pause so the user sees the confirmation, then home.
			setTimeout(() => goto('/'), 800);
		} catch (e) {
			state = 'error';
			errorMessage = e instanceof Error ? e.message : 'Login link verification failed';
		}
	});
</script>

<svelte:head>
	<title>Signing in — CxF Predictaa</title>
</svelte:head>

<div class="pn">
	<div class="pn-auth-page">
		<div class="pn-auth-card" style="text-align: center;">
			<div class="pn-auth-crest">
				<div class="crest">CxF</div>
				<div class="nm">Predict<span class="aa">aa</span><span class="sub">Vol. I — WC 2026</span></div>
			</div>

			{#if state === 'verifying'}
				<h1 class="pn-auth-h">Signing you in…</h1>
				<p style="color: var(--ink-2); font-size: 14px; margin-top: 6px;">
					Verifying your login link.
				</p>
			{:else if state === 'success'}
				<h1 class="pn-auth-h">Welcome <em>back</em></h1>
				<p style="color: var(--green); font-size: 14px; margin-top: 6px;">
					Signed in. Redirecting…
				</p>
			{:else}
				<h1 class="pn-auth-h">Couldn't sign you in</h1>
				<div class="pn-form-error" style="margin-top: 12px;">{errorMessage}</div>
				<p style="margin-top: 16px;">
					<a href="/login" class="pn-btn" style="display: inline-flex;">Back to sign in</a>
				</p>
			{/if}
		</div>
	</div>
</div>
