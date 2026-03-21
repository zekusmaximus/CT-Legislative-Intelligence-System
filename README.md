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

## Current status: MVP implemented; beta hardening still open

All six phases of the MVP implementation plan are complete. The deterministic MVP can:

1. **Ingest** daily and session-wide file-copy listings from CGA.
2. **Extract** and persist structured bill text with page-level detail, section parsing, and confidence scoring.
3. **Diff** new file copies against prior versions using exact ID match and fuzzy text-similarity alignment.
4. **Enrich** bills with status metadata and contract-compliant subject tags and change flags.
5. **Score** relevance per client using validated YAML profiles and a deterministic rules engine.
6. **Alert** via Telegram with duplicate suppression, cooldown handling, and digest batching.
7. **Expose** operational API endpoints for health, collection, processing, version review, alerts, monitoring, and feedback.
8. **Audit** all pipeline runs with run-level records, error budgets, and a system health dashboard.

Recent hardening work also:
- makes Alembic honor `DATABASE_URL` so migrations and runtime can target the same database,
- removes runtime `create_all_tables()` startup behavior from the API and scheduler paths,
- routes client scores through immediate vs digest vs suppressed thresholds,
- batches digest delivery through `send_digest()`, and
- adds smoke coverage for Alembic bootstrap, `DATABASE_URL` override, Telegram wiring, alert retry/reset, and canonical bill ID parsing.

## Beta hardening still needed

Before broader beta testing, finish or consciously accept these gaps:
- Re-run the smoke suite and full test suite in a clean Python 3.12 environment with runtime extras installed. The current local shell may not have all required dependencies.
- APScheduler now has explicit Eastern timezone handling and `max_instances=1`, but `coalesce` and misfire policy are still worth setting before broader beta use.
- Add targeted tests for the newly wired one-shot worker delivery path and stronger scheduler assertions for timezone/overlap behavior.

## Prerequisites

You need:
- Python 3.12 or newer
- network access to `cga.ct.gov` for live collection
- a local writable `var/` directory for SQLite and stored PDFs

Optional:
- Tesseract installed on your machine if you want OCR fallback enabled locally
- Telegram bot credentials if you want real alert delivery
- OpenAI API credentials only for post-MVP experiments; they are not required for the deterministic MVP path

## Required and optional configuration

All configuration lives in a root-level `.env` file.

Required for any app startup:
- `DATABASE_URL`

Recommended for local testing:
- `STORAGE_BACKEND=local`
- `STORAGE_LOCAL_DIR=./var/storage`
- `SESSION_YEAR=2026`

Optional:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `TELEGRAM_ALERTS_ENABLED=true|false`
- `OCR_ENABLED=true|false`
- `TESSERACT_CMD` if Tesseract is installed but not on `PATH`
- `OPENAI_API_KEY` and related model settings only if you are explicitly testing post-MVP LLM work
- S3 settings only if `STORAGE_BACKEND=s3`

No API key is required to collect from the Connecticut General Assembly site.

## Full local test run

Follow these steps in order for a clean end-to-end local run.

### 1. Create the virtual environment

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
```

macOS/Linux:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
```

### 2. Install the project and test/runtime extras

```bash
pip install -e ".[dev,ocr,telegram,llm]"
```

### 3. Create local directories

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force var, var\storage | Out-Null
```

macOS/Linux:

```bash
mkdir -p var/storage
```

### 4. Create `.env`

Copy the example file:

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

macOS/Linux:

```bash
cp .env.example .env
```

For the simplest local test run, this minimal `.env` is enough:

```dotenv
APP_ENV=development
LOG_LEVEL=INFO
DATABASE_URL=sqlite:///./var/ct_cga_agent.db
STORAGE_BACKEND=local
STORAGE_LOCAL_DIR=./var/storage
TELEGRAM_ALERTS_ENABLED=false
OCR_ENABLED=false
SESSION_YEAR=2026
```

Notes:
- Leave `OPENAI_API_KEY` blank for the deterministic MVP path.
- Leave Telegram vars blank unless you want real message delivery.
- If you have Tesseract installed and want OCR parity, set `OCR_ENABLED=true`. If not, leave it `false` to avoid noisy OCR error logs during local testing.
- The repository already includes a sample client profile in `config/clients/client_via.yaml`, so you do not need to create a client YAML before the first local run.

### 5. Apply database migrations

```bash
alembic upgrade head
```

Normal runtime startup assumes migrations have already been applied. The API, scheduler, and worker paths no longer auto-create tables.

### 6. Run the tests

Start with the smoke coverage:

```bash
pytest -q tests/integration/test_smoke.py
```

Then run the full suite:

```bash
pytest -q
```

If you want the convenience targets instead:

```bash
make test
```

### 7. Start the API

```bash
uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 --reload
```

### 8. Verify the API is healthy

Windows PowerShell:

```powershell
curl.exe -s http://127.0.0.1:8000/health
curl.exe -s http://127.0.0.1:8000/monitoring/health
```

macOS/Linux:

```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/monitoring/health
```

You should see `/health` report database connectivity. `/monitoring/health` is more meaningful after at least one run has completed.

### 9. Trigger a live collection run

Windows PowerShell:

```powershell
curl.exe -s -X POST http://127.0.0.1:8000/jobs/collect/daily
curl.exe -s http://127.0.0.1:8000/runs
curl.exe -s http://127.0.0.1:8000/alerts
```

macOS/Linux:

```bash
curl -s -X POST http://127.0.0.1:8000/jobs/collect/daily
curl -s http://127.0.0.1:8000/runs
curl -s http://127.0.0.1:8000/alerts
```

What success looks like:
- `/jobs/collect/daily` returns a completed job response
- `/runs` shows a recent run with nonzero `entries_collected` or `entries_processed`
- PDFs and raw artifacts appear under `var/storage`
- `/alerts` returns either alert rows or an empty list without crashing

### 10. Inspect a processed version

The API does not yet expose a list-all-versions endpoint, so you need a `canonical_version_id`.

Ways to get one:
- use a `canonical_version_id` returned in `/alerts`
- read it from the CGA file-copy page
- query the database directly

For SQLite, this quick query works:

```powershell
.\.venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect('var/ct_cga_agent.db'); [print(r[0]) for r in c.execute('select canonical_version_id from file_copies order by id desc limit 10')]"
```

Then inspect the version:

Windows PowerShell:

```powershell
curl.exe -s http://127.0.0.1:8000/versions/2026-SB00093-FC00044
curl.exe -s http://127.0.0.1:8000/review/version/2026-SB00093-FC00044
```

macOS/Linux:

```bash
curl -s http://127.0.0.1:8000/versions/2026-SB00093-FC00044
curl -s http://127.0.0.1:8000/review/version/2026-SB00093-FC00044
```

`/versions/{id}` gives a compact status view. `/review/version/{id}` is the richer artifact-review payload.

### 11. Start the scheduler

Run this in a second terminal after the API is working:

```bash
python -m apps.worker.jobs scheduler
```

This will poll CGA on the configured interval and run digest delivery on weekday evenings.

### 12. Optional: test Telegram delivery

To test real Telegram delivery, add these to `.env`:

```dotenv
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
TELEGRAM_ALERTS_ENABLED=true
```

Then restart the API or worker process.

Important delivery behavior:
- normal processing sends only `immediate` alerts
- `digest` alerts queue for the scheduled digest job
- reprocessing can retry `failed` or `pending` alerts
- reprocessing will not resend alerts already marked `sent`

### 13. Optional: one-shot worker test

You can also exercise the worker directly without the scheduler:

```bash
python -m apps.worker.jobs daily
python -m apps.worker.jobs reconcile
```

These commands now wire Telegram delivery when it is enabled.

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
  regression/   Regression and acceptance-style coverage (OCR, diffs, alert routing, output integrity)
```

## Source of truth documents

- `PLAN.md` — phased implementation plan plus the current pre-beta hardening checklist.
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
