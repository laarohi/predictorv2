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
	const SLOT_NORMAL = 56;
	const SLOT_EXPANDED = 112;
	const COL_W = 168;
	const GAP = 12;
	const STEP = COL_W + GAP;

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

	$: trackWidth = rounds.length * COL_W + (rounds.length - 1) * GAP;
	$: ease =
		'transform 500ms cubic-bezier(0.65, 0, 0.35, 1), height 500ms cubic-bezier(0.65, 0, 0.35, 1)';

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
		if (Math.abs(dragX) > STEP / 3) {
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

				<div class="pn-brkt-col" style="justify-content: center;">
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
			<span>
				<b>{locksCount}</b> / {totalPicks} PICKS LOCKED IN
			</span>
		</div>
	</div>

	<!-- ===== Mobile swipeable pages ===== -->
	<div class="pn-brkt-mob">
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
				</div>
			</div>

			<div class="pn-mb-label">
				<span class="active">{rounds[page]?.label ?? ''}</span>
				<span class="arrow">→</span>
				<span class="next">{rounds[page + 1]?.label ?? ''}</span>
			</div>

			<div class="pn-mb-stage" on:touchstart={touchStart} on:touchmove={touchMove} on:touchend={touchEnd}>
				<div class="pn-mb-scroll">
					<div
						class="pn-mb-track"
						style="width: {trackWidth}px; transform: translateX({-page * STEP + dragX}px); transition: {dragging ? 'none' : ease};"
					>
						{#each rounds as round, r (round.label)}
							{@const expanded = r === page + 1}
							{@const slotH = expanded ? SLOT_EXPANDED : SLOT_NORMAL}
							<div class="pn-mb-col" style="width: {COL_W}px;">
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
