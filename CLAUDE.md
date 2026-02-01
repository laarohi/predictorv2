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

- Dark mode default (sports/premium aesthetic)
- High contrast with green/red for win/loss
- Save actions must show feedback only after backend confirms
- Mobile: show one logical group at a time, avoid grid layouts
- Phase tabs for switching between Phase 1 and Phase 2 predictions
