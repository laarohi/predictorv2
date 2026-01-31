/**
 * Authentication API functions.
 */

import { api } from './client';
import type { Token, User, UserCreate, UserLogin } from '$types';

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
