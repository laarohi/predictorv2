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

export async function changePassword(data: PasswordChange): Promise<{ message: string }> {
	return api.post<{ message: string }>('/auth/me/password', data);
}

export async function getUserStats(): Promise<UserStats> {
	return api.get<UserStats>('/auth/me/stats');
}
