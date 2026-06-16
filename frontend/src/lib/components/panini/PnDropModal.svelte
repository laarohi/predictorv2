<script lang="ts">
	import { onMount, onDestroy, tick } from 'svelte';
	import { fly } from 'svelte/transition';
	import { getLatestDrop } from '$lib/api/dailyDrop';
	import PnIcon from '$components/panini/PnIcon.svelte';
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

	type Row = { ic: IconName; lbl: string; name: string; rest: string };
	type Theme = 'personal' | 'table' | 'picks' | 'roast';
	type Page = { key: Theme; title: string; icon: IconName; light: boolean };

	const THEMES: Record<Theme, { title: string; icon: IconName; light: boolean }> = {
		personal: { title: 'Your Day', icon: 'medal', light: true },
		table: { title: 'The Table', icon: 'crown', light: false },
		picks: { title: 'The Picks', icon: 'skull', light: false },
		roast: { title: 'The Roast', icon: 'flame', light: true }
	};

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
		open = false;
		stopRaf();
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
			import.meta.env.DEV &&
			new URLSearchParams(window.location.search).get('drop') === 'force';
		try {
			const d = await getLatestDrop();
			if (d && (forced || !seenDrops().includes(d.drop_date))) {
				drop = d;
				open = true;
				if (autoAdvance) rafId = requestAnimationFrame(frame);
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
	function dur(ms: number): number {
		return reduced ? 0 : ms;
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

		// html-to-image doesn't carry theme custom props (--accent/--fg/…) into its
		// clone, so var()-based SVG glyph fills vanish. Pin them inline for the
		// snapshot, then strip them so page-to-page theme switches stay live.
		const themeVars = ['--accent', '--fg', '--seg', '--track', '--btn', '--btn-fg'];
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
					p.mover && { ic: 'chart' as IconName, lbl: 'On the Move', name: fmtNames(p.mover.names), rest: `climbed ${p.mover.delta} place${p.mover.delta === 1 ? '' : 's'}` },
					p.faceplant && { ic: 'skull' as IconName, lbl: 'Shat the Bed', name: fmtNames(p.faceplant.names), rest: `dropped ${Math.abs(p.faceplant.delta)} place${Math.abs(p.faceplant.delta) === 1 ? '' : 's'}` },
					p.points_haul && { ic: 'money' as IconName, lbl: 'Big Earner', name: fmtNames(p.points_haul.names), rest: `+${p.points_haul.points_gained} pts` },
					p.wooden_spoon && { ic: 'trophy' as IconName, lbl: 'Why Bother?', name: fmtNames(p.wooden_spoon.names), rest: `${p.wooden_spoon.behind_leader} pts off the top` }
				].filter((r): r is Row => !!r)
			: []
	);
	$: picksSupport = (
		p
			? [
					p.called_it && { ic: 'crystal-ball' as IconName, lbl: 'Nostradamus', name: fmtNames(p.called_it.names), rest: `${p.called_it.names.length === 1 ? 'SOLO' : 'nailed'} ${p.called_it.home_team} ${p.called_it.home_score}-${p.called_it.away_score} ${p.called_it.away_team}` },
					p.contrarian && { ic: 'glasses' as IconName, lbl: 'The Hipster', name: fmtNames(p.contrarian.names), rest: `${p.contrarian.names.length} of ${p.contrarian.total} on ${p.contrarian.home_team} v ${p.contrarian.away_team}` },
					p.coldest_streak && { ic: 'snowflake' as IconName, lbl: 'Coldest', name: fmtNames(p.coldest_streak.names), rest: `${p.coldest_streak.length} wrong on the bounce` },
					p.hottest_streak && { ic: 'flame' as IconName, lbl: 'Hottest', name: fmtNames(p.hottest_streak.names), rest: `${p.hottest_streak.length} correct on the bounce` }
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

	function segWidth(i: number): number {
		if (i < page) return 100;
		if (i > page) return 0;
		return autoAdvance ? Math.min(progress, 1) * 100 : 100;
	}
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
		const page = node.closest('.pn-drop-page') as HTMLElement | null;
		function fit(): void {
			if (!page) return;
			let size = 16;
			node.style.fontSize = `${size}px`;
			let guard = 0;
			while (size > 9.5 && page.scrollHeight > page.clientHeight && guard < 60) {
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
			<div class="pn-drop-wm" aria-hidden="true">
				<PnIcon name={cur.icon} size={260} color="var(--fg)" stroke={1.5} />
			</div>

			<div class="pn-drop-top">
				<div class="pn-drop-progress">
					{#each pages as _, i}
						<div class="seg"><div class="fill" style="width:{segWidth(i)}%"></div></div>
					{/each}
				</div>
				<div class="pn-drop-head">
					<span class="brand">THE BACK PAGE · {fmtDate(drop.drop_date)}</span>
					<button class="x" on:click|stopPropagation={dismiss} aria-label="Dismiss">×</button>
				</div>
			</div>

			<div class="pn-drop-body">
				{#key page}
					<div class="pn-drop-page">
						<div class="kicker" in:fly={{ y: 8, duration: dur(220) }}>{cur.title}</div>

						{#if cur.key === 'personal' && me}
							<div class="hero" in:fly={{ y: 14, duration: dur(300), delay: dur(60) }}>
								<div class="big">{me.position}<span class="ord">{ordinal(me.position)}</span></div>
								<div class="hero-sub"><b>{me.points}</b> pts{#if me.points_gained} · +{me.points_gained} today{/if}</div>
							</div>
							<div class="support">
								<div class="s-row" in:fly={{ y: 10, duration: dur(240), delay: dur(140) }}>
									{#if me.movement > 0}
										<span class="ic"><PnIcon name="arrow-up" size={15} color="var(--accent)" /></span><span class="s-val">Up <b>{me.movement}</b> place{me.movement === 1 ? '' : 's'} overnight</span>
									{:else if me.movement < 0}
										<span class="ic"><PnIcon name="arrow-down" size={15} color="var(--accent)" /></span><span class="s-val">Down <b>{Math.abs(me.movement)}</b> place{Math.abs(me.movement) === 1 ? '' : 's'} overnight</span>
									{:else}
										<span class="ic"><PnIcon name="minus" size={15} color="var(--accent)" /></span><span class="s-val">Held your ground overnight</span>
									{/if}
								</div>
								{#if me.hot_streak >= 2 || me.cold_streak >= 2}
									<div class="s-row" in:fly={{ y: 10, duration: dur(240), delay: dur(200) }}>
										<span class="ic"><PnIcon name={me.hot_streak >= 2 ? 'flame' : 'snowflake'} size={15} color="var(--accent)" /></span>
										<span class="s-val"><b>{me.hot_streak >= 2 ? me.hot_streak : me.cold_streak}</b> {me.hot_streak >= 2 ? 'correct' : 'wrong'} on the bounce</span>
									</div>
								{/if}
								{#each me.points_breakdown as c, i (c.label)}
									<div class="s-row" in:fly={{ y: 10, duration: dur(240), delay: dur(260 + i * 50) }}>
										<span class="ic"><PnIcon name={catIcon(c.label)} size={15} color="var(--accent)" /></span>
										<span class="s-val"><b>{c.points}</b> pts · {c.label}</span>
									</div>
								{/each}
								{#if !me.points_breakdown.length}
									<div class="s-row" in:fly={{ y: 10, duration: dur(240), delay: dur(260) }}>
										<span class="ic"><PnIcon name="clock" size={15} color="var(--accent)" /></span><span class="s-val">No points on the board yet — early days.</span>
									</div>
								{/if}
							</div>

						{:else if cur.key === 'table'}
							{#if p?.leader}
								<div class="hero" in:fly={{ y: 14, duration: dur(300), delay: dur(60) }}>
									<div class="hero-ic"><PnIcon name={cur.icon} size={38} color="var(--accent)" /></div>
									<div class="hero-lbl">Top Dog</div>
									<div class="hero-name">{fmtNames(p.leader.names)}</div>
									<div class="hero-sub"><b>{p.leader.points}</b> pts{#if p.leader.lead > 0} · +{p.leader.lead} clear{/if}</div>
								</div>
							{/if}
							<div class="support">
								{#each tableSupport as r, i (r.lbl)}
									<div class="s-row" in:fly={{ y: 10, duration: dur(240), delay: dur(140 + i * 70) }}>
										<span class="ic"><PnIcon name={r.ic} size={15} color="var(--accent)" /></span><span class="s-lbl">{r.lbl}</span>
										<span class="s-val"><b>{r.name}</b> <span class="s-stat">{r.rest}</span></span>
									</div>
								{/each}
							</div>

						{:else if cur.key === 'picks'}
							{#if p?.blunder}
								<div class="hero" in:fly={{ y: 14, duration: dur(300), delay: dur(60) }}>
									<div class="hero-ic"><PnIcon name={cur.icon} size={38} color="var(--accent)" /></div>
									<div class="hero-lbl">Dumbleflynn</div>
									<div class="hero-name">{fmtNames(p.blunder.names)}</div>
									<div class="hero-sub">said <b>{p.blunder.predicted}</b> · finished <b>{p.blunder.actual}</b><br />{p.blunder.home_team} v {p.blunder.away_team}</div>
								</div>
							{/if}
							<div class="support">
								{#each picksSupport as r, i (r.lbl)}
									<div class="s-row" in:fly={{ y: 10, duration: dur(240), delay: dur(140 + i * 70) }}>
										<span class="ic"><PnIcon name={r.ic} size={15} color="var(--accent)" /></span><span class="s-lbl">{r.lbl}</span>
										<span class="s-val"><b>{r.name}</b> <span class="s-stat">{r.rest}</span></span>
									</div>
								{/each}
							</div>

						{:else if cur.key === 'roast'}
							<div class="np-byline" in:fly={{ y: 8, duration: dur(220), delay: dur(70) }}>
								<span>Our Man in the Group Chat</span>
								{#if drop.roast_is_placeholder}<span class="sample">SAMPLE</span>{/if}
							</div>
							<p class="roast-body" use:fitText={drop.roast} in:fly={{ y: 12, duration: dur(320), delay: dur(100) }}>{drop.roast}</p>
							<div class="roast-meta" in:fly={{ y: 8, duration: dur(240), delay: dur(200) }}>
								from {drop.payload.match_count} matches · {drop.payload.player_count} players
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
				<button class="share" on:click|stopPropagation={share} disabled={busy}>
					{copied ? 'Saved ✓' : busy ? 'Building image…' : 'Share the Back Page'}
				</button>
				<div class="caphint" aria-hidden="true">THE PREDICTOR · WC26</div>
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
		animation: drop-fade 180ms ease-out;
	}
	.pn-drop-card {
		position: relative;
		display: flex;
		flex-direction: column;
		width: 100%;
		max-width: 360px;
		height: min(74vh, 560px);
		border: 2px solid var(--ink);
		box-shadow: 7px 7px 0 var(--ink);
		overflow: hidden;
		color: var(--fg);
		transition: background-color 320ms ease;
		animation: drop-stamp 380ms cubic-bezier(0.16, 1.1, 0.3, 1);
		/* default (dark) theme vars; overridden per theme below.
		   --seg: the CONSTANT progress-spine + kicker colour (the Stories signature).
		   --btn/--btn-fg: solid Share-button fill + its text. */
		--fg: var(--paper);
		--accent: var(--gold);
		--seg: var(--gold);
		--btn: var(--gold);
		--btn-fg: var(--ink);
		--track: rgba(241, 235, 222, 0.28);
	}
	/* On-brand palette: alternating light/dark, no green, no repeated blue. */
	.theme-personal {
		background: var(--gold);
		--fg: var(--ink);
		--accent: var(--red-deep);
		--seg: var(--red-deep);
		--btn: var(--red-deep);
		--btn-fg: var(--paper);
		--track: rgba(14, 29, 64, 0.3);
	}
	.theme-table {
		background: var(--ink);
		--fg: var(--paper);
		--accent: var(--gold);
		--seg: var(--gold);
		--btn: var(--gold);
		--btn-fg: var(--ink);
		--track: rgba(241, 235, 222, 0.28);
	}
	.theme-picks {
		background: var(--red-deep);
		--fg: var(--paper);
		--accent: var(--gold);
		--seg: var(--gold);
		--btn: var(--gold);
		--btn-fg: var(--ink);
		--track: rgba(241, 235, 222, 0.28);
	}
	/* The Roast is now a newspaper "back page": cream newsprint, navy ink, red
	   masthead accents, justified column with a drop cap. */
	.theme-roast {
		background: var(--paper);
		--fg: var(--ink);
		--accent: var(--red);
		--seg: var(--ink);
		--btn: var(--ink);
		--btn-fg: var(--paper);
		--track: rgba(14, 29, 64, 0.3);
	}

	/* Faded geometric watermark (PnIcon, not emoji) */
	.pn-drop-wm {
		position: absolute;
		right: -34px;
		bottom: 60px;
		opacity: 0.12;
		pointer-events: none;
		z-index: 0;
		line-height: 0;
	}
	.theme-personal .pn-drop-wm {
		opacity: 0.14;
	}
	/* Newspaper page is text + rules — no big faded icon. */
	.theme-roast .pn-drop-wm {
		display: none;
	}

	.pn-drop-top {
		position: relative;
		z-index: 3;
		padding: 10px 14px 0;
	}
	.pn-drop-progress {
		display: flex;
		gap: 4px;
	}
	.seg {
		flex: 1;
		height: 4px;
		background: var(--track);
		overflow: hidden;
	}
	.seg .fill {
		height: 100%;
		background: var(--seg);
		transition: none; /* RAF drives width every frame — a 90ms ease perpetually lags */
	}
	.pn-drop-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 8px 0 4px;
	}
	.pn-drop-head .brand {
		font-family: var(--mono);
		font-size: 9.5px;
		letter-spacing: 0.16em;
		text-transform: uppercase;
		color: color-mix(in srgb, var(--fg) 65%, transparent);
	}
	.pn-drop-head .x {
		background: none;
		border: none;
		font-size: 24px;
		line-height: 1;
		color: var(--fg);
		cursor: pointer;
		padding: 0 2px;
	}

	.pn-drop-body {
		position: relative;
		z-index: 1;
		flex: 1;
		overflow: hidden;
	}

	/* Footer share CTA — sits below the tap zones so it's never a nav tap. */
	.pn-drop-foot {
		position: relative;
		z-index: 3;
		padding: 10px 16px 14px;
		border-top: 1.5px solid color-mix(in srgb, var(--fg) 18%, transparent);
	}
	.pn-drop-foot .share {
		width: 100%;
		background: var(--btn);
		border: 1.5px solid var(--ink);
		color: var(--btn-fg);
		font-family: var(--display2);
		font-weight: 700;
		font-size: 14px;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		padding: 12px;
		cursor: pointer;
	}
	.pn-drop-foot .share:active {
		transform: translateY(1px);
	}
	.pn-drop-foot .share[disabled] {
		opacity: 0.7;
		cursor: default;
	}
	/* Brand line shown only inside the rasterised PNG (replaces the button). */
	.caphint {
		display: none;
		text-align: center;
		font-family: var(--mono);
		font-size: 11px;
		letter-spacing: 0.18em;
		text-transform: uppercase;
		color: color-mix(in srgb, var(--fg) 72%, transparent);
		padding: 11px 0 3px;
	}
	/* Snapshot mode: strip interactive chrome so the shared image is a clean card. */
	.capturing .pn-drop-head .x,
	.capturing .tap,
	.capturing .pn-drop-progress {
		visibility: hidden;
	}
	.capturing .pn-drop-foot .share {
		display: none;
	}
	.capturing .caphint {
		display: block;
	}
	.pn-drop-page {
		position: absolute;
		inset: 0;
		display: flex;
		flex-direction: column;
		justify-content: flex-start; /* was center — kills P1/P2 dead-gap + P3/P4 crowding */
		padding: 14px 30px 16px; /* wide side gutters keep text clear of the nav arrows */
		overflow: hidden; /* a story page must never scroll */
	}
	/* The roast NEVER scrolls — `use:fitText` shrinks it to fit so the whole thing
	   is always visible (and never clipped in the exported PNG). */
	.theme-roast .pn-drop-page {
		overflow: hidden;
	}

	.kicker {
		font-family: var(--display);
		font-size: 12px;
		letter-spacing: 0.22em;
		text-transform: uppercase;
		color: var(--seg);
		margin-bottom: 10px;
	}

	.hero {
		margin-bottom: 14px;
	}
	.hero .big {
		font-family: var(--display);
		font-size: 58px;
		line-height: 0.9;
		color: var(--fg);
	}
	.hero .big .ord {
		font-size: 24px;
		vertical-align: super;
		margin-left: 2px;
	}
	.hero .hero-ic {
		line-height: 0;
		margin-bottom: 6px;
	}
	.hero .hero-lbl {
		font-family: var(--mono);
		font-size: 12.5px;
		font-weight: 600;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--accent); /* the award name pops; the winner still leads by size */
		margin-bottom: 6px;
	}
	.hero .hero-name {
		font-family: var(--display);
		font-size: 25px;
		line-height: 1.02;
		color: var(--fg);
		margin-bottom: 5px;
	}
	.hero .hero-sub {
		font-family: var(--body);
		font-size: 14px;
		color: color-mix(in srgb, var(--fg) 88%, transparent);
	}
	.hero .hero-sub b {
		color: var(--fg);
		font-family: var(--display2);
		font-weight: 700;
	}
	.support {
		border-top: 2px solid color-mix(in srgb, var(--fg) 22%, transparent);
	}
	.s-row {
		display: grid;
		grid-template-columns: 20px 1fr; /* icon gutter + content; no flex-wrap reflow */
		align-items: start;
		column-gap: 8px;
		row-gap: 2px;
		padding: 8px 0;
		border-bottom: 1px solid color-mix(in srgb, var(--fg) 13%, transparent);
	}
	.s-row:last-child {
		border-bottom: none;
	}
	.s-row .ic {
		grid-row: 1 / span 2; /* glyph spans the label + value lines */
		align-self: center;
		display: flex;
		align-items: center;
		justify-content: center;
		line-height: 0; /* inline SVG — no text baseline gap */
	}
	.s-row .s-lbl {
		grid-column: 2;
		font-family: var(--mono);
		font-size: 10.5px;
		font-weight: 600;
		letter-spacing: 0.07em;
		text-transform: uppercase;
		color: var(--accent); /* award name reads as a bold coloured label */
	}
	.s-row .s-val {
		grid-column: 2;
		font-family: var(--body);
		font-size: 12.5px;
		line-height: 1.35;
		color: var(--fg);
	}
	.s-row .s-val b {
		font-family: var(--display2);
		font-weight: 700;
	}
	.s-row .s-stat {
		color: color-mix(in srgb, var(--fg) 62%, transparent);
	}

	/* Light pages (gold/cream): floor muted text higher — 60–68% reads muddy on gold.
	   (Award labels are now accent-coloured, so they're excluded here.) */
	.light .hero .hero-sub {
		color: color-mix(in srgb, var(--fg) 92%, transparent);
	}
	.light .s-row .s-stat,
	.light .roast-meta {
		color: color-mix(in srgb, var(--fg) 72%, transparent);
	}
	.light .pn-drop-head .brand {
		color: color-mix(in srgb, var(--fg) 75%, transparent);
	}

	/* ── Newspaper "back page" treatment for the Roast page ──────────────────
	   THE ROAST headline (thick rule) + byline (thin rule) = a double-rule
	   nameplate; the roast itself is a justified column with a red drop cap. */
	.theme-roast .kicker {
		font-size: 27px;
		letter-spacing: 0.005em;
		line-height: 1;
		color: var(--ink);
		margin-bottom: 0;
		padding-bottom: 6px;
		border-bottom: 3px solid var(--ink);
	}
	.np-byline {
		display: flex;
		align-items: center;
		gap: 8px;
		font-family: var(--mono);
		font-size: 9px;
		letter-spacing: 0.16em;
		text-transform: uppercase;
		color: var(--red);
		padding: 6px 0 9px;
		border-bottom: 1px solid color-mix(in srgb, var(--ink) 32%, transparent);
		margin-bottom: 13px;
	}
	.np-byline .sample {
		font-size: 8.5px;
		background: var(--ink);
		color: var(--paper);
		padding: 1px 5px;
		letter-spacing: 0.08em;
	}
	.theme-roast .roast-body {
		text-align: justify;
		hyphens: auto;
	}
	.theme-roast .roast-body::first-letter {
		float: left;
		font-family: var(--display);
		font-size: 3.1em;
		line-height: 0.7;
		margin: 5px 7px 0 0;
		color: var(--red);
	}
	.theme-roast .roast-meta {
		margin-top: 13px;
		padding-top: 8px;
		border-top: 1px solid color-mix(in srgb, var(--ink) 25%, transparent);
		color: color-mix(in srgb, var(--ink) 55%, transparent);
	}
	.roast-body {
		margin: 0;
		font-family: var(--body);
		font-size: 15px;
		line-height: 1.5;
		color: var(--fg);
	}
	.roast-meta {
		margin-top: 14px;
		font-family: var(--mono);
		font-size: 9.5px;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: color-mix(in srgb, var(--fg) 50%, transparent);
	}

	.tap {
		position: absolute;
		top: 0;
		bottom: 0;
		z-index: 2;
		display: flex;
		align-items: center;
		background: none;
		border: none;
		padding: 0 4px;
		cursor: pointer;
		-webkit-tap-highlight-color: transparent;
	}
	.tap.left {
		left: 0;
		width: 32%;
		justify-content: flex-start;
	}
	.tap.right {
		right: 0;
		width: 68%;
		justify-content: flex-end;
	}
	/* Paging affordance — a subtle bare chevron at each edge (no pill). */
	.navarrow {
		display: flex;
		align-items: center;
		justify-content: center;
		line-height: 0;
		opacity: 0.38;
	}

	/* Desktop: more room → a wider, bolder Drop. Mobile sizing untouched. */
	@media (min-width: 720px) {
		.pn-drop-card {
			max-width: 560px;
			height: min(82vh, 720px);
		}
		.pn-drop-page {
			padding: 22px 44px 24px; /* wider card → roomier gutters, arrows still clear */
		}
		.kicker {
			font-size: 13px;
			margin-bottom: 14px;
		}
		.hero .big {
			font-size: 80px;
		}
		.hero .big .ord {
			font-size: 32px;
		}
		.hero .hero-name {
			font-size: 33px;
		}
		.hero .hero-sub {
			font-size: 16px;
		}
		.s-row .s-val {
			font-size: 14px;
		}
		.roast-body {
			font-size: 17px;
			line-height: 1.55;
		}
	}

	@keyframes drop-fade {
		from {
			opacity: 0;
		}
	}
	@keyframes drop-stamp {
		0% {
			opacity: 0;
			transform: translateY(16px) scale(0.92);
		}
		60% {
			opacity: 1;
		}
		100% {
			transform: translateY(0) scale(1);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.pn-drop-scrim,
		.pn-drop-card {
			animation: none;
		}
		.pn-drop-card,
		.seg .fill {
			transition: none;
		}
	}
</style>
