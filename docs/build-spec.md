# CT General Assembly File Copy Intelligence System

## Purpose

Build a production-minded monitoring system that checks new Connecticut General Assembly file copies, extracts and compares bill text, scores relevance against client-interest profiles, generates grounded internal summaries and Telegram alerts, and stores the resulting artifacts for audit and later review.

This is not a free-form chatbot. It is a deterministic legislative pipeline with optional, tightly constrained LLM features layered on top.

---

# 1. Product definition

## Core job to be done

During the Connecticut legislative session, the system should:

1. Discover new file copies from CGA.
2. Download and preserve the source PDF and page HTML.
3. Extract, normalize, and section the bill text.
4. Compare the new file copy to the prior version.
5. Classify substantive legal changes using controlled vocabularies.
6. Score relevance for each client using validated interest profiles.
7. Produce two outputs:
   - a short Telegram triage alert;
   - a deeper internal review summary.
8. Persist enough evidence for later inspection, debugging, and audit.

## Success criteria

The system is successful if it:
- catches newly posted file copies reliably;
- produces stable, non-hallucinatory outputs grounded in extracted text;
- identifies likely client relevance with deterministic, explainable reasons;
- avoids noisy Telegram alerts through thresholds and suppression rules;
- shows exactly why a bill was flagged or suppressed;
- preserves raw and processed artifacts so the pipeline is reviewable.

## Non-goals for MVP

- autonomous legislative strategy or testimony drafting;
- replacing human judgment on high-stakes legal or lobbying decisions;
- broad historical analytics before current-session operations are stable;
- embeddings or LLM reasoning as prerequisites for initial alerting;
- dashboard polish before persistence and operational APIs are complete.

---

# 2. Current repository state

> **Updated after Phase 6 completion.** The deterministic MVP is implemented. Current work should focus on pre-beta hardening and re-running the suite in the target environment rather than adding new MVP features.

The repository implements the full deterministic MVP pipeline:

- Typed settings, Pydantic schemas, and SQLAlchemy ORM models for all domain entities.
- Alembic migration history for reproducible schema setup.
- Daily and session-wide HTML collectors, bill-status enrichment, and PDF download/storage.
- PDF text extraction with OCR fallback, normalization, confidence scoring, and section parsing.
- Two-phase section diffing (exact ID match + fuzzy text-similarity alignment) and change classification.
- Contract-compliant controlled vocabularies enforced at runtime via YAML taxonomy loader.
- Validated YAML client-profile loader and deterministic rules-based scoring engine.
- Per-client score persistence with reasons, urgency, and dispositions.
- Telegram alert delivery with retry, duplicate suppression, cooldown handling, and digest batching.
- Internal summary persistence (one-sentence, deep, key sections, takeaways, confidence).
- Operational API: health, collection, processing, version lookup, alerts, runs, monitoring, review, and feedback.
- APScheduler-based job scheduling for collection polling and digest delivery.
- Pipeline run audit records with error budget tracking and system health reports.
- Regression fixtures and acceptance tests for OCR, multi-version diffs, alert routing, taxonomy compliance, and output integrity.

---

# 3. MVP phases

## Phase 0: Repository alignment — COMPLETE

### Goal
Make the repository self-describing for future coding agents and keep the docs aligned with current implementation reality.

### Deliverables
- updated `PLAN.md`;
- updated `README.md`;
- build and technical docs aligned to the current repository state;
- explicit MVP vs post-MVP boundaries.

## Phase 1: Persistence baseline — COMPLETE

### Goal
Convert the prototype pipeline into a traceable system of record.

### Deliverables
- initial Alembic revision;
- repositories for extraction and diff persistence;
- persisted raw text, normalized text, pages, sections, diffs, and change events;
- integration tests proving processed versions are queryable.

## Phase 2: Metadata enrichment and controlled vocabularies — COMPLETE

### Goal
Ensure downstream outputs are contract-compliant and ready for scoring.

### Deliverables
- bill-status enrichment wired into orchestration;
- runtime taxonomy loading and validation;
- controlled-vocabulary subject tags and change flags only;
- tests preventing unsupported enum output.

## Phase 3: Deterministic scoring and alert decisions — COMPLETE

### Goal
Make per-client relevance decisions trustworthy enough for internal use.

### Deliverables
- validated YAML client-profile loader;
- deterministic rules engine aligned with the technical contract;
- persisted client scores, urgency, reasons, and dispositions;
- duplicate suppression, threshold handling, cooldown rules, and digest routing.

## Phase 4: Summaries and Telegram delivery — COMPLETE

### Goal
Deliver useful outputs to operators and stakeholders.

### Deliverables
- persisted summaries and alert payloads;
- Telegram sender integration;
- delivery status logging;
- retry-safe send behavior.

## Phase 5: Operations API and scheduling — COMPLETE

### Goal
Operate the MVP without ad hoc scripts or database access.

### Deliverables
- minimal internal API for health, collect, process, version lookup, and alerts;
- scheduler-backed collection and digest jobs;
- structured logging and audit records.

## Phase 6: Hardening and pilot readiness — COMPLETE

### Goal
Prepare for sustained internal session use.

### Deliverables
- regression fixtures and acceptance tests;
- improved diff alignment and low-confidence handling;
- monitoring and runbook notes;
- optional feedback tooling and dashboard support.

---

# 4. Recommended tech stack

## Backend
- Python 3.12+
- FastAPI for internal APIs and admin endpoints
- SQLAlchemy ORM
- PostgreSQL in production
- SQLite only for local development/tests where appropriate
- Redis optional for queueing/caching
- APScheduler or a similarly simple scheduler for MVP jobs
- `httpx` + BeautifulSoup for collection
- PyMuPDF for primary extraction
- Tesseract only as fallback OCR
- Pydantic v2 for schemas and settings

## Intelligence layers
- deterministic rules first for subject tagging, change classification, and client scoring
- optional LLM summarization only with schema-validated JSON outputs
- optional embeddings only after deterministic scoring is stable

## Delivery and storage
- Telegram Bot API over HTTPS
- PostgreSQL for structured data
- local disk or object storage for raw PDFs and artifacts

---

# 5. Build order for coding agents

Use this order unless there is a specific reason to deviate:
1. persistence and migrations,
2. controlled vocabularies and metadata enrichment,
3. deterministic scoring and alert-decision persistence,
4. Telegram sending and summary persistence,
5. internal operations API and scheduler,
6. hardening and post-MVP enhancements.

If a task does not move one of those forward, it is probably not the most valuable MVP work.
