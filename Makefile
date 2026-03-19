.PHONY: setup lint typecheck test run-api run-worker migrate

setup:
	pip install -e ".[dev,ocr,telegram,llm]"

lint:
	ruff check src/ apps/ tests/ config/
	ruff format --check src/ apps/ tests/ config/

format:
	ruff check --fix src/ apps/ tests/ config/
	ruff format src/ apps/ tests/ config/

typecheck:
	mypy src/ apps/ config/

test:
	pytest tests/ -v

test-cov:
	pytest tests/ -v --cov=src --cov-report=term-missing

run-api:
	uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000

run-worker:
	python -m apps.worker.jobs

migrate:
	alembic upgrade head

migrate-new:
	alembic revision --autogenerate -m "$(msg)"
