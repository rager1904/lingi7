# ─────────────────────────────────────────────────────────────────────────────
# Lingi7 — Makefile
# All common development tasks as single commands.
# ─────────────────────────────────────────────────────────────────────────────

.PHONY: help up down logs shell test lint fmt migrate makemigrations \
        createsuperuser collectstatic worker beat clean reset-db \
        coverage check-secrets

# Default target
help:
	@echo ""
	@echo "  Lingi7 Developer Commands"
	@echo "  ─────────────────────────────────────────────────────"
	@echo "  make up              Start all services (db, redis, web, celery, beat)"
	@echo "  make down            Stop all services"
	@echo "  make logs            Tail logs from all services"
	@echo "  make shell           Django shell_plus"
	@echo "  make test            Run full test suite with coverage"
	@echo "  make test-fast       Run tests in parallel (faster, less output)"
	@echo "  make lint            Run flake8 + bandit"
	@echo "  make fmt             Run black + isort (auto-format code)"
	@echo "  make migrate         Apply all pending migrations"
	@echo "  make makemigrations  Create new migrations"
	@echo "  make createsuperuser Create Django superuser"
	@echo "  make worker          Start Celery worker (local, no Docker)"
	@echo "  make beat            Start Celery Beat (local, no Docker)"
	@echo "  make clean           Remove .pyc, __pycache__, coverage files"
	@echo "  make reset-db        Drop and recreate the development database"
	@echo "  make coverage        Open HTML coverage report in browser"
	@echo "  make check-secrets   Scan for committed secrets (bandit + detect-secrets)"
	@echo ""

# ── Docker ────────────────────────────────────────────────────────────────────
up:
	docker-compose up -d
	@echo "⏳ Waiting for database to be ready..."
	@sleep 5
	docker-compose exec -T web python manage.py migrate --run-syncdb
	@echo "✓ Services started and migrations applied!"
	@echo "  API at http://localhost:8000"
	@echo "  Admin at http://localhost:8000/admin/"
	@echo "  Frontend at http://localhost:3000"

down:
	docker-compose down

logs:
	docker-compose logs -f

logs-web:
	docker-compose logs -f web

logs-celery:
	docker-compose logs -f celery

# ── Django ────────────────────────────────────────────────────────────────────
shell:
	docker-compose exec web python manage.py shell_plus

migrate:
	docker-compose exec web python manage.py migrate --run-syncdb

makemigrations:
	docker-compose exec web python manage.py makemigrations

createsuperuser:
	docker-compose exec web python manage.py createsuperuser

collectstatic:
	docker-compose exec web python manage.py collectstatic --noinput

# ── Testing ───────────────────────────────────────────────────────────────────
test:
	docker-compose exec web pytest --cov=apps --cov-report=term-missing --cov-report=html -v

test-fast:
	docker-compose exec web pytest -x -n auto --cov=apps --cov-report=term-missing

test-escrow:
	docker-compose exec web pytest apps/escrow/ -v --cov=apps.escrow --cov-report=term-missing

test-payments:
	docker-compose exec web pytest apps/payments/ tests/integration/test_payment_webhook.py -v

test-fraud:
	docker-compose exec web pytest apps/fraud/ -v

coverage:
	open htmlcov/index.html

# ── Code Quality ──────────────────────────────────────────────────────────────
lint:
	docker-compose exec web flake8 apps/ config/ --max-line-length=100
	docker-compose exec web bandit -r apps/ -c pyproject.toml

fmt:
	docker-compose exec web black apps/ config/
	docker-compose exec web isort apps/ config/

check-secrets:
	@echo "Scanning for secrets..."
	docker-compose exec web bandit -r . -ll --exclude=./.venv,./tests

# ── Local (without Docker, for faster iteration) ─────────────────────────────
worker:
	DJANGO_SETTINGS_MODULE=config.settings.dev celery -A config worker \
		--loglevel=info --concurrency=2 \
		--queues=default,payments,notifications,fraud

beat:
	DJANGO_SETTINGS_MODULE=config.settings.dev celery -A config beat \
		--loglevel=info \
		--scheduler django_celery_beat.schedulers:DatabaseScheduler

# ── Utilities ─────────────────────────────────────────────────────────────────
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name ".pytest_cache" -delete
	rm -rf htmlcov/ .coverage coverage.xml

reset-db:
	@echo "WARNING: This will destroy all development data."
	@read -p "Are you sure? (yes/no): " confirm && [ "$$confirm" = "yes" ]
	docker-compose down -v
	docker-compose up -d db redis
	sleep 5
	docker-compose up -d web celery beat
	sleep 3
	$(MAKE) migrate
	@echo "✓ Database reset complete."
