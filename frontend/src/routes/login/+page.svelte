<script lang="ts">
	import { goto } from '$app/navigation';
	import { login, isAuthenticated, loading, error as authError } from '$stores/auth';
	import GoogleLoginButton from '$components/GoogleLoginButton.svelte';

	let email = '';
	let password = '';
	let localError = '';

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

			<div class="pn-auth-divider">or continue with</div>
			<GoogleLoginButton disabled={$loading} />

			<p class="pn-auth-footer">
				Don't have an account?<a href="/register">Sign up</a>
			</p>
		</div>
	</div>
</div>
