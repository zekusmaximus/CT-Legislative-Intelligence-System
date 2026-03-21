"""Worker job runner — runs the pipeline on a schedule or one-shot.

Both daily and reconciliation commands wire up TelegramSender when
configured, so one-shot runs can deliver immediate alerts end-to-end.
"""

import logging
import sys

from config.settings import get_settings
from src.alerts.telegram_sender import TelegramSender
from src.db.session import get_session_factory
from src.pipeline.orchestrator import Pipeline
from src.utils.storage import LocalStorage

logger = logging.getLogger(__name__)


def _make_telegram_sender(settings, session):
    """Create a TelegramSender if Telegram is configured, else None."""
    if settings.telegram_available and settings.telegram_alerts_enabled:
        return TelegramSender(
            bot_token=settings.telegram_bot_token,
            default_chat_id=settings.telegram_chat_id,
            session=session,
        )
    return None


def run_daily_pipeline() -> int:
    """Run the daily collection pipeline. Returns count of processed entries."""
    settings = get_settings()

    session_factory = get_session_factory(settings.database_url)
    storage = LocalStorage(settings.storage_local_dir)

    with session_factory() as db_session:
        pipeline = Pipeline(
            db_session=db_session,
            storage=storage,
            session_year=settings.session_year,
            telegram_sender=_make_telegram_sender(settings, db_session),
        )
        results = pipeline.run_daily()

    logger.info("Daily pipeline completed: %d results", len(results))
    return len(results)


def run_reconciliation() -> int:
    """Run the reconciliation pipeline. Returns count of processed entries."""
    settings = get_settings()

    session_factory = get_session_factory(settings.database_url)
    storage = LocalStorage(settings.storage_local_dir)

    with session_factory() as db_session:
        pipeline = Pipeline(
            db_session=db_session,
            storage=storage,
            session_year=settings.session_year,
            telegram_sender=_make_telegram_sender(settings, db_session),
        )
        results = pipeline.run_reconciliation()

    logger.info("Reconciliation completed: %d results", len(results))
    return len(results)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    command = sys.argv[1] if len(sys.argv) > 1 else "daily"

    if command == "daily":
        count = run_daily_pipeline()
        print(f"Daily pipeline: processed {count} entries")
    elif command == "reconcile":
        count = run_reconciliation()
        print(f"Reconciliation: processed {count} entries")
    elif command == "scheduler":
        from apps.worker.scheduler import main as scheduler_main
        scheduler_main()
    else:
        print(f"Unknown command: {command}")
        print("Usage: python -m apps.worker.jobs [daily|reconcile|scheduler]")
        sys.exit(1)


if __name__ == "__main__":
    main()
