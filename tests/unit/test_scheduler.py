"""Unit tests for the scheduler configuration."""

import os
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("APP_ENV", "development")

from unittest.mock import patch, MagicMock

from apps.worker.scheduler import create_scheduler


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
