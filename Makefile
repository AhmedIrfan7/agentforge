.PHONY: help up down api-dev web-dev worker-dev api-test api-lint api-format web-lint web-format web-build install api-migrate api-seed backup restore-drill api-openapi-export

help:
	@echo "AgentForge dev commands:"
	@echo "  make install     - install all dependencies (api + web/shared)"
	@echo "  make up          - start local services (postgres, redis, minio)"
	@echo "  make down        - stop local services"
	@echo "  make api-migrate - apply database migrations"
	@echo "  make api-seed    - seed demo org/workspace/user (idempotent)"
	@echo "  make api-dev     - run the FastAPI dev server"
	@echo "  make worker-dev  - run the Celery worker (needed to process uploaded documents)"
	@echo "  make web-dev     - run the Next.js dev server"
	@echo "  make api-test    - run backend test suite"
	@echo "  make api-lint    - run ruff + mypy on apps/api"
	@echo "  make api-format  - format apps/api with ruff"
	@echo "  make web-lint    - run eslint on apps/web"
	@echo "  make web-format  - format apps/web with prettier"
	@echo "  make web-build   - production build apps/web"
	@echo "  make backup      - back up Postgres + MinIO to backups/<timestamp>/"
	@echo "  make restore-drill BACKUP=backups/<timestamp> - restore-test a backup"
	@echo "  make api-openapi-export - regenerate docs/openapi.json from the live app"

install:
	cd apps/api && uv sync
	pnpm install

up:
	docker compose up -d

down:
	docker compose down

api-migrate:
	cd apps/api && uv run alembic upgrade head

api-seed:
	cd apps/api && uv run python -m scripts.seed

api-dev:
	cd apps/api && uv run uvicorn main:app --reload

worker-dev:
	cd apps/api && uv run celery -A celery_app worker --loglevel=info

web-dev:
	pnpm --filter @agentforge/web run dev

api-test:
	cd apps/api && uv run pytest

api-lint:
	cd apps/api && uv run ruff check . && uv run mypy .

api-format:
	cd apps/api && uv run ruff format .

web-lint:
	pnpm --filter @agentforge/web run lint

web-format:
	pnpm --filter @agentforge/web run format

web-build:
	pnpm --filter @agentforge/web run build

backup:
	./scripts/backup.sh

restore-drill:
	./scripts/restore-drill.sh $(BACKUP)

api-openapi-export:
	cd apps/api && uv run python -m scripts.export_openapi
