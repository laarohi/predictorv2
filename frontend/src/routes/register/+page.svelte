<script lang="ts">
	import { goto } from '$app/navigation';
	import { register, isAuthenticated, loading, error as authError } from '$stores/auth';
	import GoogleLoginButton from '$components/GoogleLoginButton.svelte';

	let name = '';
	let email = '';
	let password = '';
	let confirmPassword = '';
	let localError = '';

	$: if ($isAuthenticated) {
		goto('/');
	}

	async function handleSubmit() {
		localError = '';
		if (!name || !email || !password || !confirmPassword) {
			localError = 'Please fill in all fields';
			return;
		}
		if (password.length < 8) {
			localError = 'Password must be at least 8 characters';
			return;
		}
		if (password !== confirmPassword) {
			localError = 'Passwords do not match';
			return;
		}
		const success = await register({ name, email, password });
		if (success) goto('/');
	}
</script>

<svelte:head>
	<title>Sign up — Predictor</title>
</svelte:head>

<div class="pn">
	<div class="pn-auth-page">
		<div class="pn-auth-card">
			<div class="pn-auth-crest">
				<div class="crest">P</div>
				<div class="nm">The Predictor<span class="sub">Vol. I — WC 2026</span></div>
			</div>
			<h1 class="pn-auth-h">Create <em>account</em></h1>

			{#if localError || $authError}
				<div class="pn-form-error">{localError || $authError}</div>
			{/if}

			<form class="pn-form" on:submit|preventDefault={handleSubmit}>
				<div class="pn-field">
					<label for="name">Display Name</label>
					<input id="name" type="text" placeholder="Your name" bind:value={name} disabled={$loading} />
				</div>
				<div class="pn-field">
					<label for="email">Email</label>
					<input id="email" type="email" placeholder="your@email.com" bind:value={email} disabled={$loading} />
				</div>
				<div class="pn-field">
					<label for="password">Password</label>
					<input id="password" type="password" placeholder="••••••••" bind:value={password} disabled={$loading} />
					<p style="font-family: var(--mono); font-size: 10px; color: var(--ink-3); letter-spacing: 0.06em; margin-top: 4px; text-transform: uppercase;">Minimum 8 characters</p>
				</div>
				<div class="pn-field">
					<label for="confirmPassword">Confirm Password</label>
					<input id="confirmPassword" type="password" placeholder="••••••••" bind:value={confirmPassword} disabled={$loading} />
				</div>
				<button type="submit" class="pn-btn" style="justify-content: center; margin-top: 6px;" disabled={$loading}>
					{$loading ? 'Creating…' : 'Create Account'}
				</button>
			</form>

			<div class="pn-auth-divider">or continue with</div>
			<GoogleLoginButton disabled={$loading} />

			<p class="pn-auth-footer">
				Already have an account?<a href="/login">Sign in</a>
			</p>
		</div>
	</div>
</div>
