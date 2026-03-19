# CT CGA File Copy Agent: Technical Implementation Contract

## Purpose

This document is the execution contract for building the CT General Assembly file-copy intelligence system described in the build spec. It is written for direct use by Codex or a capable developer. It defines the required data models, parser behavior, scoring rules, prompt contracts, alert formats, APIs, and acceptance criteria.

This system is **not** a free-form autonomous agent. It is a deterministic monitoring and triage pipeline with tightly constrained LLM use.

---

# 1. Core principles

## 1.1 Non-negotiable design rules

1. **Never alert from raw PDF text alone.** Every alert must be grounded in extracted text, normalized sections, bill metadata, and a comparison against a prior version when one exists.
2. **Every LLM output must be schema-validated.** Invalid JSON is a failed run, not a partial success.
3. **Controlled vocabularies only.** The model may not invent subject tags, change flags, urgency levels, or client relevance reasons outside approved enums.
4. **Deterministic before probabilistic.** Collection, parsing, normalization, diffing, and rules scoring come before embeddings or LLM reasoning.
5. **Every alert must be explainable.** The system must store the exact reasons, scores, and source citations that caused the alert.
6. **Client confidentiality must be minimized in prompts.** LLM prompts should use internal client IDs and abstracted interest summaries whenever possible.
7. **Idempotency is mandatory.** Re-running the same job against the same source must not create duplicate rows, duplicate PDFs, or duplicate alerts.

## 1.2 MVP sequencing guidance

The current repository already contains prototype implementations for collection, extraction, diffing, and simplified scoring. For near-term execution, coding agents should prioritize the following order:

1. persist extraction and diff artifacts;
2. enforce controlled vocabularies and metadata enrichment;
3. implement deterministic client scoring and alert-decision persistence;
4. add Telegram delivery and suppression behavior;
5. expose operational API endpoints and scheduler-driven jobs;
6. defer embeddings, broader LLM reasoning, and dashboard work until the deterministic MVP is stable.

This sequencing guidance is intended to keep implementation aligned with `PLAN.md` and the production-readiness review.

---

# 2. System scope

## 2.1 Inputs

The system ingests:
- the daily CT General Assembly file-copy page;
- the session-wide all-file-copy listing for backfill and reconciliation;
- bill status / bill information pages;
- file-copy PDFs;
- internal client-interest profiles;
- user feedback on alert quality.

## 2.2 Outputs

The system produces:
- normalized bill/file-copy records;
- extracted and sectioned text;
- version diffs and change classifications;
- subject tags and legal-effect flags;
- per-client relevance scores and reasons;
- internal review summaries;
- Telegram alerts and digests;
- audit trails and review dashboards.

---

# 3. MVP definition for implementation

The minimum internally deployable MVP must support all of the following:

1. ingest and persist file-copy listings and PDFs;
2. extract, normalize, section, and persist bill text artifacts;
3. compare a new file copy to the prior version and persist structured diff outputs;
4. enrich bills with status metadata needed for scoring;
5. score relevance per client using validated YAML profiles and deterministic rules;
6. persist client scores, reasons, urgency, and final dispositions;
7. send or suppress Telegram alerts based on persisted decisions;
8. expose enough API surface to inspect versions, alerts, and trigger jobs.

The following are explicitly **post-MVP** unless otherwise requested:
- embeddings-based matching,
- LLM client-relevance reasoning,
- dashboard/review UI polish,
- broad feedback-driven calibration tooling.

---

# 4. Environment contract

## 4.1 Required environment variables

```env
APP_ENV=development
LOG_LEVEL=INFO
DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/ct_cga_agent
REDIS_URL=redis://localhost:6379/0
STORAGE_BACKEND=local
STORAGE_LOCAL_DIR=./var/storage
STORAGE_S3_BUCKET=
STORAGE_S3_REGION=
STORAGE_S3_ENDPOINT=
STORAGE_S3_ACCESS_KEY_ID=
STORAGE_S3_SECRET_ACCESS_KEY=
OPENAI_API_KEY=
OPENAI_MODEL_SUMMARY=
OPENAI_MODEL_REASONING=
OPENAI_EMBEDDING_MODEL=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_ALERTS_ENABLED=false
CGA_REQUEST_TIMEOUT_SECONDS=30
CGA_POLL_INTERVAL_MINUTES=20
OCR_ENABLED=true
TESSERACT_CMD=tesseract
DEFAULT_TIMEZONE=America/New_York
SESSION_YEAR=2026
```

## 4.2 Settings rules

- The app must fail fast if `DATABASE_URL` is missing.
- The app may run without Telegram credentials if alerts are disabled.
- The app may run without LLM credentials only in ingestion/test-only mode.
- All settings must be loaded through a typed config object.

---

# 5. Canonical controlled vocabularies

## 5.1 Subject tags enum

```text
health_care
insurance
labor_employment
tax_revenue
appropriations_budget
municipalities
housing
energy_environment
transportation
cannabis
gaming
data_privacy
artificial_intelligence
education
procurement
licensing_regulation
reimbursement_rate_setting
civil_liability
criminal_justice
consumer_protection
utilities
land_use_zoning
public_health
social_services
agriculture_food
banking_financial_services
professional_services
state_agency_governance
```

## 5.2 Change flag enum

```text
section_added
section_removed
definition_changed
scope_expanded
scope_narrowed
deadline_changed
reporting_requirement_added
reporting_requirement_removed
penalty_added
penalty_removed
exemption_added
exemption_removed
funding_language_added
funding_language_removed
appropriation_added
appropriation_removed
rulemaking_authority_added
rulemaking_authority_expanded
rulemaking_authority_removed
enforcement_changed
ag_enforcement_only
private_right_of_action_added
private_right_of_action_removed
licensing_requirement_added
licensing_requirement_removed
mandate_added
mandate_removed
reimbursement_changed
eligibility_changed
effective_date_changed
sunset_added
sunset_removed
preemption_risk
compliance_cost_risk
```

## 5.3 Urgency enum

```text
low
medium
high
critical
```

## 5.4 Alert disposition enum

```text
no_alert
digest
immediate
suppressed_duplicate
suppressed_below_threshold
suppressed_cooldown
```

---

# 6. Implementation guardrails for future changes

1. Prefer small deterministic services over large orchestration-heavy abstractions.
2. Persist raw artifacts and normalized artifacts separately.
3. Validate every external or model-produced payload before persistence.
4. Keep feature flags explicit for Telegram, OCR, and LLM-enabled behavior.
5. Add tests with every major module or persistence path.
6. Do not introduce agentic chat workflows as part of the product surface.

The remainder of the technical contract can be expanded as implementation requires, but these sections are the current normative baseline for MVP execution.
