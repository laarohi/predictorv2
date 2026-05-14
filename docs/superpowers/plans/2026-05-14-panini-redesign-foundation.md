# Panini Redesign — Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the shared Panini design system (fonts, CSS tokens, paper/grain shell, masthead, bottom nav, flags, icons) as a self-contained, additive layer — so subsequent plans can migrate individual pages one at a time without breaking the existing dark theme.

**Architecture:** Purely additive — no existing files are deleted or restyled. Panini lives behind a `.pn` CSS scope with its own custom-property palette (`--paper`, `--ink`, `--red`, etc.), independent of DaisyUI. Current pages continue to render in the existing `[data-theme="predictor"]` dark theme until each one is migrated by a future plan. A sandbox route `/_panini` lets you verify the chrome visually at 1440px and 375px before any real page is touched.

**Tech Stack:** SvelteKit + TypeScript, raw CSS (no new Tailwind utilities), Google Fonts (Archivo Black, Archivo, IBM Plex Sans, IBM Plex Mono).

---

## File Structure

**Create:**
- `frontend/src/lib/styles/panini-base.css` — full Panini chrome stylesheet (root vars, masthead, mobile chrome, paper grain, card/sticker/tag/button primitives)
- `frontend/src/lib/components/panini/PnFlag.svelte` — flag-stripe component, 32 country codes
- `frontend/src/lib/components/panini/PnIcon.svelte` — chunky pictogram icon set
- `frontend/src/lib/components/panini/PnMast.svelte` — desktop masthead with 5-tab nav + user avatar
- `frontend/src/lib/components/panini/PnBottomNav.svelte` — mobile bottom 5-tab nav
- `frontend/src/lib/components/panini/PnStrip.svelte` — red sub-strip (LIVE / Next Lock / You)
- `frontend/src/lib/components/panini/PnPageShell.svelte` — top-level page wrapper (paper grain + chrome slots)
- `frontend/src/lib/types/panini.ts` — shared TS types for Panini component props
- `frontend/src/routes/_panini/+page.svelte` — Foundation sandbox/test page

**Modify:**
- `frontend/src/app.html` — add Google Fonts links for the four Panini fonts
- `frontend/src/app.css` — `@import` the new `panini-base.css`
- `CLAUDE.md` — update the "UI Guidelines" section to document the Panini aesthetic

**Untouched:** all existing routes, components, stores, and the DaisyUI `predictor` theme. The Foundation plan does NOT delete `stadium-card`, `match-card`, etc. — those retire only as each page migrates.

---

## Task 1: Add Panini fonts to `app.html`

**Files:**
- Modify: `frontend/src/app.html:9-12`

- [ ] **Step 1: Add new Google Fonts link alongside existing one**

Edit `frontend/src/app.html`. The existing Google Fonts `<link>` line for Bebas Neue + DM Sans stays. Add a second `<link>` immediately after it for the Panini fonts:

```html
		<!-- Google Fonts: Bebas Neue (display) + DM Sans (body) — current theme -->
		<link rel="preconnect" href="https://fonts.googleapis.com" />
		<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
		<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:ital,opsz,wght@0,9..40,100..1000;1,9..40,100..1000&display=swap" rel="stylesheet" />
		<!-- Google Fonts: Panini theme — Archivo Black (display), Archivo (display2), IBM Plex Sans (body), IBM Plex Mono (mono) -->
		<link href="https://fonts.googleapis.com/css2?family=Archivo+Black&family=Archivo:wght@400;500;600;700;800;900&family=IBM+Plex+Sans:wght@300;400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet" />
```

- [ ] **Step 2: Verify dev server still starts**

```bash
cd frontend && npm run dev
```

Expected: server boots on `http://localhost:5173`, no console errors. Browser DevTools → Network tab → confirm `fonts.googleapis.com/css2?family=Archivo+Black...` loads with HTTP 200.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app.html
git commit -m "feat(panini): load Archivo + IBM Plex font families"
```

---

## Task 2: Create `panini-base.css`

**Files:**
- Create: `frontend/src/lib/styles/panini-base.css`

This is the consolidated stylesheet for all shared Panini chrome — root variables, paper grain, desktop masthead, red sub-strip, mobile status bar + header + bottom tab nav, mobile body, page banner, card + sticker + tag + button primitives. It is a direct port of the `pnStyles` constant in the `panini-shared.jsx` design source, with no behavioural changes.

- [ ] **Step 1: Create the file with full Panini base styles**

Create `frontend/src/lib/styles/panini-base.css` with this content:

```css
/* =========================================================================
 * Panini base stylesheet — chrome only.
 * All styles are scoped under .pn so they cannot affect existing pages.
 * Ported from panini-shared.jsx (the design source).
 * ========================================================================= */

.pn {
	--paper: #f1ebde;
	--paper-2: #e9e1cf;
	--paper-3: #dfd4ba;
	--ink: #0e1d40;
	--ink-2: #514a3d;
	--ink-3: #8a826f;
	--red: #c8281f;
	--red-deep: #8a1610;
	--navy: #1a3168;
	--navy-deep: #0a1733;
	--gold: #d49a2e;
	--green: #1b6c3e;
	--display: 'Archivo Black', 'Impact', sans-serif;
	--display2: 'Archivo', system-ui, sans-serif;
	--body: 'IBM Plex Sans', system-ui, sans-serif;
	--mono: 'IBM Plex Mono', monospace;
	font-family: var(--body);
	background: var(--paper);
	color: var(--ink);
	width: 100%;
	min-height: 100vh;
	position: relative;
}
.pn *, .pn *::before, .pn *::after { box-sizing: border-box; }

/* Subtle paper grain */
.pn::before {
	content: "";
	position: absolute; inset: 0;
	pointer-events: none;
	z-index: 1;
	background-image:
		url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/%3E%3CfeColorMatrix values='0 0 0 0 0.4  0 0 0 0 0.3  0 0 0 0 0.2  0 0 0 0.18 0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
	mix-blend-mode: multiply;
	opacity: 0.5;
}

/* ===== DESKTOP MASTHEAD ===== */
.pn-mast {
	position: relative;
	background: var(--ink);
	color: var(--paper);
	display: grid;
	grid-template-columns: auto 1fr auto;
	align-items: center;
	padding: 16px 28px;
	gap: 28px;
	z-index: 3;
	border-bottom: 4px solid var(--red);
}
.pn-mast .logo { display: flex; align-items: center; gap: 12px; }
.pn-mast .crest {
	width: 38px; height: 38px;
	background: var(--red);
	display: grid; place-items: center;
	font-family: var(--display);
	font-size: 22px; line-height: 1;
	color: var(--paper);
	transform: rotate(-4deg);
	box-shadow: 4px 4px 0 var(--paper);
}
.pn-mast .logo-name {
	font-family: var(--display);
	font-size: 28px; line-height: 1;
	letter-spacing: -0.01em;
	text-transform: uppercase;
}
.pn-mast .logo-vol {
	font-family: var(--mono); font-size: 11px;
	letter-spacing: 0.16em; color: var(--paper-3);
	margin-top: 2px; text-transform: uppercase;
}
.pn-mast .nav { display: flex; }
.pn-mast .nav a {
	font-family: var(--display); font-size: 13px;
	letter-spacing: 0.06em; text-transform: uppercase;
	padding: 8px 16px;
	color: var(--paper-3); text-decoration: none;
	border-right: 1px solid rgba(255,255,255,0.06);
	cursor: pointer;
}
.pn-mast .nav a:last-child { border-right: 0; }
.pn-mast .nav a.on { color: var(--paper); position: relative; }
.pn-mast .nav a.on::after {
	content: ""; position: absolute; left: 16px; right: 16px; bottom: -10px; height: 3px;
	background: var(--red);
}
.pn-mast .user {
	display: flex; align-items: center; gap: 12px;
	font-family: var(--mono); font-size: 11px;
	letter-spacing: 0.10em; text-transform: uppercase;
	color: var(--paper-3);
}
.pn-mast .user .av {
	width: 36px; height: 36px; background: var(--paper); color: var(--ink);
	display: grid; place-items: center;
	font-family: var(--display); font-size: 18px;
	transform: rotate(3deg);
}

/* Red sub-strip (live + lock + you) */
.pn-strip {
	background: var(--red); color: var(--paper);
	display: flex; gap: 28px;
	padding: 8px 28px;
	font-family: var(--mono); font-size: 11px;
	letter-spacing: 0.10em; text-transform: uppercase;
	border-bottom: 1px solid var(--navy);
	z-index: 3; position: relative;
}
.pn-strip b { font-weight: 600; }
.pn-strip .live::before {
	content: "●"; color: var(--paper); margin-right: 6px;
	animation: pn-blink 1.2s steps(2) infinite;
}
@keyframes pn-blink { 50% { opacity: 0.3; } }
.pn-strip .ml { margin-left: auto; }

/* ===== Page padding ===== */
.pn-body {
	padding: 28px;
	position: relative;
	z-index: 2;
}

/* ===== Section banner ===== */
.pn-banner {
	display: flex; align-items: center; gap: 14px;
	margin-bottom: 14px;
	padding-bottom: 8px;
	border-bottom: 2px solid var(--ink);
}
.pn-banner .n {
	background: var(--ink); color: var(--paper);
	font-family: var(--display); font-size: 16px;
	padding: 4px 10px; letter-spacing: 0.04em;
}
.pn-banner h2 {
	font-family: var(--display); font-size: 26px;
	line-height: 1; text-transform: uppercase; letter-spacing: -0.005em;
	margin: 0;
}
.pn-banner h2 em { color: var(--red); font-style: normal; }
.pn-banner .end {
	margin-left: auto;
	font-family: var(--mono); font-size: 11px;
	letter-spacing: 0.10em; color: var(--ink-3); text-transform: uppercase;
}

/* ===== Card chrome ===== */
.pn-card {
	background: var(--paper);
	border: 3px solid var(--ink);
	position: relative;
	box-shadow: 5px 5px 0 var(--ink);
	padding: 0;
}
.pn-card .pn-card-h {
	background: var(--ink); color: var(--paper);
	padding: 8px 14px;
	display: flex; justify-content: space-between; align-items: center;
	font-family: var(--display); font-size: 14px; letter-spacing: 0.04em;
	text-transform: uppercase;
}
.pn-card .pn-card-h .right {
	font-family: var(--mono); font-size: 11px; color: var(--paper-3);
	font-weight: 400; letter-spacing: 0.10em;
}
.pn-card .pn-card-h .live-dot {
	width: 8px; height: 8px; background: var(--gold); border-radius: 50%;
	display: inline-block; margin-right: 8px;
	animation: pn-blink 1.4s ease-in-out infinite;
}
.pn-card .pn-card-body { padding: 18px; }

/* ===== Sticker / KPI ===== */
.pn-sticker {
	background: var(--paper-2);
	border: 2px solid var(--ink);
	padding: 16px 18px;
	position: relative;
}
.pn-sticker.tilt-1 { transform: rotate(-0.8deg); }
.pn-sticker.tilt-2 { transform: rotate(0.6deg); }
.pn-sticker.tilt-3 { transform: rotate(-0.3deg); }
.pn-sticker .l {
	font-family: var(--mono); font-size: 10px; letter-spacing: 0.14em;
	text-transform: uppercase; color: var(--ink-3); margin-bottom: 4px;
	display: flex; align-items: center; gap: 6px;
}
.pn-sticker .l .pip {
	width: 8px; height: 8px; border-radius: 50%; background: var(--gold);
	display: inline-block;
}
.pn-sticker .v {
	font-family: var(--display); font-size: 44px; line-height: 0.9;
	letter-spacing: -0.02em; color: var(--ink);
	display: flex; align-items: baseline; gap: 6px;
}
.pn-sticker .v em { color: var(--red); font-style: normal; }
.pn-sticker .v .small { font-size: 18px; color: var(--ink-3); font-weight: normal; }
.pn-sticker .v .gold { color: var(--gold); }
.pn-sticker .v .green { color: var(--green); }
.pn-sticker .sub {
	font-family: var(--mono); font-size: 11px; color: var(--ink-3);
	margin-top: 6px; letter-spacing: 0.04em;
}
.pn-sticker .sub b { color: var(--ink); font-weight: 600; }
.pn-sticker .corner-tag {
	position: absolute; top: -8px; right: -8px;
	background: var(--red); color: var(--paper);
	font-family: var(--display); font-size: 11px;
	letter-spacing: 0.06em; text-transform: uppercase;
	padding: 3px 8px;
	border: 2px solid var(--ink);
	transform: rotate(6deg);
}
.pn-sticker .corner-tag.gold { background: var(--gold); color: var(--ink); }
.pn-sticker .corner-tag.green { background: var(--green); color: var(--paper); }

/* Tag chips */
.pn-tag {
	display: inline-flex; align-items: center; gap: 6px;
	padding: 4px 10px;
	font-family: var(--display); font-size: 11px;
	letter-spacing: 0.10em; text-transform: uppercase;
	border: 2px solid var(--ink);
	background: var(--paper); color: var(--ink);
}
.pn-tag.got { background: var(--green); color: var(--paper); border-color: var(--green); }
.pn-tag.gold { background: var(--gold); color: var(--ink); }
.pn-tag.red { background: var(--red); color: var(--paper); border-color: var(--red); }

/* Buttons */
.pn-btn {
	display: inline-flex; align-items: center; gap: 8px;
	padding: 11px 18px;
	font-family: var(--display); font-size: 13px;
	letter-spacing: 0.06em; text-transform: uppercase;
	background: var(--red); color: var(--paper);
	border: 2px solid var(--ink); cursor: pointer;
	box-shadow: 3px 3px 0 var(--ink);
	text-decoration: none;
	transition: transform 0.12s ease, box-shadow 0.12s ease;
}
.pn-btn:hover { transform: translate(-1px, -1px); box-shadow: 5px 5px 0 var(--ink); }
.pn-btn.gold { background: var(--gold); color: var(--ink); }
.pn-btn.ghost { background: var(--paper); color: var(--ink); }
.pn-btn.navy { background: var(--navy); color: var(--paper); }

/* ===== MOBILE bottom tab nav + status bar ===== */
.pn-mob-status {
	background: var(--ink); color: var(--paper);
	padding: 4px 18px 4px 22px;
	display: flex; justify-content: space-between; align-items: center;
	font-family: var(--mono); font-size: 11px;
	letter-spacing: 0.04em;
	height: 28px;
	position: relative; z-index: 4;
}
.pn-mob-status .time { font-weight: 600; }
.pn-mob-status .right { display: flex; gap: 5px; }

.pn-mob-header {
	background: var(--ink); color: var(--paper);
	padding: 8px 16px 10px;
	display: flex; align-items: center; justify-content: space-between;
	position: relative; z-index: 3;
	border-bottom: 3px solid var(--red);
}
.pn-mob-header .logo {
	display: flex; align-items: center; gap: 8px;
}
.pn-mob-header .crest {
	width: 28px; height: 28px;
	background: var(--red);
	display: grid; place-items: center;
	font-family: var(--display); font-size: 16px;
	color: var(--paper);
	transform: rotate(-4deg);
	box-shadow: 2px 2px 0 var(--paper);
}
.pn-mob-header .nm {
	font-family: var(--display); font-size: 16px;
	letter-spacing: 0.02em; text-transform: uppercase;
}
.pn-mob-header .nm .sub {
	display: block; font-family: var(--mono); font-size: 9px;
	color: var(--paper-3); letter-spacing: 0.12em;
	font-weight: 400; margin-top: 1px;
}
.pn-mob-header .right {
	display: flex; align-items: center; gap: 12px;
	font-family: var(--mono); font-size: 10px; color: var(--paper-3);
	letter-spacing: 0.08em; text-transform: uppercase;
}
.pn-mob-header .right .av {
	width: 30px; height: 30px;
	background: var(--gold); color: var(--ink);
	display: grid; place-items: center;
	font-family: var(--display); font-size: 14px;
}

.pn-mob-strip {
	background: var(--red); color: var(--paper);
	padding: 6px 14px;
	font-family: var(--mono); font-size: 10px;
	letter-spacing: 0.08em; text-transform: uppercase;
	position: relative; z-index: 3;
	display: flex; align-items: center; gap: 10px;
}
.pn-mob-strip .live::before {
	content: "●"; margin-right: 4px;
	animation: pn-blink 1.2s steps(2) infinite;
}
.pn-mob-strip .ml { margin-left: auto; }

.pn-mob-body {
	padding: 14px;
	background: var(--paper);
	flex: 1;
	position: relative;
	z-index: 2;
	overflow-y: auto;
}

.pn-mob-tab {
	position: sticky; bottom: 0; left: 0; right: 0;
	background: var(--ink);
	border-top: 3px solid var(--red);
	display: flex;
	z-index: 4;
}
.pn-mob-tab a {
	flex: 1;
	display: flex; flex-direction: column; align-items: center; gap: 4px;
	padding: 10px 4px 14px;
	font-family: var(--display); font-size: 10px;
	letter-spacing: 0.06em; text-transform: uppercase;
	color: var(--paper-3);
	text-decoration: none;
	cursor: pointer;
}
.pn-mob-tab a.on { color: var(--gold); position: relative; }
.pn-mob-tab a.on::before {
	content: ""; position: absolute; top: 0; left: 30%; right: 30%; height: 2px;
	background: var(--gold);
}
.pn-mob-tab svg { width: 20px; height: 20px; }
```

- [ ] **Step 2: Verify file is valid CSS**

```bash
cd frontend && npx prettier --check src/lib/styles/panini-base.css
```

Expected: prints `Checking formatting...` and (likely) reports a single style/formatting note. If it fails on real syntax (e.g. an unclosed brace), fix and re-run.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/styles/panini-base.css
git commit -m "feat(panini): add panini-base.css with chrome and primitives"
```

---

## Task 3: Wire `panini-base.css` into the app

**Files:**
- Modify: `frontend/src/app.css:1-3`

- [ ] **Step 1: Add the import line**

Edit `frontend/src/app.css`. Insert `@import` after the existing `@tailwind` directives:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

/* Panini design system (scoped under .pn) — additive, does not affect dark theme pages */
@import './lib/styles/panini-base.css';

/* Base styles */
@layer base {
```

- [ ] **Step 2: Verify dev server compiles**

```bash
cd frontend && npm run dev
```

Expected: server boots clean, no PostCSS or Vite errors in the terminal. Open `http://localhost:5173/login` in the browser — page should look **identical** to before (because no element has the `.pn` class yet).

- [ ] **Step 3: Run type check**

```bash
cd frontend && npm run check
```

Expected: no new errors. (There are ~58 pre-existing warnings per memory; warning count should not increase.)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app.css
git commit -m "feat(panini): import panini-base.css from app.css"
```

---

## Task 4: Create `PnFlag.svelte`

**Files:**
- Create: `frontend/src/lib/components/panini/PnFlag.svelte`

- [ ] **Step 1: Create the component**

Create `frontend/src/lib/components/panini/PnFlag.svelte` with this content:

```svelte
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
```

- [ ] **Step 2: Run type check**

```bash
cd frontend && npm run check
```

Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/components/panini/PnFlag.svelte
git commit -m "feat(panini): add PnFlag component"
```

---

## Task 5: Create `PnIcon.svelte`

**Files:**
- Create: `frontend/src/lib/components/panini/PnIcon.svelte`

Includes the full Panini icon set plus a new `cog` glyph for the Admin nav tab (Panini did not design one).

- [ ] **Step 1: Create the component**

Create `frontend/src/lib/components/panini/PnIcon.svelte`:

```svelte
<script lang="ts">
	// Bold, geometric pictograms in the PANINI style. All icons are 24×24
	// viewBox, currentColor-friendly by default. Sizes are controlled via the
	// `size` prop (renders to width + height in px).
	export type IconName =
		| 'ball'
		| 'home'
		| 'predict'
		| 'bracket'
		| 'trophy'
		| 'list'
		| 'flag'
		| 'target'
		| 'chevron-right'
		| 'chevron-left'
		| 'arrow-up'
		| 'arrow-down'
		| 'minus'
		| 'star'
		| 'lock'
		| 'clock'
		| 'whistle'
		| 'cog';

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
```

- [ ] **Step 2: Run type check**

```bash
cd frontend && npm run check
```

Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/components/panini/PnIcon.svelte
git commit -m "feat(panini): add PnIcon component with cog glyph for admin"
```

---

## Task 6: Create `PnMast.svelte` (desktop masthead)

**Files:**
- Create: `frontend/src/lib/components/panini/PnMast.svelte`

The masthead substitutes the Panini design's nav labels (Dashboard / Fixtures / Bracket / Leaderboard / Results) with **the current site's five tabs**: Dashboard, Predictions, Results, Leaderboard, Admin (Admin only if `$user?.is_admin`). Uses the existing auth store; routes match the existing layout.

- [ ] **Step 1: Create the component**

Create `frontend/src/lib/components/panini/PnMast.svelte`:

```svelte
<script lang="ts">
	import { page } from '$app/stores';
	import { user } from '$stores/auth';

	export let activeOverride: string | null = null;

	type NavItem = { href: string; label: string; key: string };

	const items: NavItem[] = [
		{ href: '/', label: 'Dashboard', key: 'dash' },
		{ href: '/predictions', label: 'Predictions', key: 'pred' },
		{ href: '/results', label: 'Results', key: 'res' },
		{ href: '/leaderboard', label: 'Leaderboard', key: 'ldb' }
	];

	$: currentPath = $page.url.pathname;
	$: isActive = (href: string, key: string) => {
		if (activeOverride !== null) return activeOverride === key;
		return currentPath === href || (href !== '/' && currentPath.startsWith(href));
	};
</script>

<header class="pn-mast">
	<a href="/" class="logo" style="text-decoration: none; color: inherit;">
		<div class="crest">P</div>
		<div>
			<div class="logo-name">The Predictor</div>
			<div class="logo-vol">Vol. I — World Cup 2026</div>
		</div>
	</a>
	<nav class="nav">
		{#each items as item}
			<a href={item.href} class:on={isActive(item.href, item.key)}>{item.label}</a>
		{/each}
		{#if $user?.is_admin}
			<a href="/admin" class:on={isActive('/admin', 'adm')}>Admin</a>
		{/if}
	</nav>
	<div class="user">
		<span>{$user?.name ?? 'Guest'}</span>
		<div class="av">{($user?.name?.[0] ?? '?').toUpperCase()}</div>
	</div>
</header>
```

- [ ] **Step 2: Run type check**

```bash
cd frontend && npm run check
```

Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/components/panini/PnMast.svelte
git commit -m "feat(panini): add PnMast desktop masthead with 5-tab nav"
```

---

## Task 7: Create `PnStrip.svelte` (red sub-strip)

**Files:**
- Create: `frontend/src/lib/components/panini/PnStrip.svelte`

The strip currently below the masthead is a *signal band*: live match, next lock countdown, your position. For Foundation it accepts placeholder props — real data wiring lives in the Dashboard plan.

- [ ] **Step 1: Create the component**

Create `frontend/src/lib/components/panini/PnStrip.svelte`:

```svelte
<script lang="ts">
	export let liveLabel: string | null = null;
	export let lockLabel: string | null = null;
	export let youLabel: string | null = null;
</script>

<div class="pn-strip">
	{#if liveLabel}
		<span class="live">{@html liveLabel}</span>
	{/if}
	{#if lockLabel}
		<span>{@html lockLabel}</span>
	{/if}
	{#if youLabel}
		<span class="ml">{@html youLabel}</span>
	{/if}
</div>
```

Note: `{@html ...}` is used because the design uses inline `<b>` tags inside each label (e.g., "<b>LIVE</b> · Argentina 2–1 Croatia"). All values for `liveLabel/lockLabel/youLabel` are produced by trusted page code, never user input — so the XSS surface is nil. We document this contract here so future callers don't ever pass user text into these props.

- [ ] **Step 2: Run type check**

```bash
cd frontend && npm run check
```

Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/components/panini/PnStrip.svelte
git commit -m "feat(panini): add PnStrip red sub-strip"
```

---

## Task 8: Create `PnBottomNav.svelte` (mobile bottom 5-tab)

**Files:**
- Create: `frontend/src/lib/components/panini/PnBottomNav.svelte`

The Panini design has 4 mobile tabs; we extend it to 5 (Dashboard / Predictions / Results / Leaderboard / Admin) per the captured decisions. The component matches the current layout's mobile nav semantics (visible only below 700px) but renders in the Panini style.

- [ ] **Step 1: Create the component**

Create `frontend/src/lib/components/panini/PnBottomNav.svelte`:

```svelte
<script lang="ts">
	import { page } from '$app/stores';
	import { user } from '$stores/auth';
	import PnIcon from './PnIcon.svelte';
	import type { IconName } from './PnIcon.svelte';

	type NavItem = { href: string; label: string; icon: IconName; key: string };

	const items: NavItem[] = [
		{ href: '/', label: 'Home', icon: 'home', key: 'dash' },
		{ href: '/predictions', label: 'Predict', icon: 'predict', key: 'pred' },
		{ href: '/results', label: 'Results', icon: 'whistle', key: 'res' },
		{ href: '/leaderboard', label: 'Standings', icon: 'trophy', key: 'ldb' }
	];

	$: currentPath = $page.url.pathname;
	$: isActive = (href: string) =>
		currentPath === href || (href !== '/' && currentPath.startsWith(href));
</script>

<nav class="pn-mob-tab" style="position: fixed; bottom: 0; left: 0; right: 0;">
	{#each items as item}
		{@const active = isActive(item.href)}
		<a href={item.href} class:on={active}>
			<PnIcon name={item.icon} size={20} color={active ? '#d49a2e' : '#8a826f'} />
			{item.label}
		</a>
	{/each}
	{#if $user?.is_admin}
		{@const active = isActive('/admin')}
		<a href="/admin" class:on={active}>
			<PnIcon name="cog" size={20} color={active ? '#d49a2e' : '#8a826f'} />
			Admin
		</a>
	{/if}
</nav>
```

- [ ] **Step 2: Run type check**

```bash
cd frontend && npm run check
```

Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/components/panini/PnBottomNav.svelte
git commit -m "feat(panini): add PnBottomNav mobile 5-tab nav"
```

---

## Task 9: Create `PnPageShell.svelte` (page wrapper)

**Files:**
- Create: `frontend/src/lib/components/panini/PnPageShell.svelte`

The shell is what every Panini page renders inside. It establishes the `.pn` scope (so all CSS variables apply), shows the desktop masthead above 700px and the mobile bottom nav below, and offers an optional red strip slot. Pages migrating to Panini import this and slot their body.

- [ ] **Step 1: Create the component**

Create `frontend/src/lib/components/panini/PnPageShell.svelte`:

```svelte
<script lang="ts">
	import PnMast from './PnMast.svelte';
	import PnBottomNav from './PnBottomNav.svelte';
	import PnStrip from './PnStrip.svelte';

	export let activeOverride: string | null = null;
	export let liveLabel: string | null = null;
	export let lockLabel: string | null = null;
	export let youLabel: string | null = null;
	export let showStrip: boolean = true;
</script>

<div class="pn pn-shell">
	<div class="desktop-only">
		<PnMast {activeOverride} />
		{#if showStrip}
			<PnStrip {liveLabel} {lockLabel} {youLabel} />
		{/if}
	</div>

	<main class="pn-body">
		<slot />
	</main>

	<div class="mobile-only">
		<PnBottomNav />
	</div>
</div>

<style>
	.pn-shell {
		display: flex;
		flex-direction: column;
		min-height: 100vh;
	}
	.desktop-only {
		display: none;
	}
	.mobile-only {
		display: block;
	}
	:global(.pn-shell main.pn-body) {
		flex: 1;
		padding-bottom: 80px; /* room for mobile bottom nav */
	}
	@media (min-width: 700px) {
		.desktop-only {
			display: block;
		}
		.mobile-only {
			display: none;
		}
		:global(.pn-shell main.pn-body) {
			padding-bottom: 28px;
		}
	}
</style>
```

- [ ] **Step 2: Run type check**

```bash
cd frontend && npm run check
```

Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/components/panini/PnPageShell.svelte
git commit -m "feat(panini): add PnPageShell page wrapper"
```

---

## Task 10: Create Foundation sandbox page `/_panini`

**Files:**
- Create: `frontend/src/routes/_panini/+page.svelte`

A test route that renders the foundation chrome with sample content — every primitive (card, sticker, tag, button, banner), the full icon set, several flags. Lets us eyeball the design at 1440 and 375 before any real page is migrated. The leading underscore convention keeps it from appearing in nav and signals "internal".

- [ ] **Step 1: Create the sandbox page**

Create `frontend/src/routes/_panini/+page.svelte`:

```svelte
<script lang="ts">
	import PnPageShell from '$lib/components/panini/PnPageShell.svelte';
	import PnFlag from '$lib/components/panini/PnFlag.svelte';
	import PnIcon from '$lib/components/panini/PnIcon.svelte';
	import type { IconName } from '$lib/components/panini/PnIcon.svelte';

	const icons: IconName[] = [
		'ball', 'home', 'predict', 'bracket', 'trophy', 'list', 'flag',
		'target', 'chevron-right', 'chevron-left', 'arrow-up', 'arrow-down',
		'minus', 'star', 'lock', 'clock', 'whistle', 'cog'
	];

	const flags = ['ARG', 'BRA', 'FRA', 'ESP', 'GER', 'ITA', 'POR', 'NED', 'ENG', 'MEX', 'USA', 'JPN'];
</script>

<PnPageShell
	liveLabel="<b>LIVE</b> · ARG 2–1 CRO · 41′"
	lockLabel="<b>Next lock</b> MEX–POL in 04:32"
	youLabel="<b>You</b> · 8th of 32 · 147 pts · ▲4"
>
	<section class="pn-banner">
		<span class="n">01</span>
		<h2>Foundation <em>sandbox</em></h2>
		<span class="end">Verify chrome · 1440 + 375</span>
	</section>

	<div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; margin-bottom: 24px;">
		<div class="pn-sticker tilt-1">
			<div class="l"><span class="pip"></span>Rank</div>
			<div class="v"><em>8</em><span class="small">/32</span></div>
			<div class="sub"><b>▲ 4</b> · last 7d</div>
		</div>
		<div class="pn-sticker tilt-2">
			<div class="l"><span class="pip"></span>Total</div>
			<div class="v">147</div>
			<div class="sub"><b>+42</b> · MD2</div>
		</div>
		<div class="pn-sticker tilt-3">
			<div class="l"><span class="pip"></span>Exact</div>
			<div class="v"><span class="green">3</span><span class="small">/16</span></div>
			<div class="sub"><b>+45 pts</b></div>
			<div class="corner-tag">Hot</div>
		</div>
	</div>

	<section class="pn-banner">
		<span class="n">02</span>
		<h2>Icons & <em>flags</em></h2>
	</section>

	<div style="display: flex; flex-wrap: wrap; gap: 14px; padding: 18px; background: var(--paper-2); border: 2px solid var(--ink); margin-bottom: 18px;">
		{#each icons as name}
			<div style="display: flex; flex-direction: column; align-items: center; gap: 6px; font-family: var(--mono); font-size: 10px; color: var(--ink-3);">
				<PnIcon {name} size={28} color="var(--ink)" />
				{name}
			</div>
		{/each}
	</div>

	<div style="display: flex; flex-wrap: wrap; gap: 10px; padding: 18px; background: var(--paper-2); border: 2px solid var(--ink); margin-bottom: 24px;">
		{#each flags as code}
			<div style="display: flex; align-items: center; gap: 8px; font-family: var(--display); font-size: 14px;">
				<PnFlag {code} w={28} h={20} />
				{code}
			</div>
		{/each}
	</div>

	<section class="pn-banner">
		<span class="n">03</span>
		<h2>Buttons & <em>tags</em></h2>
	</section>

	<div style="display: flex; gap: 12px; margin-bottom: 14px; flex-wrap: wrap;">
		<button class="pn-btn">Primary</button>
		<button class="pn-btn gold">Gold</button>
		<button class="pn-btn ghost">Ghost</button>
		<button class="pn-btn navy">Navy</button>
	</div>

	<div style="display: flex; gap: 10px; flex-wrap: wrap;">
		<span class="pn-tag">Plain</span>
		<span class="pn-tag gold">Gold</span>
		<span class="pn-tag got">Got it</span>
		<span class="pn-tag red">Locked</span>
	</div>
</PnPageShell>
```

- [ ] **Step 2: Verify with dev server**

```bash
cd frontend && npm run dev
```

Open `http://localhost:5173/_panini` in the browser:
- At **1440 px wide**: desktop masthead visible with "DASHBOARD / PREDICTIONS / RESULTS / LEADERBOARD / ADMIN" tabs, red sub-strip below, three tilted KPI stickers, icon grid, flag grid, buttons, tags. Paper-cream background with subtle grain.
- At **375 px wide** (DevTools responsive mode): masthead and strip are hidden, bottom 5-tab nav is fixed at bottom with current tab highlighted gold, content reflows to single column. Icons + flags remain readable.

If anything looks broken (wrong fonts, no paper background, icons missing) — fix before moving on.

- [ ] **Step 3: Run type check**

```bash
cd frontend && npm run check
```

Expected: no new errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/routes/_panini/+page.svelte
git commit -m "feat(panini): add foundation sandbox at /_panini"
```

---

## Task 11: Update CLAUDE.md UI Guidelines

**Files:**
- Modify: `CLAUDE.md` (the "UI Guidelines" section near the end)

- [ ] **Step 1: Replace the UI Guidelines section**

Find the section in `CLAUDE.md` that starts with `## UI Guidelines` and replace its body. Old content (for reference):

```markdown
## UI Guidelines

- Dark mode default (sports/premium aesthetic)
- High contrast with green/red for win/loss
- Save actions must show feedback only after backend confirms
- Mobile: show one logical group at a time, avoid grid layouts
- Phase tabs for switching between Phase 1 and Phase 2 predictions
```

Replace with:

```markdown
## UI Guidelines

The site uses the **Panini** design system — a sticker-album-inspired theme on cream paper with navy ink, red accents, and gold highlights. Pages are progressively migrated; until a page wraps itself in `<PnPageShell>` it continues to render in the legacy dark `predictor` theme.

**Design tokens** (defined as CSS variables on `.pn`):
- `--paper` `#f1ebde` (canvas) · `--paper-2` `#e9e1cf` · `--paper-3` `#dfd4ba`
- `--ink` `#0e1d40` (navy text) · `--ink-2` · `--ink-3` (subdued)
- `--red` `#c8281f` (signals, "you", urgency) · `--red-deep` `#8a1610`
- `--gold` `#d49a2e` (highlights, hot picks, exact scores)
- `--green` `#1b6c3e` (correct outcomes) · `--navy` `#1a3168` (deep panels)

**Typography:**
- `var(--display)` — Archivo Black (uppercase, tight) for numbers, titles, big stats
- `var(--display2)` — Archivo (regular display for medium-weight headings)
- `var(--body)` — IBM Plex Sans
- `var(--mono)` — IBM Plex Mono (labels, metadata, kickoffs)

**Sticker shadows:** All cards use offset hard shadows (`box-shadow: 5px 5px 0 var(--ink)`) and may carry a small `transform: rotate(±0.6deg)` tilt for character. Avoid soft drop shadows.

**Component primitives** (from `panini-base.css`): `pn-card`, `pn-sticker`, `pn-tag`, `pn-btn`, `pn-banner`. Page-specific styles arrive with each page's migration plan (`panini-dashboard.css`, etc.).

**Save actions** still show feedback only after the backend confirms.
**Mobile** still: one logical group at a time, avoid grid-of-cards on small screens.
**Phase tabs** still: switch between Phase 1 and Phase 2 predictions.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update UI guidelines for panini design system"
```

---

## Self-Review

**Spec coverage:**
- ✓ Theme tokens (vars on `.pn`) — Task 2
- ✓ Fonts (Archivo Black, Archivo, IBM Plex Sans + Mono) — Task 1
- ✓ Paper grain background — Task 2 (`.pn::before` SVG filter)
- ✓ Desktop masthead with 5 tabs (Dashboard/Predictions/Results/Leaderboard/Admin) — Task 6
- ✓ Mobile bottom nav with 5 tabs — Task 8
- ✓ Flag system (32 codes) — Task 4
- ✓ Icon system (18 glyphs incl. new `cog` for Admin) — Task 5
- ✓ Red sub-strip — Task 7
- ✓ Page shell wrapper — Task 9
- ✓ Visual verification — Task 10 sandbox at `/_panini`
- ✓ CLAUDE.md updated — Task 11

**Things deliberately deferred** (each is owned by a later plan):
- Dashboard widgets (KPI strip with real data, live match, countdown, insight cards, top 5, upcoming fixtures, rank trajectory)
- Predictions wizard rewrite (group-tab structure, bonus questions tab, Phase 2)
- Bracket (interactive ↔ display-only)
- Leaderboard (self-card, table with sparklines)
- Results redesign
- Admin redesign
- Backend support for: 7-day rank snapshots (sparklines), live match feed, social signals, hot-pick yield, bracket exposure, underdog hits, steepest climb, bonus haul

**Type consistency:** `IconName` is defined in `PnIcon.svelte` (Task 5) and imported by `PnBottomNav.svelte` (Task 8) and the sandbox page (Task 10). `NavItem` is local to each consumer.

**No placeholders:** every code block is complete and runnable.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-14-panini-redesign-foundation.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review the diff between tasks, fast iteration. Good when tasks are independent and code-heavy, which this plan is.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints for review. Good if you want to watch progress as it happens.

**Which approach?**
