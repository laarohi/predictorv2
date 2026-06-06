<script lang="ts">
	import { onMount } from 'svelte';
	import {
		pushSupported,
		isStandalone,
		isIos,
		enablePush,
		disablePush,
		sendTestPush,
		sendTestSamples,
		getPushStatus
	} from '$api/push';
	import { isAdmin } from '$stores/auth';

	let supported = false;
	let ios = false;
	let standalone = false;
	let permission: NotificationPermission | 'unsupported' = 'unsupported';
	let enabled = false;

	let busy = false;
	let testBusy = false;
	let sampleBusy = false;
	let message: string | null = null;
	let messageKind: 'ok' | 'error' = 'ok';

	onMount(async () => {
		supported = pushSupported();
		if (!supported) return;
		ios = isIos();
		standalone = isStandalone();
		permission = Notification.permission;
		if (permission === 'granted') {
			// getRegistration() (not .ready) so this resolves instead of hanging
			// in dev, where SvelteKit doesn't register the service worker.
			const reg = await navigator.serviceWorker.getRegistration();
			if (reg) {
				const sub = await reg.pushManager.getSubscription();
				// Reconcile with the server: a browser subscription can outlive a
				// server-side deactivation (logout/disable keep it), so the backend
				// 'active' flag is the source of truth for whether we're really on.
				enabled = sub ? await getPushStatus(sub.endpoint).catch(() => false) : false;
			}
		}
	});

	async function handleEnable() {
		busy = true;
		message = null;
		const result = await enablePush();
		permission = supported ? Notification.permission : 'unsupported';
		if (result === 'enabled') {
			enabled = true;
			message = 'Notifications enabled on this device.';
			messageKind = 'ok';
		} else if (result === 'denied') {
			message = 'Permission denied. Re-enable notifications in your device Settings.';
			messageKind = 'error';
		} else if (result === 'unsupported') {
			message = "Push notifications aren't available here.";
			messageKind = 'error';
		} else if (result === 'dismissed') {
			message = "You haven't allowed notifications yet — tap Enable to try again.";
			messageKind = 'error';
		} else {
			message = 'Something went wrong enabling notifications.';
			messageKind = 'error';
		}
		busy = false;
	}

	async function handleDisable() {
		busy = true;
		message = null;
		try {
			await disablePush();
			enabled = false;
			message = 'Notifications turned off.';
			messageKind = 'ok';
		} catch {
			message = "Couldn't turn off notifications.";
			messageKind = 'error';
		}
		busy = false;
	}

	async function handleTest() {
		testBusy = true;
		message = null;
		try {
			const sent = await sendTestPush();
			message =
				sent > 0
					? `Test notification sent to ${sent} device${sent === 1 ? '' : 's'}.`
					: 'No active devices to send to.';
			messageKind = sent > 0 ? 'ok' : 'error';
		} catch {
			message = 'Test failed to send.';
			messageKind = 'error';
		}
		testBusy = false;
	}

	async function handleSampleTest() {
		sampleBusy = true;
		message = null;
		try {
			const res = await sendTestSamples();
			message = `Sending ${res.scheduled} sample alerts ~${res.interval_seconds}s apart — lock your phone and watch.`;
			messageKind = 'ok';
		} catch {
			message = 'Could not start the sample alerts.';
			messageKind = 'error';
		}
		sampleBusy = false;
	}
</script>

<section class="pn-pf-section">
	<div class="h"><span>Notifications</span><span class="right">Web Push</span></div>
	<div class="body">
		<p class="pn-push-lede">
			Get a buzz for prediction lock reminders, your results &amp; points, and when the knockouts
			open.
		</p>

		{#if message}
			<div class="pn-pf-alert {messageKind === 'error' ? 'error' : 'success'}" style="margin-bottom: 12px;">
				{message}
			</div>
		{/if}

		{#if !supported}
			<p class="pn-push-note">Your browser doesn't support push notifications.</p>
		{:else if ios && !standalone}
			<p class="pn-push-note">
				On iPhone, first add CxF Predictaa to your Home Screen (Share → Add to Home Screen), open it
				from the icon, then enable notifications here.
			</p>
		{:else if permission === 'denied'}
			<p class="pn-push-note">
				Notifications are blocked. Re-enable them for this app in your device Settings, then reload.
			</p>
		{:else if enabled}
			<div class="pn-pf-alert success" style="margin-bottom: 12px;">
				✓ Notifications are on for this device.
			</div>
			<div class="pn-push-actions">
				<button class="pn-btn ghost" type="button" on:click={handleDisable} disabled={busy}>
					{busy ? 'Turning off…' : 'Turn off'}
				</button>
				<button class="pn-btn" type="button" on:click={handleTest} disabled={testBusy}>
					{testBusy ? 'Sending…' : 'Send test'}
				</button>
				{#if $isAdmin}
					<button class="pn-btn ghost" type="button" on:click={handleSampleTest} disabled={sampleBusy}>
						{sampleBusy ? 'Starting…' : 'Preview all alerts'}
					</button>
				{/if}
			</div>
		{:else}
			<button class="pn-btn" type="button" on:click={handleEnable} disabled={busy}>
				{busy ? 'Enabling…' : 'Enable notifications'}
			</button>
		{/if}
	</div>
</section>

<style>
	.pn-push-lede {
		font-family: var(--body);
		font-size: 13px;
		line-height: 1.5;
		color: var(--ink-2);
		margin: 0 0 12px;
	}
	.pn-push-note {
		font-family: var(--body);
		font-size: 12px;
		line-height: 1.5;
		color: var(--ink-3);
		margin: 0;
	}
	.pn-push-actions {
		display: flex;
		gap: 10px;
		flex-wrap: wrap;
	}
</style>
