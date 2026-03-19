"""Integration tests for repository layer with real DB operations."""

from pathlib import Path

from src.collectors.cga_daily_filecopies import parse_daily_filecopies_page
from src.db.repositories.bills import BillRepository
from src.db.repositories.file_copies import FileCopyRepository
from src.db.repositories.source_pages import SourcePageRepository

FIXTURE_PATH = (
    Path(__file__).parent.parent.parent / "data" / "fixtures" / "daily_filecopies_sample.html"
)


class TestPersistenceIntegration:
    def test_ingest_daily_page(self, db_session):
        """Full integration: parse HTML -> persist source page + bills + file copies."""
        html = FIXTURE_PATH.read_text()
        source_record, rows = parse_daily_filecopies_page(html, session_year=2026)

        # Persist source page
        source_repo = SourcePageRepository(db_session)
        source_page = source_repo.create(source_record)
        db_session.commit()
        assert source_page.id is not None

        # Persist bills and file copies
        bill_repo = BillRepository(db_session)
        fc_repo = FileCopyRepository(db_session)

        for row in rows:
            bill = bill_repo.upsert(
                session_year=row.session_year,
                bill_id=row.bill_id,
                title=row.bill_title,
            )
            fc, created = fc_repo.create_if_new(
                bill_db_id=bill.id,
                session_year=row.session_year,
                bill_id=row.bill_id,
                file_copy_number=row.file_copy_number,
                pdf_url=str(row.file_copy_pdf_url),
                listing_date=str(row.listing_date),
            )
            assert created is True

        db_session.commit()

        # Verify persistence
        sb93 = bill_repo.get_by_bill_id(2026, "SB00093")
        assert sb93 is not None
        assert "TRANSPORTATION" in sb93.current_title

    def test_idempotent_ingest(self, db_session):
        """Running the same ingest twice should not create duplicates."""
        html = FIXTURE_PATH.read_text()
        _, rows = parse_daily_filecopies_page(html, session_year=2026)

        bill_repo = BillRepository(db_session)
        fc_repo = FileCopyRepository(db_session)

        # First pass
        for row in rows:
            bill = bill_repo.upsert(2026, row.bill_id, row.bill_title)
            fc_repo.create_if_new(
                bill.id, 2026, row.bill_id, row.file_copy_number, str(row.file_copy_pdf_url)
            )
        db_session.commit()

        # Second pass (same data)
        for row in rows:
            bill = bill_repo.upsert(2026, row.bill_id, row.bill_title)
            _, created = fc_repo.create_if_new(
                bill.id, 2026, row.bill_id, row.file_copy_number, str(row.file_copy_pdf_url)
            )
            assert created is False  # Should not create duplicates

    def test_source_page_dedup(self, db_session):
        html = FIXTURE_PATH.read_text()
        source_record, _ = parse_daily_filecopies_page(html, session_year=2026)

        repo = SourcePageRepository(db_session)
        assert repo.exists_by_hash(source_record.content_sha256) is False

        repo.create(source_record)
        db_session.commit()

        assert repo.exists_by_hash(source_record.content_sha256) is True

    def test_prior_version_lookup(self, db_session):
        """Test finding prior version of a bill."""
        bill_repo = BillRepository(db_session)
        fc_repo = FileCopyRepository(db_session)

        bill = bill_repo.upsert(2026, "SB00093", "Test Bill")
        db_session.commit()

        fc_repo.create_if_new(bill.id, 2026, "SB00093", 31, "https://example.com/fc31.pdf")
        fc_repo.create_if_new(bill.id, 2026, "SB00093", 44, "https://example.com/fc44.pdf")
        db_session.commit()

        prior = fc_repo.get_prior_version(bill.id, 44)
        assert prior is not None
        assert prior.file_copy_number == 31

        # No prior for the first version
        no_prior = fc_repo.get_prior_version(bill.id, 31)
        assert no_prior is None
