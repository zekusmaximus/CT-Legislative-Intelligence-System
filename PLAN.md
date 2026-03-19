# MVP Implementation Plan: CT Legislative Intelligence System

## Purpose

This plan translates the findings in `docs/production-readiness-review.md` into a phased, execution-ready roadmap for coding agents. It replaces the earlier greenfield scaffold plan, which no longer reflects the repository's actual state.

The goal is to move the repository from **"promising prototype"** to **"traceable, internally deployable MVP"** by prioritizing persistence, controlled vocabularies, operational APIs, and deterministic alerting before any optional intelligence layers.

## Planning principles

1. **System of record before polish.** Persist extraction, diff, scoring, and alert artifacts before expanding UI or agentic behavior.
2. **Deterministic before probabilistic.** Finish rules-based collection, extraction, alignment, scoring, and alerting before embeddings or broader LLM use.
3. **Contract compliance over feature count.** Runtime outputs must use approved enums, validated schemas, and idempotent writes.
4. **Operational traceability is mandatory.** Every alert decision must be inspectable through stored artifacts and minimal internal APIs.
5. **Small, test-backed tranches.** Each phase should end in a testable capability that future agents can extend safely.

---

## Current repository snapshot

### What is already in place
- Python project scaffold with typed settings, test harness, and Makefile.
- SQLAlchemy models for the core domain tables.
- Daily and session-wide collectors plus bill-status parsing.
- PDF download, text extraction, normalization, confidence scoring, and section parsing.
- Basic diffing, subject tagging, simplified scoring, deterministic summary generation, and Telegram formatting.
- Pipeline orchestration tests demonstrating a narrow happy-path flow.

### What is still blocking MVP
- No Alembic revision history.
- No persistence for extracted text, sections, diffs, scores, summaries, or alerts.
- Runtime vocabularies do not fully enforce the technical contract enums.
- Bill-status enrichment is not fully wired into the end-to-end pipeline.
- Alert sending, suppression, and per-client decision persistence are incomplete.
- API surface is effectively limited to health checks.
- Operational logging, scheduling, and review flows are incomplete.

### Delivery target
The next milestone is an **internal MVP** that can:
1. ingest file copies,
2. extract and persist structured legislative text,
3. diff against prior versions,
4. score relevance deterministically against validated client profiles,
5. persist alert decisions and send Telegram alerts with suppression rules, and
6. expose enough API surface to inspect and re-run work.

---

## Phase 0 - Repository alignment and execution contract

### Objective
Make the repository self-describing so coding agents can continue safely without rediscovering priorities.

### Scope
- Rewrite planning docs to match the actual repository state.
- Define MVP scope explicitly and mark post-MVP items.
- Document current architecture, operating assumptions, and build order.
- Keep agent instructions aligned with deterministic pipeline goals.

### Exit criteria
- `PLAN.md`, `README.md`, and core docs reflect the current implementation state.
- Future agents can identify the next build tranche without reading the full review.

### Status
- **In progress with this revision.**

---

## Phase 1 - Persistence baseline and migration history

### Objective
Turn the prototype into a real system of record.

### Required deliverables
1. Create the **initial Alembic revision** for existing ORM tables.
2. Stop relying on ad hoc `create_all()` flows for normal app setup.
3. Add repositories/services for:
   - `bill_text_extractions`
   - `bill_text_pages`
   - `bill_sections`
   - `bill_diffs`
   - `bill_change_events`
4. Persist extraction outputs and diff outputs during pipeline execution.
5. Add integration tests proving a processed file copy can be queried after persistence.

### Notes for agents
- Keep writes idempotent and keyed by canonical version identifiers.
- Preserve raw artifacts and normalized artifacts separately.
- Treat this phase as the highest-priority coding tranche.

### Exit criteria
- A newly processed file copy produces durable extraction and diff records.
- `alembic upgrade head` can initialize a clean environment.
- Tests cover repeat processing without duplicate rows.

### Status
- **Top-priority MVP blocker.**

---

## Phase 2 - Metadata enrichment and contract-compliant vocabularies

### Objective
Ensure pipeline outputs comply with the technical contract and are ready for scoring.

### Required deliverables
1. Wire **bill-status enrichment** into the orchestration path before scoring.
2. Load and enforce approved taxonomy values from config files at runtime.
3. Replace ad hoc subject tags and change flags with controlled vocabulary outputs only.
4. Fail fast on unknown or invalid enum values.
5. Add tests proving taggers/classifiers cannot emit unsupported values.

### Exit criteria
- Enriched bill metadata is persisted before scoring/alerting.
- Runtime outputs match the controlled vocabularies in `docs/technical-contract.md`.
- Diff/change artifacts are consistent enough for downstream alert logic.

### Status
- **Immediate follow-on after Phase 1.**

---

## Phase 3 - Deterministic client scoring and alert decisioning

### Objective
Make relevance scoring trustworthy enough for internal pilot use.

### Required deliverables
1. Implement a validated **YAML client-profile loader**.
2. Replace the placeholder scorer with a contract-aligned deterministic rules engine.
3. Persist per-client score breakdowns, reasons, urgency, and dispositions.
4. Implement alert suppression rules:
   - below-threshold suppression,
   - duplicate suppression,
   - cooldown handling,
   - digest vs immediate routing.
5. Add tests covering positive, negative, and suppression cases.

### Explicit non-goals for this phase
- Embeddings-based relevance.
- Broad LLM reasoning for client relevance.

### Exit criteria
- Each processed version has persisted per-client scoring outputs.
- Alert decisions are explainable from stored reasons and citations.
- False-positive control is manageable for internal use.

### Status
- **MVP-critical.**

---

## Phase 4 - Summary generation and Telegram delivery

### Objective
Produce actionable outputs and deliver them reliably.

### Required deliverables
1. Persist internal summaries and alert payloads.
2. Implement Telegram sending via Bot API.
3. Ensure alert payloads include:
   - bill number/title,
   - file-copy version,
   - client/disposition context,
   - concise reasons,
   - links to PDF and bill page.
4. Add delivery logging and retry-safe send behavior.
5. Keep summary generation deterministic unless a schema-validated LLM path is explicitly enabled.

### Exit criteria
- Telegram alerts send successfully in enabled environments.
- Alert records are persisted with delivery state.
- Users can inspect why a message was or was not sent.

### Status
- **MVP-critical.**

---

## Phase 5 - Operational API, jobs, and auditability

### Objective
Make the MVP operable during session without direct database access.

### Required deliverables
1. Expand FastAPI with a minimal internal operations surface:
   - `GET /health`
   - `POST /jobs/collect/daily`
   - `POST /jobs/process/{canonical_version_id}`
   - `GET /versions/{canonical_version_id}`
   - `GET /alerts`
2. Add scheduler/job orchestration for session polling and digest runs.
3. Introduce structured logging and run-level audit records.
4. Add tests for API responses and orchestration idempotency.

### Exit criteria
- Operators can trigger collection and inspect outputs through the API.
- Scheduled runs follow session-aware cadence rules.
- Logs support debugging and post-run review.

### Status
- **Required for internal deployability, but after Phases 1-4.**

---

## Phase 6 - Hardening and pilot readiness

### Objective
Prepare the MVP for sustained internal use during the legislative session.

### Required deliverables
1. Regression fixtures covering low-quality OCR, multi-version diffs, no-alert, immediate-alert, and digest-only scenarios.
2. Acceptance tests for duplicate suppression, taxonomy compliance, and persisted outputs.
3. Improved section alignment and change classification thresholds.
4. Monitoring, error budgets, and runbook notes.
5. Optional review dashboard and feedback capture only after APIs and persistence are stable.

### Exit criteria
- The system can run during session with predictable behavior.
- Core outputs are reproducible, inspectable, and test-backed.
- Operational issues can be diagnosed quickly.

### Status
- **Production-minded pilot target.**

---

## Post-MVP roadmap

Only begin these items after the internal MVP is stable:
- embeddings-based client matching,
- LLM-generated summaries/relevance reasoning with strict JSON validation,
- dashboard/review UX,
- feedback-driven calibration workflows,
- broader backfill and historical analytics.

These are valuable, but they should not displace the persistence, scoring, and alerting work that makes the system usable.

---

## Recommended next coding tranche

### Tranche name
**Persist the intelligence layer and make it queryable.**

### In-scope tasks
1. Create the initial Alembic revision.
2. Add repositories/services for persisted extraction and diff artifacts.
3. Wire those writes into pipeline extraction and diff execution.
4. Add `GET /versions/{canonical_version_id}`.
5. Add integration tests proving persisted outputs are queryable after processing.

### Why this tranche comes next
- It closes the largest gap between the current prototype and a usable MVP.
- It unlocks auditability, downstream scoring persistence, and alert traceability.
- It is narrow enough for a coding agent to implement safely in one focused pass.

---

## Working order for future agents

When choosing the next task, prefer this order:
1. Persistence and migrations.
2. Controlled vocabularies and metadata enrichment.
3. Deterministic scoring and alert decision persistence.
4. Telegram sending and summary persistence.
5. Operational APIs and scheduler.
6. Hardening and post-MVP intelligence layers.

If a task does not advance one of those steps, it is probably not the highest-value work for MVP.
