# Implementation Plan: CT Legislative Intelligence System

## Current State
- Empty repo with only `README.md` and `docs/` (build-spec.md + technical-contract.md)
- On branch `claude/plan-app-development-yvDpE`
- Python 3.12+ project using the spec's recommended stack

---

## Pass 1: Skeleton, Config & Schemas

### 1.1 Project scaffold
- Create `pyproject.toml` with dependencies: FastAPI, SQLAlchemy, Pydantic v2, PyMuPDF, BeautifulSoup4, httpx, APScheduler, python-telegram-bot, alembic, psycopg, rapidfuzz
- Dev deps: pytest, ruff, mypy, pytest-asyncio
- Create `Makefile` with targets: setup, lint, typecheck, test, run-api, run-worker
- Create `.env.example` with all required env vars from technical contract §4.1
- Create `AGENTS.md` per spec §21

### 1.2 Typed config loader
- `config/settings.py` — Pydantic Settings class loading from env vars
- Fail-fast on missing `DATABASE_URL`
- Optional Telegram/LLM credentials with feature flags

### 1.3 Controlled taxonomy YAML files
- `config/taxonomy.subjects.yaml` — 27 subject tags from technical contract §5.1
- `config/taxonomy.change_flags.yaml` — 25 change flags from §5.2
- `config/taxonomy.urgency.yaml` — 4 urgency levels from §5.3
- `config/clients.example.yaml` — Via Transportation example profile from §12.1

### 1.4 Pydantic v2 schemas
- `src/schemas/intake.py` — SourcePageRecord, FileCopyListingRow
- `src/schemas/bills.py` — BillRecord, FileCopyRecord
- `src/schemas/extraction.py` — PageText, SectionSpan, ExtractedDocument
- `src/schemas/diff.py` — SectionDelta, ChangeEvent, BillDiffResult
- `src/schemas/scoring.py` — SubjectTagResult, ClientMatchReason, ClientScoreResult
- `src/schemas/summary.py` — InternalSummary, TelegramAlertPayload
- All per technical contract §6

### 1.5 SQLAlchemy models & Alembic
- `src/db/models.py` — All tables from technical contract §7 (source_pages, bills, file_copies, bill_text_extractions, bill_text_pages, bill_sections, bill_diffs, bill_change_events, clients, client_interest_profiles, client_bill_scores, alerts, feedback_labels)
- `src/db/session.py` — Engine/session factory
- `alembic.ini` + `migrations/` — Initial migration generating all tables
- Support SQLite for dev/testing and PostgreSQL for production

### 1.6 Utility modules
- `src/utils/bill_id.py` — Bill ID normalization (HB/SB + 5-digit zero-pad) and canonical version ID generation (`{year}-{bill_id}-FC{fc:05d}`)

### 1.7 Tests for Pass 1
- `tests/unit/test_bill_id.py` — Normalization edge cases
- `tests/unit/test_schemas.py` — Schema validation with sample payloads
- `tests/unit/test_settings.py` — Config loader behavior

### 1.8 Package structure `__init__.py` files
- Create `src/__init__.py`, `src/schemas/__init__.py`, `src/db/__init__.py`, `src/utils/__init__.py`, etc.

---

## Pass 2: Collectors & Persistence

### 2.1 Daily file-copy collector
- `src/collectors/cga_daily_filecopies.py` — Fetch and parse daily CGA file-copy page
- HTML parsing with BeautifulSoup
- Extract: bill number, title, file copy number, PDF link
- Normalize bill IDs per §8.1

### 2.2 All-file-copy reconciliation collector
- `src/collectors/cga_all_filecopies.py` — Fetch session-wide listing for backfill
- Gap detection against existing records

### 2.3 Bill-status collector
- `src/collectors/cga_bill_status.py` — Fetch bill info pages for title, committee, status

### 2.4 PDF downloader
- `src/collectors/pdf_downloader.py` — Download PDFs with idempotency (skip if sha256 exists)
- Local file storage adapter in `src/utils/storage.py`

### 2.5 Repository/persistence layer
- `src/db/repositories/bills.py` — CRUD for bills table
- `src/db/repositories/file_copies.py` — CRUD with duplicate detection
- `src/db/repositories/source_pages.py` — Source page audit trail

### 2.6 Tests for Pass 2
- HTML fixture files in `data/fixtures/` (saved sample CGA pages)
- `tests/unit/test_daily_collector.py` — Parser tests against fixtures
- `tests/unit/test_all_filecopies_collector.py`
- `tests/integration/test_persistence.py` — DB round-trip tests

---

## Pass 3: Extraction & Parsing

### 3.1 PDF text extraction
- `src/extract/pdf_text.py` — PyMuPDF-based text extraction
- `src/extract/ocr_fallback.py` — Tesseract OCR for low-confidence pages

### 3.2 Extraction confidence scoring
- `src/extract/confidence.py` — Heuristic per technical contract §10.2 (text ratio, legislative patterns, OCR garbage detection)

### 3.3 Text normalization
- `src/extract/normalize_text.py` — Header/footer removal, page number stripping, hyphenation repair, whitespace collapse per §10.3

### 3.4 Section parser
- `src/extract/section_parser.py` — Detect "Section X" / "Sec. X" boundaries, effective-date sections, definition blocks, appropriation blocks per §10.4
- Fallback paragraph chunking with deterministic IDs

### 3.5 Tests for Pass 3
- Sample PDF fixtures in `data/samples/`
- `tests/unit/test_pdf_extraction.py`
- `tests/unit/test_normalize.py`
- `tests/unit/test_section_parser.py`

---

## Pass 4: Diffing & Enrichment

### 4.1 Prior-version resolver
- `src/diff/prior_version.py` — Find previous file copy for same bill per §11.1

### 4.2 Section aligner
- `src/diff/align_sections.py` — Exact match → fuzzy heading match → semantic text similarity per §11.2

### 4.3 Deterministic change classifier
- `src/diff/classify_changes.py` — Rule-based detection of effective date changes, added/removed sections, appropriation language, penalty changes, shall/may changes per §11.4

### 4.4 Diff persistence
- Store BillDiffResult and ChangeEvent records

### 4.5 Tests for Pass 4
- Two-version bill fixtures for diff testing
- `tests/unit/test_section_alignment.py`
- `tests/unit/test_change_classification.py`

---

## Pass 5: Scoring, Summaries & Alerts

### 5.1 Client profile loader
- `src/scoring/client_profiles.py` — Load and validate YAML profiles per §12

### 5.2 Rules engine
- `src/scoring/rules_engine.py` — Deterministic scoring with weights from §13.1

### 5.3 Embeddings integration (post-MVP)
- `src/scoring/embeddings.py` — Cosine similarity mapping per §13.2

### 5.4 LLM wrappers
- `src/llm/prompts.py` — System/user prompt templates per §14
- `src/llm/schemas.py` — Response validation models
- `src/llm/summarize.py` — Summary generation with strict JSON validation
- `src/llm/relevance.py` — Client relevance scoring

### 5.5 Final score blending
- `src/scoring/relevance.py` — Weighted combination per §13.4, urgency mapping per §13.5

### 5.6 Telegram alerts
- `src/alerts/telegram.py` — Bot API integration
- `src/alerts/templates.py` — Immediate + digest templates per §15
- `src/alerts/routing.py` — Disposition logic, suppression, dedup per §13.6

### 5.7 Tests for Pass 5
- `tests/unit/test_rules_engine.py`
- `tests/unit/test_scoring.py`
- `tests/unit/test_alert_suppression.py`

---

## Pass 6: API, Jobs & Dashboard

### 6.1 FastAPI endpoints
- `apps/api/main.py` — All endpoints from §16.1 (health, jobs, bills, versions, alerts, feedback)

### 6.2 Job orchestration
- `apps/worker/jobs.py` — APScheduler-based job runner per §17
- Full pipeline chain per §17.2

### 6.3 Pipeline service
- `src/services/pipeline.py` — Orchestrates the 15-step job chain for a new file copy

### 6.4 Logging & audit
- Structured JSON logging per §18

---

## Implementation Priority (MVP Focus)

Per spec §17 (MVP scope), build in this order and stop when functional:

1. **Pass 1** — Scaffold + schemas + config + tests (foundation)
2. **Pass 2** — Collectors + PDF download + persistence (data ingestion)
3. **Pass 3** — Text extraction + section parsing (content pipeline)
4. **Pass 4** — Diffing + change detection (intelligence layer)
5. **Pass 5** — Rules scoring + LLM summary + Telegram alerts (output)
6. **Pass 6** — API + jobs + dashboard (operations)

MVP excludes: full dashboard, OCR for all files, embeddings scoring, feedback UI, historical backfill beyond test corpus.
