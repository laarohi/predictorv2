<script lang="ts">
	// Panini knockout bracket — interactive when phase is open, display when
	// locked. Reuses the existing bracketResolver state machine, so prediction
	// persistence and the click-to-advance logic are identical to the legacy
	// KnockoutBracket; only the rendering layer is new.
	//
	// Desktop layout: 9-column wall chart with the final in the centre column.
	// Mobile layout:  4 swipeable pages of round-pairs (R32+R16, R16+QF, QF+SF,
	// SF+Final). Slot heights animate as the user paginates so that the
	// "next round" column visually contains two of its predecessors.
	import { createEventDispatcher } from 'svelte';
	import {
		initializeBracketState,
		predictionToBracketState,
		getDisplayMatches,
		bracketStateToPrediction,
		setMatchWinner,
		type GroupStandingsMap
	} from '$lib/utils/bracketResolver';
	import type { BracketPrediction } from '$types';
	import PnBracketMatch from './PnBracketMatch.svelte';
	import PnFlag from './PnFlag.svelte';
	import { teamCode } from '$lib/utils/teamCodes';

	export let prediction: BracketPrediction | null = null;
	export let groupStandings: GroupStandingsMap = {};
	export let locked: boolean = false;
	export let phase: 'phase_1' | 'phase_2' = 'phase_1';
	/** Hide R32 column (Phase 2 starts at R16). */
	export let hideR32: boolean = false;

	const dispatch = createEventDispatcher<{ update: BracketPrediction }>();

	function hasValidPrediction(pred: BracketPrediction | null): boolean {
		if (!pred) return false;
		return (
			(pred.round_of_16?.some((t) => !!t) ?? false) ||
			(pred.quarter_finals?.some((t) => !!t) ?? false) ||
			(pred.semi_finals?.some((t) => !!t) ?? false) ||
			(pred.final?.some((t) => !!t) ?? false) ||
			!!pred.winner
		);
	}

	$: state = (() => {
		if (Object.keys(groupStandings).length === 0) return null;
		if (prediction && hasValidPrediction(prediction)) {
			return predictionToBracketState(prediction, groupStandings);
		}
		return initializeBracketState(groupStandings);
	})();

	$: r32 = state ? getDisplayMatches(state, 'round_of_32') : [];
	$: r16 = state ? getDisplayMatches(state, 'round_of_16') : [];
	$: qf = state ? getDisplayMatches(state, 'quarter_finals') : [];
	$: sf = state ? getDisplayMatches(state, 'semi_finals') : [];
	$: f = state ? getDisplayMatches(state, 'final') : [];

	function pick(matchNumber: number, team: string) {
		if (!state || locked) return;
		const nextState = setMatchWinner(state, matchNumber, team);
		dispatch('update', bracketStateToPrediction(nextState));
	}

	export function clearAllSelections() {
		if (!groupStandings) return;
		const emptyState = initializeBracketState(groupStandings);
		dispatch('update', bracketStateToPrediction(emptyState));
	}

	function handleClearClick() {
		if (locked) return;
		if (locksCount === 0) return;
		const confirmed = window.confirm(
			`Clear all ${locksCount} bracket pick${locksCount === 1 ? '' : 's'}?\n\nThis only resets your draft — nothing is sent to the server until you press Save bracket.`
		);
		if (confirmed) clearAllSelections();
	}

	$: leftR32 = r32.slice(0, 8);
	$: rightR32 = r32.slice(8);
	$: leftR16 = r16.slice(0, 4);
	$: rightR16 = r16.slice(4);
	$: leftQF = qf.slice(0, 2);
	$: rightQF = qf.slice(2);
	$: leftSF = sf.slice(0, 1);
	$: rightSF = sf.slice(1);
	$: finalMatch = f[0] ?? null;

	$: finalWinner = finalMatch ? finalMatch.winner : null;
	$: locksCount = state
		? Object.values(state.matchResults).filter((m) => m.winner !== null).length
		: 0;
	$: totalPicks = hideR32 ? 15 : 31; // R16(8)+QF(4)+SF(2)+F(1) = 15; +R32(16) = 31

	// ===== Mobile swipeable pagination =====
	// Slot heights: each "expanded" (next-up) round is 2× the "normal"
	// (current) round so each next-round card aligns vertically with the
	// pair of preceding-round cards it consumes.
	const SLOT_NORMAL = 56;
	const SLOT_EXPANDED = 112;
	// Column width is reactive — we measure the bracket panel and split
	// the available space across exactly 2 visible columns. Min keeps
	// codes legible on phones, max stops the cards becoming silly on
	// large screens that fall under the mobile breakpoint.
	const MIN_COL_W = 130;
	const MAX_COL_W = 230;
	const GAP = 12;
	const STAGE_PAD = 24; // .pn-mb-stage has padding: 12px each side
	const COL_HEAD_H = 32; // col-head visual height + margin-bottom
	const FALLBACK_COL_W = 168;

	let mobPanelWidth = 0;
	// Stage spans full panel width (navy bleeds to the screen edges). The
	// viewport — a centred block INSIDE the stage — is sized exactly to
	// fit 2 cols + gap + padding, with overflow:hidden clipping anything
	// outside. So off-screen cols (R32 when you're on R16/QF, etc.) are
	// clipped, never peek through, regardless of how wide the screen is.
	$: viewportW = Math.max(0, mobPanelWidth - STAGE_PAD);
	$: colW = mobPanelWidth > 0
		? Math.max(MIN_COL_W, Math.min(MAX_COL_W, Math.floor((viewportW - GAP) / 2)))
		: FALLBACK_COL_W;
	$: step = colW + GAP;
	// Viewport (clipping window) width: exactly 2 cols + gap + horizontal
	// padding. Anything wider becomes navy gutter outside the viewport.
	$: viewportWidth = 2 * colW + GAP + STAGE_PAD;

	$: rounds = hideR32
		? [
			{ label: 'R16', matches: r16 },
			{ label: 'QF', matches: qf },
			{ label: 'SF', matches: sf },
			{ label: 'FINAL', matches: f, isFinal: true }
		]
		: [
			{ label: 'R32', matches: r32 },
			{ label: 'R16', matches: r16 },
			{ label: 'QF', matches: qf },
			{ label: 'SF', matches: sf },
			{ label: 'FINAL', matches: f, isFinal: true }
		];

	$: numPages = Math.max(1, rounds.length - 1);
	let page = 0;
	let dragX = 0;
	let dragging = false;
	let touchAxis: 'h' | 'v' | null = null;
	let touchStartX = 0;
	let touchStartY = 0;

	$: trackWidth = rounds.length * colW + (rounds.length - 1) * GAP;
	$: ease =
		'transform 500ms cubic-bezier(0.65, 0, 0.35, 1), height 500ms cubic-bezier(0.65, 0, 0.35, 1)';

	// Stage height = tallest of the two currently-visible columns (current
	// page is normal slots, next page is expanded slots). Cols off the
	// visible window don't contribute, so swiping to a shorter round-pair
	// makes the navy stage literally shrink — no inner scrollbar, no
	// dead navy space below.
	$: currentRound = rounds[page] ?? null;
	$: nextRound = rounds[page + 1] ?? null;
	$: currentColH = (currentRound?.matches.length ?? 0) * SLOT_NORMAL + COL_HEAD_H;
	$: nextColH = (nextRound?.matches.length ?? 0) * SLOT_EXPANDED + COL_HEAD_H;
	$: stageContentH = Math.max(currentColH, nextColH);
	$: stageHeight = stageContentH + STAGE_PAD;

	function touchStart(e: TouchEvent) {
		touchStartX = e.touches[0].clientX;
		touchStartY = e.touches[0].clientY;
		touchAxis = null;
		dragging = true;
	}
	function touchMove(e: TouchEvent) {
		const dx = e.touches[0].clientX - touchStartX;
		const dy = e.touches[0].clientY - touchStartY;
		if (touchAxis === null && (Math.abs(dx) > 8 || Math.abs(dy) > 8)) {
			touchAxis = Math.abs(dx) > Math.abs(dy) ? 'h' : 'v';
		}
		if (touchAxis === 'h') {
			e.preventDefault();
			let d = dx;
			if ((page === 0 && d > 0) || (page === numPages - 1 && d < 0)) d *= 0.3;
			dragX = d;
		}
	}
	function touchEnd() {
		dragging = false;
		if (Math.abs(dragX) > step / 3) {
			if (dragX < 0 && page < numPages - 1) page += 1;
			else if (dragX > 0 && page > 0) page -= 1;
		}
		dragX = 0;
	}

	function goPrev() {
		if (page > 0) page -= 1;
	}
	function goNext() {
		if (page < numPages - 1) page += 1;
	}
</script>

{#if state}
	<!-- ===== Desktop wall chart ===== -->
	<div class="pn-brkt-desk">
		<section class="pn-brkt-body">
			<div class="pn-brkt-h">
				<div class="ttl">YOUR <em>BRACKET</em></div>
				<div class="stat">
					PICKS LOCKED
					<b>{locksCount} / {totalPicks}</b>
				</div>
				<div class="stat">
					STATUS
					<b>{locked ? 'LOCKED' : 'OPEN'}</b>
				</div>
				<div class="stat">
					FINAL · YOUR PICK
					<b class="gold-text">
						{#if finalWinner}{finalWinner.toUpperCase()}{:else}—{/if}
					</b>
				</div>
			</div>

			<div class="pn-brkt-grid" style={hideR32 ? 'grid-template-columns: repeat(7, 1fr);' : ''}>
				{#if !hideR32}
					<div class="pn-brkt-col">
						<div class="head">R32 · L</div>
						{#each leftR32 as m (m.match.matchNumber)}
							<PnBracketMatch
								homeTeam={m.homeTeam}
								awayTeam={m.awayTeam}
								winner={m.winner}
								{locked}
								onSelect={(t) => pick(m.match.matchNumber, t)}
							/>
						{/each}
					</div>
				{/if}

				<div class="pn-brkt-col">
					<div class="head">R16 · L</div>
					{#each leftR16 as m (m.match.matchNumber)}
						<PnBracketMatch
							homeTeam={m.homeTeam}
							awayTeam={m.awayTeam}
							winner={m.winner}
							{locked}
							onSelect={(t) => pick(m.match.matchNumber, t)}
						/>
					{/each}
				</div>

				<div class="pn-brkt-col">
					<div class="head">QF · L</div>
					{#each leftQF as m (m.match.matchNumber)}
						<PnBracketMatch
							homeTeam={m.homeTeam}
							awayTeam={m.awayTeam}
							winner={m.winner}
							{locked}
							onSelect={(t) => pick(m.match.matchNumber, t)}
						/>
					{/each}
				</div>

				<div class="pn-brkt-col">
					<div class="head">SF · L</div>
					{#each leftSF as m (m.match.matchNumber)}
						<PnBracketMatch
							homeTeam={m.homeTeam}
							awayTeam={m.awayTeam}
							winner={m.winner}
							{locked}
							onSelect={(t) => pick(m.match.matchNumber, t)}
						/>
					{/each}
				</div>

				<div class="pn-brkt-col pn-brkt-col-final" style="justify-content: center;">
					{#if finalWinner}
						<div class="pn-champ-sticker-pos">
							{#key finalWinner}
								<div class="pn-champ-sticker" aria-live="polite">
									<div class="badge">★ MY CHAMPION</div>
									<div class="body">
										<PnFlag code={teamCode(finalWinner)} w={44} h={30} />
										<span class="name">{finalWinner.toUpperCase()}</span>
									</div>
								</div>
							{/key}
						</div>
					{/if}
					<div class="head final">FINAL</div>
					{#if finalMatch}
						<PnBracketMatch
							isFinal
							homeTeam={finalMatch.homeTeam}
							awayTeam={finalMatch.awayTeam}
							winner={finalMatch.winner}
							{locked}
							onSelect={(t) => pick(finalMatch.match.matchNumber, t)}
						/>
					{:else}
						<div class="pn-bm tbd"></div>
					{/if}
				</div>

				<div class="pn-brkt-col">
					<div class="head">SF · R</div>
					{#each rightSF as m (m.match.matchNumber)}
						<PnBracketMatch
							homeTeam={m.homeTeam}
							awayTeam={m.awayTeam}
							winner={m.winner}
							{locked}
							onSelect={(t) => pick(m.match.matchNumber, t)}
						/>
					{/each}
				</div>

				<div class="pn-brkt-col">
					<div class="head">QF · R</div>
					{#each rightQF as m (m.match.matchNumber)}
						<PnBracketMatch
							homeTeam={m.homeTeam}
							awayTeam={m.awayTeam}
							winner={m.winner}
							{locked}
							onSelect={(t) => pick(m.match.matchNumber, t)}
						/>
					{/each}
				</div>

				<div class="pn-brkt-col">
					<div class="head">R16 · R</div>
					{#each rightR16 as m (m.match.matchNumber)}
						<PnBracketMatch
							homeTeam={m.homeTeam}
							awayTeam={m.awayTeam}
							winner={m.winner}
							{locked}
							onSelect={(t) => pick(m.match.matchNumber, t)}
						/>
					{/each}
				</div>

				{#if !hideR32}
					<div class="pn-brkt-col">
						<div class="head">R32 · R</div>
						{#each rightR32 as m (m.match.matchNumber)}
							<PnBracketMatch
								homeTeam={m.homeTeam}
								awayTeam={m.awayTeam}
								winner={m.winner}
								{locked}
								onSelect={(t) => pick(m.match.matchNumber, t)}
							/>
						{/each}
					</div>
				{/if}
			</div>
		</section>

		<div class="pn-brkt-foot">
			<span>
				{#if locked}
					★ Locked · awaiting results
				{:else}
					Click any team to pick them as winner of their match
				{/if}
			</span>
			<span class="actions">
				{#if !locked && locksCount > 0}
					<button type="button" class="pn-brkt-clear" on:click={handleClearClick}>
						↺ Clear bracket
					</button>
				{/if}
				<span class="count">
					<b>{locksCount}</b> / {totalPicks} PICKS LOCKED IN
				</span>
			</span>
		</div>
	</div>

	<!-- ===== Mobile swipeable pages ===== -->
	<div class="pn-brkt-mob" bind:clientWidth={mobPanelWidth}>
		<div class="pn-mb">
			<div class="pn-mb-h">
				<div class="ttl">YOUR <em>BRACKET</em></div>
				<div class="dots">
					{#each Array(numPages) as _, i}
						<button class="dot" class:on={i === page} on:click={() => (page = i)} aria-label="Go to page {i + 1}"></button>
					{/each}
				</div>
				<div class="end">
					<b>{locksCount} / {totalPicks}</b>
					<span>{locked ? 'LOCKED' : 'PICKED'}</span>
					{#if !locked && locksCount > 0}
						<button type="button" class="pn-mb-clear" on:click={handleClearClick} aria-label="Clear bracket">
							↺ Clear
						</button>
					{/if}
				</div>
			</div>

			<div class="pn-mb-label">
				<span class="active">{rounds[page]?.label ?? ''}</span>
				<span class="arrow">→</span>
				<span class="next">{rounds[page + 1]?.label ?? ''}</span>
			</div>

			<div
				class="pn-mb-stage"
				style="height: {stageHeight}px; --viewport-w: {viewportWidth}px; transition: {dragging ? 'none' : 'height 500ms cubic-bezier(0.65, 0, 0.35, 1)'};"
				on:touchstart={touchStart}
				on:touchmove={touchMove}
				on:touchend={touchEnd}
			>
				{#if page > 0}
					<button
						type="button"
						class="pn-mb-arrow prev"
						on:click={goPrev}
						aria-label="Previous round pair"
					>◂</button>
				{/if}
				{#if page < numPages - 1}
					<button
						type="button"
						class="pn-mb-arrow next"
						on:click={goNext}
						aria-label="Next round pair"
					>▸</button>
				{/if}
				<div class="pn-mb-viewport" style="width: {viewportWidth}px;">
					<div class="pn-mb-scroll">
						<div
							class="pn-mb-track"
							style="width: {trackWidth}px; transform: translateX({-page * step + dragX}px); transition: {dragging ? 'none' : ease};"
						>
						{#each rounds as round, r (round.label)}
							{@const expanded = r === page + 1}
							{@const slotH = expanded ? SLOT_EXPANDED : SLOT_NORMAL}
							<div class="pn-mb-col" style="width: {colW}px;">
								<div class="pn-mb-col-head" class:final={round.isFinal}>{round.label}</div>
								{#each round.matches as m (m.match.matchNumber)}
									<div
										class="pn-mb-slot"
										style="height: {slotH}px; transition: {dragging ? 'none' : ease};"
									>
										{#if round.isFinal}
											<PnBracketMatch
												isFinal
												homeTeam={m.homeTeam}
												awayTeam={m.awayTeam}
												winner={m.winner}
												{locked}
												onSelect={(t) => pick(m.match.matchNumber, t)}
											/>
										{:else}
											<PnBracketMatch
												compact
												homeTeam={m.homeTeam}
												awayTeam={m.awayTeam}
												winner={m.winner}
												{locked}
												onSelect={(t) => pick(m.match.matchNumber, t)}
											/>
										{/if}
									</div>
								{/each}
							</div>
						{/each}
					</div>
				</div>
			</div>
			</div>

			{#if finalWinner}
				<div class="pn-mb-champ">
					<span style="display: flex; align-items: center;">
						<!-- intentionally rendered via PnBracketMatch's flag styling elsewhere -->
						<span style="width: 36px; height: 24px; display: inline-block; background: var(--ink); color: var(--paper); font-family: var(--display); font-size: 14px; text-align: center; line-height: 24px;">★</span>
					</span>
					<div class="info">
						<div class="l">Your champion</div>
						<div class="nm">{finalWinner}</div>
					</div>
					<span class="info" style="text-align: right;">
						<span class="l" style="display: block;">{locksCount}/{totalPicks}</span>
					</span>
				</div>
			{/if}

			<div class="pn-mb-nav">
				<button class="prev" type="button" on:click={goPrev} disabled={page === 0}>← PREV</button>
				<span class="label">PAGE {page + 1} / {numPages}</span>
				<button class="next" type="button" on:click={goNext} disabled={page === numPages - 1}>NEXT →</button>
			</div>
		</div>
	</div>
{:else}
	<div style="padding: 24px; text-align: center; font-family: var(--mono); font-size: 11px; color: var(--ink-3); letter-spacing: 0.08em; text-transform: uppercase;">
		Waiting for group standings to render bracket…
	</div>
{/if}
