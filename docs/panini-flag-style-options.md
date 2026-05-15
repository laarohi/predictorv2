# Panini Flag Style — sourcing decision (deferred)

**Status:** Decision deferred to 2026-Q3. The Panini `PnFlag.svelte` component
currently renders 2/3-stripe colour bars as a placeholder. This document
captures the option space so the decision can be made cold later.

## The fork in the road

Two distinct aesthetics are on the table; each has a different free-source
ecosystem.

| Direction | Look | Best fit for |
|-----------|------|--------------|
| **Vintage print** | Clean flat flags with slight desaturation, sticker chrome (border + offset shadow), faint paper-grain overlay | Reads "Panini sticker album". Editorial, restrained. |
| **Pixel art** | 16×12 to 24×16 pixel grid, blocky | Reads "8-bit videogame". Playful, gamey. |

Both work on cream paper with a navy border. They pull the page in different
directions, so picking the *feeling* matters before sourcing assets — switching
later means re-downloading ~48 SVGs.

## Candidate sources

### Option A — `lipis/flag-icons` + CSS treatment (recommended)

- **Repo:** `github.com/lipis/flag-icons` · ~260 SVG flags · MIT licensed
- **Why for Panini:** Vector means a CSS/SVG treatment in `PnFlag.svelte`
  applies *uniformly* to every flag. No per-flag work needed.
- **Treatment to apply:** `filter: contrast(1.1) saturate(0.85);` plus the
  existing sticker chrome (2px ink border, `5px 5px 0 var(--ink)` shadow).
  Optional: an SVG `<filter>` with `feTurbulence` to overlay paper grain.
- **Trade-off:** Not pixel art. Feels Panini-faithful (clean flag, sticker
  frame) rather than retro-gamey.

### Option B — Pixel-art flag set

No canonical source like `flag-icons` exists. Realistic paths:

- **OpenGameArt.org** — search "pixel flag" / "world flags pixel". CC0 packs
  aimed at game dev. Coverage is patchy (often ~50 countries — need to verify
  all 48 World Cup teams are covered).
- **itch.io asset packs** — search "pixel art flags". Quality varies, some are
  paid (~$5 typical).
- **Roll-your-own:** rasterise the `lipis/flag-icons` SVGs to 24×16 px via a
  Node script with `sharp`, then render upscaled with `image-rendering:
  pixelated` in CSS. Gives guaranteed coverage in a consistent style.
  ~30 lines of script.

**Resolution tip:** target 24×16 px source resolution. Smaller, and Brazil's
star-cluster vs. Argentina's sun become unreadable; identifying flags like
the UK or South Korea also requires that level of detail.

### Option C — `twemoji` flags (middle-ground)

- **Repo:** `github.com/twitter/twemoji` · MIT licensed
- **Style:** Slightly stylised/flat-illustration. Thicker outlines than
  `flag-icons`. Reads "playful" but not pixelated.
- **Trade-off:** Sits between Panini-faithful and gamey. Risks looking generic
  on a sticker-album page.

### Option D — `OpenMoji` flags

- **Site:** `openmoji.org` · CC BY-SA 4.0
- **Style:** Hand-drawn-ish, friendlier than `flag-icons`. Two variants
  (colour + monochrome black).
- **Trade-off:** Same family as twemoji — sits between styles. The mono
  variant could be interesting as a secondary marker (e.g., "team eliminated").

## Recommendation

**Option A** — `lipis/flag-icons` + CSS treatment.

Rationale: matches the existing sticker chrome (border + offset shadow already
defined in `panini-base.css`), zero per-flag work, easy to swap later. The
component API in `PnFlag.svelte` stays stable, so consumers (Dashboard,
Wizard, Bracket, Results) never have to change.

If we later decide pixel-art is the right call, the implementation work is
isolated to `PnFlag.svelte` — swap the SVG source and add
`image-rendering: pixelated`. The 32 FIFA three-letter codes already
supported in `PnFlag.svelte` map onto either option.

## Implementation outline (when decision is made)

1. `npm i flag-icons` (CSS sprite, ~140 KB gzip) OR vendor a slimmed SVG set
   for just the 48 WC teams into `frontend/static/flags/`.
2. Rewrite `PnFlag.svelte` body to emit a `<span class="fi fi-{code}">` or
   an `<img src="/flags/{code}.svg">` depending on (1).
3. Apply the CSS treatment in `panini-base.css`:
   ```css
   .pn .pn-flag {
     border: 2px solid var(--ink);
     box-shadow: 4px 4px 0 var(--ink);
     filter: contrast(1.1) saturate(0.85);
   }
   ```
4. Verify on Dashboard / Wizard / Bracket at 375 px viewport.

## Related

- `frontend/src/lib/components/panini/PnFlag.svelte` — current placeholder
- `frontend/src/lib/styles/panini-base.css` — sticker chrome tokens
- Memory: `project_panini_flag_replacement.md`
