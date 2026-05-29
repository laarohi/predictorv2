/**
 * API client for communicating with the backend.
 */

import type { ApiError } from '$types';

const API_BASE = '/api';

export class ApiClient {
	private token: string | null = null;
	private onUnauthorized: (() => void) | null = null;

	setToken(token: string | null) {
		this.token = token;
	}

	/**
	 * Register a handler invoked when any request returns 401. The auth store
	 * uses this to clear the dead token and bounce to /login, rather than the
	 * client importing the store (which would create an import cycle).
	 */
	setUnauthorizedHandler(handler: (() => void) | null) {
		this.onUnauthorized = handler;
	}

	private async request<T>(
		endpoint: string,
		options: RequestInit = {}
	): Promise<T> {
		const url = `${API_BASE}${endpoint}`;
		                const headers: Record<string, string> = {
		                        'Content-Type': 'application/json',
		                        ...(options.headers as Record<string, string> || {})
		                };
		
		                if (this.token) {
		                        headers['Authorization'] = `Bearer ${this.token}`;
		                }
		const response = await fetch(url, {
			...options,
			headers
		});

		if (!response.ok) {
			// A 401 means the session is invalid/expired — let the auth layer
			// clear it and redirect before we surface the error.
			if (response.status === 401) {
				this.onUnauthorized?.();
			}
			const error: ApiError = await response.json().catch(() => ({
				detail: `HTTP ${response.status}: ${response.statusText}`
			}));
			throw new Error(error.detail);
		}

		// Handle empty responses
		const text = await response.text();
		if (!text) {
			return {} as T;
		}

		return JSON.parse(text);
	}

	async get<T>(endpoint: string): Promise<T> {
		return this.request<T>(endpoint, { method: 'GET' });
	}

	async post<T>(endpoint: string, data?: unknown): Promise<T> {
		return this.request<T>(endpoint, {
			method: 'POST',
			body: data ? JSON.stringify(data) : undefined
		});
	}

	async put<T>(endpoint: string, data?: unknown): Promise<T> {
		return this.request<T>(endpoint, {
			method: 'PUT',
			body: data ? JSON.stringify(data) : undefined
		});
	}

	async patch<T>(endpoint: string, data?: unknown): Promise<T> {
		return this.request<T>(endpoint, {
			method: 'PATCH',
			body: data ? JSON.stringify(data) : undefined
		});
	}

	async delete<T>(endpoint: string): Promise<T> {
		return this.request<T>(endpoint, { method: 'DELETE' });
	}
}

export const api = new ApiClient();
