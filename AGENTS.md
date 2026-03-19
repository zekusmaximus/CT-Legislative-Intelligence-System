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
- SQLAlchemy ORM
- Alembic migrations
- Structured logging

## LLM rules
- All prompts must request JSON only
- All JSON must be validated before persistence
- Never include full client names in prompts unless explicitly configured
- Prefer internal client IDs and abstracted interest summaries
