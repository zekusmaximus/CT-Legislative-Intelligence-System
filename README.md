# CT Legislative Intelligence System

A production-minded, deterministic monitoring system for Connecticut General Assembly file copies.

## What this system does

This application:
- collects new CT General Assembly file copies on a scheduled basis,
- downloads and preserves raw legislative PDFs,
- extracts, normalizes, and sections bill text with confidence scoring,
- diffs new file copies against prior versions using two-phase section alignment,
- scores relevance against validated YAML client-interest profiles using deterministic rules,
- generates internal summaries and delivers Telegram alerts with suppression logic,
- persists all artifacts (extractions, diffs, scores, summaries, alerts) for audit and review, and
- exposes an operational API for inspection, reprocessing, and monitoring.

This repository is **not** a free-form chatbot. It is a deterministic legislative pipeline with tightly controlled use of LLM features.

## Current status: MVP complete (Phases 0-6)

All six phases of the MVP implementation plan are complete. The system can:

1. **Ingest** daily and session-wide file-copy listings from CGA.
2. **Extract** and persist structured bill text with page-level detail, section parsing, and confidence scoring.
3. **Diff** new file copies against prior versions using exact ID match and fuzzy text-similarity alignment.
4. **Enrich** bills with status metadata and contract-compliant subject tags and change flags.
5. **Score** relevance per client using validated YAML profiles and a deterministic rules engine.
6. **Alert** via Telegram with duplicate suppression, cooldown handling, and digest batching.
7. **Expose** operational API endpoints for health, collection, processing, version review, alerts, monitoring, and feedback.
8. **Audit** all pipeline runs with run-level records, error budgets, and a system health dashboard.

**320 tests pass** covering unit, integration, regression, and acceptance scenarios.

## Quick start

```bash
# Install dependencies
pip install -e ".[dev]"

# Set up environment
cp .env.example .env
# Edit .env with your DATABASE_URL, TELEGRAM_BOT_TOKEN, etc.

# Run migrations
alembic upgrade head

# Run tests
pytest -q

# Start the API server
uvicorn apps.api.main:app --reload

# Start the scheduler (collection + digest delivery)
python -m apps.worker.jobs scheduler
```

## Key API endpoints

| Endpoint | Purpose |
|---|---|
| `GET /health` | Basic health check with DB connectivity |
| `GET /monitoring/health` | Full system health with error budgets |
| `POST /jobs/collect/daily` | Trigger daily collection |
| `POST /jobs/process/{id}` | Reprocess a single version |
| `GET /versions/{id}` | Version extraction and diff data |
| `GET /review/version/{id}` | Full artifact review (extraction, tags, diffs, scores, alerts) |
| `GET /alerts` | Query alerts with delivery_status/urgency filters |
| `GET /runs` | Pipeline run audit trail |
| `POST /feedback` | Capture operator feedback |

## Project structure

```
apps/
  api/          FastAPI application and operational endpoints
  worker/       CLI worker and APScheduler-based job scheduler
config/
  clients/      YAML client-interest profiles
  settings.py   Typed Pydantic settings
  taxonomy.*.yaml  Controlled vocabulary definitions
docs/
  build-spec.md              Product scope and MVP phases
  technical-contract.md      Normative contract for schemas, enums, APIs
  production-readiness-review.md  Historical pre-MVP gap analysis
  runbook.md                 Operational runbook for pilot use
migrations/     Alembic migration history
src/
  alerts/       Telegram formatter and sender with retry/suppression
  collectors/   CGA HTML parsers, PDF downloader, bill-status enrichment
  db/           SQLAlchemy models and repositories
  diff/         Section differ (exact + fuzzy alignment) and change classifier
  extract/      PDF text extraction, OCR fallback, normalization, section parsing
  monitoring/   Error budget tracking and system health reports
  pipeline/     Orchestrator for end-to-end processing
  scoring/      Subject tagger, client scorer, summary generator
  schemas/      Pydantic schemas for pipeline data
  utils/        Bill ID normalization, storage adapters
tests/
  unit/         Unit tests for individual modules
  integration/  Integration tests for persistence and pipeline flows
  regression/   Regression fixtures (OCR, multi-version diffs, alert routing)
  acceptance/   Acceptance tests (taxonomy compliance, dedup, output integrity)
```

## Source of truth documents

- `PLAN.md` — phased implementation plan (all phases complete).
- `docs/build-spec.md` — product scope, MVP boundaries, and delivery phases.
- `docs/technical-contract.md` — normative contract for schemas, enums, storage, APIs, and pipeline behavior.
- `docs/runbook.md` — operational runbook for pilot use during session.
- `AGENTS.md` — agent-specific guardrails for working in this repository.

## Post-MVP roadmap

The following items are planned after the internal MVP is stable:
- Embeddings-based client matching
- LLM-generated summaries and relevance reasoning with strict JSON validation
- Dashboard and review UX
- Feedback-driven calibration workflows
- Broader backfill and historical analytics

## Tech stack

- **Python 3.12+** with Pydantic v2 for typed settings and schemas
- **FastAPI** for internal APIs
- **SQLAlchemy ORM** with Alembic migrations
- **PostgreSQL** in production, SQLite for local dev/tests
- **APScheduler** for scheduled collection and digest jobs
- **httpx + BeautifulSoup** for CGA page collection
- **PyMuPDF** for PDF text extraction, Tesseract as OCR fallback
- **Telegram Bot API** for alert delivery
