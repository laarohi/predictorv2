/**
 * Authentication API functions.
 */

import { api } from './client';
import type { Token, User, UserCreate, UserLogin, PasswordChange, UserStats } from '$types';

export async function register(data: UserCreate): Promise<Token> {
	return api.post<Token>('/auth/register', data);
}

export async function login(data: UserLogin): Promise<Token> {
	return api.post<Token>('/auth/login', data);
}

export async function getCurrentUser(): Promise<User> {
	return api.get<User>('/auth/me');
}

export function getGoogleAuthUrl(): string {
	return '/api/auth/google';
}

export async function changePassword(
	data: PasswordChange
): Promise<{ message: string; access_token: string }> {
	// The backend revokes all outstanding tokens (token_version bump) and
	// returns a fresh one so this session can stay signed in.
	return api.post<{ message: string; access_token: string }>('/auth/me/password', data);
}

export async function getUserStats(): Promise<UserStats> {
	return api.get<UserStats>('/auth/me/stats');
}

// Magic-link login

export async function requestMagicLink(email: string): Promise<{ status: string }> {
	return api.post<{ status: string }>('/auth/magic-link/request', { email });
}

export async function verifyMagicLink(token: string): Promise<Token> {
	return api.post<Token>('/auth/magic-link/verify', { token });
}
