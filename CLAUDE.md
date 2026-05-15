# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**The Predictor v2** is a self-hosted web application for managing international football prediction competitions (World Cup, Euros) for ~30 friends.

Current focus: **World Cup 2026**

## Tech Stack

**Backend:**
- FastAPI (Python 3.11+)
- SQLModel (Pydantic + SQLAlchemy ORM)
- PostgreSQL 16
- Alembic for migrations
- YAML-based tournament configuration
- External data: Football-Data.org or API-Football (planned)

**Frontend:**
- SvelteKit with TypeScript
- Tailwind CSS + DaisyUI
- Svelte stores for state management
- svelte-motion for animations (planned)

**Infrastructure:**
- Docker Compose (development)
- Nginx reverse proxy (production)
- Cloudflare Tunnel (for self-hosting)

## Project Structure

```
/predictorv2
├── /backend
│   ├── /app
│   │   ├── /api             # FastAPI routes
│   │   ├── /models          # SQLModel tables
│   │   ├── /schemas         # Pydantic request/response models
│   │   └── /services        # Business logic (scoring, locking, standings)
│   └── /tests               # pytest tests
├── /frontend
│   ├── /src
│   │   ├── /lib
│   │   │   ├── /api         # API client functions
│   │   │   ├── /components  # Svelte components
│   │   │   ├── /stores      # Svelte stores
│   │   │   ├── /types       # TypeScript interfaces
│   │   │   └── /utils       # Helper functions
│   │   └── /routes          # SvelteKit pages
├── /config                  # Tournament YAML configuration
├── /docs                    # Documentation
├── /nginx                   # Proxy config (production)
└── docker-compose.yml
```

## Key Domain Concepts

### Competition Phases
- **Phase 1**: Pre-tournament predictions
  - Group stage match scores
  - Knockout bracket advancement (predict which teams reach each round)
  - Locks at tournament start or per-match (5 min before kickoff)

- **Phase 2**: Knockout stage predictions (activated by admin after groups complete)
  - Knockout match scores
  - Updated bracket predictions based on actual group results
  - Points reduced to 70% (configurable multiplier)

### Scoring System

Configured in `config/worldcup2026.yml`. See `docs/scoring-system.md` for full documentation.

**Scoring Modes:**
- `fixed`: Flat points for correct predictions
- `hybrid`: Base points + rarity bonus (fewer correct = higher bonus)

**Match predictions:**
- 5 pts: correct outcome (1-X-2)
- +10 pts: exact score bonus

**Advancement predictions:**
- 10 pts: team advances from group
- 5 pts: correct group position
- 10-100 pts: knockout stage advancement (scales by round)

### Critical Constraints
- Predictions lock 5 minutes before kickoff
- Users cannot see others' predictions until match locks (blind pool)
- Phase 1 and Phase 2 predictions are stored separately
- 100% data integrity required - no lost predictions

### Datetime Rule (system-wide invariant)

**Every datetime in this system is timezone-aware UTC.** Naive datetimes are forbidden — comparing or storing one is a bug.

- **DB**: every datetime column is `TIMESTAMPTZ` (PostgreSQL `TIMESTAMP WITH TIME ZONE`). See `backend/app/models/_datetime.py` for the column factory and `default_factory`.
- **Python**: use `utc_now()` from `app.models._datetime`, never `datetime.utcnow()` (deprecated and naive). Construct test datetimes with `datetime(..., tzinfo=timezone.utc)`.
- **API**: Pydantic serializes aware datetimes as ISO 8601 with explicit offset (`...Z` or `+00:00`).
- **Frontend**: `new Date(string).toLocaleString(...)` parses correctly because of the explicit offset, then renders in the user's local timezone via `Intl`.
- **DB-driver gotcha**: aiosqlite drops tzinfo on read even when the column is declared aware; PostgreSQL preserves it. Use `aware_utc()` (also in `_datetime.py`) at any compare site that touches DB-loaded values, defensively.

The rule was established in commit `c6089cc`. The original conversion migration was subsequently squashed into the consolidated initial migration (`f06b6a2077d3`) during pre-production prep. Violating the rule silently shifts kickoffs and deadlines by the user's UTC offset — a data-integrity disaster for a prediction app where lock timing matters.

## Key Files

| File | Purpose |
|------|---------|
| `config/worldcup2026.yml` | Tournament and scoring configuration |
| `backend/app/services/scoring.py` | Scoring strategies and point calculation |
| `backend/app/services/locking.py` | Prediction locking logic |
| `backend/app/services/standings.py` | Group standings calculation |
| `frontend/src/lib/stores/predictions.ts` | Prediction state management |
| `frontend/src/lib/utils/bracketResolver.ts` | FIFA 2026 knockout bracket logic |

## Development

### Running Locally

```bash
# Start all services
docker-compose up -d

# Backend: http://localhost:8000
# Frontend dev: http://localhost:5173 (with --profile dev)
```

### Common Commands

```bash
# Run backend tests
docker-compose exec backend pytest tests/ -v

# Check frontend types
cd frontend && npm run check

# View logs
docker-compose logs -f backend
```

## Development Rules

1. **Scoring Engine Safety**: No scoring logic changes without a corresponding `pytest` test case
2. **Mobile First**: Verify all UI on 375px viewport width
3. **Type Safety**:
   - Backend: Strict Pydantic models
   - Frontend: No `any` types - define interfaces in `/lib/types`
4. **Phase Separation**: Phase 1 and Phase 2 data must be kept separate (different stores, filtered queries)

## Testing

```bash
# Backend unit tests (scoring, auth, locking)
docker-compose exec backend pytest tests/test_scoring.py -v

# Frontend type checking
cd frontend && npm run check

# Manual testing with test data
docker-compose exec backend python scripts/seed_phase2_test.py
```

## UI Guidelines

The site uses the **Panini** design system — a sticker-album-inspired theme on cream paper with navy ink, red accents, and gold highlights. Every user-visible page (Dashboard, Predictions, Leaderboard, Results, Profile, Admin, Login/Register/Auth callback) renders inside `<PnPageShell>`, which establishes the `.pn` CSS scope.

**Design tokens** (CSS variables on `.pn`, defined in `frontend/src/lib/styles/panini-base.css`):
- `--paper` `#f1ebde` (canvas) · `--paper-2` `#e9e1cf` · `--paper-3` `#dfd4ba`
- `--ink` `#0e1d40` (navy text) · `--ink-2` `#514a3d` · `--ink-3` `#8a826f` (subdued)
- `--red` `#c8281f` (signals, "you", urgency) · `--red-deep` `#8a1610`
- `--gold` `#d49a2e` (highlights, hot picks, exact scores)
- `--green` `#1b6c3e` (correct outcomes) · `--navy` `#1a3168` (deep panels)

**Typography:**
- `var(--display)` — Archivo Black (uppercase, tight) for numbers, titles, big stats
- `var(--display2)` — Archivo (regular display for medium-weight headings)
- `var(--body)` — IBM Plex Sans
- `var(--mono)` — IBM Plex Mono (labels, metadata, kickoffs)

**Sticker shadows:** all cards use offset hard shadows (`box-shadow: 5px 5px 0 var(--ink)`). **Do not apply `transform: rotate(...)` to card-level containers** (sticker, KPI, match, profile-hero) — only small decorative accents (the crest logo, corner-tag pills, avatar chips) may carry a slight rotation. Soft drop shadows are out of style.

**Component primitives** (in `panini-base.css`): `pn-card`, `pn-sticker`, `pn-tag`, `pn-btn`, `pn-banner`. Page-specific stylesheets live under `frontend/src/lib/styles/panini-*.css` and are imported by `app.css` ahead of the `@tailwind` directives (the import position is load-bearing; PostCSS drops `@import` rules that appear after other at-rules).

**Save actions** still show feedback only after the backend confirms.
**Mobile** still: one logical group at a time, avoid grid-of-cards on small screens.
**Phase tabs** still: switch between Phase 1 and Phase 2 predictions. The Phase I/II toggle and the Groups/Knockout/Bonus section toggle live as a stacked pair in the wizard hero.
**Bracket** gating: in Phase 1 the Knockout sub-section is locked until every group prediction is filled in (uses predicted standings to seed R32 — would otherwise show TBD slots).
**Score inputs** are capped at 15 goals per side, enforced live in the input event so the user sees the cap immediately.

**Flag swatches** are 2/3-stripe gradient placeholders (`PnFlag.svelte`) — earmarked for a real flag library in a follow-up plan.

**Backend-dependent widgets** (sparklines, social signals, hot pick, bracket exposure, underdog hits, steepest climb) use deterministic stubs in `frontend/src/lib/stubs/panini.ts` until the backend supports them. Each stub logs `[panini:stub] <name>` in dev so they're greppable.
