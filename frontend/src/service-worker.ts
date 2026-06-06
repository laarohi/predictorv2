/// <reference types="@sveltejs/kit" />
/// <reference lib="webworker" />

// Web Push service worker. SvelteKit auto-registers this in production builds
// (kit.serviceWorker.register defaults to true); it is NOT registered in dev,
// so push is exercised on prod only. Scope is '/' (app root). This worker does
// NOT do offline caching — it only receives pushes and routes notification
// taps.

const sw = self as unknown as ServiceWorkerGlobalScope;

// Activate a new worker immediately so push-handler fixes propagate without
// waiting for every (rarely-closed) PWA window to close first.
sw.addEventListener('install', () => {
	sw.skipWaiting();
});
sw.addEventListener('activate', (event) => {
	event.waitUntil(sw.clients.claim());
});

interface PushPayload {
	title?: string;
	body?: string;
	url?: string;
}

sw.addEventListener('push', (event) => {
	let payload: PushPayload = {};
	try {
		payload = (event.data?.json() as PushPayload) ?? {};
	} catch {
		payload = { body: event.data?.text() };
	}

	const title = payload.title ?? 'CxF Predictaa';
	// iOS REVOKES the subscription if a push arrives and we don't show a
	// notification — there is no silent push. Always showNotification, always
	// inside waitUntil so the worker isn't torn down mid-handler.
	event.waitUntil(
		sw.registration.showNotification(title, {
			body: payload.body ?? '',
			icon: '/icon-192.png',
			badge: '/icon-192.png',
			data: { url: payload.url ?? '/' }
		})
	);
});

sw.addEventListener('notificationclick', (event) => {
	event.notification.close();
	const data = event.notification.data as { url?: string } | undefined;
	const target = new URL(data?.url ?? '/', sw.location.origin).href;

	event.waitUntil(
		(async () => {
			const clients = (await sw.clients.matchAll({
				type: 'window',
				includeUncontrolled: true
			})) as readonly WindowClient[];

			// 1) A window already on the target page — just focus it (no reload).
			for (const client of clients) {
				if (client.url === target) {
					await client.focus();
					return;
				}
			}
			// 2) Otherwise focus an existing window and navigate it there; if that
			//    isn't permitted (uncontrolled tab), fall back to a fresh window.
			const existing = clients[0];
			if (existing) {
				await existing.focus();
				if ('navigate' in existing) {
					try {
						await existing.navigate(target);
						return;
					} catch {
						/* fall through to openWindow */
					}
				}
			}
			await sw.clients.openWindow(target);
		})()
	);
});
