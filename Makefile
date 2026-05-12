.PHONY: help dev dev-backend dev-frontend build up down logs clean test migrate \
        deploy vps-ssh vps-context local-context context \
        vps-ps vps-logs vps-logs-backend vps-logs-cloudflared \
        vps-restart-backend vps-restart-nginx vps-shell vps-db-shell vps-migrate \
        vps-up vps-down vps-backup

# === Production VPS configuration ===
# Override on the command line if your SSH alias / remote path differs:
#   make deploy VPS_HOST=user@1.2.3.4
VPS_HOST ?= pred-mplex
REMOTE_PATH ?= ~/predictorv2

help:
	@echo "Predictor v2 - Development Commands"
	@echo ""
	@echo "Development:"
	@echo "  make dev           - Start all services in development mode"
	@echo "  make dev-backend   - Start backend only (with hot reload)"
	@echo "  make dev-frontend  - Start frontend only (with hot reload)"
	@echo ""
	@echo "Docker:"
	@echo "  make build         - Build all Docker images"
	@echo "  make up            - Start all services"
	@echo "  make down          - Stop all services"
	@echo "  make logs          - View logs from all services"
	@echo "  make clean         - Remove containers and volumes"
	@echo ""
	@echo "Database:"
	@echo "  make migrate       - Run database migrations"
	@echo "  make db-shell      - Open PostgreSQL shell"
	@echo ""
	@echo "Testing:"
	@echo "  make test          - Run all tests"
	@echo "  make test-backend  - Run backend tests"
	@echo "  make test-frontend - Run frontend tests"
	@echo ""
	@echo "Production (VPS):"
	@echo "  make deploy             - SSH to VPS, git pull, rebuild, restart prod stack"
	@echo "  make vps-ssh            - Open interactive SSH session on VPS"
	@echo "  make vps-context        - Switch local docker CLI to predictor (PROD)"
	@echo "  make local-context      - Switch back to local default docker context"
	@echo "  make context            - Show current docker context"
	@echo "  make vps-ps             - List running containers on VPS"
	@echo "  make vps-logs           - Tail all VPS logs"
	@echo "  make vps-logs-backend   - Tail backend logs only"
	@echo "  make vps-logs-cloudflared - Tail cloudflared tunnel logs"
	@echo "  make vps-shell          - Bash shell inside backend container on VPS"
	@echo "  make vps-db-shell       - psql shell on VPS database"
	@echo "  make vps-migrate        - Run alembic migrations on VPS"
	@echo "  make vps-up             - Start prod stack on VPS"
	@echo "  make vps-down           - Stop prod stack on VPS (with confirmation)"
	@echo "  make vps-backup         - Trigger manual DB backup on VPS"

# Development
dev:
	docker-compose --profile dev up -d db
	@echo "Waiting for database..."
	@sleep 3
	docker-compose --profile dev up backend frontend-dev

dev-force:
	docker-compose --profile dev up -d db
	@echo "Waiting for database..."
	@sleep 3
	docker-compose --profile dev up backend frontend-dev --force-recreate

dev-backend:
	docker-compose up -d db
	@echo "Waiting for database..."
	@sleep 3
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend:
	cd frontend && npm run dev

# Docker
build:
	docker-compose build

up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f

clean:
	docker-compose down -v
	docker system prune -f

# Database
migrate:
	cd backend && alembic upgrade head

migrate-new:
	@read -p "Migration message: " msg; \
	cd backend && alembic revision --autogenerate -m "$$msg"

db-shell:
	docker-compose exec db psql -U predictor -d predictor

# Testing
test: test-backend test-frontend

test-backend:
	cd backend && pytest -v

test-frontend:
	cd frontend && npm test

# Linting
lint:
	cd backend && ruff check . && mypy .
	cd frontend && npm run lint

lint-fix:
	cd backend && ruff check . --fix
	cd frontend && npm run lint -- --fix

# Production (local prod-profile testing — NOT the live VPS)
prod-up:
	docker-compose --profile prod up -d

prod-down:
	docker-compose --profile prod down

# === Production VPS targets ===
# All vps-* targets explicitly use --context predictor so they're safe regardless
# of your shell's current docker context. The PS1 indicator (see ops/shell/) shows
# context for ad-hoc docker commands you run outside the Makefile.

# Context switching
vps-context:
	docker context use predictor
	@echo "→ Switched to predictor (PROD) context. Verify your prompt indicator."

local-context:
	docker context use default
	@echo "→ Switched to default (local) context."

context:
	@docker context show

# Deploy: pull latest code on VPS, rebuild images, restart prod stack
deploy:
	@echo "→ Deploying to $(VPS_HOST):$(REMOTE_PATH)..."
	ssh $(VPS_HOST) 'cd $(REMOTE_PATH) && git pull && docker compose --profile prod up -d --build'
	@echo "✓ Deploy complete. Tail logs with: make vps-logs"

# Interactive SSH (use sparingly; most ops can use the targets below)
vps-ssh:
	ssh $(VPS_HOST)

# Inspection
vps-ps:
	docker --context predictor compose ps

vps-logs:
	docker --context predictor compose logs -f

vps-logs-backend:
	docker --context predictor compose logs -f backend

vps-logs-cloudflared:
	docker --context predictor compose logs -f cloudflared

# Lifecycle
vps-restart-backend:
	docker --context predictor compose restart backend

vps-restart-nginx:
	docker --context predictor compose restart nginx

vps-up:
	docker --context predictor compose --profile prod up -d

vps-down:
	@read -p "⚠  Take PRODUCTION down? Type 'yes' to confirm: " confirm; \
	if [ "$$confirm" = "yes" ]; then \
		docker --context predictor compose --profile prod down; \
	else \
		echo "Aborted."; \
	fi

# Interactive shells
vps-shell:
	docker --context predictor compose exec backend bash

vps-db-shell:
	docker --context predictor compose exec db psql -U predictor -d predictor

# Migrations (run after a deploy that adds/changes models)
vps-migrate:
	docker --context predictor compose exec backend alembic upgrade head

# Trigger manual DB backup (script will be added in ops/backup-db.sh post-deploy)
vps-backup:
	ssh $(VPS_HOST) '$(REMOTE_PATH)/ops/backup-db.sh'
