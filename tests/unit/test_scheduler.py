"""Unit tests for the scheduler configuration."""

import os
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("APP_ENV", "development")

from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo

from apps.worker.scheduler import create_scheduler


_ET = ZoneInfo("America/New_York")


class TestSchedulerConfiguration:
    @patch("apps.worker.scheduler.get_settings")
    def test_scheduler_creates_jobs(self, mock_settings):
        mock_settings.return_value = MagicMock(
            cga_poll_interval_minutes=20,
        )
        scheduler = create_scheduler()

        jobs = scheduler.get_jobs()
        job_ids = {j.id for j in jobs}
        assert "daily_collection" in job_ids
        assert "digest_delivery" in job_ids

    @patch("apps.worker.scheduler.get_settings")
    def test_scheduler_uses_configured_interval(self, mock_settings):
        mock_settings.return_value = MagicMock(
            cga_poll_interval_minutes=30,
        )
        scheduler = create_scheduler()

        daily_job = scheduler.get_job("daily_collection")
        assert daily_job is not None
        # The trigger interval should be 30 minutes
        assert daily_job.trigger.interval.total_seconds() == 30 * 60


class TestSchedulerHardening:
    """Verify timezone, overlap, and safety controls."""

    @patch("apps.worker.scheduler.get_settings")
    def test_scheduler_timezone_is_eastern(self, mock_settings):
        mock_settings.return_value = MagicMock(cga_poll_interval_minutes=20)
        scheduler = create_scheduler()
        assert str(scheduler.timezone) == "America/New_York"

    @patch("apps.worker.scheduler.get_settings")
    def test_digest_trigger_timezone_is_eastern(self, mock_settings):
        mock_settings.return_value = MagicMock(cga_poll_interval_minutes=20)
        scheduler = create_scheduler()

        digest_job = scheduler.get_job("digest_delivery")
        assert digest_job is not None
        trigger = digest_job.trigger
        assert str(trigger.timezone) == "America/New_York"

    @patch("apps.worker.scheduler.get_settings")
    def test_digest_fires_at_6pm_weekdays(self, mock_settings):
        mock_settings.return_value = MagicMock(cga_poll_interval_minutes=20)
        scheduler = create_scheduler()

        digest_job = scheduler.get_job("digest_delivery")
        trigger = digest_job.trigger

        # APScheduler CronTrigger fields
        # hour and day_of_week are CronExpression objects
        assert str(trigger.fields[5]) == "18"  # hour field
        assert str(trigger.fields[4]) == "mon-fri"  # day_of_week

    @patch("apps.worker.scheduler.get_settings")
    def test_max_instances_prevents_overlap(self, mock_settings):
        mock_settings.return_value = MagicMock(cga_poll_interval_minutes=20)
        scheduler = create_scheduler()

        daily_job = scheduler.get_job("daily_collection")
        digest_job = scheduler.get_job("digest_delivery")

        assert daily_job.max_instances == 1
        assert digest_job.max_instances == 1
