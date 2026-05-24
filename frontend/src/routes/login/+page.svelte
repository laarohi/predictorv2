<script lang="ts">
	import { goto } from '$app/navigation';
	import { login, isAuthenticated, loading, error as authError } from '$stores/auth';
	import { requestMagicLink } from '$api/auth';
	import GoogleLoginButton from '$components/GoogleLoginButton.svelte';

	let email = '';
	let password = '';
	let localError = '';

	// Magic-link state
	let sendingMagicLink = false;
	let magicLinkSent = false;
	let magicLinkError = '';

	$: if ($isAuthenticated) {
		goto('/');
	}

	async function handleSubmit() {
		localError = '';
		if (!email || !password) {
			localError = 'Please fill in all fields';
			return;
		}
		const success = await login({ email, password });
		if (success) goto('/');
	}

	async function handleMagicLink() {
		magicLinkError = '';
		magicLinkSent = false;
		// No email entered — defer to the dedicated request page where
		// the user can supply it without the password-field distraction.
		if (!email.trim()) {
			goto('/auth/magic/request');
			return;
		}
		sendingMagicLink = true;
		try {
			await requestMagicLink(email);
			magicLinkSent = true;
		} catch (e) {
			magicLinkError = e instanceof Error ? e.message : 'Could not send the login link';
		} finally {
			sendingMagicLink = false;
		}
	}
</script>

<svelte:head>
	<title>Sign in — Predictor</title>
</svelte:head>

<div class="pn">
	<div class="pn-auth-page">
		<div class="pn-auth-card">
			<div class="pn-auth-crest">
				<div class="crest">P</div>
				<div class="nm">The Predictor<span class="sub">Vol. I — WC 2026</span></div>
			</div>
			<h1 class="pn-auth-h">Welcome <em>back</em></h1>

			{#if localError || $authError}
				<div class="pn-form-error">{localError || $authError}</div>
			{/if}

			<form class="pn-form" on:submit|preventDefault={handleSubmit}>
				<div class="pn-field">
					<label for="email">Email</label>
					<input id="email" type="email" placeholder="your@email.com" bind:value={email} disabled={$loading} />
				</div>
				<div class="pn-field">
					<label for="password">Password</label>
					<input id="password" type="password" placeholder="••••••••" bind:value={password} disabled={$loading} />
				</div>
				<button type="submit" class="pn-btn" style="justify-content: center; margin-top: 6px;" disabled={$loading}>
					{$loading ? 'Signing in…' : 'Sign In'}
				</button>
			</form>

			{#if magicLinkSent}
				<div class="pn-form-success" style="font-size: 13px; padding: 10px 12px; background: rgba(27,108,62,0.1); border: 1.5px solid var(--green); color: var(--green); margin-top: 10px;">
					Check your inbox — we sent a one-time login link to <b>{email}</b>.
					It's valid for 15 minutes.
				</div>
			{:else}
				{#if magicLinkError}
					<div class="pn-form-error" style="margin-top: 10px;">{magicLinkError}</div>
				{/if}
				<button
					type="button"
					class="pn-btn gold"
					style="justify-content: center; width: 100%; margin-top: 10px;"
					on:click={handleMagicLink}
					disabled={sendingMagicLink || $loading}
				>
					{sendingMagicLink ? 'Sending…' : 'Email me a login link instead'}
				</button>
			{/if}

			<div class="pn-auth-divider" style="margin-top: 26px;">or continue with</div>
			<GoogleLoginButton disabled={$loading} />

			<p class="pn-auth-footer">
				Don't have an account?<a href="/register">Sign up</a>
			</p>
		</div>
	</div>
</div>
