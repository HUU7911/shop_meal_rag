.PHONY: seed install dev up down logs migrate migrate-check purge ingest-full ingest-inc eval test lint

install:      ; pip install -r requirements-dev.txt
dev:          ; uvicorn app.main:app --reload --port 8000
up:           ; docker compose up -d --build
down:         ; docker compose down
logs:         ; docker compose logs -f chatbot
migrate:      ; alembic upgrade head
migrate-check: ; alembic check          # model và migration không được lệch nhau
purge:        ; python -m scripts.purge_history
ingest-full:  ; python -m app.ingestion.cli full
ingest-inc:   ; python -m app.ingestion.cli incremental
eval:         ; python -m eval.run_eval --mode intent
seed:         ; python -m scripts.seed_faq
test:         ; pytest -m "not integration"
lint:         ; ruff check . && ruff format --check . && mypy app
