/** @type {import('tailwindcss').Config} */
export default {
	content: ['./src/**/*.{html,js,svelte,ts}'],
	theme: {
		extend: {
			colors: {
				// Custom colors for win/loss indicators
				'win': '#22c55e',
				'loss': '#ef4444',
				'draw': '#f59e0b'
			}
		}
	},
	plugins: [require('daisyui')],
	daisyui: {
		themes: [
			{
				predictor: {
					'primary': '#3b82f6',
					'secondary': '#8b5cf6',
					'accent': '#22c55e',
					'neutral': '#1f2937',
					'base-100': '#111827',
					'base-200': '#1f2937',
					'base-300': '#374151',
					'info': '#3abff8',
					'success': '#22c55e',
					'warning': '#f59e0b',
					'error': '#ef4444',
				}
			}
		],
		darkTheme: 'predictor'
	}
};
