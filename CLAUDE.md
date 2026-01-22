# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**The Predictor v2** is a self-hosted web application for managing international football prediction competitions (World Cup, Euros) for ~30 friends. This is a planned rewrite of an existing Dash-based application.

Current focus: **World Cup 2026**

## Tech Stack (Planned)

**Backend:**
- FastAPI (Python 3.11+)
- SQLModel (Pydantic + SQLAlchemy ORM)
- PostgreSQL 16
- Alembic for migrations
- External data: Football-Data.org or API-Football

**Frontend:**
- SvelteKit with TypeScript
- Tailwind CSS + DaisyUI
- svelte-motion for animations

**Infrastructure:**
- Docker Compose
- Nginx reverse proxy
- Cloudflare Tunnel (for self-hosting)

## Planned Project Structure

```
/predictor
├── /backend                 # FastAPI
│   ├── /app
│   │   ├── /models          # SQLModel Tables
│   │   ├── /services        # Scoring Logic
│   │   └── /api             # Routes
├── /frontend                # SvelteKit
│   ├── /src
│   │   ├── /lib/components  # UI Components
│   │   └── /routes          # Pages
├── /nginx                   # Proxy Config
└── docker-compose.yml
```

## Key Domain Concepts

### Competition Phases
- **Phase I**: Pre-tournament predictions (group stage matches + knockout bracket advancement)
- **Phase II**: Knockout score predictions (submitted after group stage ends, before knockouts begin)

### Scoring System (YAML-configurable)
Match predictions:
- 5 pts for correct outcome (1-X-2)
- 15 pts for exact score

Advancement predictions (Phase I):
- 10 pts: team advances from group
- 5 pts: correct group position
- 15-100 pts: knockout stage advancement (scales by round)

### Critical Constraints
- Predictions lock 5 minutes before kickoff
- Users cannot see others' predictions until match locks (blind pool)
- 100% data integrity required - no lost predictions

## Development Rules

1. **Scoring Engine Safety**: No scoring logic changes without a corresponding `pytest` test case
2. **Mobile First**: Verify all UI on 375px viewport width
3. **Type Safety**:
   - Backend: Strict Pydantic models
   - Frontend: No `any` types - define interfaces for User, Match, Prediction

## Testing

- **Unit**: pytest for scoring logic and auth
- **Integration**: vitest for Svelte components
- **Manual**: "Dry Run" pre-tournament test on dummy matches

## UI Guidelines

- Dark mode default (sports/premium aesthetic)
- High contrast with green/red for win/loss
- Save actions must show feedback only after backend confirms
- Mobile: show one logical group at a time, avoid grid layouts
