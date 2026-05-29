<script lang="ts">
	import { requestMagicLink } from '$api/auth';

	let email = '';
	let sending = false;
	let sent = false;
	let errorMessage = '';

	async function handleSubmit() {
		errorMessage = '';
		sent = false;
		if (!email.trim()) {
			errorMessage = 'Please enter your email address';
			return;
		}
		sending = true;
		try {
			await requestMagicLink(email);
			sent = true;
		} catch (e) {
			errorMessage = e instanceof Error ? e.message : 'Could not send the login link';
		} finally {
			sending = false;
		}
	}
</script>

<svelte:head>
	<title>Email me a login link — CxF Predictaa</title>
</svelte:head>

<div class="pn">
	<div class="pn-auth-page">
		<div class="pn-auth-card">
			<div class="pn-auth-crest">
				<div class="crest">CxF</div>
				<div class="nm">Predict<span class="aa">aa</span><span class="sub">Vol. I — WC 2026</span></div>
			</div>
			<h1 class="pn-auth-h">Email <em>login link</em></h1>

			{#if sent}
				<div
					class="pn-form-success"
					style="font-size: 13px; padding: 10px 12px; background: rgba(27,108,62,0.1); border: 1.5px solid var(--green); color: var(--green); margin-bottom: 10px;"
				>
					Check your inbox — we sent a one-time login link to <b>{email}</b>.
					It's valid for 15 minutes.
				</div>
				<p class="pn-auth-footer">
					<a href="/login">← Back to sign in</a>
				</p>
			{:else}
				<p
					style="color: var(--ink-2); font-size: 13px; line-height: 1.5; margin: 0 0 16px;"
				>
					We'll email you a one-time link that signs you in — no password required.
				</p>

				{#if errorMessage}
					<div class="pn-form-error">{errorMessage}</div>
				{/if}

				<form class="pn-form" on:submit|preventDefault={handleSubmit}>
					<div class="pn-field">
						<label for="email">Email</label>
						<input
							id="email"
							type="email"
							placeholder="your@email.com"
							bind:value={email}
							disabled={sending}
							autocomplete="email"
						/>
					</div>
					<button
						type="submit"
						class="pn-btn gold"
						style="justify-content: center; margin-top: 6px;"
						disabled={sending}
					>
						{sending ? 'Sending…' : 'Send login link'}
					</button>
				</form>

				<p class="pn-auth-footer">
					Have a password? <a href="/login">Sign in with password</a>
				</p>
			{/if}
		</div>
	</div>
</div>
