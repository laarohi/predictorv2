<script lang="ts">
	import { goto } from '$app/navigation';
	import { login, isAuthenticated, loading, error as authError } from '$stores/auth';
	import { getGoogleAuthUrl } from '$api/auth';

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
		if (success) {
			goto('/');
		}
	}

	function handleGoogleLogin() {
		window.location.href = getGoogleAuthUrl();
	}
</script>

<svelte:head>
	<title>Login - Predictor v2</title>
</svelte:head>

<div class="min-h-screen flex items-center justify-center bg-base-100 px-4">
	<div class="card w-full max-w-md bg-base-200 shadow-xl">
		<div class="card-body">
			<h1 class="card-title text-2xl font-bold justify-center mb-4">Welcome Back</h1>

			{#if localError || $authError}
				<div class="alert alert-error mb-4">
					<span>{localError || $authError}</span>
				</div>
			{/if}

			<form on:submit|preventDefault={handleSubmit} class="space-y-4">
				<div class="form-control">
					<label class="label" for="email">
						<span class="label-text">Email</span>
					</label>
					<input
						id="email"
						type="email"
						placeholder="your@email.com"
						class="input input-bordered w-full"
						bind:value={email}
						disabled={$loading}
					/>
				</div>

				<div class="form-control">
					<label class="label" for="password">
						<span class="label-text">Password</span>
					</label>
					<input
						id="password"
						type="password"
						placeholder="••••••••"
						class="input input-bordered w-full"
						bind:value={password}
						disabled={$loading}
					/>
				</div>

				<button type="submit" class="btn btn-primary w-full" disabled={$loading}>
					{#if $loading}
						<span class="loading loading-spinner"></span>
					{/if}
					Sign In
				</button>
			</form>

			<div class="divider">OR</div>

			<button
				type="button"
				class="btn btn-outline w-full gap-2"
				on:click={handleGoogleLogin}
				disabled={$loading}
			>
				<svg class="w-5 h-5" viewBox="0 0 24 24">
					<path
						fill="currentColor"
						d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
					/>
					<path
						fill="currentColor"
						d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
					/>
					<path
						fill="currentColor"
						d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
					/>
					<path
						fill="currentColor"
						d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
					/>
				</svg>
				Continue with Google
			</button>

			<p class="text-center text-sm text-base-content/70 mt-4">
				Don't have an account?
				<a href="/register" class="link link-primary">Sign up</a>
			</p>
		</div>
	</div>
</div>
