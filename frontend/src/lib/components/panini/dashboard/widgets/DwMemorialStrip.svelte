<script lang="ts">
	/**
	 * Volume-closed strip footer for the post-competition dashboard. Two
	 * tightly-laid-out lines:
	 *   left  — seal + closing summary ("VOL. I CLOSED · 19 Jul · ARG 3–1 FRA")
	 *   right — teaser for the next edition
	 */
	export let sealGlyph: string = '★';
	export let leftHtml: string = '';
	export let rightHtml: string = '';
</script>

<div class="pn-final-strip">
	<div class="left">
		<div class="seal">{sealGlyph}</div>
		<span>{@html leftHtml}</span>
	</div>
	<span>{@html rightHtml}</span>
</div>
