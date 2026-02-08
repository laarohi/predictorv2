<script lang="ts">
	type IconName = 'lock' | 'check' | 'clock' | 'trash';

	export let name: IconName;
	let className = '';
	export { className as class };

	const paths: Record<IconName, { d: string; strokeWidth?: number }[]> = {
		lock: [
			{ d: 'M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z', strokeWidth: 2 }
		],
		check: [
			{ d: 'M5 13l4 4L19 7', strokeWidth: 2.5 }
		],
		clock: [
			{ d: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z', strokeWidth: 2 }
		],
		trash: [
			{ d: 'M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16', strokeWidth: 2 }
		]
	};
</script>

<svg class={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
	{#each paths[name] as { d, strokeWidth }}
		<path
			stroke-linecap="round"
			stroke-linejoin="round"
			stroke-width={strokeWidth ?? 2}
			{d}
		/>
	{/each}
</svg>
