.PHONY: help dev dev-backend dev-frontend build up down logs clean test migrate

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

# Production
prod-up:
	docker-compose --profile prod up -d

prod-down:
	docker-compose --profile prod down
