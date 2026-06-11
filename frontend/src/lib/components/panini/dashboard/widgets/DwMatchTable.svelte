<script context="module" lang="ts">
	export type RowKind = 'finished' | 'live' | 'upcoming';
	export type PickResult = 'exact' | 'outc' | 'miss';
	export type PtsVariant =
		| ''
		| 'exact'
		| 'outc'
		| 'miss'
		| 'pending-exact'
		| 'pending-outc'
		| 'pending-miss'
		| 'dash';
	export type StatusVariant = 'ft' | 'live' | 'cd' | 'cd-soon';
	export type CtaVariant = 'edit' | 'pick';

	/** Row data passed into <DwMatchTable />. The widget is purely presentational
	 * — every formatting decision (status text, points number, CTA choice) is
	 * built by the parent dashboard from fixtures + predictions + scores. */
	export type MatchTableRow = {
		/** Stable identity for keyed-each. Use fixture id. */
		id: string;
		kind: RowKind;
		/** Text shown in the Status cell ("FT", "67", "02:14:08", "1d 02h"). */
		statusText: string;
		statusVariant: StatusVariant;
		/** "A"…"L" for group stage, "R16"/"QF"/"SF"/"F" for knockout. */
		grpLabel: string;
		/** 3-letter team codes (FIFA-style). */
		home: string;
		away: string;
		/** Final or live score (h, a). null = not played yet → shows "VS". */
		score: [number, number] | null;
		/** User's pick (h, a). null = no pick → empty pill. */
		pick: [number, number] | null;
		/** Kickoff label ("WED 21:00", user-local) shown inside the score
		 * chip on upcoming rows — replaces the "VS" placeholder, so the
		 * kickoff costs no extra column. Omit to render "VS". */
		koLabel?: string;
		/** Pick result colouring on the pick pill. null = not yet scored. */
		pickResult: PickResult | null;
		/** Number shown inside the points badge (e.g. "+15", "+5", "0", "—"). */
		pointsText: string | null;
		pointsVariant: PtsVariant;
		/** CTA in the Points cell for upcoming rows. undefined = show points instead. */
		cta?: CtaVariant;
		/** Target for the CTA link (default /predictions). */
		ctaHref?: string;
		/** Row click handler (typically navigate to /results/[id]). */
		onClick?: () => void;
	};
</script>

<script lang="ts">
	import PnFlag from '$components/panini/PnFlag.svelte';

	/** Column heading for the Grp cell. Group dashboards label it "Grp",
	 * knockout dashboards label it "Rnd". */
	export let groupColumnLabel: 'Grp' | 'Rnd' = 'Grp';
	export let rows: MatchTableRow[] = [];
	/** Caption shown inside the table when `rows` is empty. */
	export let emptyText: string = 'No matches.';
	/** Target row count — short tables get padded with empty placeholder
	 * rows up to this number so side-by-side tables (Past + Upcoming)
	 * line up at the same height regardless of how many real matches
	 * each holds. Set to 0 to opt out of padding. */
	export let targetRows: number = 4;

	// Drop the Status column entirely when no row in this table needs it
	// (upcoming-only tables). The widget toggles `.no-status` on .mtab so
	// CSS can switch its grid template between 5 and 4 columns. Cells in
	// rows are conditionally rendered to match.
	$: hasStatusCol = rows.some(
		(r) => r.statusVariant === 'ft' || r.statusVariant === 'live'
	);

	// Empty placeholder rows needed to reach targetRows. Only padded when
	// at least one real row exists — a table with zero rows still falls
	// through to the .mtab-empty single-line message instead.
	$: padCount = rows.length > 0 ? Math.max(0, targetRows - rows.length) : 0;

	function handleClick(row: MatchTableRow, e: Event) {
		// Clicks on the inline CTA shouldn't bubble to the row navigation.
		const target = e.target as HTMLElement;
		if (target.closest('.cta')) return;
		row.onClick?.();
	}
	function handleKey(row: MatchTableRow, e: KeyboardEvent) {
		if (e.key === 'Enter') row.onClick?.();
	}
</script>

<div class="mtab" class:no-status={!hasStatusCol}>
	<div class="mtab-head">
		<!-- Status header intentionally has no label — the cell content
		     (FT / minute) is self-explanatory. Omitted entirely when no
		     row in the table needs it (CSS template drops to 4 columns). -->
		{#if hasStatusCol}<span class="c-status"></span>{/if}
		<span class="c-grp">{groupColumnLabel}</span>
		<span class="c-match">Match</span>
		<span class="c-pick">Pick</span>
		<span class="c-pts">Points</span>
	</div>

	{#each rows as r (r.id)}
		<div
			class="mtab-row"
			class:live={r.kind === 'live'}
			on:click={(e) => handleClick(r, e)}
			on:keydown={(e) => handleKey(r, e)}
			role={r.onClick ? 'button' : undefined}
			tabindex={r.onClick ? 0 : undefined}
		>
			<!-- Status. FT / live minute only — upcoming rows leave this
			     cell empty (the row's whole state is already signalled by
			     the VS score chip and the Edit/Pick CTA in the points
			     column). The whole cell is omitted when no row in the
			     table needs it. -->
			{#if hasStatusCol}
				{#if r.statusVariant === 'live'}
					<span class="status live">{r.statusText}<span class="tick">′</span></span>
				{:else if r.statusVariant === 'ft'}
					<span class="status ft">{r.statusText}</span>
				{:else}
					<span class="status"></span>
				{/if}
			{/if}

			<!-- Group / Round chip -->
			<span class="grp" class:ko={r.grpLabel.length > 1}>{r.grpLabel}</span>

			<!-- Match cell -->
			<div class="c-match">
				<span class="team home">
					<PnFlag code={r.home} w={24} h={16} />
					{r.home}
				</span>
				{#if r.score}
					<span class="sc" class:live={r.kind === 'live'}>
						<span>{r.score[0]}</span><span class="dash">–</span><span>{r.score[1]}</span>
					</span>
				{:else}
					<span class="sc vs" class:ko={!!r.koLabel}>{r.koLabel ?? 'VS'}</span>
				{/if}
				<span class="team away">
					{r.away}
					<PnFlag code={r.away} w={24} h={16} />
				</span>
			</div>

			<!-- Pick pill -->
			<div class="c-pick">
				{#if r.pick}
					<span class="pick {r.pickResult ?? ''}">
						{r.pick[0]}<span class="dash">–</span>{r.pick[1]}
					</span>
				{:else}
					<span class="pick empty">—</span>
				{/if}
			</div>

			<!-- Points / CTA -->
			<div class="c-pts">
				{#if r.cta === 'pick'}
					<a class="cta primary" href={r.ctaHref ?? '/predictions'} on:click|stopPropagation>Pick</a>
				{:else if r.cta === 'edit'}
					<a class="cta secondary" href={r.ctaHref ?? '/predictions'} on:click|stopPropagation>Edit</a>
				{:else if r.pointsText !== null}
					<span class="pts {r.pointsVariant}">{r.pointsText}</span>
				{/if}
			</div>
		</div>
	{:else}
		<div class="mtab-empty">{emptyText}</div>
	{/each}

	<!-- Padding rows so side-by-side tables line up at the same height.
	     Empty divs keep the grid's row count + dashed dividers consistent;
	     no content, no hover, no interaction. -->
	{#each Array(padCount) as _, i (`pad-${i}`)}
		<div class="mtab-row pad" aria-hidden="true"></div>
	{/each}
</div>
