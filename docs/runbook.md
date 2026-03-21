# Operational Runbook — CT Legislative Intelligence System

## Quick reference

| Endpoint | Purpose |
|---|---|
| `GET /health` | Basic health check (DB connectivity) |
| `GET /monitoring/health` | Full system health with error budgets |
| `GET /runs` | Recent pipeline run audit trail |
| `GET /alerts?delivery_status=failed` | Failed alert deliveries |
| `GET /review/version/{id}` | Full artifact review for a version |
| `POST /jobs/collect/daily` | Trigger daily collection |
| `POST /jobs/process/{id}` | Reprocess a single version |
| `POST /feedback` | Capture operator feedback |

---

## First startup checklist

1. Create `.env` from `.env.example` and set `DATABASE_URL` before starting any process.
2. Run `alembic upgrade head` against that `DATABASE_URL`.
3. Start the API locally: `uvicorn apps.api.main:app --host 127.0.0.1 --port 8000`.
4. Start the scheduler: `python -m apps.worker.jobs scheduler`.

Runtime startup no longer calls `create_all()`. If migrations have not been applied, the API and worker processes should fail rather than silently create a partial schema.

---

## Error budget targets

| Metric | Target | Window |
|---|---|---|
| Pipeline run failure rate | ≤ 5% | Rolling 24h |
| Alert delivery failure rate | ≤ 2% | Rolling 24h |
| Average extraction confidence | ≥ 0.80 | All time |

Check `GET /monitoring/health` → `error_budget.healthy` for a single boolean.

---

## Common operational scenarios

### 1. Pipeline not running / stale data

**Symptoms**: `hours_since_last_run > 2.0` in health check, status = "degraded".

**Diagnosis**:
```bash
# Check scheduler is running
python -m apps.worker.jobs scheduler

# Check recent runs
curl localhost:8000/runs | jq '.[0]'
```

**Resolution**:
- If scheduler crashed: restart the worker process
- If CGA site is down: check `https://www.cga.ct.gov` — the fetcher will retry on next poll
- Manual trigger: `POST /jobs/collect/daily`

### 2. Alert delivery failures

**Symptoms**: `failed_alerts > 0` in health check, alerts with `delivery_status=failed`.

**Diagnosis**:
```bash
curl "localhost:8000/alerts?delivery_status=failed" | jq '.[] | {id, bill_id, delivery_attempts}'
```

**Resolution**:
- Check Telegram bot token is valid: `TELEGRAM_BOT_TOKEN` env var
- Check chat ID: `TELEGRAM_CHAT_ID` env var
- Reprocess the version to retry `failed` or `pending` delivery: `POST /jobs/process/{canonical_version_id}`
- Telegram rate limits: alerts are sent with retry (max 3 attempts)
- Already-sent alerts remain duplicate-suppressed and will not be resent on reprocess

### 3. Low extraction confidence

**Symptoms**: `avg_extraction_confidence < 0.80`, `extraction_below_target = true`.

**Diagnosis**:
```bash
# Find low-confidence versions
curl "localhost:8000/runs" | jq '.[] | select(.entries_failed > 0)'
```

**Resolution**:
- Low confidence is usually from scanned PDFs. The system will attempt OCR fallback automatically when confidence < 0.50.
- If Tesseract is not installed: `pip install pytesseract` and ensure `tesseract` is on PATH
- Some CGA PDFs are genuinely low quality — these are tracked with warnings but still processed

### 4. Duplicate alert suppression

**Symptoms**: Operator expects an alert but none was sent.

**Diagnosis**:
```bash
# Check the version's review data
curl "localhost:8000/review/version/2026-SB00093-FC00044" | jq '.alerts'
```

Look at the `disposition` field:
- `immediate` — sent during normal processing if Telegram delivery is enabled
- `digest` — queued for the scheduled digest batch rather than sent immediately
- `suppressed_duplicate` — same client+version was already sent
- `suppressed_cooldown` — another version of the same bill alerted within 24h
- `suppressed_below_threshold` — score didn't meet the client's threshold

**Resolution**:
- Duplicate/cooldown suppressions are working as designed
- If the threshold is too high: edit the client YAML in `config/clients/` and lower `alert_threshold`
- Reprocessing can retry alerts that are still `pending` or `failed`, but it will not resend alerts already marked `sent`

### 5. Wrong or missing subject tags

**Symptoms**: Bill should be tagged with a subject but isn't.

**Diagnosis**:
```bash
curl "localhost:8000/review/version/{id}" | jq '.subject_tags'
```

**Resolution**:
- Subject tagging requires ≥2 keyword hits. Check `src/scoring/subject_tagger.py` → `SUBJECT_KEYWORDS` for the keyword list.
- If a subject needs more keywords: add them to the `SUBJECT_KEYWORDS` dict (must match `config/taxonomy.subjects.yaml`).
- Reprocess: `POST /jobs/process/{id}`

### 6. Database issues

**Symptoms**: `GET /health` returns `database: "unreachable"`.

**Resolution**:
- Check `DATABASE_URL` environment variable
- For SQLite (dev): ensure the directory exists
- For PostgreSQL (prod): check the connection string and that the server is running
- Run migrations: `alembic upgrade head`
- API, scheduler, and worker startup no longer auto-create schema objects

---

## Scheduled jobs

| Job | Schedule | Description |
|---|---|---|
| Daily collection | Every 20 min (configurable) | Polls CGA for new file copies |
| Digest delivery | 6 PM ET weekdays | Sends batched digest alerts |

Start the scheduler:
```bash
python -m apps.worker.jobs scheduler
```

Current scheduler behavior now uses explicit Eastern timezone handling and `max_instances=1` on both jobs. Before broader beta use, add `coalesce` and misfire handling and consider whether a stronger lock is needed for multi-process deployment.

---

## Key configuration

| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | Database connection | (required) |
| `TELEGRAM_BOT_TOKEN` | Telegram bot API token | (empty) |
| `TELEGRAM_CHAT_ID` | Telegram chat for alerts | (empty) |
| `TELEGRAM_ALERTS_ENABLED` | Enable alert delivery | `false` |
| `CGA_POLL_INTERVAL_MINUTES` | Polling frequency | `20` |
| `LOG_LEVEL` | Logging verbosity | `INFO` |
| `OCR_ENABLED` | Enable Tesseract OCR fallback | `true` |
| `SESSION_YEAR` | Legislative session year | `2026` |

---

## Feedback loop

Operators can submit feedback on alert decisions to capture ground truth for future scoring calibration:

```bash
curl -X POST localhost:8000/feedback \
  -H "Content-Type: application/json" \
  -d '{"client_id": "client_via", "bill_id": "SB00093", "canonical_version_id": "2026-SB00093-FC00044", "label": "relevant", "notes": "This bill directly affects our operations"}'
```

Feedback is stored in the `feedback_labels` table for future calibration passes.
