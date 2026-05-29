import { describe, it, expect, vi, afterEach } from 'vitest';
import { ApiClient } from './client';

function mockResponse({ ok, status, body }: { ok: boolean; status: number; body: unknown }): Response {
	return {
		ok,
		status,
		statusText: 'status',
		json: async () => body,
		text: async () => JSON.stringify(body)
	} as unknown as Response;
}

afterEach(() => {
	vi.unstubAllGlobals();
	vi.restoreAllMocks();
});

describe('ApiClient 401 handling (FLOW-2)', () => {
	it('invokes the unauthorized handler on 401 and still throws', async () => {
		const client = new ApiClient();
		const onUnauth = vi.fn();
		client.setUnauthorizedHandler(onUnauth);
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue(
				mockResponse({ ok: false, status: 401, body: { detail: 'Could not validate credentials' } })
			)
		);
		await expect(client.get('/auth/me')).rejects.toThrow('Could not validate credentials');
		expect(onUnauth).toHaveBeenCalledTimes(1);
	});

	it('does not invoke the handler on a successful response', async () => {
		const client = new ApiClient();
		const onUnauth = vi.fn();
		client.setUnauthorizedHandler(onUnauth);
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue(mockResponse({ ok: true, status: 200, body: { ok: true } })));
		await client.get('/x');
		expect(onUnauth).not.toHaveBeenCalled();
	});

	it('does not invoke the handler on a non-401 error (e.g. 500)', async () => {
		const client = new ApiClient();
		const onUnauth = vi.fn();
		client.setUnauthorizedHandler(onUnauth);
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue(mockResponse({ ok: false, status: 500, body: { detail: 'boom' } })));
		await expect(client.get('/x')).rejects.toThrow('boom');
		expect(onUnauth).not.toHaveBeenCalled();
	});
});
