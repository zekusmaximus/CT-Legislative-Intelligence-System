"""Session-aware scheduler for pipeline jobs.

Runs daily collection on a configurable interval and digest delivery
at a fixed time (US/Eastern). Respects session-aware cadence: during
legislative session, polling is more frequent.
"""

import logging
import sys
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

# CT General Assembly operates in US/Eastern
_ET = ZoneInfo("America/New_York")

from config.settings import get_settings
from src.alerts.telegram_sender import TelegramSender
from src.db.session import get_session_factory
from src.pipeline.orchestrator import Pipeline
from src.utils.storage import LocalStorage

logger = logging.getLogger(__name__)


def _make_pipeline(settings=None):
    """Create a configured Pipeline instance with a fresh DB session."""
    if settings is None:
        settings = get_settings()

    session_factory = get_session_factory(settings.database_url)
    session = session_factory()
    storage = LocalStorage(settings.storage_local_dir)

    telegram_sender = None
    if settings.telegram_available and settings.telegram_alerts_enabled:
        telegram_sender = TelegramSender(
            bot_token=settings.telegram_bot_token,
            default_chat_id=settings.telegram_chat_id,
            session=session,
        )

    return Pipeline(
        db_session=session,
        storage=storage,
        session_year=settings.session_year,
        telegram_sender=telegram_sender,
    ), session


def scheduled_daily_collection():
    """Job: run the daily collection pipeline."""
    logger.info("Scheduled daily collection starting at %s", datetime.now(UTC).isoformat())
    try:
        pipeline, session = _make_pipeline()
        try:
            results = pipeline.run_daily()
            logger.info("Scheduled daily collection complete: %d entries", len(results))
        finally:
            session.close()
    except Exception:
        logger.exception("Scheduled daily collection failed")


def scheduled_digest_delivery():
    """Job: deliver pending digest alerts."""
    logger.info("Scheduled digest delivery starting at %s", datetime.now(UTC).isoformat())
    try:
        settings = get_settings()
        if not (settings.telegram_available and settings.telegram_alerts_enabled):
            logger.info("Telegram not configured, skipping digest delivery")
            return

        session_factory = get_session_factory(settings.database_url)
        session = session_factory()
        try:
            from src.db.repositories.alerts import AlertRepository
            from src.db.repositories.clients import ClientRepository

            client_repo = ClientRepository(session)
            alert_repo = AlertRepository(session)

            sender = TelegramSender(
                bot_token=settings.telegram_bot_token,
                default_chat_id=settings.telegram_chat_id,
                session=session,
            )

            clients = client_repo.get_active_clients()
            total_sent = 0
            for client in clients:
                digests = alert_repo.get_unsent_digests(client.id)
                if digests:
                    success = sender.send_digest(
                        digests, client.display_name or client.client_id
                    )
                    session.commit()
                    if success:
                        total_sent += len(digests)

            logger.info("Digest delivery complete: %d alerts sent", total_sent)
        finally:
            session.close()
    except Exception:
        logger.exception("Scheduled digest delivery failed")


def create_scheduler() -> BlockingScheduler:
    """Create and configure the APScheduler instance."""
    settings = get_settings()
    scheduler = BlockingScheduler(timezone=_ET)

    poll_minutes = settings.cga_poll_interval_minutes

    # Daily collection on interval — max_instances=1 prevents overlap
    # if a run takes longer than the interval.
    scheduler.add_job(
        scheduled_daily_collection,
        trigger=IntervalTrigger(minutes=poll_minutes),
        id="daily_collection",
        name="Daily file copy collection",
        max_instances=1,
        replace_existing=True,
    )

    # Digest delivery at 6pm ET on weekdays — explicit timezone
    scheduler.add_job(
        scheduled_digest_delivery,
        trigger=CronTrigger(
            hour=18, minute=0, day_of_week="mon-fri", timezone=_ET
        ),
        id="digest_delivery",
        name="Evening digest delivery",
        max_instances=1,
        replace_existing=True,
    )

    logger.info(
        "Scheduler configured: collection every %d min, digest at 18:00 ET weekdays",
        poll_minutes,
    )
    return scheduler


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    settings = get_settings()

    scheduler = create_scheduler()
    logger.info("Starting scheduler...")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler shutting down")
        scheduler.shutdown()


if __name__ == "__main__":
    main()
