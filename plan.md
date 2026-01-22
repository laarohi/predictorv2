# Predictor v2 - Implementation Plan

## Overview

A from-scratch rewrite of the football prediction competition web app for World Cup 2026. ~30 users, 5-month timeline.

**Tech Stack:**
- Frontend: SvelteKit + TypeScript + Tailwind CSS + DaisyUI
- Backend: FastAPI + SQLModel + PostgreSQL
- Auth: Google OAuth (fastapi-sso) + email/password (JWT)
- Infrastructure: Docker Compose (portable to Hetzner VPS)
- Live Scores: API-Football (api-football.com)

**Key Design Decisions:**
- Flexible tournament format via YAML config (supports 24-team Euro and 48-team World Cup)
- World Cup 2026 format: 48 teams → 12 groups of 4 → Round of 32 → R16 → QF → SF → Final

---

## Project Structure

```
predictorv2/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── config.py            # Settings, YAML loader
│   │   ├── database.py          # SQLModel engine
│   │   ├── dependencies.py      # Auth deps, DB session
│   │   ├── models/              # SQLModel tables
│   │   ├── schemas/             # Pydantic request/response
│   │   ├── api/                 # Route modules
│   │   └── services/            # Business logic (scoring, locking)
│   ├── tests/
│   ├── alembic/                 # DB migrations
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── lib/
│   │   │   ├── components/      # Svelte components
│   │   │   ├── stores/          # Svelte stores
│   │   │   ├── api/             # API client
│   │   │   └── types/           # TypeScript interfaces
│   │   └── routes/              # SvelteKit pages
│   └── Dockerfile
├── config/
│   └── worldcup2026.yml         # Tournament configuration
├── nginx/
├── docker-compose.yml
└── Makefile
```

---

## Database Schema

| Table | Key Fields | Notes |
|-------|------------|-------|
| `users` | id (UUID), email, name, password_hash, google_id, auth_provider, is_admin | OAuth + email auth |
| `competitions` | id, name, entry_fee, phase1_deadline, phase2_deadline | Tournament instance |
| `fixtures` | id, home_team, away_team, kickoff, stage, group, status | Match data |
| `match_predictions` | id, user_id, fixture_id, home_score, away_score, phase, locked_at | Score predictions |
| `team_predictions` | id, user_id, team, stage, group_position, phase | Bracket predictions |
| `scores` | id, fixture_id, home_score, away_score, source | Actual results |

---

## Scoring System

**Match Predictions (Hybrid):**
- 5 pts for correct outcome (1-X-2)
- +10 pts for exact score
- Hybrid bonus capped at 10 pts

**Advancement Predictions:**
| Stage | Phase 1 | Phase 2 |
|-------|---------|---------|
| Round of 32 | 10 | - |
| Round of 16 | 15 | 10 |
| Quarter-Finals | 20 | 15 |
| Semi-Finals | 40 | 25 |
| Final | 60 | 40 |
| Winner | 100 | 70 |

---

## Development Phases

### Phase 1: Foundation ✅ COMPLETED
- [x] FastAPI + SQLModel project setup
- [x] PostgreSQL + Alembic migrations config
- [x] User model with email/password auth (JWT)
- [x] Google OAuth integration
- [x] SvelteKit setup with Tailwind + DaisyUI
- [x] Login/register pages
- [x] Auth store and protected routes
- [x] Docker Compose dev environment
- [x] Tournament YAML configuration

**Deliverable:** Working authentication flow

### Phase 2: Group Stage (IN PROGRESS)
- [ ] Run database migrations
- [ ] Seed data for testing (competition, fixtures)
- [ ] GroupTable component with live standings
- [ ] Mobile-responsive group view
- [ ] End-to-end testing of prediction flow
- [ ] Admin endpoints for fixtures/scores

**Deliverable:** Users can enter all group stage predictions

### Phase 3: Knockout Bracket
- [ ] Bracket validation (teams must advance)
- [ ] KnockoutBracket visualization
- [ ] SVG connectors with animations
- [ ] Mobile accordion view
- [ ] Phase 1 vs Phase 2 handling

**Deliverable:** Visual bracket with team selection

### Phase 4: Scoring & Leaderboard
- [ ] Scoring service (fixed + hybrid modes)
- [ ] Leaderboard calculation with caching
- [ ] Live score sync from external API
- [ ] 60-second polling endpoint
- [ ] Position change animations
- [ ] Score breakdown view

**Deliverable:** Complete scoring and live updates

### Phase 5: Polish & Deploy
- [ ] Admin dashboard
- [ ] Production Docker setup
- [ ] Cloudflare Tunnel or VPS deployment
- [ ] "Dry run" test with friends
- [ ] Mobile device testing
- [ ] Final bug fixes

**Deliverable:** Production-ready for World Cup 2026

---

## Key Constraints

- Predictions lock 5 minutes before kickoff
- Blind pool: users cannot see others' predictions until match locks
- 100% data integrity required - no lost predictions
- Mobile-first: verify all UI on 375px viewport

---

## Commands

```bash
# Development
make dev              # Start all services
make dev-backend      # Backend only
make dev-frontend     # Frontend only

# Database
make migrate          # Run migrations
make db-shell         # PostgreSQL shell

# Testing
make test             # All tests
make test-backend     # Backend tests only
```
