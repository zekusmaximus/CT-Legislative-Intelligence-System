 # CT General Assembly File Copy Intelligence Agent

## Purpose

Build a production-minded monitoring system that checks new Connecticut General Assembly file copies, extracts and compares bill text, scores relevance against client-interest profiles, generates high-level deep summaries and subject-matter flags, and sends Telegram alerts only when the item crosses a configurable relevance threshold.

This is not a free-form chatbot. It is a deterministic legislative pipeline with an LLM summarization and reasoning layer.

## Why this architecture

The CT General Assembly publishes a daily “Today’s File Copies” page that lists bill number, title, and file copy number, and also maintains all-file-copy views for the session. The 2026 Regular Session runs from February 4, 2026 through May 6, 2026. Telegram’s Bot API is HTTP-based, which makes it straightforward to use as the delivery layer for alerts. OpenAI’s Codex CLI can read, change, and run code in a local repository, making it a practical implementation tool for this project. citeturn964825search0turn964825search6turn964825search15turn239401view2turn239401view3

---

# 1. Product definition

## Core job to be done

Each day during session, and on a shorter interval during active floor periods, the system should:

1. Discover new file copies from CGA.
2. Download and extract each PDF.
3. Normalize the text and split it into legal sections.
4. Compare the new file copy to the prior bill version.
5. Assign subject-matter tags and legal-effect flags.
6. Score relevance for each client based on a structured interest profile.
7. Produce two outputs:
   - a short Telegram triage alert
   - a deeper internal review summary
8. Store the results, links, and citations for later search and audit.

## Success criteria

The system is successful if it:

- catches newly posted file copies reliably;
- produces stable, non-hallucinatory summaries grounded in extracted text;
- identifies when a change is likely relevant to at least one client;
- avoids spamming Telegram with low-value alerts;
- shows *why* a bill was flagged;
- improves over time based on feedback.

## Non-goals for v1

- automated testimony drafting;
- auto-filing or legislative position taking;
- complete bill-history analysis back to session start for every run;
- replacing human review on high-stakes calls.

---

# 2. Phase plan

## Phase 0: Repository bootstrap and contracts

### Goal
Create the repository, project conventions, schemas, environment settings, and test harness before touching production scraping.

### Deliverables
- monorepo or single backend repo;
- `README.md`;
- `AGENTS.md` for Codex;
- `.env.example`;
- typed config loader;
- JSON schemas / Pydantic models for all core outputs;
- seed files for client profiles and subject taxonomy;
- Makefile or task runner;
- CI stub.

### Exit criteria
- repo runs locally with one command;
- tests execute;
- schemas validate sample payloads;
- Codex has clear repo instructions.

## Phase 1: Intake and persistence

### Goal
Collect file-copy listings and persist raw source metadata and PDF files.

### Deliverables
- scraper for daily page;
- scraper for all-file-copy session page for backfill;
- bill/file-copy discovery job;
- PDF downloader;
- object storage abstraction;
- database tables for bills, file copies, source pages, and jobs.

### Exit criteria
- system can ingest a full day of file copies;
- duplicate detection works;
- each file copy has a canonical ID and stored PDF.

## Phase 2: Text extraction and normalization

### Goal
Extract machine-usable text and structure from file-copy PDFs.

### Deliverables
- PDF extraction pipeline using PyMuPDF first;
- fallback OCR path for broken PDFs;
- text cleaner for headers, footers, line wraps, page numbers;
- section parser;
- citation map by page and section;
- confidence metrics on extraction quality.

### Exit criteria
- extracted text for sample PDFs is readable and section-aware;
- system detects low-confidence extraction;
- raw text and cleaned text are both stored.

## Phase 3: Bill metadata enrichment and diffing

### Goal
Turn static file copies into version-aware legislative change events.

### Deliverables
- bill-status metadata fetcher;
- prior-version lookup;
- section-by-section diff engine;
- change classifier;
- effective-date detector;
- definitions/additions/removals detector.

### Exit criteria
- a newly ingested file copy can be compared to its previous file copy;
- output includes structured changes, not just raw diff text.

## Phase 4: Subject tagging and client scoring

### Goal
Map bills to practice areas and clients.

### Deliverables
- controlled taxonomy for subjects and legal-effect flags;
- client profile schema;
- rules engine;
- embeddings-based semantic matching;
- optional LLM reasoning pass constrained to structured inputs;
- final weighted relevance score per client.

### Exit criteria
- each file copy receives stable subject tags;
- each client gets a scored relevance decision with reasons;
- false positives are manageable.

## Phase 5: Summaries and Telegram alerts

### Goal
Generate usable lawyer-lobbyist output and deliver it cleanly.

### Deliverables
- short alert generator;
- deep internal summary generator;
- Telegram bot integration;
- digest mode and immediate-alert mode;
- alert suppression and deduplication rules.

### Exit criteria
- Telegram messages send successfully;
- alerts link to the PDF and bill page;
- multiple clients can have distinct thresholds.

## Phase 6: Dashboard, feedback, and hardening

### Goal
Make the system reviewable, tunable, and reliable during session.

### Deliverables
- lightweight review dashboard;
- feedback labels: useful, not useful, missed, wrong client, wrong subject;
- relevance calibration tools;
- retry queues, logging, monitoring, and audit trail;
- unit and regression tests using historical file copies.

### Exit criteria
- you can review what happened on a given day;
- the system learns from your feedback;
- operations are stable enough for session use.

---

# 3. Recommended tech stack

## Backend
- Python 3.12+
- FastAPI for APIs and admin endpoints
- SQLAlchemy or SQLModel
- PostgreSQL
- Redis optional for queueing and caching
- Celery, Dramatiq, or APScheduler for jobs
- Playwright or `requests` + BeautifulSoup for collection
- PyMuPDF for primary extraction
- Tesseract OCR only as fallback
- `rapidfuzz`, `difflib`, and custom section alignment for diffs
- Pydantic for schemas

## AI layer
- one chat/completions model for structured summarization and explanation
- one embeddings model for semantic client matching
- JSON-schema or Pydantic validation for all LLM outputs

## Delivery
- Telegram Bot API over HTTPS
- optional email digest fallback

## Storage
- PostgreSQL for structured data
- local disk, S3, or Supabase storage bucket for PDFs and extraction artifacts

## Hosting
- Railway, Render, Fly.io, or small VPS

---

# 4. Repository layout

```text
ct-cga-filecopy-agent/
├─ AGENTS.md
├─ README.md
├─ Makefile
├─ pyproject.toml
├─ .env.example
├─ alembic.ini
├─ migrations/
├─ config/
│  ├─ settings.py
│  ├─ taxonomy.subjects.yaml
│  ├─ taxonomy.change_flags.yaml
│  └─ clients.example.yaml
├─ data/
│  ├─ fixtures/
│  └─ samples/
├─ apps/
│  ├─ api/
│  │  └─ main.py
│  ├─ worker/
│  │  └─ jobs.py
│  └─ admin/
├─ src/
│  ├─ collectors/
│  │  ├─ cga_daily_filecopies.py
│  │  ├─ cga_all_filecopies.py
│  │  └─ cga_bill_status.py
│  ├─ extract/
│  │  ├─ pdf_fetch.py
│  │  ├─ pdf_text.py
│  │  ├─ ocr_fallback.py
│  │  ├─ normalize_text.py
│  │  └─ section_parser.py
│  ├─ diff/
│  │  ├─ align_sections.py
│  │  ├─ classify_changes.py
│  │  └─ effective_date.py
│  ├─ scoring/
│  │  ├─ rules_engine.py
│  │  ├─ embeddings.py
│  │  ├─ client_profiles.py
│  │  └─ relevance.py
│  ├─ llm/
│  │  ├─ prompts.py
│  │  ├─ schemas.py
│  │  └─ summarize.py
│  ├─ alerts/
│  │  ├─ telegram.py
│  │  ├─ templates.py
│  │  └─ routing.py
│  ├─ db/
│  │  ├─ models.py
│  │  ├─ session.py
│  │  └─ repositories/
│  ├─ services/
│  │  ├─ pipeline.py
│  │  ├─ backfill.py
│  │  └─ feedback.py
│  └─ utils/
├─ tests/
│  ├─ unit/
│  ├─ integration/
│  └─ regression/
└─ docs/
   ├─ architecture.md
   ├─ prompts.md
   ├─ runbook.md
   └─ data_model.md
```

---

# 5. Data model

## Primary tables

### `bills`
- `id`
- `session_year`
- `bill_type` (`SB`, `HB`)
- `bill_number`
- `canonical_bill_id` (`2026-SB-00093`)
- `current_title`
- `committee`
- `status_url`
- `created_at`
- `updated_at`

### `file_copies`
- `id`
- `bill_id`
- `file_copy_no`
- `file_copy_url`
- `pdf_storage_key`
- `posted_date`
- `page_source_url`
- `sha256_pdf`
- `sha256_text`
- `is_duplicate`
- `created_at`

### `bill_text_versions`
- `id`
- `file_copy_id`
- `raw_text`
- `clean_text`
- `extraction_method`
- `extraction_confidence`
- `page_count`
- `token_count`
- `created_at`

### `bill_sections`
- `id`
- `file_copy_id`
- `section_key`
- `section_heading`
- `page_start`
- `page_end`
- `text`
- `text_hash`

### `bill_diffs`
- `id`
- `bill_id`
- `from_file_copy_id`
- `to_file_copy_id`
- `summary_json`
- `raw_diff`
- `diff_confidence`
- `created_at`

### `clients`
- `id`
- `client_code`
- `display_name`
- `is_active`

### `client_interest_profiles`
- `id`
- `client_id`
- `sector_tags`
- `agencies`
- `committees`
- `priority_keywords`
- `exclude_keywords`
- `watched_bills`
- `watched_topics`
- `threshold_immediate`
- `threshold_digest`
- `notes`

### `bill_client_scores`
- `id`
- `file_copy_id`
- `client_id`
- `rules_score`
- `embedding_score`
- `llm_score`
- `final_score`
- `why_json`
- `watch_closer`
- `created_at`

### `summaries`
- `id`
- `file_copy_id`
- `summary_type` (`triage`, `deep_review`)
- `content_markdown`
- `content_json`
- `model_name`
- `created_at`

### `alerts`
- `id`
- `file_copy_id`
- `client_id`
- `channel` (`telegram`, `email`, `dashboard`)
- `alert_type` (`immediate`, `digest`)
- `message_text`
- `status`
- `sent_at`

### `feedback_labels`
- `id`
- `file_copy_id`
- `client_id`
- `label`
- `notes`
- `created_at`

---

# 6. Canonical workflows

## 6.1 Discovery workflow

1. Hit daily file-copy page for the current date.
2. Parse rows: bill number, title, file copy number, PDF link.
3. Normalize bill identifiers.
4. Upsert bill record.
5. Upsert file-copy record.
6. Download PDF if new.
7. Enqueue extraction job.

## 6.2 Extraction workflow

1. Open PDF.
2. Extract embedded text using PyMuPDF.
3. If extraction quality falls below threshold, run OCR fallback.
4. Clean line breaks, headers, page footers, duplicate whitespace.
5. Parse sections using legislative section markers.
6. Persist text, section objects, and extraction metrics.
7. Enqueue metadata and diff job.

## 6.3 Diff workflow

1. Find previous version for same bill.
2. Align sections between prior and current versions.
3. Compute section-level changes.
4. Classify changes into controlled change types.
5. Detect effective date changes.
6. Persist structured diff JSON.
7. Enqueue scoring job.

## 6.4 Scoring workflow

1. Apply deterministic rules against title, text, sections, and change flags.
2. Generate embeddings for structured bill representation.
3. Compare bill vectors to client profile vectors.
4. Optionally ask model to explain relevance using only structured inputs.
5. Blend scores into final value.
6. If above threshold, enqueue summary + alert.

## 6.5 Summary workflow

1. Produce one-sentence summary.
2. Produce deep summary.
3. Produce why-it-matters-to-client explanation.
4. Produce recommended review sections.
5. Validate JSON schema.
6. Render alert text and internal memo.

## 6.6 Alert workflow

1. Suppress duplicates.
2. Route by client threshold and channel preferences.
3. Send Telegram immediate alert if high confidence.
4. Add medium-confidence items to digest queue.
5. Log delivery results.

---

# 7. Controlled taxonomies

## Subject taxonomy v1

- health_care
- insurance
- labor_employment
- tax_revenue
- appropriations_budget
- municipalities
- housing
- energy_environment
- transportation
- cannabis
- gaming
- data_privacy
- ai_automated_decisionmaking
- education
- procurement
- licensing_professional_regulation
- reimbursement_rate_setting
- civil_liability
- criminal_justice
- consumer_protection
- utilities
- land_use_zoning
- public_health
- social_services
- agriculture_food
- banking_financial_services

## Legal-effect / change-flag taxonomy v1

- definition_changed
- scope_expanded
- scope_narrowed
- agency_authority_expanded
- reporting_requirement_added
- mandate_added
- exemption_added
- penalty_added
- appropriation_added
- funding_changed
- private_right_of_action_added
- ag_enforcement_only
- rulemaking_authority_added
- licensure_requirement_changed
- reimbursement_structure_changed
- effective_date_changed
- implementation_deadline_changed
- municipal_impact
- compliance_cost_risk

---

# 8. Client interest profile schema

Use YAML so it is editable without a UI.

```yaml
client_code: via
client_name: Via Transportation
is_active: true
sector_tags:
  - transportation
  - microtransit
agencies:
  - DOT
  - DMV
  - OPM
committees:
  - Transportation
  - Finance
priority_keywords:
  - microtransit
  - transit district
  - demand responsive
  - paratransit
  - rideshare
  - transportation network company
  - state-funded transportation
  - mobility
exclude_keywords:
  - bicycle trail
  - boating safety
watched_bills:
  - SB00009
watched_topics:
  - transportation
  - appropriations_budget
immediate_threshold: 0.82
digest_threshold: 0.58
notes: >
  High sensitivity to changes affecting state-funded mobility services,
  labor classification issues in transit-adjacent programs, municipal transit pilots,
  and procurement language affecting service providers.
```

---

# 9. Relevance scoring design

## Rules score

Start with a transparent points model.

Example:
- `+0.30` if bill text or title contains a priority keyword
- `+0.20` if a watched agency is referenced
- `+0.15` if a watched committee is primary or bill is referred there
- `+0.20` if change flags include funding, mandate, or agency authority
- `+0.15` if effective date is immediate or current fiscal year
- `+0.20` if bill is on explicit watch list
- `-0.25` if excluded topic dominates the text

Clamp to `0..1`.

## Embeddings score

Create embeddings for:
- condensed bill representation
- condensed diff representation
- client profile text representation

Weighted similarity:
- 60% diff representation
- 40% bill representation

## LLM reasoning score

Model prompt should not ask, “Is this important?”

Ask instead:
- which client interests are implicated;
- whether the change is direct, indirect, or weak;
- what legal/operational implications are visible from the structured diff.

Then map output to a score.

## Final score

Suggested v1 weights:
- 0.50 rules
- 0.25 embeddings
- 0.25 LLM reasoning

Reason: deterministic signals should dominate early versions.

---

# 10. Structured output contracts

## Diff summary schema

```json
{
  "bill_id": "2026-SB-00093",
  "file_copy_no": 44,
  "prior_file_copy_no": 31,
  "changes": [
    {
      "change_type": "agency_authority_expanded",
      "section": "Sec. 4",
      "page_start": 7,
      "page_end": 8,
      "old_text_summary": "Prior version limited authority to annual reporting.",
      "new_text_summary": "New version authorizes additional rulemaking and implementation authority.",
      "practical_effect": "Agency discretion increases and compliance details may later move to regulation.",
      "confidence": 0.88
    }
  ],
  "effective_date": {
    "changed": true,
    "old": "October 1, 2026",
    "new": "July 1, 2026"
  }
}
```

## Subject tagging schema

```json
{
  "bill_id": "2026-SB-00093",
  "subjects": [
    "health_care",
    "public_health",
    "licensing_professional_regulation"
  ],
  "change_flags": [
    "agency_authority_expanded",
    "reporting_requirement_added",
    "effective_date_changed"
  ],
  "confidence": 0.84
}
```

## Client relevance schema

```json
{
  "client_code": "via",
  "final_score": 0.87,
  "watch_closer": true,
  "why": [
    "Transportation subject matter with state-service implications.",
    "Possible procurement and operating-model consequences.",
    "Change appears to expand oversight or implementation authority."
  ],
  "urgency": "high"
}
```

## Deep summary schema

```json
{
  "bill_id": "2026-SB-00093",
  "file_copy_no": 44,
  "one_sentence_summary": "This file copy revises the bill's implementation structure and appears to expand administrative authority while modifying the timeline for compliance.",
  "deep_summary_markdown": "...",
  "recommended_review_sections": ["Sec. 2", "Sec. 4", "Effective Date"],
  "questions_to_check": [
    "Does the new language shift any substantive detail from statute to regulation?",
    "Does the timing change create a near-term compliance or budget issue?"
  ]
}
```

---

# 11. Prompting rules for the LLM layer

## General rules

- Never summarize a bill without providing page or section anchors from extracted text.
- Never infer a client impact that is not grounded in the text or structured diff.
- Prefer “appears to,” “would,” and “may” over false certainty when text is ambiguous.
- Output JSON only for machine steps.
- Use a separate rendering step to turn JSON into human-facing markdown.

## Prompt 1: Deep summary from structured inputs

**System**

You are a legislative analyst. Work only from the provided extracted text, metadata, and structured diff. Do not invent bill effects not supported by the input. Return valid JSON matching the schema.

**User payload**
- bill metadata
- title
- cleaned bill summary chunks
- structured section diffs
- effective date info
- subject taxonomy
- change taxonomy

## Prompt 2: Client relevance reasoning

**System**

You are scoring legislative relevance for a lobbying practice. Work only from the structured client profile and structured bill diff. Do not use outside facts. Return valid JSON.

**User payload**
- client profile
- structured bill summary
- structured diff
- current subject tags

---

# 12. Telegram design

Telegram’s Bot API is HTTP-based, so sending alerts is a standard HTTPS POST integration. The API also supports formatted messages and linkable content. citeturn239401view2

## Message types

### Immediate alert
Use only when:
- score exceeds `immediate_threshold`; or
- a critical watched bill changes; or
- change flags indicate unusually high importance.

Template:

```text
SB 93 | File Copy 44 | High relevance: Via

High-level summary:
This file copy appears to revise implementation details and could affect transportation program administration or procurement-related oversight.

Why flagged:
- transportation
- appropriations_budget
- agency_authority_expanded

Review next:
Sec. 2, Sec. 4, effective date

Links:
PDF: {pdf_url}
Bill: {status_url}
```

### Daily digest
Group medium-confidence alerts by client.

### Suppression rules
- do not resend same file copy for same client;
- suppress low-confidence LLM-only flags;
- suppress bills whose only changes are formatting or harmless conforming edits.

---

# 13. Reliability and audit design

## Required logging
- source page fetched
- rows found
- rows new vs already known
- PDF download success/failure
- extraction method used
- extraction confidence
- diff success/failure
- score per client
- alert sent/suppressed
- model response validation success/failure

## Failure modes to design for
- CGA page layout changes
- PDFs missing text layer
- broken or partial downloads
- duplicate rows on refresh
- bill number normalization bugs
- LLM returning invalid JSON
- over-alerting due to vague client profiles

## Guardrails
- validate all bill IDs against strict regex
- keep a raw copy of source HTML and PDF hash
- never delete historical versions
- never send an alert unless summary JSON validated
- fallback to dashboard-only on model failure

---

# 14. Testing strategy

## Unit tests
- bill ID normalization
- file-copy row parsing
- PDF link extraction
- text cleanup
- section detection
- change classification
- rules scoring
- alert suppression

## Integration tests
- scrape known CGA daily page fixture
- fetch and parse sample PDF
- compute diff between two saved file copies
- run full scoring path on seeded client profiles

## Regression tests
Use a saved corpus of historical file copies from a few weeks of session and assert:
- stable extraction;
- stable tags;
- stable scores within tolerance;
- no duplicate alerts.

---

# 15. Operational cadence

Because the CGA publishes daily file-copy pages and the regular session is bounded, schedule should be session-aware. The official CGA site lists the 2026 Regular Session as February 4, 2026 to May 6, 2026. citeturn964825search15

Recommended schedule:
- every 30 minutes from 7:00 AM to 10:00 PM Eastern during session;
- every 10 minutes on peak floor days if needed;
- backfill once nightly from all-file-copies view;
- pause or reduce frequency outside session.

---

# 16. Security and confidentiality

## Minimum safeguards
- keep full client names and strategy notes outside model prompts where possible;
- prompt with client codes plus distilled interest profiles;
- store API tokens in environment secrets only;
- maintain audit trail of what text was sent to the model;
- redact internal notes from Telegram if chat membership is broader than you alone.

## Practical note
Telegram is convenient, but it should be treated as an alerting surface, not your authoritative archive. Use the database/dashboard as the system of record.

---

# 17. MVP scope recommendation

If you want this built quickly and usefully, the MVP should stop here:

### MVP includes
- daily page scraper
- PDF downloader
- text extraction
- section parser
- prior-version diff
- client YAML profiles
- deterministic rules scoring
- one LLM summary pass
- Telegram immediate alerts
- SQLite or PostgreSQL persistence

### MVP excludes
- full web dashboard
- OCR for every file
- semantic embeddings
- human feedback tuning UI
- historical backfill beyond test corpus

That MVP is enough to prove whether the workflow is worth operationalizing.

---

# 18. First implementation backlog for Codex

## Epic 1: Bootstrap
1. Initialize Python project with Poetry or uv.
2. Add FastAPI, SQLAlchemy, Pydantic, Playwright, BeautifulSoup, PyMuPDF.
3. Add `.env.example` and typed settings.
4. Add `AGENTS.md` with repo rules.
5. Add pre-commit hooks, Ruff, mypy, pytest.

## Epic 2: Core persistence
1. Create database models and Alembic migrations.
2. Add repository layer for bills, file copies, text versions, summaries, alerts.
3. Add local file storage adapter.

## Epic 3: Scraping
1. Implement parser for daily page.
2. Implement parser for all-file-copies page.
3. Add bill ID normalization.
4. Add source fixtures and parser tests.

## Epic 4: Extraction
1. Implement PDF fetcher.
2. Implement PyMuPDF text extraction.
3. Implement cleaner and section parser.
4. Add extraction confidence heuristic.

## Epic 5: Diffing
1. Lookup prior version.
2. Align sections.
3. Classify changes.
4. Persist diff JSON.

## Epic 6: Scoring and summary
1. Load client YAML profiles.
2. Implement deterministic rules engine.
3. Implement summary prompt scaffolding.
4. Add JSON validation.
5. Render markdown outputs.

## Epic 7: Telegram
1. Add Telegram client.
2. Add immediate alert routing.
3. Add digest queue.
4. Add dedupe/suppression layer.

---

# 19. Suggested `AGENTS.md` for the repository

```md
# AGENTS.md

This repository builds a Connecticut General Assembly file-copy monitoring and alerting system.

## Rules
- Preserve deterministic collection and diffing before adding AI behavior.
- Do not replace typed schemas with unstructured strings.
- All model outputs must validate against Pydantic schemas.
- Prefer small pure functions with tests.
- Never send Telegram alerts directly from parsing code; routing belongs in the alerts layer.
- Treat bill numbers and file copy numbers as normalized canonical identifiers.
- Do not remove historical versions.
- Add regression tests whenever changing parsing or diff logic.

## Priorities
1. Reliability of collection
2. Accuracy of text extraction
3. Stability of diff classification
4. Transparency of client scoring
5. Clear alert formatting

## Coding standards
- Python 3.12+
- type hints required
- Ruff, mypy, pytest
- Pydantic for external contracts
- SQLAlchemy for persistence
```

---

# 20. Suggested first Codex prompt

```text
Build Phase 0 and Phase 1 of this repository.

Requirements:
- Python 3.12 project using uv or Poetry
- FastAPI app scaffold
- PostgreSQL-ready SQLAlchemy models and Alembic migrations
- typed settings loader from environment
- parser for Connecticut General Assembly daily file-copy page
- parser for all-file-copies page
- canonical bill ID normalization
- persistence for bills and file copies
- local storage of downloaded PDFs
- pytest fixtures and unit tests for parsing logic
- Ruff, mypy, pytest, pre-commit configuration
- README with local setup instructions
- AGENTS.md matching repo rules

Use clean modular architecture. Do not implement the LLM layer yet. Use sample HTML fixtures in tests rather than live network calls.
```

---

# 21. My blunt recommendation on build order

Do not start with embeddings, chat prompts, or a dashboard.

Start with:
1. collection,
2. extraction,
3. structured diffs,
4. deterministic client scoring,
5. only then summaries and Telegram.

If the extraction and diff layers are weak, the rest of the system will be expensive theater.

---

# 22. Next document to create after this one

The next useful spec is a **technical implementation contract** containing:
- exact Pydantic models;
- exact database DDL;
- exact parser rules for bill numbers, file-copy links, and section detection;
- exact scoring formulas;
- exact prompt templates;
- exact Telegram render templates.

That is what Codex will use best after the initial repository scaffold.
