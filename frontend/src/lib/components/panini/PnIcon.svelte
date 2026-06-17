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
	{#if name === 'ghost'}
		<!-- classic sheet ghost: dome head, wavy hem, two eyes -->
		<path
			d="M12 3a7 7 0 00-7 7v10.5l2.33-2 2.33 2 2.34-2 2.34 2 2.33-2 2.33 2V10a7 7 0 00-7-7z"
			fill={color}
			stroke="none"
		/>
		<circle cx="9.5" cy="10.5" r="1.4" fill="#fff" stroke="none" />
		<circle cx="14.5" cy="10.5" r="1.4" fill="#fff" stroke="none" />
	{:else if name === 'ball'}
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
		<path d="M6 3h12v4a6 6 0 0 1-12 0z" fill={color} stroke="none" />
		<path d="M6 4H2.5v2.2A3.5 3.5 0 0 0 6 9.7M18 4h3.5v2.2A3.5 3.5 0 0 1 18 9.7" fill="none" stroke={color} stroke-width="2" />
		<rect x="10" y="13" width="4" height="4.5" fill={color} stroke="none" />
		<rect x="6.5" y="19.5" width="11" height="2.6" rx="1" fill={color} stroke="none" />
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
			stroke="none"
		/>
	{:else if name === 'lock'}
		<rect x="5" y="11" width="14" height="10" rx="1" fill={color} />
		<path d="M8 11V7a4 4 0 018 0v4" stroke={color} fill="none" stroke-width="2.2" />
	{:else if name === 'clock'}
		<circle cx="12" cy="12" r="9" fill={color} />
		<path d="M12 7v5l3 2" stroke="#fff" stroke-width="2.2" />
	{:else if name === 'whistle'}
		<path d="M3 9h12a5 5 0 1 1-5 5v-2H3a1.5 1.5 0 0 1 0-3z" fill={color} stroke="none" />
		<rect x="6" y="5.5" width="5.5" height="2.4" rx="1.2" fill={color} stroke="none" />
		<circle cx="13" cy="14" r="2.1" fill="#fff" stroke="none" />
	{:else if name === 'user'}
		<circle cx="12" cy="8" r="4" fill={color} />
		<path d="M4 21v-1a6 6 0 016-6h4a6 6 0 016 6v1" fill={color} stroke={color} />
	{:else if name === 'cog'}
		<circle cx="12" cy="12" r="3" fill={color} />
		<path
			d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 01-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.6 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.6a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09A1.65 1.65 0 0015 4.6a1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"
			fill="none"
			stroke={color}
			stroke-width="2"
		/>
	{:else if name === 'crown'}
		<!-- 3-point crown: rounded jewel tips, a solid band, three gems on the band -->
		<path d="M4 18V9.5L8 12 12 5.5 16 12 20 9.5V18Z" fill={color} stroke="none" />
		<circle cx="4" cy="9" r="1.6" fill={color} stroke="none" />
		<circle cx="12" cy="5" r="1.8" fill={color} stroke="none" />
		<circle cx="20" cy="9" r="1.6" fill={color} stroke="none" />
		<rect x="4" y="17.4" width="16" height="3.6" rx="0.7" fill={color} stroke="none" />
		<circle cx="8" cy="19.2" r="0.95" fill="#fff" stroke="none" />
		<circle cx="12" cy="19.2" r="0.95" fill="#fff" stroke="none" />
		<circle cx="16" cy="19.2" r="0.95" fill="#fff" stroke="none" />
	{:else if name === 'flame'}
		<!-- Filled adaptation of Lucide's "flame" (MIT) for the bold Panini style. -->
		<path
			d="M12 3q1 4 4 6.5t3 5.5a1 1 0 0 1-14 0 5 5 0 0 1 1-3 1 1 0 0 0 5 0c0-2-1.5-3-1.5-5q0-2 2.5-4"
			fill={color}
			stroke="none"
		/>
	{:else if name === 'skull'}
		<!-- Lucide "skull" (MIT) as one filled path; the eyes + nose are evenodd
		     cut-outs, so the background shows THROUGH the sockets (true holes,
		     not white fills) — gives the watermark real depth. -->
		<path
			fill-rule="evenodd"
			d="M15 22a1 1 0 0 0 1-1v-1a2 2 0 0 0 1.56-3.25 8 8 0 1 0-11.12 0A2 2 0 0 0 8 20v1a1 1 0 0 0 1 1zM9 10.5a1.5 1.5 0 1 0 0 3 1.5 1.5 0 1 0 0-3zM15 10.5a1.5 1.5 0 1 0 0 3 1.5 1.5 0 1 0 0-3zM12 15.6l-0.8 1.7h1.6z"
			fill={color}
			stroke="none"
		/>
	{:else if name === 'snowflake'}
		<g fill={color} stroke="none">
			<rect x="10.7" y="2" width="2.6" height="20" rx="1" />
			<rect x="10.7" y="2" width="2.6" height="20" rx="1" transform="rotate(60 12 12)" />
			<rect x="10.7" y="2" width="2.6" height="20" rx="1" transform="rotate(120 12 12)" />
			<circle cx="12" cy="12" r="2.2" fill="#fff" />
		</g>
	{:else if name === 'bolt'}
		<path d="M13 2L4 14h6l-1 8 9-12h-6z" fill={color} stroke={color} />
	{:else if name === 'medal'}
		<path d="M9 2.2l3 5.4 3-5.4 2.3 1.2-3 5.5-2.3-1.2-2.3 1.2-3-5.5z" fill={color} stroke="none" />
		<circle cx="12" cy="15.5" r="6.3" fill={color} stroke="none" />
		<polygon
			points="12,11.7 13.05,14.05 15.6,14.2 13.6,15.85 14.25,18.35 12,16.9 9.75,18.35 10.4,15.85 8.4,14.2 10.95,14.05"
			fill="#fff"
			stroke="none"
		/>
	{:else if name === 'chart'}
		<rect x="3" y="13" width="4" height="8" rx="0.6" fill={color} stroke="none" />
		<rect x="10" y="8" width="4" height="13" rx="0.6" fill={color} stroke="none" />
		<rect x="17" y="3.5" width="4" height="17.5" rx="0.6" fill={color} stroke="none" />
	{:else if name === 'money'}
		<!-- banknote: a bill with a bold $ and two denomination pips -->
		<rect x="2" y="6.5" width="20" height="11" rx="2" fill={color} stroke="none" />
		<circle cx="5" cy="12" r="0.9" fill="#fff" stroke="none" />
		<circle cx="19" cy="12" r="0.9" fill="#fff" stroke="none" />
		<g
			transform="translate(12 12) scale(0.42) translate(-11.5 -12)"
			stroke="#fff"
			stroke-width="5"
			fill="none"
			stroke-linecap="round"
			stroke-linejoin="round"
		>
			<line x1="12" x2="12" y1="2" y2="22" />
			<path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
		</g>
	{:else if name === 'crystal-ball'}
		<circle cx="12" cy="10" r="7.5" fill={color} stroke="none" />
		<rect x="5" y="18" width="14" height="3" rx="1.2" fill={color} stroke="none" />
		<circle cx="9.5" cy="7.5" r="2" fill="#fff" stroke="none" />
	{:else if name === 'glasses'}
		<!-- round-lens hipster spectacles: thick frames, arched nose bridge, temples -->
		<path
			d="M2.6 11.2 1.1 8.7M21.4 11.2 22.9 8.7"
			fill="none"
			stroke={color}
			stroke-width="1.9"
			stroke-linecap="round"
		/>
		<circle cx="6.7" cy="13.3" r="4.5" fill={color} stroke="none" />
		<circle cx="17.3" cy="13.3" r="4.5" fill={color} stroke="none" />
		<path
			d="M10.7 11.7q1.3-1.3 2.6 0"
			fill="none"
			stroke={color}
			stroke-width="1.8"
			stroke-linecap="round"
		/>
		<circle cx="6.7" cy="13.3" r="2.1" fill="#fff" stroke="none" />
		<circle cx="17.3" cy="13.3" r="2.1" fill="#fff" stroke="none" />
	{:else if name === 'pen-nib'}
		<path d="M12 2.5 16 6.5 8.5 19l-4 2.5 1.5-4.4z" fill={color} stroke="none" />
		<path d="M12 2.5 16 6.5" stroke="#fff" stroke-width="1.4" />
		<circle cx="9.4" cy="14.6" r="1.5" fill="#fff" stroke="none" />
	{:else if name === 'quote'}
		<path
			d="M4 6h6v6q0 5-5 6v-3q2-.6 2-3H4zM14 6h6v6q0 5-5 6v-3q2-.6 2-3h-3z"
			fill={color}
			stroke="none"
		/>
	{:else if name === 'replay'}
		<!-- counter-clockwise circular arrow (rotate-ccw) -->
		<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" fill="none" stroke={color} />
		<path d="M3 3v5h5" fill="none" stroke={color} />
	{:else if name === 'close'}
		<path d="M6 6l12 12M18 6 6 18" fill="none" stroke={color} />
	{:else if name === 'help'}
		<!-- "Clueless": a bold filled disc with a white question mark (matches the
		     filled-glyph family: clock, target, crystal-ball). -->
		<circle cx="12" cy="12" r="9" fill={color} stroke="none" />
		<path
			d="M9.2 9.3a3 3 0 0 1 5.6 1.2c0 2-2.7 2.3-2.7 4"
			fill="none"
			stroke="#fff"
			stroke-width="2.2"
		/>
		<circle cx="12" cy="17.2" r="1.3" fill="#fff" stroke="none" />
	{:else}
		<circle cx="12" cy="12" r="9" />
	{/if}
</svg>
