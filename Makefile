.PHONY: install dev up down logs migrate ingest-full ingest-inc eval test lint

install:      ; pip install -r requirements-dev.txt
dev:          ; uvicorn app.main:app --reload --port 8000
up:           ; docker compose up -d --build
down:         ; docker compose down
logs:         ; docker compose logs -f chatbot
migrate:      ; alembic upgrade head
ingest-full:  ; python -m app.ingestion.cli full
ingest-inc:   ; python -m app.ingestion.cli incremental
eval:         ; python -m eval.run_eval
test:         ; pytest -m "not integration"
lint:         ; ruff check . && ruff format --check . && mypy app
