/**
 * Web Push opt-in helpers — wraps both the backend API and the browser
 * Push API dance, so the UI component stays declarative.
 */

import { api } from '$api/client';

export type EnablePushResult = 'enabled' | 'denied' | 'dismissed' | 'unsupported' | 'error';

/** Feature-detect Web Push. False on browsers without SW/Push/Notification. */
export function pushSupported(): boolean {
	return (
		typeof window !== 'undefined' &&
		'serviceWorker' in navigator &&
		'PushManager' in window &&
		'Notification' in window
	);
}

/** Is the app running as an installed (home-screen) PWA? */
export function isStandalone(): boolean {
	if (typeof window === 'undefined') return false;
	const iosStandalone = (navigator as Navigator & { standalone?: boolean }).standalone === true;
	return window.matchMedia?.('(display-mode: standalone)').matches || iosStandalone;
}

/** iPhone/iPad (incl. iPadOS masquerading as Mac). Drives the "install first" hint. */
export function isIos(): boolean {
	if (typeof navigator === 'undefined') return false;
	return (
		/iphone|ipad|ipod/i.test(navigator.userAgent) ||
		(navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)
	);
}

/** Current OS-level permission, or 'unsupported'. */
export function notificationPermission(): NotificationPermission | 'unsupported' {
	if (!pushSupported()) return 'unsupported';
	return Notification.permission;
}

async function getVapidPublicKey(): Promise<string> {
	const res = await api.get<{ key: string }>('/push/vapid-public-key');
	return res.key;
}

async function subscribePush(sub: PushSubscriptionJSON): Promise<void> {
	await api.post('/push/subscribe', sub);
}

async function unsubscribePush(endpoint: string): Promise<void> {
	await api.post('/push/unsubscribe', { endpoint });
}

export async function sendTestPush(): Promise<number> {
	const res = await api.post<{ sent: number }>('/push/test');
	return res.sent;
}

/** Is THIS device's subscription active server-side (vs merely present in the browser)? */
export async function getPushStatus(endpoint: string): Promise<boolean> {
	const res = await api.post<{ active: boolean }>('/push/status', { endpoint });
	return res.active;
}

/**
 * Enable push: request permission, subscribe via the service worker, and
 * register the subscription with the backend.
 *
 * MUST be called directly from a click/tap handler — iOS silently denies
 * Notification.requestPermission() outside a user gesture, so it runs first
 * with only a synchronous support-check before it.
 */
export async function enablePush(): Promise<EnablePushResult> {
	if (!pushSupported()) return 'unsupported';

	const permission = await Notification.requestPermission();
	if (permission === 'denied') return 'denied';
	if (permission !== 'granted') return 'dismissed'; // 'default' — prompt dismissed

	try {
		const key = await getVapidPublicKey();
		if (!key) return 'unsupported'; // backend has no VAPID configured
		const desiredKey = urlBase64ToUint8Array(key);

		const registration = await navigator.serviceWorker.ready;
		let subscription = await registration.pushManager.getSubscription();
		if (subscription && !sameApplicationServerKey(subscription, desiredKey)) {
			// VAPID key changed (rotation, or minted against a different key) — the
			// stale subscription would fail VAPID verification (403) on every push
			// forever, so drop it and re-mint against the current key.
			await subscription.unsubscribe();
			subscription = null;
		}
		if (!subscription) {
			subscription = await registration.pushManager.subscribe({
				userVisibleOnly: true,
				applicationServerKey: desiredKey
			});
		}
		await subscribePush(subscription.toJSON());
		return 'enabled';
	} catch (e) {
		console.error('[push] enable failed', e);
		return 'error';
	}
}

/**
 * Disable push by deactivating the subscription server-side. We deliberately
 * do NOT browser-unsubscribe: iOS won't let us silently re-subscribe later, so
 * keeping the browser subscription makes re-enabling instant.
 */
export async function disablePush(): Promise<void> {
	if (!pushSupported()) return;
	const registration = await navigator.serviceWorker.ready;
	const subscription = await registration.pushManager.getSubscription();
	if (subscription?.endpoint) {
		await unsubscribePush(subscription.endpoint);
	}
}

/** Does the existing subscription's applicationServerKey match the current VAPID key? */
function sameApplicationServerKey(
	subscription: PushSubscription,
	desired: Uint8Array<ArrayBuffer>
): boolean {
	const current = subscription.options.applicationServerKey;
	if (!current) return false;
	const a = new Uint8Array(current);
	if (a.length !== desired.length) return false;
	for (let i = 0; i < a.length; i++) {
		if (a[i] !== desired[i]) return false;
	}
	return true;
}

/** Convert a base64url VAPID public key to the Uint8Array applicationServerKey. */
function urlBase64ToUint8Array(base64String: string): Uint8Array<ArrayBuffer> {
	const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
	const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
	const raw = atob(base64);
	const buffer = new ArrayBuffer(raw.length);
	const output = new Uint8Array(buffer);
	for (let i = 0; i < raw.length; i++) {
		output[i] = raw.charCodeAt(i);
	}
	return output;
}
