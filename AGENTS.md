# AGENTS.md

## Mission
Build a deterministic legislative monitoring system for CT General Assembly file copies.
Do not implement this as an autonomous chatbot.

## Current MVP priority order
1. Persistence and Alembic migrations
2. Metadata enrichment and controlled vocabularies
3. Deterministic client scoring and alert decision persistence
4. Telegram sending and suppression logic
5. Internal API and scheduler support
6. Hardening, regression coverage, and post-MVP intelligence layers

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
- SQLAlchemy ORM
- Alembic migrations
- Structured logging

## LLM rules
- All prompts must request JSON only
- All JSON must be validated before persistence
- Never include full client names in prompts unless explicitly configured
- Prefer internal client IDs and abstracted interest summaries

## Agent workflow guidance
- Read `PLAN.md` before starting any major implementation tranche.
- Use `docs/production-readiness-review.md` to understand why MVP priorities are ordered the way they are.
- Treat embeddings, broader LLM reasoning, and dashboard work as post-MVP unless the task explicitly requires them.
- Favor narrow, test-backed increments that make the system more queryable, auditable, and deterministic.
