"""Worker job runner — runs the pipeline on a schedule or one-shot."""

import logging
import sys

from config.settings import get_settings
from src.db.session import create_all_tables, get_session_factory
from src.pipeline.orchestrator import Pipeline
from src.utils.storage import LocalStorage

logger = logging.getLogger(__name__)


def run_daily_pipeline() -> int:
    """Run the daily collection pipeline. Returns count of processed entries."""
    settings = get_settings()
    create_all_tables(settings.database_url)

    session_factory = get_session_factory(settings.database_url)
    storage = LocalStorage(settings.storage_local_dir)

    with session_factory() as db_session:
        pipeline = Pipeline(
            db_session=db_session,
            storage=storage,
            session_year=settings.session_year,
        )
        results = pipeline.run_daily()

    logger.info("Daily pipeline completed: %d results", len(results))
    return len(results)


def run_reconciliation() -> int:
    """Run the reconciliation pipeline. Returns count of processed entries."""
    settings = get_settings()
    create_all_tables(settings.database_url)

    session_factory = get_session_factory(settings.database_url)
    storage = LocalStorage(settings.storage_local_dir)

    with session_factory() as db_session:
        pipeline = Pipeline(
            db_session=db_session,
            storage=storage,
            session_year=settings.session_year,
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
    else:
        print(f"Unknown command: {command}")
        print("Usage: python -m apps.worker.jobs [daily|reconcile]")
        sys.exit(1)


if __name__ == "__main__":
    main()
