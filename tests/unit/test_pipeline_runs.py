"""Unit tests for PipelineRun audit records and repository."""

from src.db.models import PipelineRun
from src.db.repositories.pipeline_runs import PipelineRunRepository


class TestPipelineRunRepository:
    def test_start_run(self, db_session):
        repo = PipelineRunRepository(db_session)
        run = repo.start_run("daily")
        db_session.commit()

        assert run.id is not None
        assert run.run_type == "daily"
        assert run.status == "running"
        assert run.entries_collected == 0
        assert run.entries_processed == 0

    def test_complete_run(self, db_session):
        repo = PipelineRunRepository(db_session)
        run = repo.start_run("daily")
        db_session.flush()

        updated = repo.complete_run(
            run.id,
            entries_collected=10,
            entries_processed=8,
            entries_failed=2,
            alerts_sent=3,
        )
        db_session.commit()

        assert updated.status == "completed"
        assert updated.entries_collected == 10
        assert updated.entries_processed == 8
        assert updated.entries_failed == 2
        assert updated.alerts_sent == 3
        assert updated.finished_at is not None

    def test_fail_run(self, db_session):
        repo = PipelineRunRepository(db_session)
        run = repo.start_run("reconciliation")
        db_session.flush()

        updated = repo.fail_run(run.id, "Connection timeout")
        db_session.commit()

        assert updated.status == "failed"
        assert updated.error_message == "Connection timeout"
        assert updated.finished_at is not None

    def test_get_by_id(self, db_session):
        repo = PipelineRunRepository(db_session)
        run = repo.start_run("single")
        db_session.commit()

        found = repo.get_by_id(run.id)
        assert found is not None
        assert found.run_type == "single"

    def test_get_by_id_not_found(self, db_session):
        repo = PipelineRunRepository(db_session)
        assert repo.get_by_id(999) is None

    def test_get_recent(self, db_session):
        repo = PipelineRunRepository(db_session)
        for i in range(5):
            repo.start_run("daily")
        db_session.commit()

        recent = repo.get_recent(limit=3)
        assert len(recent) == 3

    def test_complete_run_nonexistent(self, db_session):
        repo = PipelineRunRepository(db_session)
        result = repo.complete_run(999)
        assert result is None

    def test_fail_run_nonexistent(self, db_session):
        repo = PipelineRunRepository(db_session)
        result = repo.fail_run(999, "error")
        assert result is None
