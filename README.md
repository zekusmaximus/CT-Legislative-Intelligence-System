# CT Legislative Intelligence System

A production-minded, deterministic monitoring system for Connecticut General Assembly file copies.

## What this repository is for

This application is intended to:
- collect new CT General Assembly file copies,
- download and preserve raw legislative artifacts,
- extract and normalize bill text,
- diff new file copies against prior versions,
- score relevance against structured client-interest profiles,
- generate internal summaries and Telegram alerts, and
- retain enough structured data for audit and later review.

This repository is **not** intended to become a free-form chatbot. The priority is a deterministic legislative pipeline with tightly controlled use of LLM features.

## Current status

The repository already contains a meaningful prototype foundation:
- typed settings and schemas,
- SQLAlchemy models for the core entities,
- collectors for daily/session file-copy pages and bill status pages,
- PDF download and extraction utilities,
- section parsing and basic diffing,
- simplified scoring and summary generation,
- a narrow orchestrated pipeline exercised by tests.

However, the repository is **not yet an internal MVP**. The highest-priority gaps are:
- Alembic revision history,
- persistence for extraction/diff/scoring/alert artifacts,
- contract-compliant controlled vocabularies at runtime,
- validated client-profile loading and deterministic alert decisions,
- Telegram sending and suppression logic,
- internal operational API endpoints beyond health.

## Source of truth documents

Start with these documents before making major changes:
- `PLAN.md` - the current phased implementation plan for MVP.
- `docs/production-readiness-review.md` - detailed gap analysis and tranche recommendation.
- `docs/build-spec.md` - product scope, MVP boundaries, and delivery phases.
- `docs/technical-contract.md` - normative contract for schemas, enums, storage, APIs, and pipeline behavior.
- `AGENTS.md` - agent-specific guardrails for working in this repository.

## Recommended next build tranche

The next build tranche is:

1. create the initial Alembic migration,
2. persist extraction and diff artifacts,
3. make persisted version outputs queryable via API, and
4. prove the flow with integration tests.

See `PLAN.md` for the full phased roadmap.
