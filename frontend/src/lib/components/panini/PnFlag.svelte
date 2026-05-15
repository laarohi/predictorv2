<script lang="ts">
	// Two- or three-stripe horizontal flag swatch. Not a real flag — a stylised
	// sticker-album substitute that reads as a colour-coded country chip.
	// Codes are FIFA three-letter; unknown codes fall back to a neutral grey.

	export let code: string;
	export let w: number = 18;
	export let h: number = 12;
	export let border: boolean = true;

	const FLAGS: Record<string, string[]> = {
		ARG: ['#74acdf', '#ffffff', '#74acdf'],
		BRA: ['#009c3b', '#fedf00'],
		FRA: ['#012169', '#ed2939'],
		ESP: ['#aa151b', '#f1bf00'],
		GER: ['#000000', '#dd0000', '#ffce00'],
		ITA: ['#009246', '#ffffff', '#ce2b37'],
		POR: ['#005826', '#ed2939'],
		NED: ['#ae1c28', '#ffffff', '#21468b'],
		CRO: ['#ed1c24', '#ffffff', '#171796'],
		ENG: ['#ffffff', '#cf142b'],
		URU: ['#75aadb', '#ffffff'],
		MAR: ['#c1272d', '#006233'],
		JPN: ['#bc002d', '#ffffff'],
		MEX: ['#006847', '#ffffff', '#ce1126'],
		KOR: ['#cd2e3a', '#ffffff', '#0047a0'],
		USA: ['#bf0a30', '#ffffff', '#002868'],
		POL: ['#ffffff', '#dc143c'],
		BEL: ['#000000', '#fae042', '#ed2939'],
		SUI: ['#dc143c', '#ffffff'],
		SEN: ['#00853f', '#fdef42', '#e31b23'],
		GHA: ['#ce1126', '#fcd116', '#006b3f'],
		TUN: ['#e70013', '#ffffff'],
		EGY: ['#ce1126', '#ffffff', '#000000'],
		IRN: ['#239f40', '#ffffff', '#da0000'],
		AUS: ['#00008b', '#ffffff'],
		CAN: ['#ff0000', '#ffffff'],
		KSA: ['#006c35', '#ffffff'],
		DEN: ['#c60c30', '#ffffff'],
		COL: ['#fcd116', '#003893', '#ce1126'],
		NGA: ['#008751', '#ffffff', '#008751'],
		ECU: ['#ffdd00', '#003893', '#ce1126'],
		SRB: ['#c6363c', '#0c4076', '#ffffff']
	};

	$: colors = FLAGS[code] ?? ['#888', '#444'];
	$: bg =
		colors.length === 3
			? `linear-gradient(180deg, ${colors[0]} 33%, ${colors[1]} 33% 66%, ${colors[2]} 66%)`
			: `linear-gradient(180deg, ${colors[0]} 50%, ${colors[1]} 50%)`;
</script>

<span
	style="background: {bg}; width: {w}px; height: {h}px; display: inline-block; border: {border
		? '1.5px solid #161513'
		: '0'}; flex-shrink: 0;"
	aria-label={code}
	role="img"
></span>
