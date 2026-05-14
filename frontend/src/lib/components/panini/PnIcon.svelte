<script lang="ts">
	// Bold, geometric pictograms in the PANINI style. All icons are 24×24 viewBox,
	// currentColor-friendly by default. Size + stroke are controlled via props.
	import type { IconName } from '$types/panini';

	export let name: IconName;
	export let size: number = 18;
	export let color: string = 'currentColor';
	export let stroke: number = 2;
</script>

<svg
	width={size}
	height={size}
	viewBox="0 0 24 24"
	fill="none"
	stroke={color}
	stroke-width={stroke}
	stroke-linecap="round"
	stroke-linejoin="round"
	style="--ic-color: {color};"
	aria-hidden="true"
>
	{#if name === 'ball'}
		<circle cx="12" cy="12" r="9" fill={color} />
		<polygon points="12,7 16,10 14.5,14.5 9.5,14.5 8,10" fill="#fff" stroke="#fff" />
	{:else if name === 'home'}
		<path d="M3 11l9-7 9 7v9a1 1 0 01-1 1h-5v-6h-6v6H4a1 1 0 01-1-1z" fill={color} />
	{:else if name === 'predict'}
		<rect x="4" y="4" width="16" height="16" rx="1" fill={color} />
		<path d="M8 12l3 3 5-6" stroke="#fff" stroke-width="2.5" />
	{:else if name === 'bracket'}
		<path
			d="M4 4v16M20 4v16M4 8h4v8H4M20 8h-4v8h4M8 12h4M12 12h4"
			stroke={color}
			fill="none"
			stroke-width="2.2"
		/>
	{:else if name === 'trophy'}
		<path d="M7 4h10v4a5 5 0 01-10 0V4z" fill={color} />
		<path d="M5 4H3v2a3 3 0 003 3M19 4h2v2a3 3 0 01-3 3" stroke={color} fill="none" />
		<path d="M10 14h4v4h-4z M8 20h8" fill={color} />
	{:else if name === 'list'}
		<rect x="3" y="5" width="18" height="3" fill={color} />
		<rect x="3" y="11" width="18" height="3" fill={color} />
		<rect x="3" y="17" width="18" height="3" fill={color} />
	{:else if name === 'flag'}
		<path d="M5 3v18M5 4h14l-3 5 3 5H5" fill={color} stroke={color} />
	{:else if name === 'target'}
		<circle cx="12" cy="12" r="9" fill={color} />
		<circle cx="12" cy="12" r="6" fill="#fff" />
		<circle cx="12" cy="12" r="3" fill={color} />
	{:else if name === 'chevron-right'}
		<path d="M9 6l6 6-6 6" />
	{:else if name === 'chevron-left'}
		<path d="M15 6l-6 6 6 6" />
	{:else if name === 'arrow-up'}
		<path d="M12 19V5M5 12l7-7 7 7" />
	{:else if name === 'arrow-down'}
		<path d="M12 5v14M5 12l7 7 7-7" />
	{:else if name === 'minus'}
		<path d="M5 12h14" />
	{:else if name === 'star'}
		<polygon
			points="12,2 15,9 22,9.5 16.5,14 18.5,21 12,17 5.5,21 7.5,14 2,9.5 9,9"
			fill={color}
			stroke={color}
		/>
	{:else if name === 'lock'}
		<rect x="5" y="11" width="14" height="10" rx="1" fill={color} />
		<path d="M8 11V7a4 4 0 018 0v4" stroke={color} fill="none" stroke-width="2.2" />
	{:else if name === 'clock'}
		<circle cx="12" cy="12" r="9" fill={color} />
		<path d="M12 7v5l3 2" stroke="#fff" stroke-width="2.2" />
	{:else if name === 'whistle'}
		<circle cx="9" cy="13" r="5" fill={color} />
		<rect x="13" y="9" width="9" height="3" fill={color} />
	{:else if name === 'cog'}
		<circle cx="12" cy="12" r="3" fill={color} />
		<path
			d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 01-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.6 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.6a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09A1.65 1.65 0 0015 4.6a1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"
			fill="none"
			stroke={color}
			stroke-width="2"
		/>
	{:else}
		<circle cx="12" cy="12" r="9" />
	{/if}
</svg>
