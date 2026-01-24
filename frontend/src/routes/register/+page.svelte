<script lang="ts">
	import { goto } from '$app/navigation';
	import { register, isAuthenticated, loading, error as authError } from '$stores/auth';
	import { getGoogleAuthUrl } from '$api/auth';

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
		if (success) {
			goto('/');
		}
	}

	function handleGoogleLogin() {
		window.location.href = getGoogleAuthUrl();
	}
</script>

<svelte:head>
	<title>Register - Predictor v2</title>
</svelte:head>

<div class="auth-bg flex items-center justify-center px-4 py-12">
	<div class="w-full max-w-md animate-slide-up">
		<!-- Logo/Brand -->
		<div class="text-center mb-8">
			<h1 class="text-5xl font-display tracking-wider text-gradient mb-2">PREDICTOR</h1>
			<p class="text-base-content/50 text-sm">World Cup 2026 Predictions</p>
		</div>

		<!-- Register Card -->
		<div class="stadium-card p-6 sm:p-8">
			<h2 class="text-2xl font-display tracking-wide text-center mb-6">Create Account</h2>

			{#if localError || $authError}
				<div class="mb-6 p-4 bg-error/10 border border-error/30 rounded-lg text-error text-sm flex items-center gap-3">
					<svg class="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
					</svg>
					<span>{localError || $authError}</span>
				</div>
			{/if}

			<form on:submit|preventDefault={handleSubmit} class="space-y-4">
				<div>
					<label class="block text-sm font-medium text-base-content/70 mb-2" for="name">
						Display Name
					</label>
					<input
						id="name"
						type="text"
						placeholder="Your name"
						class="w-full px-4 py-3 bg-base-300 border border-base-100 rounded-lg text-base-content placeholder:text-base-content/30 focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/30 transition-all"
						bind:value={name}
						disabled={$loading}
					/>
				</div>

				<div>
					<label class="block text-sm font-medium text-base-content/70 mb-2" for="email">
						Email
					</label>
					<input
						id="email"
						type="email"
						placeholder="your@email.com"
						class="w-full px-4 py-3 bg-base-300 border border-base-100 rounded-lg text-base-content placeholder:text-base-content/30 focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/30 transition-all"
						bind:value={email}
						disabled={$loading}
					/>
				</div>

				<div>
					<label class="block text-sm font-medium text-base-content/70 mb-2" for="password">
						Password
					</label>
					<input
						id="password"
						type="password"
						placeholder="••••••••"
						class="w-full px-4 py-3 bg-base-300 border border-base-100 rounded-lg text-base-content placeholder:text-base-content/30 focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/30 transition-all"
						bind:value={password}
						disabled={$loading}
					/>
					<p class="mt-1.5 text-xs text-base-content/40">Minimum 8 characters</p>
				</div>

				<div>
					<label class="block text-sm font-medium text-base-content/70 mb-2" for="confirmPassword">
						Confirm Password
					</label>
					<input
						id="confirmPassword"
						type="password"
						placeholder="••••••••"
						class="w-full px-4 py-3 bg-base-300 border border-base-100 rounded-lg text-base-content placeholder:text-base-content/30 focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/30 transition-all"
						bind:value={confirmPassword}
						disabled={$loading}
					/>
				</div>

				<button
					type="submit"
					class="w-full btn btn-primary btn-lg font-semibold gap-2 mt-2"
					disabled={$loading}
				>
					{#if $loading}
						<span class="loading loading-spinner loading-sm"></span>
					{/if}
					Create Account
				</button>
			</form>

			<div class="relative my-6">
				<div class="absolute inset-0 flex items-center">
					<div class="w-full border-t border-base-300"></div>
				</div>
				<div class="relative flex justify-center">
					<span class="px-4 text-sm text-base-content/40 bg-base-200">or continue with</span>
				</div>
			</div>

			<button
				type="button"
				class="w-full btn btn-outline btn-lg gap-3 hover:bg-base-300 hover:border-base-300"
				on:click={handleGoogleLogin}
				disabled={$loading}
			>
				<svg class="w-5 h-5" viewBox="0 0 24 24">
					<path
						fill="#4285F4"
						d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
					/>
					<path
						fill="#34A853"
						d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
					/>
					<path
						fill="#FBBC05"
						d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
					/>
					<path
						fill="#EA4335"
						d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
					/>
				</svg>
				Continue with Google
			</button>

			<p class="text-center text-sm text-base-content/50 mt-6">
				Already have an account?
				<a href="/login" class="text-primary hover:text-primary/80 transition-colors font-medium">
					Sign in
				</a>
			</p>
		</div>
	</div>
</div>
