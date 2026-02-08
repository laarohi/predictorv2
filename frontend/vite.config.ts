import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	server: {
		port: 5173,
		proxy: {
			'/api': {
				target: process.env.VITE_API_TARGET || 'http://backend:8000',
				changeOrigin: true
			}
		}
	}
});
