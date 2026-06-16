<script lang="ts">
	import { onMount, onDestroy, tick } from 'svelte';
	import { getLatestDrop } from '$lib/api/dailyDrop';
	import PnIcon from '$components/panini/PnIcon.svelte';
	import { latestDrop, dropSeen, replaySignal } from '$stores/backPage';
	import type { DailyDrop } from '$types';
	import type { IconName } from '$types/panini';

	const SEEN_KEY = 'predictor_seen_drops';
	const HOLD_MS = 250;

	let drop: DailyDrop | null = null;
	let open = false;
	let reduced = false;

	let page = 0;
	let progress = 0;
	let paused = false;
	let rafId = 0;
	let lastTs = 0;
	let downAt = 0;
	let copied = false; // download-fallback feedback for the Share button
	let cardEl: HTMLElement; // the node we rasterise to a shareable PNG
	let capturing = false; // hides chrome (×, arrows, button) during the snapshot
	let busy = false; // share in flight — guards against double taps

	type Row = { ic: IconName; lbl: string; name: string; stat: string };
	type Theme = 'personal' | 'table' | 'picks' | 'roast';
	type Page = { key: Theme; title: string; icon: IconName; light: boolean };

	const THEMES: Record<Theme, { title: string; icon: IconName; light: boolean }> = {
		personal: { title: 'Your Day', icon: 'medal', light: true },
		table: { title: 'The Table', icon: 'crown', light: false },
		picks: { title: 'The Picks', icon: 'skull', light: false },
		roast: { title: 'The Roast', icon: 'pen-nib', light: true }
	};

	// Edition number derived from the date (no backend field) — tournament
	// opener = 11 Jun 2026, so opening day is "Ed. No. 1".
	const TOURNAMENT_START = '2026-06-11';
	function editionNo(iso: string): number {
		const ms =
			new Date(iso + 'T00:00:00').getTime() - new Date(TOURNAMENT_START + 'T00:00:00').getTime();
		return Math.max(1, Math.round(ms / 86_400_000) + 1);
	}

	function seenDrops(): string[] {
		try {
			return JSON.parse(localStorage.getItem(SEEN_KEY) || '[]');
		} catch {
			return [];
		}
	}
	function markSeen(date: string): void {
		const next = Array.from(new Set([...seenDrops(), date]));
		try {
			localStorage.setItem(SEEN_KEY, JSON.stringify(next));
		} catch {
			/* ignore */
		}
	}
	function stopRaf(): void {
		if (rafId) cancelAnimationFrame(rafId);
		rafId = 0;
	}
	function dismiss(): void {
		if (drop) markSeen(drop.drop_date);
		dropSeen.set(true); // surfaces the dashboard "Replay" button
		open = false;
		stopRaf();
	}

	// Reopen the story on demand (the dashboard Replay button), bypassing the
	// once-per-drop seen gate. Tracks the last signal value so the reactive
	// block below only fires on an actual bump, not on unrelated re-renders.
	function reopen(): void {
		if (!drop) return;
		page = 0;
		progress = 0;
		capturing = false;
		lastTs = 0;
		open = true;
		stopRaf();
		if (autoAdvance) rafId = requestAnimationFrame(frame);
	}
	let lastReplay = 0;
	$: if ($replaySignal !== lastReplay) {
		lastReplay = $replaySignal;
		if ($replaySignal > 0) reopen();
	}

	$: autoAdvance = !reduced;

	function frame(ts: number): void {
		if (!open) return;
		if (lastTs && !paused && autoAdvance) {
			progress += (ts - lastTs) / pageMs;
			if (progress >= 1) {
				if (page < pages.length - 1) {
					page += 1;
					progress = 0;
				} else {
					dismiss(); // finale done — close cleanly instead of parking + leaking RAF
					return;
				}
			}
		}
		lastTs = ts;
		rafId = requestAnimationFrame(frame);
	}
	function go(delta: number): void {
		const target = page + delta;
		if (target < 0) {
			progress = 0;
			return;
		}
		if (target > pages.length - 1) {
			dismiss();
			return;
		}
		page = target;
		progress = 0;
	}
	function onDown(): void {
		downAt = performance.now();
		paused = true;
	}
	function onUp(): void {
		paused = false;
	}
	function navTap(delta: number): void {
		if (performance.now() - downAt > HOLD_MS) return;
		go(delta);
	}
	function onKey(e: KeyboardEvent): void {
		if (!open) return;
		if (e.key === 'Escape') dismiss();
		else if (e.key === 'ArrowRight') go(1);
		else if (e.key === 'ArrowLeft') go(-1);
	}

	onMount(async () => {
		reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
		const forced =
			import.meta.env.DEV && new URLSearchParams(window.location.search).get('drop') === 'force';
		try {
			const d = await getLatestDrop();
			if (d) {
				drop = d;
				latestDrop.set(d); // let the dashboard offer a Replay button
				const alreadySeen = seenDrops().includes(d.drop_date);
				if (alreadySeen) dropSeen.set(true);
				if (forced || !alreadySeen) {
					open = true;
					if (autoAdvance) rafId = requestAnimationFrame(frame);
				}
			}
		} catch {
			/* silent — the Drop is a delight, never load-critical */
		}
	});

	$: if (typeof document !== 'undefined') {
		// Only lock scroll when a page is actually rendered ({#if open && drop && cur});
		// never strand the body scroll-locked behind an invisible modal.
		document.body.style.overflow = open && cur ? 'hidden' : '';
	}
	onDestroy(() => {
		stopRaf();
		if (typeof document !== 'undefined') document.body.style.overflow = '';
	});

	function fmtDate(iso: string): string {
		const d = new Date(iso + 'T00:00:00');
		return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }).toUpperCase();
	}
	function ordinal(n: number): string {
		if (n % 100 >= 11 && n % 100 <= 13) return 'TH';
		return ['TH', 'ST', 'ND', 'RD'][n % 10] ?? 'TH';
	}

	// Overflow formatting for a tied set: 'A' · 'A & B' · 'A, B & C' · 'A, B +N'.
	function fmtNames(names: string[]): string {
		const n = names.length;
		if (n === 0) return 'Nobody';
		if (n === 1) return names[0];
		if (n === 2) return `${names[0]} & ${names[1]}`;
		if (n === 3) return `${names[0]}, ${names[1]} & ${names[2]}`;
		return `${names[0]}, ${names[1]} +${n - 2}`;
	}

	// A short text summary for sharing (the headline burns of the day).
	function shareText(): string {
		if (!drop) return '';
		const q = drop.payload;
		const lines = [`🗞️ The Back Page · ${fmtDate(drop.drop_date)}`];
		if (q.leader) lines.push(`👑 Top Dog: ${fmtNames(q.leader.names)}`);
		if (q.faceplant) lines.push(`💀 Shat the Bed: ${fmtNames(q.faceplant.names)}`);
		if (q.blunder) lines.push(`🤡 Dumbleflynn: ${fmtNames(q.blunder.names)}`);
		return lines.join('\n');
	}

	// Rasterise the current card to a PNG and share THAT (the WhatsApp loop):
	// native file-share sheet on mobile, download fallback on desktop. Chrome
	// (×, arrows, button) is hidden for the snapshot via the `capturing` flag.
	async function share(): Promise<void> {
		if (!drop || busy) return;
		busy = true;
		paused = true;
		capturing = true;
		await tick();
		// two RAFs so the hidden-chrome layout + fonts settle before the snapshot
		await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r(null))));

		// html-to-image doesn't carry theme custom props into its clone, so
		// var()-based fills/rules vanish. Pin every theme var the redesign reads
		// inline for the snapshot, then strip them so theme switches stay live.
		const themeVars = [
			'--bg',
			'--accent',
			'--fg',
			'--seg',
			'--track',
			'--btn',
			'--btn-fg',
			'--rule',
			'--rule-soft',
			'--muted'
		];
		const cs = getComputedStyle(cardEl);
		for (const v of themeVars) cardEl.style.setProperty(v, cs.getPropertyValue(v).trim());

		let blob: Blob | null = null;
		try {
			const { toBlob } = await import('html-to-image');
			blob = await toBlob(cardEl, { pixelRatio: 2 });
		} catch {
			blob = null;
		}
		for (const v of themeVars) cardEl.style.removeProperty(v);
		capturing = false;
		paused = false;
		busy = false;
		if (!blob) return;

		const file = new File([blob], `back-page-${drop.drop_date}.png`, { type: 'image/png' });
		const text = shareText();
		// Mobile (HTTPS only — Web Share needs a secure context): the native share
		// sheet with the image file → straight into WhatsApp.
		if (navigator.canShare?.({ files: [file] })) {
			try {
				await navigator.share({ files: [file], title: 'The Back Page', text });
				return; // shared successfully
			} catch (e) {
				// User cancelled the sheet → stop. Any other failure (e.g. iOS lost
				// the gesture) → fall through to the download so they still get it.
				if (e instanceof DOMException && e.name === 'AbortError') return;
			}
		}
		// Desktop / insecure context / share failed: download the PNG instead.
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = file.name;
		document.body.appendChild(a);
		a.click();
		a.remove();
		URL.revokeObjectURL(url);
		copied = true;
		setTimeout(() => (copied = false), 1800);
	}

	$: p = drop?.payload ?? null;
	$: me = drop?.personal ?? null;

	$: tableSupport = (
		p
			? [
					p.mover && { ic: 'chart' as IconName, lbl: 'On the Move', name: fmtNames(p.mover.names), stat: `+${p.mover.delta} place${p.mover.delta === 1 ? '' : 's'}` },
					p.faceplant && { ic: 'skull' as IconName, lbl: 'Shat the Bed', name: fmtNames(p.faceplant.names), stat: `${p.faceplant.delta} place${Math.abs(p.faceplant.delta) === 1 ? '' : 's'}` },
					p.points_haul && { ic: 'money' as IconName, lbl: 'Big Earner', name: fmtNames(p.points_haul.names), stat: `+${p.points_haul.points_gained} pts` },
					p.wooden_spoon && { ic: 'trophy' as IconName, lbl: 'Why Bother?', name: fmtNames(p.wooden_spoon.names), stat: `−${p.wooden_spoon.behind_leader} pts` }
				].filter((r): r is Row => !!r)
			: []
	);
	$: picksSupport = (
		p
			? [
					p.called_it && { ic: 'crystal-ball' as IconName, lbl: 'Nostradamus', name: fmtNames(p.called_it.names), stat: `${p.called_it.count === 1 ? 'SOLO ' : ''}${p.called_it.home_score}–${p.called_it.away_score}` },
					p.contrarian && { ic: 'glasses' as IconName, lbl: 'The Hipster', name: fmtNames(p.contrarian.names), stat: `avg ${p.contrarian.avg_pct}% agreed` },
					p.hottest_streak && { ic: 'flame' as IconName, lbl: 'Hottest', name: fmtNames(p.hottest_streak.names), stat: `${p.hottest_streak.length} in a row` },
					p.coldest_streak && { ic: 'snowflake' as IconName, lbl: 'Coldest', name: fmtNames(p.coldest_streak.names), stat: `${p.coldest_streak.length} wrong in a row` }
				].filter((r): r is Row => !!r)
			: []
	);

	$: pages = (
		drop
			? ([
					me ? { key: 'personal', ...THEMES.personal } : null,
					p && (p.leader || tableSupport.length) ? { key: 'table', ...THEMES.table } : null,
					p && (p.blunder || picksSupport.length) ? { key: 'picks', ...THEMES.picks } : null,
					drop.roast ? { key: 'roast', ...THEMES.roast } : null
				].filter(Boolean) as Page[])
			: []
	);
	$: if (page > pages.length - 1) page = Math.max(0, pages.length - 1);
	$: cur = pages[page] ?? null;
	// Per-page dwell — generous so everything is readable before auto-advance
	// (tap/arrows still skip instantly). Roast carries the most text.
	$: pageMs = cur?.key === 'roast' ? 24000 : 20000;

	// Segment fills, REACTIVE so the active bar grows as `progress` advances each
	// RAF frame. (A `segWidth(i)` call in the template wouldn't re-run on `progress`
	// changes — Svelte can't see the dep inside the function — so the bar froze.)
	$: fills = pages.map((_, i) =>
		i < page ? 100 : i > page ? 0 : autoAdvance ? Math.min(progress, 1) * 100 : 100
	);
	// Panini glyph for a points-breakdown category (bracket rounds → trophy fallback).
	function catIcon(label: string): IconName {
		const m: Record<string, IconName> = {
			'Exact scores': 'target',
			'Correct outcomes': 'predict',
			'Rarity bonus': 'star',
			'Bonus questions': 'medal',
			'Group advance': 'flag',
			'Group position': 'list',
			Winner: 'crown'
		};
		return m[label] ?? 'trophy';
	}

	// Shrink the roast text until it fits the card with NO scroll — guarantees the
	// whole roast shows both in the modal and in the rasterised PNG (a clipped
	// roast is a dead roast). Re-fits on resize and whenever the text changes.
	function fitText(node: HTMLElement, _deps?: unknown) {
		const pageEl = node.closest('.pn-drop-page') as HTMLElement | null;
		function fit(): void {
			if (!pageEl) return;
			let size = 15; // new column base (was 16)
			node.style.fontSize = `${size}px`;
			let guard = 0;
			while (size > 9.5 && pageEl.scrollHeight > pageEl.clientHeight && guard < 60) {
				size -= 0.5;
				node.style.fontSize = `${size}px`;
				guard += 1;
			}
		}
		requestAnimationFrame(fit);
		window.addEventListener('resize', fit);
		return {
			update(_d?: unknown): void {
				requestAnimationFrame(fit);
			},
			destroy(): void {
				window.removeEventListener('resize', fit);
			}
		};
	}

	// Shrink the award-hero screamer only when a long (often tied) name would wrap
	// enough to overflow the honours page — normal names keep the full 33px.
	function fitHeading(node: HTMLElement, _dep?: unknown) {
		const pageEl = node.closest('.pn-drop-page') as HTMLElement | null;
		function fit(): void {
			if (!pageEl) return;
			let size = 33;
			node.style.fontSize = `${size}px`;
			let guard = 0;
			while (size > 17 && pageEl.scrollHeight > pageEl.clientHeight && guard < 30) {
				size -= 1;
				node.style.fontSize = `${size}px`;
				guard += 1;
			}
		}
		requestAnimationFrame(fit);
		window.addEventListener('resize', fit);
		return {
			update(_d?: unknown): void {
				requestAnimationFrame(fit);
			},
			destroy(): void {
				window.removeEventListener('resize', fit);
			}
		};
	}
</script>

<svelte:window on:keydown={onKey} />

{#if open && drop && cur}
	<!-- Backdrop click-to-dismiss is intentional; Esc + the × cover keyboard. -->
	<!-- svelte-ignore a11y-no-noninteractive-element-interactions a11y-click-events-have-key-events -->
	<div
		class="pn pn-drop-scrim"
		role="dialog"
		aria-modal="true"
		aria-label="The Back Page"
		on:click|self={dismiss}
	>
		<div
			bind:this={cardEl}
			class="pn-drop-card theme-{cur.key}"
			class:light={cur.light}
			class:capturing
			on:pointerdown={onDown}
			on:pointerup={onUp}
			on:pointerleave={onUp}
		>
			<div class="pn-drop-half" aria-hidden="true"></div>
			{#if cur.key !== 'roast'}
				<div class="pn-drop-wm" aria-hidden="true">
					<PnIcon name={cur.icon} size={250} color="var(--fg)" stroke={1.4} />
				</div>
			{/if}

			<div class="pn-drop-top">
				<div class="pn-drop-progress">
					{#each pages as _, i}
						<div class="seg"><div class="fill" style="width:{fills[i]}%"></div></div>
					{/each}
				</div>
				<div class="pn-drop-head">
					<span class="runhead"><span class="dot"></span>The Back Page · Ed. No. {editionNo(drop.drop_date)}</span>
					<button class="x" on:click|stopPropagation={dismiss} aria-label="Dismiss">×</button>
				</div>
			</div>

			<div class="pn-drop-body">
				{#key page}
					<div class="pn-drop-page enter">
						{#if cur.key === 'personal' && me}
							<div class="kicker-row">
								<span class="kicker">Your Day</span><span class="kicker-rule"></span>
								<span class="kicker-date">{fmtDate(drop.drop_date)}</span>
							</div>
							<div class="yd-hero">
								<div class="yd-num screamer">{me.position}<span class="ord">{ordinal(me.position)}</span></div>
								<div class="yd-side">
									<span class="yd-of">Position · of {p?.player_count ?? ''}</span>
									<span class="yd-flag">
										<PnIcon name={me.movement > 0 ? 'arrow-up' : me.movement < 0 ? 'arrow-down' : 'minus'} size={13} color="var(--paper)" />
										{me.movement > 0 ? `Up ${me.movement}` : me.movement < 0 ? `Down ${Math.abs(me.movement)}` : 'Steady'} overnight
									</span>
									<span class="yd-pts"><em>{me.points}</em> pts{#if me.points_gained} · +{me.points_gained} today{/if}</span>
								</div>
							</div>
							<div class="yd-formline">
								{#if me.hot_streak >= 2}
									<PnIcon name="flame" size={17} color="var(--accent)" /><span><b>{me.hot_streak}</b> correct on the bounce</span>
								{:else if me.cold_streak >= 2}
									<PnIcon name="snowflake" size={17} color="var(--accent)" /><span><b>{me.cold_streak}</b> wrong on the bounce</span>
								{:else if me.movement !== 0}
									<PnIcon name={me.movement > 0 ? 'arrow-up' : 'arrow-down'} size={17} color="var(--accent)" /><span>{me.movement > 0 ? 'Up' : 'Down'} <b>{Math.abs(me.movement)}</b> overnight</span>
								{:else}
									<PnIcon name="minus" size={17} color="var(--accent)" /><span>Held your ground</span>
								{/if}
							</div>
							{#if me.points_breakdown.length}
								<div class="yd-ledger">
									<div class="ledger-cap">Today's returns · {me.points_breakdown.length} ways</div>
									{#each me.points_breakdown as c (c.label)}
										<div class="ledger-row">
											<span class="ic"><PnIcon name={catIcon(c.label)} size={14} color="var(--accent)" /></span>
											<span class="lbl"><span>{c.label}</span></span>
											<span class="val">{c.points}</span>
										</div>
									{/each}
									<div class="ledger-total"><span class="l">Day's haul</span><span class="v">+{me.points_gained}</span></div>
								</div>
							{/if}

						{:else if cur.key === 'table' || cur.key === 'picks'}
							{@const isTable = cur.key === 'table'}
							<div class="kicker-row">
								<span class="kicker">{isTable ? 'The Table · Standings Drama' : 'The Picks · Hits & Howlers'}</span>
								<span class="kicker-rule"></span>
							</div>
							<div class="award-hero">
								<div class="glyph"><PnIcon name={isTable ? 'crown' : 'skull'} size={34} color="var(--accent)" /></div>
								{#if isTable && p?.leader}
									<div class="lbl">Top Dog</div>
									<div class="name screamer" use:fitHeading={p.leader.names}>{fmtNames(p.leader.names)}</div>
									<div class="sub"><b>{p.leader.points}</b> pts{#if p.leader.lead > 0} · <b>+{p.leader.lead}</b> clear at the summit{/if}</div>
								{:else if !isTable && p?.blunder}
									<div class="lbl">Dumbleflynn of the Day</div>
									<div class="name screamer" use:fitHeading={p.blunder.names}>{fmtNames(p.blunder.names)}</div>
									<div class="sub">Said <b>{p.blunder.predicted}</b> · finished <b>{p.blunder.actual}</b><span class="vs">{p.blunder.home_team} v {p.blunder.away_team}</span></div>
								{/if}
							</div>
							<div class="honours">
								<div class="h-cap">{isTable ? 'Today’s honours & horrors' : 'Crystal balls & cold spells'}</div>
								{#each (isTable ? tableSupport : picksSupport) as r (r.lbl)}
									<div class="h-row">
										<span class="ic"><PnIcon name={r.ic} size={16} color="var(--accent)" /></span>
										<span class="lbl">{r.lbl}</span>
										<span class="who">{r.name}</span>
										<span class="stat">{r.stat}</span>
									</div>
								{/each}
							</div>

						{:else if cur.key === 'roast'}
							<div class="np">
								<div class="np-plate">
									<div class="np-ears"><span>Late Edition</span><span>Back Page</span></div>
									<div class="np-name">The Roast</div>
								</div>
								<div class="np-byline">
									<span class="pen"><PnIcon name="pen-nib" size={12} color="var(--red)" /></span>
									<span>{fmtDate(drop.drop_date)}</span>
									{#if drop.roast_is_placeholder}<span class="sample ml">Sample</span>{/if}
								</div>
								<p class="roast-body" use:fitText={drop.roast}>{drop.roast}<span class="roast-end"></span></p>
							</div>
						{/if}
					</div>
				{/key}

				<button class="tap left" on:click|stopPropagation={() => navTap(-1)} aria-label="Previous">
					{#if page > 0}<span class="navarrow" aria-hidden="true"><PnIcon name="chevron-left" size={20} color="var(--fg)" stroke={2.4} /></span>{/if}
				</button>
				<button class="tap right" on:click|stopPropagation={() => navTap(1)} aria-label="Next">
					<span class="navarrow" aria-hidden="true"><PnIcon name="chevron-right" size={20} color="var(--fg)" stroke={2.4} /></span>
				</button>
			</div>

			<div class="pn-drop-foot">
				<span class="foot-brand"><span class="bp-logo bp-logo-sm"><span class="crest">CxF</span><span class="wm">Predict<span class="aa">aa</span></span></span></span>
				<button class="share" on:click|stopPropagation={share} disabled={busy}>
					{#if !copied && !busy}<PnIcon name="quote" size={14} color="var(--btn-fg)" />{/if}
					{copied ? 'Saved ✓' : busy ? 'Building image…' : 'Share the Scoop'}
				</button>
				<div class="caphint" aria-hidden="true">
					<span class="lockup"><span class="bp-logo bp-logo-lg"><span class="crest">CxF</span><span class="wm">Predict<span class="aa">aa</span></span></span></span>
					<span class="ed"><b>The Back Page</b><br />{fmtDate(drop.drop_date)} · Ed. No. {editionNo(drop.drop_date)}</span>
				</div>
			</div>
		</div>
	</div>
{/if}

<style>
	.pn-drop-scrim {
		position: fixed;
		inset: 0;
		z-index: 9999;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 20px;
		background: rgba(14, 29, 64, 0.62);
	}
	.pn-drop-card {
		position: relative;
		display: flex;
		flex-direction: column;
		width: 100%;
		max-width: 360px;
		height: min(79vh, 650px);
		border: 2px solid var(--ink);
		box-shadow: 8px 8px 0 var(--ink);
		overflow: hidden;
		color: var(--fg);
		background: var(--bg);
		transition: background-color 320ms ease;
		animation: drop-stamp 420ms cubic-bezier(0.16, 1.1, 0.3, 1);
		--bg: var(--ink);
		--fg: var(--paper);
		--accent: var(--gold);
		--seg: var(--gold);
		--btn: var(--gold);
		--btn-fg: var(--ink);
		--track: rgba(241, 235, 222, 0.26);
		--rule: color-mix(in srgb, var(--fg) 22%, transparent);
		--rule-soft: color-mix(in srgb, var(--fg) 13%, transparent);
		--muted: color-mix(in srgb, var(--fg) 62%, transparent);
	}
	.theme-personal {
		--bg: var(--gold);
		--fg: var(--ink);
		--accent: var(--red-deep);
		--seg: var(--ink);
		--btn: var(--ink);
		--btn-fg: var(--paper);
		--track: rgba(14, 29, 64, 0.26);
		--muted: color-mix(in srgb, var(--fg) 70%, transparent);
	}
	.theme-table {
		--bg: var(--ink);
		--fg: var(--paper);
		--accent: var(--gold);
		--seg: var(--gold);
		--btn: var(--gold);
		--btn-fg: var(--ink);
		--track: rgba(241, 235, 222, 0.26);
	}
	.theme-picks {
		--bg: var(--red-deep);
		--fg: var(--paper);
		--accent: var(--gold);
		--seg: var(--gold);
		--btn: var(--gold);
		--btn-fg: var(--ink);
		--track: rgba(241, 235, 222, 0.26);
	}
	.theme-roast {
		--bg: var(--paper);
		--fg: var(--ink);
		--accent: var(--red);
		--seg: var(--ink);
		--btn: var(--ink);
		--btn-fg: var(--paper);
		--track: rgba(14, 29, 64, 0.26);
		--muted: color-mix(in srgb, var(--fg) 60%, transparent);
	}

	/* Halftone newsprint screen */
	.pn-drop-half {
		position: absolute;
		inset: 0;
		z-index: 0;
		pointer-events: none;
		color: var(--fg);
		background-image: radial-gradient(currentColor 1px, transparent 1.5px);
		background-size: 5px 5px;
		opacity: 0.1;
		mask-image: radial-gradient(120% 80% at 100% 0%, #000 0%, transparent 62%);
		-webkit-mask-image: radial-gradient(120% 80% at 100% 0%, #000 0%, transparent 62%);
	}
	.theme-personal .pn-drop-half {
		opacity: 0.13;
	}
	.theme-roast .pn-drop-half {
		opacity: 0.08;
		mask-image: radial-gradient(140% 60% at 0% 100%, #000 0%, transparent 55%);
		-webkit-mask-image: radial-gradient(140% 60% at 0% 100%, #000 0%, transparent 55%);
	}

	.pn-drop-wm {
		position: absolute;
		right: -40px;
		top: 64px;
		opacity: 0.09;
		pointer-events: none;
		z-index: 0;
		line-height: 0;
	}

	/* top / running head */
	.pn-drop-top {
		position: relative;
		z-index: 3;
		padding: 10px 16px 0;
	}
	.pn-drop-progress {
		display: flex;
		gap: 4px;
	}
	.seg {
		flex: 1;
		height: 3px;
		background: var(--track);
		overflow: hidden;
	}
	.seg .fill {
		height: 100%;
		background: var(--seg);
		transition: none;
	}
	.pn-drop-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 9px 0 7px;
		margin-top: 2px;
		border-bottom: 1.5px solid var(--rule);
	}
	.pn-drop-head .runhead {
		font-family: var(--mono);
		font-size: 9px;
		letter-spacing: 0.22em;
		text-transform: uppercase;
		color: var(--muted);
		display: flex;
		align-items: center;
		gap: 7px;
	}
	.pn-drop-head .runhead .dot {
		width: 5px;
		height: 5px;
		background: var(--accent);
		border-radius: 50%;
	}
	.pn-drop-head .x {
		background: none;
		border: none;
		font-size: 22px;
		line-height: 1;
		color: var(--fg);
		cursor: pointer;
		padding: 0 2px;
		opacity: 0.8;
	}

	.pn-drop-body {
		position: relative;
		z-index: 1;
		flex: 1;
		overflow: hidden;
	}
	.pn-drop-page {
		position: absolute;
		inset: 0;
		display: flex;
		flex-direction: column;
		justify-content: center;
		padding: 13px 26px 14px;
		overflow: hidden;
	}

	/* shared editorial furniture */
	.kicker-row {
		display: flex;
		align-items: baseline;
		gap: 9px;
		margin-bottom: 9px;
	}
	.kicker {
		font-family: var(--mono);
		font-size: 10px;
		font-weight: 600;
		letter-spacing: 0.2em;
		text-transform: uppercase;
		color: var(--accent);
		white-space: nowrap;
	}
	.kicker-rule {
		flex: 1;
		height: 2px;
		background: var(--accent);
		align-self: center;
	}
	.kicker-date {
		font-family: var(--mono);
		font-size: 9px;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--muted);
	}
	.screamer {
		font-family: var(--display);
		line-height: 0.82;
		letter-spacing: -0.02em;
		transform: scaleX(0.93);
		transform-origin: left;
		text-transform: uppercase;
	}

	/* P1 Your Day */
	.yd-hero {
		display: grid;
		grid-template-columns: auto 1fr;
		column-gap: 14px;
		align-items: center;
		margin-bottom: 12px;
	}
	.yd-num {
		font-family: var(--display);
		font-size: 104px;
		line-height: 0.74;
		letter-spacing: -0.04em;
		transform: scaleX(0.9);
		transform-origin: left;
	}
	.yd-num .ord {
		font-size: 30px;
		vertical-align: super;
		margin-left: 1px;
	}
	.yd-side {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.yd-flag {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		align-self: flex-start;
		background: var(--accent);
		color: var(--paper);
		font-family: var(--display2);
		font-weight: 800;
		font-size: 12.5px;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		padding: 4px 9px;
		border: 1.5px solid var(--ink);
	}
	.yd-of {
		font-family: var(--mono);
		font-size: 10px;
		letter-spacing: 0.14em;
		text-transform: uppercase;
		color: var(--muted);
	}
	.yd-pts {
		font-family: var(--display2);
		font-weight: 700;
		font-size: 15px;
	}
	.yd-pts em {
		font-style: normal;
		color: var(--accent);
	}
	.yd-formline {
		display: flex;
		align-items: center;
		gap: 8px;
		font-family: var(--display2);
		font-weight: 700;
		font-size: 13.5px;
		padding: 9px 0;
		border-top: 2px solid var(--rule);
		border-bottom: 2px solid var(--rule);
		margin-bottom: 2px;
	}
	.yd-formline :global(svg) {
		flex-shrink: 0;
	}
	.yd-ledger {
		margin-top: 12px;
		border: 2px solid var(--rule);
		padding: 3px 14px 11px;
	}
	.ledger-cap {
		font-family: var(--mono);
		font-size: 9.5px;
		font-weight: 600;
		letter-spacing: 0.16em;
		text-transform: uppercase;
		color: var(--muted);
		margin: 11px 0 3px;
	}
	.ledger-row {
		display: grid;
		grid-template-columns: 18px 1fr auto;
		align-items: center;
		column-gap: 9px;
		padding: 8.5px 0;
	}
	.ledger-row .ic {
		line-height: 0;
	}
	.ledger-row .lbl {
		font-family: var(--body);
		font-size: 13px;
		position: relative;
		overflow: hidden;
		white-space: nowrap;
	}
	.ledger-row .lbl span {
		background: var(--bg);
		padding-right: 6px;
		position: relative;
		z-index: 1;
	}
	.ledger-row .lbl::after {
		content: '';
		position: absolute;
		left: 0;
		right: 0;
		bottom: 5px;
		border-bottom: 1.5px dotted var(--rule);
		z-index: 0;
	}
	.ledger-row .val {
		font-family: var(--display2);
		font-weight: 800;
		font-size: 16px;
	}
	.ledger-total {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		margin-top: 5px;
		padding-top: 9px;
		border-top: 3px double var(--rule);
	}
	.ledger-total .l {
		font-family: var(--mono);
		font-size: 10px;
		font-weight: 600;
		letter-spacing: 0.14em;
		text-transform: uppercase;
	}
	.ledger-total .v {
		font-family: var(--display);
		font-size: 30px;
		color: var(--accent);
		transform: scaleX(0.93);
	}

	/* P2/P3 award hero + honours */
	.award-hero {
		margin-bottom: 9px;
	}
	.award-hero .glyph {
		line-height: 0;
		margin-bottom: 5px;
	}
	.award-hero .lbl {
		font-family: var(--mono);
		font-size: 11px;
		font-weight: 600;
		letter-spacing: 0.16em;
		text-transform: uppercase;
		color: var(--accent);
		margin-bottom: 5px;
	}
	.award-hero .name {
		font-size: 33px;
		line-height: 0.86;
		margin-bottom: 6px;
	}
	.award-hero .sub {
		font-family: var(--body);
		font-size: 13px;
		line-height: 1.32;
		color: color-mix(in srgb, var(--fg) 90%, transparent);
	}
	.award-hero .sub b {
		font-family: var(--display2);
		font-weight: 800;
	}
	.award-hero .sub .vs {
		font-family: var(--mono);
		font-size: 10.5px;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--muted);
		display: block;
		margin-top: 3px;
	}
	.honours {
		border-top: 2px solid var(--rule);
	}
	.h-cap {
		font-family: var(--mono);
		font-size: 9.5px;
		font-weight: 600;
		letter-spacing: 0.16em;
		text-transform: uppercase;
		color: var(--muted);
		padding: 8px 0 2px;
	}
	.h-row {
		display: grid;
		grid-template-columns: 19px 1fr auto;
		align-items: center;
		column-gap: 9px;
		padding: 7px 0;
		border-bottom: 1px solid var(--rule-soft);
	}
	.h-row:last-child {
		border-bottom: none;
	}
	.h-row .ic {
		grid-row: 1 / span 2;
		align-self: center;
		line-height: 0;
		display: flex;
	}
	.h-row .lbl {
		grid-column: 2;
		font-family: var(--mono);
		font-size: 10px;
		font-weight: 600;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--accent);
	}
	.h-row .who {
		grid-column: 2;
		font-family: var(--display2);
		font-weight: 800;
		font-size: 14.5px;
		line-height: 1.12;
	}
	.h-row .stat {
		grid-column: 3;
		grid-row: 1 / span 2;
		align-self: center;
		text-align: right;
		font-family: var(--mono);
		font-size: 11px;
		color: var(--muted);
		white-space: nowrap;
		padding-left: 8px;
	}

	/* P4 Roast — newspaper */
	.np {
		display: flex;
		flex-direction: column;
		height: 100%;
	}
	.np-ears {
		display: flex;
		align-items: flex-end;
		justify-content: space-between;
		font-family: var(--mono);
		font-size: 7.5px;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		color: var(--muted);
		padding-bottom: 4px;
	}
	.np-name {
		font-family: var(--display);
		font-size: 44px;
		line-height: 0.82;
		letter-spacing: -0.015em;
		text-transform: uppercase;
		color: var(--ink);
		transform: scaleX(0.9);
		transform-origin: left;
		border-top: 3px solid var(--ink);
		border-bottom: 3px solid var(--ink);
		padding: 5px 0 6px;
	}
	.np-byline {
		display: flex;
		align-items: center;
		gap: 8px;
		font-family: var(--mono);
		font-size: 8.5px;
		letter-spacing: 0.16em;
		text-transform: uppercase;
		color: var(--red);
		padding: 6px 0 8px;
		border-bottom: 1px solid color-mix(in srgb, var(--ink) 30%, transparent);
		margin-bottom: 11px;
	}
	.np-byline .pen {
		line-height: 0;
	}
	.np-byline .sample {
		font-size: 8px;
		background: var(--ink);
		color: var(--paper);
		padding: 1px 5px;
		letter-spacing: 0.06em;
	}
	.np-byline .ml {
		margin-left: auto;
	}
	.roast-body {
		margin: 0;
		font-family: var(--body);
		font-size: 15px;
		line-height: 1.46;
		color: var(--ink);
		text-align: justify;
		hyphens: auto;
	}
	.roast-body::first-letter {
		float: left;
		font-family: var(--display);
		font-size: 3.2em;
		line-height: 0.66;
		margin: 6px 7px 0 0;
		color: var(--red);
	}
	.roast-end {
		display: inline-block;
		width: 9px;
		height: 9px;
		background: var(--red);
		margin-left: 3px;
		vertical-align: baseline;
	}

	/* tap zones + arrows */
	.tap {
		position: absolute;
		top: 0;
		bottom: 0;
		z-index: 2;
		display: flex;
		align-items: center;
		background: none;
		border: none;
		padding: 0 6px;
		cursor: pointer;
		-webkit-tap-highlight-color: transparent;
	}
	.tap.left {
		left: 0;
		width: 30%;
		justify-content: flex-start;
	}
	.tap.right {
		right: 0;
		width: 70%;
		justify-content: flex-end;
	}
	.navarrow {
		display: flex;
		line-height: 0;
		opacity: 0.34;
	}

	/* footer + brand lockup */
	.pn-drop-foot {
		position: relative;
		z-index: 3;
		padding: 10px 14px 13px;
		border-top: 1.5px solid var(--rule);
		display: flex;
		align-items: center;
		gap: 10px;
	}
	.bp-logo {
		display: inline-flex;
		align-items: center;
		gap: 7px;
	}
	.bp-logo .crest {
		background: var(--red);
		color: var(--paper);
		font-family: var(--display);
		letter-spacing: 0.01em;
		line-height: 1;
		display: grid;
		place-items: center;
		transform: rotate(-4deg);
		filter: drop-shadow(2px 2px 0 var(--fg));
	}
	.bp-logo .wm {
		font-family: var(--display);
		text-transform: uppercase;
		letter-spacing: -0.01em;
		line-height: 1;
		color: var(--fg);
	}
	.bp-logo .wm .aa {
		color: var(--accent);
	}
	.bp-logo-sm .crest {
		font-size: 10px;
		padding: 3px 5px;
	}
	.bp-logo-sm .wm {
		font-size: 14px;
	}
	.bp-logo-lg .crest {
		font-size: 13px;
		padding: 4px 6px;
	}
	.bp-logo-lg .wm {
		font-size: 20px;
	}
	.foot-brand {
		flex: 1; /* take the space left of the button so the logo can centre in it */
		display: flex;
		align-items: center;
		justify-content: center;
	}
	.pn-drop-foot .share {
		flex-shrink: 0;
		background: var(--btn);
		border: 1.5px solid var(--ink);
		color: var(--btn-fg);
		font-family: var(--display2);
		font-weight: 800;
		font-size: 12px;
		letter-spacing: 0.03em;
		text-transform: uppercase;
		padding: 11px 10px;
		cursor: pointer;
		white-space: nowrap;
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 6px;
	}
	.pn-drop-foot .share:active {
		transform: translateY(1px);
	}
	.pn-drop-foot .share[disabled] {
		opacity: 0.7;
		cursor: default;
	}

	/* export lockup — only inside the PNG */
	.caphint {
		display: none;
		width: 100%;
		align-items: center;
		gap: 10px;
	}
	.caphint .lockup {
		display: flex;
		align-items: center;
	}
	.caphint .ed {
		margin-left: auto;
		text-align: right;
		font-family: var(--mono);
		font-size: 9px;
		letter-spacing: 0.16em;
		text-transform: uppercase;
		color: var(--muted);
		line-height: 1.5;
	}
	.caphint .ed b {
		color: var(--fg);
		font-weight: 600;
	}

	/* capture mode strips chrome */
	.capturing .pn-drop-head .x,
	.capturing .tap,
	.capturing .pn-drop-progress {
		visibility: hidden;
	}
	.capturing .pn-drop-foot .share,
	.capturing .foot-brand {
		display: none;
	}
	.capturing .caphint {
		display: flex;
	}
	.pn-drop-card.capturing,
	.capturing .pn-drop-page {
		animation: none !important;
		transform: none !important;
		opacity: 1 !important;
	}

	/* Transform-only entrance — a paused animation timeline (background tab OR the
	   html-to-image snapshot) must never freeze the card at opacity:0 → blank PNG. */
	@keyframes drop-stamp {
		0% {
			transform: translateY(16px) scale(0.96);
		}
		100% {
			transform: translateY(0) scale(1);
		}
	}
	.pn-drop-page.enter {
		animation: page-in 360ms cubic-bezier(0.16, 1, 0.3, 1) both;
	}
	@keyframes page-in {
		from {
			transform: translateY(12px);
		}
		to {
			transform: translateY(0);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.pn-drop-card,
		.pn-drop-page.enter {
			animation: none;
		}
	}

	/* Short screens (≈iPhone SE, ≤700px tall): the card falls to 79vh, so the
	   only un-fitted page — Your Day (big position numeral + returns ledger) —
	   can overrun its box. Tighten its vertical rhythm here; taller phones keep
	   the generous sizing above. The table/picks/roast pages self-fit already. */
	@media (max-height: 700px) {
		.pn-drop-page {
			padding: 10px 22px 11px;
		}
		.yd-num {
			font-size: 76px;
		}
		.yd-num .ord {
			font-size: 24px;
		}
		.yd-hero {
			margin-bottom: 7px;
		}
		.yd-formline {
			padding: 5px 0;
		}
		.yd-ledger {
			margin-top: 6px;
		}
		.ledger-cap {
			margin: 6px 0 2px;
		}
		.ledger-row {
			padding: 5px 0;
		}
		.ledger-total {
			padding-top: 5px;
		}
	}

	/* Desktop: a wider, bolder back page; mobile values above are the source of truth. */
	@media (min-width: 720px) {
		.pn-drop-card {
			max-width: 480px;
			height: min(84vh, 720px);
		}
		.pn-drop-page {
			padding: 15px 34px 16px;
		}
		.yd-num {
			font-size: 128px;
		}
		.award-hero .name {
			font-size: 42px;
		}
		.np-name {
			font-size: 56px;
		}
	}
</style>
