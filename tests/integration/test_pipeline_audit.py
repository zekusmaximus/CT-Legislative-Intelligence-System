"""Integration tests for pipeline run audit tracking."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.db.models import PipelineRun
from src.db.repositories.pipeline_runs import PipelineRunRepository
from src.pipeline.orchestrator import Pipeline
from src.utils.storage import LocalStorage


class TestPipelineRunAudit:
    def test_daily_run_creates_audit_record(self, db_session, tmp_path):
        """A daily run that finds no new pages still creates a completed audit record."""
        storage = LocalStorage(tmp_path)
        fetcher = MagicMock()
        # Return empty page so no work is done
        fetcher.fetch_html.return_value = ("", 404)

        pipeline = Pipeline(
            db_session=db_session,
            storage=storage,
            fetcher=fetcher,
            session_year=2026,
        )
        results = pipeline.run_daily()
        assert results == []

        # Should have one completed run record
        runs = db_session.query(PipelineRun).all()
        assert len(runs) == 1
        assert runs[0].run_type == "daily"
        assert runs[0].status == "completed"
        assert runs[0].entries_collected == 0

    def test_single_version_not_found(self, db_session, tmp_path):
        """Processing a non-existent version returns None."""
        storage = LocalStorage(tmp_path)
        pipeline = Pipeline(
            db_session=db_session,
            storage=storage,
            session_year=2026,
        )
        result = pipeline.process_single_version("2026-NOEXIST-FC00001")
        assert result is None

    def test_reconciliation_run_creates_audit_record(self, db_session, tmp_path):
        """A reconciliation run creates a completed audit record."""
        storage = LocalStorage(tmp_path)
        fetcher = MagicMock()
        fetcher.fetch_html.return_value = ("", 404)

        pipeline = Pipeline(
            db_session=db_session,
            storage=storage,
            fetcher=fetcher,
            session_year=2026,
        )
        results = pipeline.run_reconciliation()
        assert results == []

        runs = db_session.query(PipelineRun).all()
        assert len(runs) == 1
        assert runs[0].run_type == "reconciliation"
        assert runs[0].status == "completed"

    def test_multiple_runs_tracked_independently(self, db_session, tmp_path):
        """Each pipeline invocation gets its own audit record."""
        storage = LocalStorage(tmp_path)
        fetcher = MagicMock()
        fetcher.fetch_html.return_value = ("", 404)

        pipeline = Pipeline(
            db_session=db_session,
            storage=storage,
            fetcher=fetcher,
            session_year=2026,
        )
        pipeline.run_daily()
        pipeline.run_daily()

        runs = db_session.query(PipelineRun).all()
        assert len(runs) == 2
        assert all(r.status == "completed" for r in runs)

    def test_failed_run_records_error(self, db_session, tmp_path):
        """If the pipeline raises, the run is marked failed with the error."""
        storage = LocalStorage(tmp_path)
        fetcher = MagicMock()
        fetcher.fetch_html.side_effect = RuntimeError("Network error")

        pipeline = Pipeline(
            db_session=db_session,
            storage=storage,
            fetcher=fetcher,
            session_year=2026,
        )

        try:
            pipeline.run_daily()
        except RuntimeError:
            pass

        runs = db_session.query(PipelineRun).all()
        assert len(runs) == 1
        assert runs[0].status == "failed"
        assert "Network error" in runs[0].error_message
