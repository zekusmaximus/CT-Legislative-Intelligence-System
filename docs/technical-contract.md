 # CT CGA File Copy Agent: Technical Implementation Contract

## Purpose

This document is the execution contract for building the CT General Assembly file-copy intelligence system described in the build spec. It is written for direct use by Codex or a capable developer. It defines the required data models, parser behavior, scoring rules, prompt contracts, alert formats, APIs, and acceptance criteria.

This system is **not** a free-form autonomous agent. It is a deterministic monitoring and triage pipeline with tightly constrained LLM use.

---

# 1. Core principles

## 1.1 Non-negotiable design rules

1. **Never alert from raw PDF text alone.**
   Every alert must be grounded in extracted text, normalized sections, bill metadata, and a comparison against a prior version when one exists.

2. **Every LLM output must be schema-validated.**
   Invalid JSON is a failed run, not a partial success.

3. **Controlled vocabularies only.**
   The model may not invent subject tags, change flags, urgency levels, or client relevance reasons outside approved enums.

4. **Deterministic before probabilistic.**
   Collection, parsing, normalization, and diffing come before embeddings and LLM reasoning.

5. **Every alert must be explainable.**
   The system must store the exact reasons, scores, and source citations that caused the alert.

6. **Client confidentiality must be minimized in prompts.**
   LLM prompts should use internal client IDs and abstracted interest summaries whenever possible.

7. **Idempotency is mandatory.**
   Re-running the same job against the same source must not create duplicate rows, duplicate PDFs, or duplicate alerts.

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

# 3. Required repository structure

```text
ct-cga-filecopy-agent/
â”œâ”€ AGENTS.md
â”œâ”€ README.md
â”œâ”€ Makefile
â”œâ”€ pyproject.toml
â”œâ”€ .env.example
â”œâ”€ alembic.ini
â”œâ”€ migrations/
â”œâ”€ docs/
â”‚  â”œâ”€ build-spec.md
â”‚  â””â”€ technical-contract.md
â”œâ”€ config/
â”‚  â”œâ”€ taxonomy.subjects.yaml
â”‚  â”œâ”€ taxonomy.change_flags.yaml
â”‚  â”œâ”€ taxonomy.urgency.yaml
â”‚  â””â”€ clients.example.yaml
â”œâ”€ data/
â”‚  â”œâ”€ fixtures/
â”‚  â””â”€ samples/
â”œâ”€ apps/
â”‚  â”œâ”€ api/
â”‚  â”‚  â””â”€ main.py
â”‚  â”œâ”€ worker/
â”‚  â”‚  â””â”€ jobs.py
â”‚  â””â”€ admin/
â”œâ”€ src/
â”‚  â”œâ”€ collectors/
â”‚  â”œâ”€ extract/
â”‚  â”œâ”€ normalize/
â”‚  â”œâ”€ diff/
â”‚  â”œâ”€ metadata/
â”‚  â”œâ”€ scoring/
â”‚  â”œâ”€ llm/
â”‚  â”œâ”€ alerts/
â”‚  â”œâ”€ db/
â”‚  â”œâ”€ schemas/
â”‚  â””â”€ utils/
â””â”€ tests/
```

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

The first production taxonomy should include only these values:

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

# 6. Pydantic schema contract

The actual implementation should use Pydantic v2 models. The field names below are normative.

## 6.1 Intake models

```python
from datetime import datetime, date
from typing import Literal, Optional
from pydantic import BaseModel, HttpUrl, Field

class SourcePageRecord(BaseModel):
    source_type: Literal["daily_filecopies", "all_filecopies", "bill_status"]
    source_url: HttpUrl
    fetched_at: datetime
    content_sha256: str
    http_status: int
    session_year: int

class FileCopyListingRow(BaseModel):
    session_year: int
    bill_id: str = Field(pattern=r"^(HB|SB)\d{5}$")
    bill_number_display: str
    bill_title: str
    file_copy_number: int
    file_copy_pdf_url: HttpUrl
    listing_date: date
    listing_source_url: HttpUrl
```

## 6.2 Bill and file-copy models

```python
class BillRecord(BaseModel):
    session_year: int
    bill_id: str = Field(pattern=r"^(HB|SB)\d{5}$")
    chamber: Literal["house", "senate"]
    bill_number_numeric: int
    current_title: str
    committee_name: Optional[str] = None
    bill_status_url: Optional[HttpUrl] = None
    last_seen_at: datetime

class FileCopyRecord(BaseModel):
    session_year: int
    bill_id: str
    file_copy_number: int
    canonical_version_id: str
    pdf_url: HttpUrl
    pdf_sha256: str
    local_pdf_path: Optional[str] = None
    page_count: Optional[int] = None
    discovered_at: datetime
    extracted_at: Optional[datetime] = None
```

## 6.3 Extraction models

```python
class PageText(BaseModel):
    page_number: int
    raw_text: str
    cleaned_text: str
    extraction_method: Literal["text", "ocr"]
    extraction_confidence: float = Field(ge=0, le=1)

class SectionSpan(BaseModel):
    section_id: str
    heading: str
    start_page: int
    end_page: int
    start_char: int
    end_char: int
    text: str

class ExtractedDocument(BaseModel):
    canonical_version_id: str
    pages: list[PageText]
    full_raw_text: str
    full_cleaned_text: str
    sections: list[SectionSpan]
    overall_extraction_confidence: float = Field(ge=0, le=1)
    extraction_warnings: list[str] = []
```

## 6.4 Diff models

```python
class SectionDelta(BaseModel):
    section_id: str
    old_heading: Optional[str] = None
    new_heading: Optional[str] = None
    delta_type: Literal["added", "removed", "modified", "unchanged"]
    old_text: Optional[str] = None
    new_text: Optional[str] = None
    similarity_score: float = Field(ge=0, le=1)

class ChangeEvent(BaseModel):
    change_flag: str
    section_id: Optional[str] = None
    old_text_summary: str
    new_text_summary: str
    practical_effect: str
    confidence: float = Field(ge=0, le=1)

class BillDiffResult(BaseModel):
    bill_id: str
    current_version_id: str
    prior_version_id: Optional[str] = None
    compared_against: Literal["prior_file_copy", "prior_bill_text", "none"]
    sections_added: int
    sections_removed: int
    sections_modified: int
    section_deltas: list[SectionDelta]
    change_events: list[ChangeEvent]
    effective_date_old: Optional[str] = None
    effective_date_new: Optional[str] = None
```

## 6.5 Subject tagging and client scoring models

```python
class SubjectTagResult(BaseModel):
    bill_id: str
    version_id: str
    subject_tags: list[str]
    change_flags: list[str]
    tag_confidence: float = Field(ge=0, le=1)
    rationale: list[str]

class ClientMatchReason(BaseModel):
    reason_code: Literal[
        "keyword_match",
        "agency_match",
        "committee_match",
        "subject_match",
        "change_flag_match",
        "embedding_match",
        "llm_relevance_reason",
        "watched_bill"
    ]
    reason_text: str
    weight: float

class ClientScoreResult(BaseModel):
    client_id: str
    bill_id: str
    version_id: str
    rules_score: float
    embedding_score: float
    llm_score: float
    final_score: float
    urgency: Literal["low", "medium", "high", "critical"]
    should_alert: bool
    alert_disposition: str
    match_reasons: list[ClientMatchReason]
```

## 6.6 Summary and alert models

```python
class InternalSummary(BaseModel):
    bill_id: str
    version_id: str
    one_sentence_summary: str
    deep_summary: str
    key_sections_to_review: list[str]
    practical_takeaways: list[str]
    confidence: float = Field(ge=0, le=1)

class TelegramAlertPayload(BaseModel):
    client_id: str
    bill_id: str
    version_id: str
    urgency: Literal["low", "medium", "high", "critical"]
    alert_text: str
    file_copy_url: HttpUrl
    bill_status_url: Optional[HttpUrl] = None
    suppression_key: str
```

---

# 7. Database contract

These tables are required.

## 7.1 Core tables

### `source_pages`
- `id`
- `source_type`
- `source_url`
- `session_year`
- `fetched_at`
- `http_status`
- `content_sha256`
- `raw_html_path`

### `bills`
- `id`
- `session_year`
- `bill_id` unique with `session_year`
- `chamber`
- `bill_number_numeric`
- `current_title`
- `committee_name`
- `bill_status_url`
- `created_at`
- `updated_at`

### `file_copies`
- `id`
- `bill_id_fk`
- `session_year`
- `file_copy_number`
- `canonical_version_id` unique
- `listing_date`
- `pdf_url`
- `pdf_sha256`
- `local_pdf_path`
- `page_count`
- `discovered_at`
- `extracted_at`

### `bill_text_extractions`
- `id`
- `canonical_version_id_fk`
- `full_raw_text`
- `full_cleaned_text`
- `overall_extraction_confidence`
- `extraction_warnings_json`
- `created_at`

### `bill_text_pages`
- `id`
- `extraction_id_fk`
- `page_number`
- `raw_text`
- `cleaned_text`
- `extraction_method`
- `extraction_confidence`

### `bill_sections`
- `id`
- `canonical_version_id_fk`
- `section_id`
- `heading`
- `start_page`
- `end_page`
- `start_char`
- `end_char`
- `text`

### `bill_diffs`
- `id`
- `bill_id_fk`
- `current_version_id_fk`
- `prior_version_id_fk`
- `compared_against`
- `sections_added`
- `sections_removed`
- `sections_modified`
- `effective_date_old`
- `effective_date_new`
- `created_at`

### `bill_change_events`
- `id`
- `bill_diff_id_fk`
- `change_flag`
- `section_id`
- `old_text_summary`
- `new_text_summary`
- `practical_effect`
- `confidence`

## 7.2 Client and scoring tables

### `clients`
- `id`
- `client_id` unique
- `display_name`
- `is_active`
- `alert_threshold`
- `digest_threshold`
- `created_at`
- `updated_at`

### `client_interest_profiles`
- `id`
- `client_id_fk`
- `profile_yaml`
- `profile_text_for_embedding`
- `profile_version`
- `created_at`

### `client_bill_scores`
- `id`
- `client_id_fk`
- `bill_id_fk`
- `canonical_version_id_fk`
- `rules_score`
- `embedding_score`
- `llm_score`
- `final_score`
- `urgency`
- `should_alert`
- `alert_disposition`
- `reasons_json`
- `created_at`

## 7.3 Alert and feedback tables

### `alerts`
- `id`
- `client_id_fk`
- `bill_id_fk`
- `canonical_version_id_fk`
- `urgency`
- `alert_disposition`
- `alert_text`
- `telegram_message_id`
- `suppression_key`
- `sent_at`
- `created_at`

### `feedback_labels`
- `id`
- `client_id_fk`
- `bill_id_fk`
- `canonical_version_id_fk`
- `label` (`useful`, `not_useful`, `wrong_client`, `wrong_subject`, `missed`, `over_alerted`)
- `notes`
- `created_at`

---

# 8. Canonical identifiers

## 8.1 Bill ID normalization

Normalize all bill identifiers into this format:

- `SB00093`
- `HB05140`

Rules:
- prefix is chamber abbreviation in uppercase;
- numeric portion is zero-padded to five digits;
- display values may preserve spaces and punctuation separately.

## 8.2 Canonical version ID

Use this format:

```text
{session_year}-{bill_id}-FC{file_copy_number:05d}
```

Example:

```text
2026-SB00093-FC00044
```

---

# 9. Collector behavior contract

## 9.1 Daily file-copy collector

The daily collector must:

1. fetch the daily page;
2. persist the raw HTML and metadata;
3. parse each file-copy row;
4. normalize bill identifiers;
5. create or update bill records;
6. create file-copy records only if the canonical version ID does not already exist;
7. enqueue PDF download jobs for newly discovered file copies.

## 9.2 All-file-copy reconciliation collector

The reconciliation job must:

- run at least once daily during session;
- fetch the broader all-file-copy listing;
- fill any gaps missed by the daily collector;
- mark discrepancies for review.

## 9.3 Bill-status collector

For each newly discovered bill, and periodically for active bills, fetch the bill-status page and extract at minimum:

- bill title;
- committee;
- status link;
- procedural history snippet if available.

---

# 10. PDF extraction and normalization rules

## 10.1 Extraction order

1. Use PDF text extraction first.
2. Measure extraction quality.
3. Use OCR only if confidence falls below threshold.

## 10.2 Extraction confidence heuristic

Compute a provisional extraction confidence from:

- proportion of pages with non-trivial text;
- ratio of printable characters to whitespace/noise;
- presence of expected legislative patterns like `Section`, `Sec.`, `Effective`, `AN ACT CONCERNING`;
- absence of obvious OCR garbage.

Recommend threshold:

- `>= 0.80`: accept text extraction;
- `0.50-0.79`: accept with warning;
- `< 0.50`: force OCR fallback.

## 10.3 Cleaning rules

The normalization step must:

- preserve substantive capitalization;
- remove repeated page headers/footers if they recur across pages;
- remove stand-alone page numbers;
- repair common hyphenation line breaks;
- collapse repeated blank lines;
- preserve section boundaries and effective-date language;
- store both pre-clean and post-clean text.

## 10.4 Section parsing rules

The parser must identify, at minimum:

- `Section 1.` / `Sec. 1.` style headings;
- effective-date sections;
- repeal-and-substitute phrases;
- definition blocks;
- appropriation/funding blocks where present.

### Required behavior

- If formal section boundaries are found, split on them.
- If not found, fall back to paragraph chunking with deterministic chunk IDs.
- Never discard text because it does not fit a pattern.

## 10.5 Citation mapping rules

Every section must retain:

- start page;
- end page;
- character span;
- raw text snippet reference.

This is required so summaries and alerts can say, for example, â€œreview Section 4â€ rather than only vague narrative.

---

# 11. Diff engine contract

## 11.1 Comparison selection

For a current file copy, compare in this order:

1. prior file copy for the same bill;
2. if none, prior known bill text version;
3. if none, mark as first comparable version.

## 11.2 Section alignment strategy

1. exact match on section ID where possible;
2. fuzzy match on heading similarity;
3. fallback semantic similarity on section text;
4. if unmatched, classify as added or removed.

## 11.3 Similarity thresholds

Suggested defaults:

- `>= 0.98`: unchanged;
- `0.80-0.97`: modified;
- `< 0.80`: treat as heavily modified or unmatched depending on alignment context.

## 11.4 Deterministic change classification

Before invoking the LLM, the diff engine must attempt rule-based detection of:

- effective date changes;
- added or removed sections;
- presence of appropriation language;
- added or removed penalties;
- phrase changes indicating `shall` vs `may`;
- added or removed reporting language;
- added or removed references to the Attorney General;
- added or removed references to a private cause of action;
- added or removed references to regulations or rulemaking;
- added or removed licensing terms.

## 11.5 LLM-assisted change classification

Use the LLM only after the deterministic diff is available. The model may refine and explain changes, but it may not contradict obvious structural facts such as whether a section was added or removed.

---

# 12. Client-profile schema contract

Client profiles should be stored in YAML and rendered into both structured fields and a flattened embedding string.

## 12.1 Example YAML schema

```yaml
client_id: client_via
client_name: Via Transportation
is_active: true
alert_threshold: 78
_digest_threshold: 58
watched_bills:
  - SB00009
subject_priorities:
  transportation: 1.0
  municipalities: 0.8
  labor_employment: 0.4
change_flag_priorities:
  mandate_added: 1.0
  rulemaking_authority_added: 0.8
  funding_language_added: 0.7
agency_keywords:
  - Department of Transportation
  - DOT
  - OPM
committee_keywords:
  - Transportation Committee
positive_keywords:
  - microtransit
  - dial-a-ride
  - paratransit
  - transit district
  - mobility
negative_keywords:
  - hospital rate setting
  - cannabis establishment
entities_of_interest:
  - municipalities
  - transit providers
  - transportation network companies
notes_for_reasoning: >
  Client is highly sensitive to state-funded transit program structure,
  municipal transportation authority, labor classification spillover,
  procurement constraints, and pilot-program language.
```

## 12.2 Profile validation rules

- `client_id` is required and immutable once created.
- Thresholds must be integers from 0 to 100.
- Subject priorities and change-flag priorities must map only to approved enums.
- Empty profiles are invalid.

---

# 13. Relevance scoring contract

The final score should be a 0-100 scale.

## 13.1 Rules score

Start at `0` and add/subtract weights.

### Suggested baseline weights

#### Positive
- watched bill match: `+35`
- exact positive keyword in title: `+20`
- exact positive keyword in body: `+12`
- agency keyword match: `+12`
- committee keyword match: `+8`
- subject tag exact priority match: `priority * 18`
- change flag priority match: `priority * 20`
- funding/appropriation language present and client cares: `+10`
- immediate effective date or current FY implementation: `+8`

#### Negative
- negative keyword in title: `-25`
- negative keyword in body: `-15`
- excluded subject-area mismatch: `-20`
- low-confidence extraction: `-10`

Clamp rules score to `0-100`.

## 13.2 Embedding score

- Compute cosine similarity between bill representation and client profile representation.
- Map cosine similarity to a `0-100` scale.
- Recommended initial mapping: `embedding_score = max(0, min(100, (cosine - 0.55) * 222.22))`

This roughly means:
- `0.55` similarity => `0`
- `1.00` similarity => `100`

Tune later from actual feedback.

## 13.3 LLM score

Ask the model for a relevance score from `0-100` using only the structured bill summary, diff summary, subject tags, and client profile summary.

The model must also return 1-5 short reasons chosen from real content.

## 13.4 Final weighted score

Initial weighting:

```text
final_score = (0.50 * rules_score) + (0.20 * embedding_score) + (0.30 * llm_score)
```

## 13.5 Urgency mapping

```text
0-39   => low
40-59  => medium
60-79  => high
80-100 => critical
```

## 13.6 Alert disposition logic

- `final_score >= client.alert_threshold` => immediate alert
- `final_score >= client.digest_threshold` and below alert threshold => digest
- otherwise => no alert
- duplicates within cooldown window => suppressed duplicate

Recommended cooldown window:
- same client + same bill + same version + same suppression key: 24 hours

---

# 14. LLM prompt contracts

All prompts must request strict JSON and be validated. No markdown.

## 14.1 Subject-tagging prompt

### Inputs
- bill title
- bill metadata
- top extracted sections
- deterministic diff summary
- approved subject tags
- approved change flags

### Required output shape

```json
{
  "subject_tags": ["transportation"],
  "change_flags": ["mandate_added", "effective_date_changed"],
  "rationale": [
    "Creates duties for municipal transit operations.",
    "Changes implementation timing language."
  ],
  "tag_confidence": 0.86
}
```

### System prompt

```text
You are classifying a Connecticut legislative file copy.
Return valid JSON only.
You must choose subject_tags only from the approved subject tag list.
You must choose change_flags only from the approved change flag list.
Do not invent values.
Base your answer only on the provided bill metadata, extracted text, and deterministic diff summary.
If uncertain, return fewer tags, not more.
```

## 14.2 Internal-summary prompt

### Required output shape

```json
{
  "one_sentence_summary": "...",
  "deep_summary": "...",
  "key_sections_to_review": ["Section 2", "Section 5"],
  "practical_takeaways": [
    "Expands agency authority.",
    "Adds reporting obligations for affected entities."
  ],
  "confidence": 0.84
}
```

### System prompt

```text
You are generating an internal legislative review summary for a Connecticut lawyer-lobbyist.
Return valid JSON only.
Be specific, restrained, and non-hyperbolic.
Do not speculate beyond the text.
Explain what changed, why it matters, and what sections deserve review.
Ground every takeaway in the provided extracted text and change events.
```

## 14.3 Client-relevance prompt

### Required output shape

```json
{
  "llm_score": 74,
  "reasons": [
    "Touches municipal transportation authority.",
    "Adds implementation language that could affect providers.",
    "Matches the client's transportation and procurement profile."
  ]
}
```

### System prompt

```text
You are scoring strategic relevance of a Connecticut legislative file copy for a client profile.
Return valid JSON only.
Use only the structured bill summary, change events, subject tags, and client profile summary.
Do not rely on unstated assumptions.
Give a score from 0 to 100 and 1 to 5 short reasons.
A high score requires a concrete connection to the client's actual interests.
```

---

# 15. Telegram rendering contract

## 15.1 Immediate-alert template

```text
{urgency_emoji} {bill_number_display} | File {file_copy_number} | {urgency_upper}
{title}

Why flagged for {client_display_name}:
â€¢ {reason_1}
â€¢ {reason_2}
â€¢ {reason_3}

What changed:
{one_sentence_summary}

Review next:
{key_sections_to_review_line}

Links:
File copy: {file_copy_url}
Bill status: {bill_status_url}
```

## 15.2 Digest template

```text
Daily CGA File Copy Digest for {client_display_name}

{n} items crossed the digest threshold.

1. {bill_number_display} | File {file_copy_number}
{title}
Why flagged: {short_reason_line}
Links: file copy | bill status

2. ...
```

## 15.3 Emoji mapping

```text
low      => âšª
medium   => ðŸŸ¡
high     => ðŸŸ 
critical => ðŸ”´
```

## 15.4 Telegram constraints

- Escape content where necessary for the chosen Telegram parse mode.
- Truncate overlong messages gracefully.
- Include canonical URLs.
- Never send duplicate alerts for the same suppression key inside the cooldown window.

---

# 16. API contract

A minimal internal API is required for health checks, dashboard use, and manual reprocessing.

## 16.1 Required endpoints

### `GET /health`
Returns service status.

### `POST /jobs/collect/daily`
Triggers daily file-copy collection.

### `POST /jobs/collect/reconcile`
Triggers all-file-copy reconciliation.

### `POST /jobs/process/{canonical_version_id}`
Runs extraction, enrichment, diffing, scoring, summary, and alert logic for a specific version.

### `GET /bills/{bill_id}`
Returns bill metadata and latest versions.

### `GET /versions/{canonical_version_id}`
Returns extraction, sections, diff result, subject tags, summary, and client scores.

### `GET /alerts`
Returns recent alerts with filters.

### `POST /feedback`
Stores a feedback label.

---

# 17. Job orchestration contract

## 17.1 Required scheduled jobs

### During session
- daily collector every 20 minutes from 7:00 AM to 10:00 PM Eastern
- reconciliation collector once nightly
- digest sender once daily at configurable time

### Off session
- reduced collector cadence or disabled by configuration

## 17.2 Job chain for a new file copy

1. collect listing row
2. persist source metadata
3. create file-copy record
4. download PDF
5. extract text
6. normalize text
7. parse sections
8. fetch/enrich bill metadata
9. compute prior-version diff
10. run subject tagging
11. compute client scores
12. generate internal summary
13. decide alert disposition
14. send Telegram message if allowed
15. persist all artifacts and logs

---

# 18. Logging and audit contract

Every processing run must log:

- source URLs fetched;
- hash of source content;
- job start and end times;
- extraction method chosen;
- extraction confidence;
- prior version used for comparison;
- subject tags and change flags assigned;
- per-client score components;
- alert disposition;
- error traces if any.

Logs must be structured JSON in production.

---

# 19. Testing contract

## 19.1 Unit tests

Must cover:

- bill ID normalization;
- file-copy row parsing;
- PDF extraction confidence logic;
- header/footer stripping;
- section parsing;
- prior-version selection;
- rule-based change detection;
- scoring formulas;
- alert suppression logic;
- schema validation for all LLM outputs.

## 19.2 Regression fixtures

Maintain sample fixtures for at least:

- one clean text-based file copy;
- one poor-quality/OCR-required file copy;
- one bill with multiple file copies and meaningful changes;
- one bill with no prior comparable version;
- one bill that should not alert any client;
- one bill that should alert exactly one client;
- one bill that should go only to digest.

## 19.3 Acceptance tests

The system is acceptable for pilot use when it can:

1. ingest a full day of file copies without duplicate versions;
2. extract and section at least 95 percent of sample text cleanly;
3. produce a valid diff against the prior version for at least 90 percent of multi-version fixtures;
4. generate schema-valid subject tags, summaries, and client scores for all fixtures;
5. suppress duplicate alerts correctly;
6. produce human-credible summaries on at least 10 manually reviewed historical examples.

---

# 20. Initial implementation sequence for Codex

## 20.1 Pass 1: skeleton and schemas

Codex should first create:

- repo scaffold;
- config loader;
- database models;
- Pydantic schemas;
- YAML taxonomy files;
- placeholder job runner;
- tests for schema validation and ID normalization.

## 20.2 Pass 2: collectors and persistence

Then create:

- daily page collector;
- all-file-copy reconciliation collector;
- PDF downloader;
- persistence layer;
- idempotency guards.

## 20.3 Pass 3: extraction and parsing

Then create:

- PDF extraction service;
- OCR fallback;
- text cleaner;
- section parser;
- extraction confidence scoring;
- fixtures and tests.

## 20.4 Pass 4: diffing and enrichment

Then create:

- bill-status fetcher;
- prior-version resolver;
- section aligner;
- deterministic change detectors;
- diff persistence.

## 20.5 Pass 5: scoring, summaries, and alerts

Then create:

- rules engine;
- embeddings integration;
- LLM wrappers with schema validation;
- Telegram renderer and sender;
- suppression logic.

## 20.6 Pass 6: API and dashboard support

Then create:

- FastAPI endpoints;
- feedback endpoints;
- admin-oriented query views.

---

# 21. AGENTS.md draft

```md
# AGENTS.md

## Mission
Build a deterministic legislative monitoring system for CT General Assembly file copies.
Do not implement this as an autonomous chatbot.

## Build order
1. Schemas and config
2. Collectors and persistence
3. PDF extraction and section parsing
4. Metadata enrichment and version diffing
5. Subject tagging and client scoring
6. Summaries and Telegram alerts
7. API and dashboard support

## Rules
- Use Python 3.12+
- Use typed models everywhere
- Use Pydantic v2 for validation
- Fail fast on invalid LLM JSON
- Do not invent taxonomy values
- Preserve raw source artifacts
- Write tests with each major module
- Keep functions small and deterministic
- Prefer explicitness over cleverness

## Coding standards
- Ruff + black formatting
- SQLAlchemy or SQLModel ORM
- Alembic migrations
- Docstrings on public functions
- Structured logging

## LLM rules
- All prompts must request JSON only
- All JSON must be validated before persistence
- Never include full client names in prompts unless explicitly configured
- Prefer internal client IDs and abstracted interest summaries
```

---

# 22. First Codex execution prompt

```text
You are building a production-minded Python repository called ct-cga-filecopy-agent.
Read docs/build-spec.md and docs/technical-contract.md and implement the project in the required order.

Start with Pass 1 only:
- create the repository scaffold;
- create pyproject.toml;
- create typed settings loader;
- create Pydantic v2 schemas matching the technical contract;
- create SQLAlchemy/SQLModel models and Alembic setup for the required tables;
- create YAML taxonomy config files;
- create a Makefile with setup, lint, test, run-api, and run-worker targets;
- create tests for bill ID normalization, canonical version ID creation, and schema validation.

Do not implement scraping yet.
Do not implement LLM calls yet.
Do not skip tests.
Return a summary of files created, key design decisions, and any assumptions.
```

---

# 23. Second Codex execution prompt

```text
Now implement Pass 2 and Pass 3 from the technical contract.

Requirements:
- add the daily file-copy collector;
- add the all-file-copy reconciliation collector;
- persist raw source pages and parsed rows;
- add PDF download service with idempotency checks;
- add PDF text extraction with PyMuPDF first and OCR fallback second;
- add normalization and section parsing;
- add extraction confidence scoring;
- add fixtures and tests for at least one clean PDF and one OCR fallback path.

Do not add embeddings or LLM logic yet.
Do not add Telegram yet.
Preserve raw artifacts and write regression-friendly tests.
Return a summary of what works and what remains.
```

