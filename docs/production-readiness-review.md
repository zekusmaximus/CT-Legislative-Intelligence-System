# CT Legislative Intelligence System: Production Readiness Review

## 1. Executive verdict

This repo is **not deployable today as a credible MVP**. It is deployable only as a **development prototype with a decent foundation and a narrow happy-path demo pipeline**. The single biggest reason is simple: the code does **not persist or expose the core intelligence artifacts that the spec requires**—extractions, sections, diffs, scores, summaries, alerts, feedback, and audit data are mostly modeled but never written or served, which means the system cannot deliver a traceable end-to-end product output. The technical contract explicitly requires those outputs and persistence guarantees, but the current pipeline stops at in-memory tagging and summary generation. 【F:docs/build-spec.md†L19-L41】【F:docs/technical-contract.md†L53-L62】【F:src/pipeline/orchestrator.py†L278-L362】

The repo is **not “mostly empty scaffolding”** either. Passes 1-3 are meaningfully underway: typed settings exist, Pydantic schemas exist, SQLAlchemy models exist, collectors parse sample HTML, PDF extraction/normalization/section parsing exist, and the test suite passes on the included fixtures. But the production-facing parts—migration history, contract-complete API, orchestration, persistence of downstream artifacts, controlled-vocabulary compliance, alerting, and ops hardening—are still materially incomplete. 【F:config/settings.py†L10-L73】【F:src/db/models.py†L24-L232】【F:src/collectors/cga_daily_filecopies.py†L18-L141】【F:src/extract/pdf_text.py†L11-L88】【F:src/extract/normalize_text.py†L17-L100】【F:src/extract/section_parser.py†L34-L280】【F:tests/integration/test_pipeline.py†L42-L160】

## 2. Overall progress estimate

- **Overall completion toward MVP: 42%**.
  - Reason: the repository has credible foundation work and a demonstrable ingest→extract→diff→tag→summarize path in tests, but it still lacks major MVP-deliverable pieces from Phases 4-6: contract-compliant scoring, Telegram sending, alert suppression, persistence of downstream outputs, and almost the entire internal API surface. 【F:docs/build-spec.md†L129-L179】【F:src/pipeline/orchestrator.py†L297-L362】【F:apps/api/main.py†L1-L14】
- **Overall completion toward full planned system: 27%**.
  - Reason: the fuller system in the technical contract includes LLM wrappers with schema validation, embeddings, dashboard/review tooling, feedback ingestion, audit-grade storage, monitoring, and pilot acceptance behavior. Most of that is absent. 【F:docs/technical-contract.md†L893-L1074】【F:docs/technical-contract.md†L1078-L1167】

### Pass / phase estimate

| Pass / phase | Estimate | Justification |
|---|---|---|
| Pass 1 / Phase 0 | substantially complete | Core scaffold exists: `pyproject.toml`, `Makefile`, `.env.example`, settings, schemas, DB models, and tests. But `README.md` is effectively empty, Python version misses the 3.12 spec, and there is no real CI stub. 【F:pyproject.toml†L1-L60】【F:Makefile†L1-L33】【F:.env.example†L1-L42】【F:config/settings.py†L10-L73】【F:README.md†L1-L1】 |
| Pass 2 / Phase 1 | substantially complete | Daily/all-file-copy parsing, PDF download, storage adapter, repositories, and idempotent insert behavior exist. Missing pieces include bill-status integration into the pipeline, discrepancy marking, and a jobs table. 【F:src/collectors/cga_daily_filecopies.py†L18-L141】【F:src/collectors/cga_all_filecopies.py†L11-L115】【F:src/collectors/pdf_downloader.py†L12-L74】【F:src/db/repositories/file_copies.py†L11-L66】【F:docs/build-spec.md†L81-L92】 |
| Pass 3 / Phase 2 | partial | PDF extraction, confidence scoring, normalization, OCR fallback, and section parsing exist, but extraction artifacts are not persisted and there is no citation map implementation beyond section spans. 【F:src/extract/pdf_text.py†L11-L88】【F:src/extract/confidence.py†L13-L43】【F:src/extract/normalize_text.py†L17-L100】【F:src/extract/section_parser.py†L34-L280】【F:docs/build-spec.md†L99-L110】 |
| Pass 4 / Phase 3 | partial | Prior-version lookup and a basic section differ/classifier exist, but alignment is simplistic, bill-status enrichment is not wired into the pipeline, and diff results are never persisted. 【F:src/db/repositories/file_copies.py†L43-L52】【F:src/diff/section_differ.py†L13-L116】【F:src/diff/change_classifier.py†L47-L189】【F:src/pipeline/orchestrator.py†L252-L273】 |
| Pass 5 / Phase 4-5 | minimal | There is rudimentary keyword subject tagging, simple rules scoring, summary generation, and a Telegram formatter. There is no client profile loader, no contract-compliant weighting, no LLM layer, no Telegram sender, and no suppression/cooldown implementation. 【F:src/scoring/subject_tagger.py†L11-L154】【F:src/scoring/client_scorer.py†L9-L136】【F:src/scoring/summary_generator.py†L11-L149】【F:src/alerts/telegram_formatter.py†L23-L105】【F:docs/build-spec.md†L134-L162】 |
| Pass 6 / Phase 6 | minimal | FastAPI exposes only `/health`; the worker is a plain CLI wrapper; there is no scheduler, no dashboard, no feedback endpoint, and no production audit/logging implementation. 【F:apps/api/main.py†L1-L14】【F:apps/worker/jobs.py†L14-L75】【F:docs/technical-contract.md†L1046-L1106】 |

## 3. Feature-by-feature implementation matrix

| Area | Spec requirement | Current implementation | Status | Evidence | Production risk | MVP blocker? |
|---|---|---|---|---|---|---|
| Repo scaffold | README, task runner, env example, schemas, CI stub | `Makefile`, `.env.example`, schemas, and tests exist; `README.md` is one line and no CI config is present. | partial | README is empty of operational content; Make targets exist. 【F:README.md†L1-L1】【F:Makefile†L1-L33】 | high | yes |
| Python/runtime contract | Python 3.12+ | Project declares `>=3.11`, Ruff/Mypy target 3.11. | broken | Spec says 3.12+; project config targets 3.11. 【F:AGENTS.md†L15-L24】【F:docs/build-spec.md†L185-L196】【F:pyproject.toml†L1-L5】【F:pyproject.toml†L45-L56】 | medium | no |
| Typed settings | Typed config, fail-fast on missing DB URL | `Settings` uses Pydantic Settings and requires `database_url`. No validation of Redis/LLM/Telegram mode assumptions. | partial | Settings loader exists and tests cover missing DB URL. 【F:config/settings.py†L10-L73】【F:tests/unit/test_settings.py†L8-L58】【F:docs/technical-contract.md†L142-L147】 | medium | no |
| Env contract completeness | Include all required env vars | `.env.example` omits `REDIS_URL`. Settings class omits Redis entirely. | broken | Contract requires `REDIS_URL`; repo omits it. 【F:docs/technical-contract.md†L115-L139】【F:.env.example†L1-L42】【F:config/settings.py†L17-L57】 | medium | no |
| Controlled vocabularies | Use approved subject/change/urgency enums only | YAML taxonomy files match the contract, but runtime tagger/classifier ignore them and emit non-contract values. | broken | YAML is correct; tagger emits `healthcare`, `environment`, etc.; classifier emits `effective_date_change`, `new_section_added`, etc. 【F:config/taxonomy.subjects.yaml†L1-L32】【F:config/taxonomy.change_flags.yaml†L1-L38】【F:src/scoring/subject_tagger.py†L11-L111】【F:src/diff/change_classifier.py†L11-L23】【F:docs/technical-contract.md†L153-L245】 | critical | yes |
| Pydantic schema layer | Contract §6 models | Most schemas exist and are structurally close. Some fields are looser than the contract and typechecking shows schema usage mismatches. | partial | Schemas exist; mypy reports invalid `str` passed where `HttpUrl`/Literal types are required. 【F:src/schemas/intake.py†L9-L28】【F:src/schemas/scoring.py†L8-L57】【F:src/schemas/summary.py†L8-L30】 | medium | no |
| Database models | Contract §7 tables | All major tables are modeled. No jobs table despite Phase 1 deliverable. No migration revision generates them. | partial | ORM models cover main contract tables; migrations folder has only env/template. 【F:src/db/models.py†L24-L232】【F:PLAN.md†L39-L43】【F:docs/build-spec.md†L81-L88】【F:migrations/env.py†L1-L44】 | high | yes |
| Alembic/migrations | Initial migration generating all tables | Alembic is scaffolded only; there are no revision files. | stubbed | `migrations/` contains only `env.py` and template. 【F:migrations/env.py†L1-L44】【F:migrations/script.py.mako†L1-L27】 | critical | yes |
| Persistence layer | CRUD/idempotency for intake and downstream artifacts | Bills, file copies, and source pages have repositories and idempotent create-if-new behavior. No repositories for extractions, sections, diffs, scores, alerts, or feedback. | partial | Only three repositories exist. 【F:src/db/repositories/bills.py†L11-L45】【F:src/db/repositories/file_copies.py†L11-L66】【F:src/db/repositories/source_pages.py†L9-L31】 | high | yes |
| Daily collector | Fetch, parse, persist raw HTML, normalize IDs, enqueue work | Parsing is implemented; pipeline fetches page, stores HTML, persists source record. There is no queue; processing is synchronous. | partial | Parser + pipeline collection stage exist. 【F:src/collectors/cga_daily_filecopies.py†L18-L141】【F:src/pipeline/orchestrator.py†L57-L86】【F:docs/technical-contract.md†L619-L629】 | medium | no |
| Reconciliation collector | Fill gaps and mark discrepancies | Parsing and ingestion exist, but there is no discrepancy marking/review mechanism. | partial | Reconciliation just parses and processes new rows. 【F:src/collectors/cga_all_filecopies.py†L11-L115】【F:src/pipeline/orchestrator.py†L88-L115】【F:docs/technical-contract.md†L631-L638】 | medium | no |
| Bill-status collector | Extract title, committee, status link, procedural history | Parser exists but returns a bare dict; pipeline never calls it. | partial | Parser code exists; orchestrator never imports or invokes it. 【F:src/collectors/cga_bill_status.py†L6-L97】【F:src/pipeline/orchestrator.py†L11-L31】 | high | yes |
| HTTP/network hardening | Retry, rate limiting, safe fetch behavior | `CGAFetcher` has basic retry/backoff/rate limiting. No `Client` reuse, no explicit timeout config injection from settings in pipeline, no content-type validation. | partial | Fetcher does retries with `httpx.get`. 【F:src/collectors/http_fetcher.py†L11-L98】 | medium | no |
| PDF download/storage | Idempotent download and storage abstraction | Local storage and idempotent storage path checks exist. No S3 implementation despite config. | partial | Only `LocalStorage` exists. 【F:src/collectors/pdf_downloader.py†L12-L74】【F:src/utils/storage.py†L7-L43】 | medium | no |
| Extraction pipeline | Text extraction, OCR fallback, confidence, normalization | Implemented for local PDFs and exercised in tests. OCR is optional and only opportunistic. | partial | Extraction modules exist and tests cover them. 【F:src/extract/pdf_text.py†L11-L88】【F:src/extract/ocr_fallback.py†L12-L62】【F:src/extract/confidence.py†L13-L43】【F:tests/unit/test_pdf_extraction.py†L1-L73】 | medium | no |
| Extraction persistence | Store raw text, cleaned text, pages, sections | Tables exist but pipeline never persists extraction artifacts. | missing | Orchestrator returns `ExtractedDocument` in memory only. 【F:src/db/models.py†L82-L123】【F:src/pipeline/orchestrator.py†L201-L247】 | critical | yes |
| Citation retention | Page spans / section spans for review and alerts | `SectionSpan` includes page and char ranges, but there is no raw snippet reference and nothing is written to DB or surfaced via API. | partial | Section span fields exist; persistence/API absent. 【F:src/schemas/extraction.py†L17-L37】【F:docs/technical-contract.md†L702-L711】 | high | yes |
| Diff engine | Prior-version resolution, section alignment, deterministic classification | Prior-version lookup exists, but alignment is exact section ID only; similarity thresholds do not match contract; no prior-bill-text fallback. | partial | Diff uses dict-by-section-id + SequenceMatcher. 【F:src/db/repositories/file_copies.py†L43-L52】【F:src/diff/section_differ.py†L13-L116】【F:docs/technical-contract.md†L717-L753】 | high | yes |
| Diff persistence | Store diffs and change events | Tables exist, but no write path. | missing | No repository or insert logic for diff tables. 【F:src/db/models.py†L126-L155】【F:src/pipeline/orchestrator.py†L252-L273】 | critical | yes |
| Client profiles | YAML loader and validation | Only a sample YAML file and an in-code `ClientProfile` helper class exist. No YAML loader or enum validation. | missing | Sample file exists; no loader module exists. 【F:config/clients.example.yaml†L1-L47】【F:src/scoring/client_scorer.py†L9-L31】【F:docs/technical-contract.md†L761-L814】 | high | yes |
| Scoring engine | Rules + embeddings + LLM + weighted blend | Current scorer is a simplified rules-only implementation with thresholds that do not match contract weights/dispositions. No embedding or LLM path. | partial | Scorer computes only `rules_score` and mirrors it as final score. 【F:src/scoring/client_scorer.py†L33-L136】【F:docs/technical-contract.md†L817-L889】 | critical | yes |
| Summary generation | Deep internal summary, schema-valid, grounded | A deterministic summary generator exists. No LLM summary path, no schema validation of LLM output because no LLM integration exists. | partial | Rules-based summary exists only. 【F:src/scoring/summary_generator.py†L11-L149】【F:docs/technical-contract.md†L935-L959】 | medium | no |
| Alert rendering/sending | Telegram template, duplicate suppression, sender | Formatter exists but does not match contract template/emoji mapping, and there is no sender or cooldown logic. | partial | Formatter only; no send integration or suppression store. 【F:src/alerts/telegram_formatter.py†L14-L105】【F:docs/technical-contract.md†L989-L1042】 | critical | yes |
| API surface | Health/jobs/bills/versions/alerts/feedback endpoints | Only `/health` exists. | broken | FastAPI app exposes one business route. 【F:apps/api/main.py†L1-L14】【F:docs/technical-contract.md†L1046-L1074】 | critical | yes |
| Job orchestration | Scheduler + full 15-step chain | Worker runs pipeline on demand, but no APScheduler setup, no digest job, no off-session behavior, and chain skips enrichment/scoring persistence/alerts. | partial | CLI wrapper only. 【F:apps/worker/jobs.py†L14-L75】【F:docs/technical-contract.md†L1078-L1106】 | critical | yes |
| Logging/audit | Structured JSON logs and artifact trail | `structlog` is a dependency, but code uses plain `logging`; source-page HTML and PDFs are stored, but downstream audit trail is absent. | partial | Standard library logging only. 【F:pyproject.toml†L19-L21】【F:src/collectors/pdf_downloader.py†L1-L10】【F:src/pipeline/orchestrator.py†L1-L6】【F:docs/technical-contract.md†L1110-L1127】 | high | yes |
| Test coverage | Unit/integration/regression/acceptance coverage | Unit and integration tests are broad for implemented modules, but there are no regression fixtures from real PDFs, no API tests, no alert suppression tests, and no acceptance/pilot tests. | partial | Tests exist and pass, but coverage is foundation-heavy. 【F:tests/unit/test_settings.py†L1-L58】【F:tests/integration/test_pipeline.py†L42-L160】【F:docs/technical-contract.md†L1129-L1167】 | medium | no |

## 4. What is genuinely done

Only the following features clear the bar as **actually implemented** rather than merely planned:

- **Typed settings with fail-fast DB requirement.** `Settings` is a real Pydantic settings object and tests confirm it raises when `DATABASE_URL` is missing. 【F:config/settings.py†L10-L73】【F:tests/unit/test_settings.py†L8-L25】
- **Canonical ID normalization utilities.** Bill ID normalization, chamber extraction, numeric extraction, and canonical version ID generation are implemented and tested. 【F:src/utils/bill_id.py†L10-L52】【F:tests/unit/test_bill_id.py†L1-L39】
- **Core SQLAlchemy schema modeling.** The main tables from contract §7 are represented in ORM code, enough for local in-memory testing and basic persistence. 【F:src/db/models.py†L24-L232】【F:tests/unit/test_db_models.py†L1-L82】
- **Daily and all-file-copy HTML parsing.** Both collectors parse fixture HTML into validated intake rows, and the pipeline persists source-page hashes and new file copies. 【F:src/collectors/cga_daily_filecopies.py†L18-L141】【F:src/collectors/cga_all_filecopies.py†L11-L115】【F:tests/unit/test_daily_collector.py†L1-L61】【F:tests/unit/test_all_filecopies_collector.py†L1-L47】
- **Basic idempotent intake persistence.** Bill upsert, file-copy create-if-new, and source-page hash dedup are implemented and integration-tested. 【F:src/db/repositories/bills.py†L11-L45】【F:src/db/repositories/file_copies.py†L11-L66】【F:src/db/repositories/source_pages.py†L9-L31】【F:tests/integration/test_persistence.py†L13-L84】
- **PDF extraction/normalization/section parsing primitives.** Text extraction, confidence scoring, optional OCR fallback, normalization, and section parsing all exist and are covered by tests. 【F:src/extract/pdf_text.py†L11-L88】【F:src/extract/confidence.py†L13-L43】【F:src/extract/ocr_fallback.py†L12-L62】【F:src/extract/normalize_text.py†L17-L100】【F:src/extract/section_parser.py†L34-L280】
- **A basic in-process pipeline.** `Pipeline.run_daily()` and `run_reconciliation()` can process fixture-backed entries through ingest, download, extraction, diffing, subject tagging, and summary generation in tests. 【F:src/pipeline/orchestrator.py†L297-L362】【F:tests/integration/test_pipeline.py†L42-L160】
- **A passing local test suite for the implemented foundation.** `pytest -q` passed with 161 tests in this review environment. This is real evidence of internal consistency for the currently implemented scope. (Command run: `pytest -q` → `161 passed in 6.41s`.)

## 5. What is partially done but not production-ready

- **Schemas are present, but runtime discipline is weaker than the contract implies.** The models use `HttpUrl` and Literal fields, but collector and alert code pass plain strings into them, which `mypy` flags. That means schema design is ahead of the actual type discipline in the implementation. (Command run: `timeout 20s mypy src/ apps/ config/`.) 【F:src/schemas/intake.py†L9-L28】【F:src/schemas/summary.py†L19-L30】【F:src/collectors/cga_daily_filecopies.py†L29-L41】【F:src/alerts/telegram_formatter.py†L23-L45】
- **Database design is ahead of execution.** The repo models extraction, diff, score, alert, and feedback tables, but none of those downstream artifacts are inserted by the pipeline. This is classic “schema-first scaffolding”: useful groundwork, not a working product. 【F:src/db/models.py†L82-L232】【F:src/pipeline/orchestrator.py†L201-L362】
- **Collectors are functional, but limited to fixtures and simple HTML assumptions.** The parsing logic is plausible, but it uses table heuristics and bare exception swallowing, which is not yet a production-grade parser/audit implementation for a government site that may change layout. 【F:src/collectors/cga_daily_filecopies.py†L54-L141】【F:src/collectors/cga_all_filecopies.py†L52-L115】
- **Diffing exists, but the implementation is materially below the contract.** The contract requires exact ID match, fuzzy heading match, and fallback semantic similarity. The current differ only compares same `section_id` values and otherwise labels add/remove; there is no fuzzy or semantic alignment stage. 【F:src/diff/section_differ.py†L21-L82】【F:docs/technical-contract.md†L725-L738】
- **Scoring and alert formatting are placeholders, not production scoring.** The client scorer is a convenience rule set, not the contract scoring engine. It lacks negative keywords, client YAML priorities, embedding score, LLM score, weighted blend, and suppression logic. The Telegram formatter similarly produces a custom message rather than the contract template and does not send anything. 【F:src/scoring/client_scorer.py†L33-L136】【F:src/alerts/telegram_formatter.py†L48-L97】【F:docs/technical-contract.md†L821-L889】【F:docs/technical-contract.md†L991-L1042】
- **Worker/API layers are placeholders.** The worker is basically a command-line entrypoint, not a scheduler. The API is a health endpoint only. Those files exist, but they do not meaningfully satisfy Pass 6. 【F:apps/worker/jobs.py†L14-L75】【F:apps/api/main.py†L1-L14】

## 6. What is missing

### Configuration and ops

- `REDIS_URL` support from the technical contract is missing from both `.env.example` and the typed settings object. 【F:docs/technical-contract.md†L115-L139】【F:.env.example†L1-L42】【F:config/settings.py†L17-L57】
- There is no CI configuration or pre-commit setup despite Phase 0 calling for a CI stub. 【F:docs/build-spec.md†L59-L74】
- `README.md` contains no setup, architecture, runbook, or deployment guidance. 【F:README.md†L1-L1】

### Database and migrations

- No Alembic revision history at all. The project has migration scaffolding but no actual migration files. 【F:migrations/env.py†L1-L44】【F:migrations/script.py.mako†L1-L27】
- No jobs table, even though Phase 1 deliverables explicitly include database tables for jobs. 【F:docs/build-spec.md†L81-L88】
- No repositories/services for writing `bill_text_extractions`, `bill_text_pages`, `bill_sections`, `bill_diffs`, `bill_change_events`, `client_bill_scores`, `alerts`, or `feedback_labels`. 【F:src/db/models.py†L82-L232】

### Enrichment and intelligence

- Bill-status enrichment is not integrated into ingestion. The parser exists but is unused. 【F:src/collectors/cga_bill_status.py†L6-L97】【F:src/pipeline/orchestrator.py†L11-L31】
- No prior-bill-text fallback comparator. 【F:docs/technical-contract.md†L717-L723】
- No fuzzy/semantic section alignment implementation. 【F:docs/technical-contract.md†L725-L730】
- No diff persistence. 【F:src/pipeline/orchestrator.py†L252-L273】
- No controlled-vocabulary enforcement in runtime tagging/classification. 【F:src/scoring/subject_tagger.py†L11-L154】【F:src/diff/change_classifier.py†L11-L189】

### Scoring, LLM, and alerts

- No YAML client-profile loader/validator. The contract calls for YAML-backed profiles with enum validation; the repo has only a sample file and an ad hoc class. 【F:config/clients.example.yaml†L1-L47】【F:docs/technical-contract.md†L761-L814】
- No embeddings integration. 【F:docs/technical-contract.md†L846-L856】
- No LLM prompts, wrappers, or schema-validated JSON handling. The `src/llm/` package is effectively empty. 【F:docs/technical-contract.md†L893-L988】
- No Telegram sender, digest mode, duplicate suppression, or cooldown persistence. 【F:docs/technical-contract.md†L881-L889】【F:docs/technical-contract.md†L989-L1042】

### API and product surface

- Missing required endpoints for jobs, bills, versions, alerts, and feedback. 【F:docs/technical-contract.md†L1050-L1074】【F:apps/api/main.py†L1-L14】
- No dashboard/admin views. 【F:docs/build-spec.md†L169-L179】
- No ability to query extracted sections, diffs, summaries, scores, or alerts because those artifacts are not persisted or exposed. 【F:src/pipeline/orchestrator.py†L278-L362】【F:apps/api/main.py†L1-L14】

### Operational hardening

- No structured JSON logging implementation even though `structlog` is declared. 【F:pyproject.toml†L19-L21】【F:docs/technical-contract.md†L1110-L1127】
- No monitoring/metrics. 【F:docs/build-spec.md†L169-L179】
- No regression fixture set matching the contract’s required historical scenarios. The repo has HTML fixtures but no sample PDF corpus under `data/samples/`. 【F:docs/technical-contract.md†L1146-L1156】

## 7. Code-quality review

### Architecture

The architecture is directionally sane for a deterministic pipeline: schemas, collectors, extraction, diffing, scoring, alerts, DB, and API are separated into modules. That is the best thing about the repo. But the architecture is still **layer-skewed**: schema/model breadth is much farther along than actual service behavior. The result is a repo that *looks* more complete than it is. 【F:src/db/models.py†L24-L232】【F:src/pipeline/orchestrator.py†L38-L362】

### Modularity

Modularity is decent in the foundation layers. Utility functions are small, parsing logic is split by source, and extraction stages are distinct. That said, the main pipeline uses untyped `dict` payloads between stages (`entry`, `result`) instead of typed internal DTOs, which will become fragile once more stages are added. 【F:src/pipeline/orchestrator.py†L120-L178】【F:src/pipeline/orchestrator.py†L339-L362】

### Correctness

Correctness is mixed:

- Good: canonical bill ID handling and basic dedup work. 【F:src/utils/bill_id.py†L10-L52】【F:tests/integration/test_persistence.py†L49-L84】
- Bad: runtime taxonomy values diverge from the approved enums, which is a direct contract violation. 【F:src/scoring/subject_tagger.py†L11-L111】【F:src/diff/change_classifier.py†L11-L23】【F:docs/technical-contract.md†L21-L28】
- Bad: the differ’s `bill_id` derivation uses `canonical_version_id.rsplit("-", 1)[0]`, which yields strings like `2026-SB00093` instead of pure bill IDs, so even some schema-level outputs are semantically wrong. 【F:src/diff/section_differ.py†L69-L87】【F:src/scoring/subject_tagger.py†L145-L153】

### Coupling

The code is not overly coupled, but the pipeline currently owns too much orchestration logic directly. Once persistence of downstream artifacts arrives, this file will bloat fast unless extraction, diff persistence, scoring, and alerting move into dedicated services. 【F:src/pipeline/orchestrator.py†L38-L362】

### Naming

Naming is mostly clear, but there are some contract drifts that matter:

- `healthcare`, `environment`, `taxation`, `labor`, `public_safety`, `technology`, and `government_operations` do not match the approved taxonomy values. 【F:src/scoring/subject_tagger.py†L12-L110】【F:docs/technical-contract.md†L157-L186】
- `effective_date_change` and `new_section_added` do not match the approved change flags such as `effective_date_changed` and `section_added`. 【F:src/diff/change_classifier.py†L11-L23】【F:docs/technical-contract.md†L190-L224】

### Testability

Testability is one of the stronger areas. The code is structured so collectors and extractors can be unit-tested, and the pipeline accepts a mock fetcher. That is good engineering. 【F:tests/integration/test_pipeline.py†L27-L40】【F:tests/unit/test_daily_collector.py†L1-L61】

### Schema discipline

The repository talks a stronger schema game than it actually plays. Pydantic models exist, but the code often downgrades back to untyped dicts or plain strings. The failing `mypy` run is evidence that the team is not yet keeping implementation and schema contracts aligned. (Command run: `timeout 20s mypy src/ apps/ config/`.) 【F:src/schemas/intake.py†L9-L28】【F:src/pipeline/orchestrator.py†L120-L178】

### Error handling

Error handling is acceptable for a prototype, not for production. Network errors are logged and suppressed; parser errors are swallowed broadly; PDF page count extraction ignores all exceptions; and there is no retry queue or dead-letter path. 【F:src/collectors/http_fetcher.py†L35-L98】【F:src/collectors/cga_daily_filecopies.py†L88-L141】【F:src/pipeline/orchestrator.py†L185-L191】

### Idempotency

Intake idempotency is real for source pages and file copies. Full-pipeline idempotency is **not** implemented because scores/alerts/diffs are not persisted and there is no suppression/cooldown layer. The contract’s idempotency rule is therefore only partially satisfied. 【F:src/db/repositories/file_copies.py†L15-L37】【F:src/db/repositories/source_pages.py†L24-L31】【F:docs/technical-contract.md†L33-L35】

### Maintainability

The repo is maintainable **if** the next tranche closes the gap between scaffolding and execution. If not, it will drift into a misleading state where there are many models and tests for a system that still cannot operate during session. The missing migration history is especially dangerous: it will make every later DB change more painful. 【F:src/db/models.py†L24-L232】【F:migrations/env.py†L1-L44】

## 8. Production blockers

### Blockers for a working MVP

1. **No persistence for extraction/diff/score/summary/alert artifacts.** Without this, the system cannot produce auditable outputs or support any API/view layer. 【F:src/db/models.py†L82-L232】【F:src/pipeline/orchestrator.py†L201-L362】
2. **Runtime taxonomy and change-flag outputs violate the controlled vocabularies.** That breaks the technical contract and undermines downstream scoring/alert logic. 【F:src/scoring/subject_tagger.py†L11-L154】【F:src/diff/change_classifier.py†L11-L189】【F:docs/technical-contract.md†L21-L28】
3. **No real alerting system.** There is no Telegram sender, suppression logic, or per-client disposition persistence. 【F:src/alerts/telegram_formatter.py†L23-L105】【F:docs/technical-contract.md†L881-L889】
4. **API is nonfunctional beyond health.** MVP operations require manual reprocessing/query capabilities that do not exist. 【F:apps/api/main.py†L1-L14】【F:docs/technical-contract.md†L1050-L1074】
5. **No migration history.** A deployable MVP should not rely on `Base.metadata.create_all()` for schema setup. 【F:src/db/session.py†L19-L25】【F:migrations/env.py†L1-L44】

### Blockers for a production-minded pilot

1. **No contract-compliant scoring engine or client profile loader.** Current scoring is a placeholder and cannot be trusted for client-facing alert decisions. 【F:src/scoring/client_scorer.py†L33-L136】【F:docs/technical-contract.md†L761-L889】
2. **No structured logging/audit trail for downstream reasoning.** Production use requires traceability of why alerts were sent or suppressed. 【F:docs/technical-contract.md†L27-L29】【F:docs/technical-contract.md†L1110-L1127】
3. **No scheduler/digest job/off-session controls.** The worker does not satisfy the operational cadence contract. 【F:apps/worker/jobs.py†L14-L75】【F:docs/technical-contract.md†L1080-L1089】
4. **Mypy is failing.** Type contract drift is already visible in core modules. (Command run: `timeout 20s mypy src/ apps/ config/`.)
5. **No real migration/deployment path.** `alembic upgrade head` failed in this review environment and, separately, there are no revision files to apply anyway. (Command run: `alembic upgrade head` → SQLite `unable to open database file` from `alembic.ini` default path.) 【F:alembic.ini†L1-L3】

### Blockers for the full system

1. **LLM subsystem is absent.** No prompts, no wrappers, no schema-validated JSON path, no confidentiality controls in prompts. 【F:docs/technical-contract.md†L893-L988】
2. **Embeddings subsystem is absent.** 【F:docs/technical-contract.md†L846-L856】
3. **Feedback loop and dashboard are absent.** 【F:docs/build-spec.md†L164-L179】【F:docs/technical-contract.md†L1070-L1074】
4. **Regression and acceptance test corpus is absent.** 【F:docs/technical-contract.md†L1146-L1167】

## 9. Fastest path to a deployable MVP

### 1. Working internal MVP

1. **Close the database execution gap.** Create the initial Alembic migration, stop relying on `create_all_tables()` for normal operation, and add repositories/services for extraction artifacts, sections, diffs, scores, and alerts. 【F:src/db/session.py†L19-L25】【F:src/db/models.py†L82-L232】
2. **Make runtime outputs obey the contract enums.** Replace ad hoc subject tags and change flags with values loaded from the taxonomy YAMLs; fail fast on unknown values. 【F:config/taxonomy.subjects.yaml†L1-L32】【F:config/taxonomy.change_flags.yaml†L1-L38】【F:docs/technical-contract.md†L21-L28】
3. **Wire bill-status enrichment into the pipeline.** Persist title/committee/status metadata before scoring. 【F:src/collectors/cga_bill_status.py†L6-L97】【F:docs/technical-contract.md†L640-L647】
4. **Persist extraction and diff artifacts.** The MVP cannot be reviewed or queried otherwise. 【F:docs/build-spec.md†L27-L41】【F:src/pipeline/orchestrator.py†L201-L362】
5. **Implement a contract-aligned rules scorer + YAML client-profile loader.** Skip embeddings/LLM for the first internal MVP if necessary, but make rules scoring deterministic and spec-consistent. 【F:docs/build-spec.md†L134-L145】【F:docs/technical-contract.md†L821-L889】
6. **Implement Telegram sending plus duplicate suppression/cooldown persistence.** Without this there is no alerting product. 【F:docs/build-spec.md†L152-L162】【F:docs/technical-contract.md†L881-L889】
7. **Expand the API minimally.** Add `/jobs/collect/daily`, `/jobs/process/{canonical_version_id}`, `/versions/{canonical_version_id}`, and `/alerts`. That is enough to operate the MVP internally. 【F:docs/technical-contract.md†L1050-L1074】

### 2. Production-minded pilot during session

1. **Replace the simplistic section differ with contract-aligned alignment and thresholds.** 【F:docs/technical-contract.md†L725-L738】
2. **Introduce structured JSON logging and persistent run/audit records.** 【F:docs/technical-contract.md†L1110-L1127】
3. **Add APScheduler-backed cadence controls, digest job, and session-aware scheduling.** 【F:docs/technical-contract.md†L1080-L1089】
4. **Add regression PDF fixtures covering low-quality OCR, multi-version changes, no-alert, single-alert, and digest-only cases.** 【F:docs/technical-contract.md†L1146-L1156】
5. **Add acceptance tests for duplicate suppression, diff correctness, and schema-valid outputs.** 【F:docs/technical-contract.md†L1158-L1167】
6. **Only after the deterministic path is stable, add LLM summary/relevance wrappers with hard JSON validation.** 【F:docs/technical-contract.md†L15-L29】【F:docs/technical-contract.md†L893-L988】

## 10. Recommended next build tranche

The next Codex build tranche should be:

**“Persist the intelligence layer and make it queryable.”**

Concretely, the next coding pass should do only these things:

1. create the initial Alembic revision;
2. add repositories/services to persist `bill_text_extractions`, `bill_text_pages`, `bill_sections`, `bill_diffs`, and `bill_change_events`;
3. wire those writes into `Pipeline.extract_document()` / `diff_version()` flow;
4. add `GET /versions/{canonical_version_id}` to return the persisted extraction + diff payload;
5. add integration tests proving a newly processed file copy is queryable afterward.

Why this tranche next:

- It is **narrow** enough to implement safely.
- It unlocks **auditability**, **API usefulness**, and **future scoring/alert persistence**.
- It turns the repo from a demo pipeline into an actual system of record, which is the biggest current gap. 【F:src/db/models.py†L82-L155】【F:src/pipeline/orchestrator.py†L201-L273】【F:docs/technical-contract.md†L53-L62】

## 11. Appendix: evidence inventory

### Governing documents reviewed

- `PLAN.md` — implementation pass plan and claimed sequencing. 【F:PLAN.md†L10-L195】
- `docs/build-spec.md` — MVP phase definitions, outputs, and success criteria. 【F:docs/build-spec.md†L15-L179】
- `docs/technical-contract.md` — normative contract for env vars, schemas, DB, collectors, diffing, scoring, alerts, API, orchestration, and testing. 【F:docs/technical-contract.md†L111-L245】【F:docs/technical-contract.md†L249-L428】【F:docs/technical-contract.md†L432-L1167】

### High-impact implementation files reviewed

- `config/settings.py` — typed settings and fail-fast behavior. 【F:config/settings.py†L10-L73】
- `pyproject.toml` — dependency/runtime contract and tool configuration. 【F:pyproject.toml†L1-L60】
- `.env.example` — environment contract completeness. 【F:.env.example†L1-L42】
- `src/db/models.py` — ORM coverage versus contract tables. 【F:src/db/models.py†L24-L232】
- `src/db/repositories/*.py` — actual persistence behavior and idempotency scope. 【F:src/db/repositories/bills.py†L11-L45】【F:src/db/repositories/file_copies.py†L11-L66】【F:src/db/repositories/source_pages.py†L9-L31】
- `src/collectors/*.py` — intake and metadata parsing behavior. 【F:src/collectors/cga_daily_filecopies.py†L18-L141】【F:src/collectors/cga_all_filecopies.py†L11-L115】【F:src/collectors/cga_bill_status.py†L6-L97】【F:src/collectors/http_fetcher.py†L11-L98】
- `src/extract/*.py` — extraction/normalization/section parsing implementation. 【F:src/extract/pdf_text.py†L11-L88】【F:src/extract/confidence.py†L13-L43】【F:src/extract/normalize_text.py†L17-L100】【F:src/extract/section_parser.py†L34-L280】
- `src/diff/*.py` — comparison logic and change classification. 【F:src/diff/section_differ.py†L13-L116】【F:src/diff/change_classifier.py†L47-L189】
- `src/scoring/*.py` — current subject tagging, scoring, and summary behavior. 【F:src/scoring/subject_tagger.py†L11-L154】【F:src/scoring/client_scorer.py†L9-L136】【F:src/scoring/summary_generator.py†L11-L149】
- `src/alerts/telegram_formatter.py` — current alert formatting scope. 【F:src/alerts/telegram_formatter.py†L23-L105】
- `src/pipeline/orchestrator.py` — actual end-to-end behavior and current stopping point. 【F:src/pipeline/orchestrator.py†L38-L362】
- `apps/api/main.py` and `apps/worker/jobs.py` — API/jobs readiness. 【F:apps/api/main.py†L1-L14】【F:apps/worker/jobs.py†L14-L75】

### Commands run during review

- `pytest -q` → passed: `161 passed in 6.41s`.
- `ruff check src/ apps/ tests/ config/` → passed: `All checks passed!`.
- `timeout 20s mypy src/ apps/ config/` → failed with 13 type errors, including `HttpUrl`/Literal mismatches and missing optional OCR stubs.
- `python - <<'PY' ...` to inspect FastAPI routes → only `/health` plus docs routes were present.
- `alembic upgrade head` → failed with SQLite `unable to open database file`; even aside from that environment-path issue, there are no revision files in `migrations/` to establish a real schema history. 【F:alembic.ini†L1-L3】【F:migrations/env.py†L1-L44】
