import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	server: {
		port: 5173,
		// Allow access from any device on the private Tailscale tailnet
		// (Mac, phone, etc.). The leading dot makes Vite match the bare
		// domain plus all subdomains. Vite's allowedHosts check is a guard
		// against DNS-rebinding attacks; restricting to *.gazelle-mahi.ts.net
		// keeps the protection in place for non-tailnet hosts.
		allowedHosts: ['.gazelle-mahi.ts.net'],
		proxy: {
			'/api': {
				target: process.env.VITE_API_TARGET || 'http://backend:8000',
				changeOrigin: true
			}
		}
	}
});
