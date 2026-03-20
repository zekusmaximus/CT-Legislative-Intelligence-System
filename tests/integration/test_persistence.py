"""Integration tests for repository layer with real DB operations."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pymupdf

from src.collectors.cga_daily_filecopies import parse_daily_filecopies_page
from src.db.models import BillDiff, BillSubjectTag, BillTextExtraction
from src.db.repositories.bills import BillRepository
from src.db.repositories.diffs import DiffRepository
from src.db.repositories.extractions import ExtractionRepository
from src.db.repositories.file_copies import FileCopyRepository
from src.db.repositories.sections import SectionRepository
from src.db.repositories.source_pages import SourcePageRepository
from src.db.repositories.subject_tags import SubjectTagRepository
from src.metadata.taxonomy import load_subject_tags
from src.pipeline.orchestrator import Pipeline
from src.utils.storage import LocalStorage

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


# ---------------------------------------------------------------------------
# Phase 1: Extraction, section, and diff persistence tests
# ---------------------------------------------------------------------------

DAILY_FIXTURE = (
    Path(__file__).parent.parent.parent / "data" / "fixtures" / "daily_filecopies_sample.html"
)


def _create_fake_pdf(text: str = "Section 1. AN ACT CONCERNING testing.") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text(pymupdf.Point(72, 72), text, fontsize=11)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _make_mock_fetcher(daily_html: str, pdf_bytes: bytes):
    fetcher = MagicMock()
    fetcher.fetch_html = MagicMock(side_effect=lambda url: (daily_html, 200))
    fetcher.fetch_pdf = MagicMock(side_effect=lambda url: (pdf_bytes, 200))
    return fetcher


class TestExtractionPersistence:
    def test_extraction_persisted_after_pipeline(self, db_session):
        """After running the pipeline, extraction records exist in DB."""
        daily_html = DAILY_FIXTURE.read_text()
        pdf_bytes = _create_fake_pdf(
            "Section 1. This act shall take effect July 1, 2026.\n"
            "The Commissioner of Transportation shall establish "
            "a municipal transit pilot program."
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            fetcher = _make_mock_fetcher(daily_html, pdf_bytes)
            pipeline = Pipeline(
                db_session=db_session, storage=storage,
                fetcher=fetcher, session_year=2026,
            )

            results = pipeline.run_daily()
            assert len(results) > 0

            canonical_id = results[0]["canonical_id"]
            extraction_repo = ExtractionRepository(db_session)
            extraction = extraction_repo.get_by_canonical_id(canonical_id)

            assert extraction is not None
            assert extraction.full_raw_text != ""
            assert extraction.full_cleaned_text != ""
            assert extraction.overall_extraction_confidence > 0

            # Pages were persisted
            pages = extraction_repo.get_pages(extraction.id)
            assert len(pages) > 0
            assert pages[0].page_number == 1
            assert pages[0].extraction_method in ("text", "ocr")

    def test_extraction_warnings_round_trip(self, db_session):
        """Extraction warnings survive JSON round-trip."""
        pdf_bytes = _create_fake_pdf("Section 1. Short text.")

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            pdf_path = storage.store_pdf(2026, "SB00050", 1, pdf_bytes)
            pipeline = Pipeline(db_session=db_session, storage=storage, session_year=2026)

            doc = pipeline.extract_document(pdf_path, "2026-SB00050-FC00001")
            assert doc is not None

            # Need a file_copy row for the FK
            bill_repo = BillRepository(db_session)
            bill = bill_repo.upsert(2026, "SB00050", "Warnings Test")
            fc_repo = FileCopyRepository(db_session)
            fc_repo.create_if_new(bill.id, 2026, "SB00050", 1, "http://example.com/t.pdf")
            db_session.commit()

            extraction_repo = ExtractionRepository(db_session)
            extraction_repo.save_extraction(doc)
            db_session.commit()

            fetched = extraction_repo.get_by_canonical_id("2026-SB00050-FC00001")
            assert fetched is not None
            if fetched.extraction_warnings_json:
                warnings = json.loads(fetched.extraction_warnings_json)
                assert isinstance(warnings, list)


class TestSectionPersistence:
    def test_sections_persisted_after_pipeline(self, db_session):
        """After pipeline, section records are queryable."""
        daily_html = DAILY_FIXTURE.read_text()
        pdf_bytes = _create_fake_pdf(
            "Section 1. Definitions.\n\n"
            "Section 2. This act shall take effect October 1, 2026."
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            fetcher = _make_mock_fetcher(daily_html, pdf_bytes)
            pipeline = Pipeline(
                db_session=db_session, storage=storage,
                fetcher=fetcher, session_year=2026,
            )

            results = pipeline.run_daily()
            assert len(results) > 0

            canonical_id = results[0]["canonical_id"]
            section_repo = SectionRepository(db_session)
            sections = section_repo.get_by_canonical_id(canonical_id)

            assert len(sections) > 0
            for s in sections:
                assert s.section_id != ""
                assert s.text != ""


class TestDiffPersistence:
    def test_diff_persisted_after_pipeline(self, db_session):
        """After pipeline, diff records are queryable."""
        daily_html = DAILY_FIXTURE.read_text()
        pdf_bytes = _create_fake_pdf(
            "Section 1. This act shall take effect July 1, 2026.\n"
            "The Commissioner of Transportation shall establish "
            "a municipal transit pilot program."
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            fetcher = _make_mock_fetcher(daily_html, pdf_bytes)
            pipeline = Pipeline(
                db_session=db_session, storage=storage,
                fetcher=fetcher, session_year=2026,
            )

            results = pipeline.run_daily()
            assert len(results) > 0

            canonical_id = results[0]["canonical_id"]
            diff_repo = DiffRepository(db_session)
            diff_row = diff_repo.get_by_version_id(canonical_id)

            assert diff_row is not None
            assert diff_row.compared_against in ("none", "prior_file_copy", "prior_bill_text")
            assert diff_row.sections_added >= 0

    def test_change_events_persisted(self, db_session):
        """Change events are stored alongside the diff."""
        daily_html = DAILY_FIXTURE.read_text()
        pdf_bytes = _create_fake_pdf(
            "Section 1. This act shall take effect July 1, 2026.\n"
            "The Commissioner shall establish regulations."
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            fetcher = _make_mock_fetcher(daily_html, pdf_bytes)
            pipeline = Pipeline(
                db_session=db_session, storage=storage,
                fetcher=fetcher, session_year=2026,
            )

            results = pipeline.run_daily()
            assert len(results) > 0

            canonical_id = results[0]["canonical_id"]
            diff_repo = DiffRepository(db_session)
            diff_row = diff_repo.get_by_version_id(canonical_id)
            assert diff_row is not None

            events = diff_repo.get_change_events(diff_row.id)
            assert isinstance(events, list)
            for event in events:
                assert event.change_flag != ""
                assert event.confidence > 0


class TestIdempotentExtractionAndDiff:
    def test_repeat_extraction_no_duplicates(self, db_session):
        """Processing the same document twice does not create duplicate extraction rows."""
        bill_repo = BillRepository(db_session)
        bill = bill_repo.upsert(2026, "HB00001", "Idempotent Test")
        fc_repo = FileCopyRepository(db_session)
        fc_repo.create_if_new(bill.id, 2026, "HB00001", 1, "http://example.com/t.pdf")
        db_session.commit()

        pdf_bytes = _create_fake_pdf("Section 1. AN ACT CONCERNING tests.")

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            pdf_path = storage.store_pdf(2026, "HB00001", 1, pdf_bytes)
            pipeline = Pipeline(db_session=db_session, storage=storage, session_year=2026)

            doc = pipeline.extract_document(pdf_path, "2026-HB00001-FC00001")
            assert doc is not None

            extraction_repo = ExtractionRepository(db_session)
            section_repo = SectionRepository(db_session)

            ext1 = extraction_repo.save_extraction(doc)
            sec1 = section_repo.save_sections(doc)
            db_session.commit()

            ext2 = extraction_repo.save_extraction(doc)
            sec2 = section_repo.save_sections(doc)
            db_session.commit()

            assert ext1.id == ext2.id
            assert len(sec1) == len(sec2)

            count = (
                db_session.query(BillTextExtraction)
                .filter_by(canonical_version_id="2026-HB00001-FC00001")
                .count()
            )
            assert count == 1

    def test_repeat_diff_no_duplicates(self, db_session):
        """Saving the same diff twice does not create duplicate rows."""
        bill_repo = BillRepository(db_session)
        bill = bill_repo.upsert(2026, "HB00002", "Diff Idempotent Test")
        fc_repo = FileCopyRepository(db_session)
        fc_repo.create_if_new(bill.id, 2026, "HB00002", 1, "http://example.com/t.pdf")
        db_session.commit()

        pdf_bytes = _create_fake_pdf("Section 1. Test content.")

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            pdf_path = storage.store_pdf(2026, "HB00002", 1, pdf_bytes)
            pipeline = Pipeline(db_session=db_session, storage=storage, session_year=2026)

            doc = pipeline.extract_document(pdf_path, "2026-HB00002-FC00001")
            assert doc is not None

            diff_result = pipeline.diff_version(doc, bill.id, 1)

            diff_repo = DiffRepository(db_session)
            d1 = diff_repo.save_diff(diff_result, bill.id)
            db_session.commit()

            d2 = diff_repo.save_diff(diff_result, bill.id)
            db_session.commit()

            assert d1.id == d2.id

            count = (
                db_session.query(BillDiff)
                .filter_by(current_version_id="2026-HB00002-FC00001")
                .count()
            )
            assert count == 1


# ---------------------------------------------------------------------------
# Phase 2: Subject tag persistence and metadata enrichment tests
# ---------------------------------------------------------------------------


class TestSubjectTagPersistence:
    def test_subject_tags_persisted_after_pipeline(self, db_session):
        """After pipeline, subject tags are stored in the DB."""
        daily_html = DAILY_FIXTURE.read_text()
        pdf_bytes = _create_fake_pdf(
            "Section 1. An act concerning transportation network companies "
            "and municipal transit pilot programs for highway and vehicle."
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            fetcher = _make_mock_fetcher(daily_html, pdf_bytes)
            pipeline = Pipeline(
                db_session=db_session, storage=storage,
                fetcher=fetcher, session_year=2026,
            )

            results = pipeline.run_daily()
            assert len(results) > 0

            canonical_id = results[0]["canonical_id"]
            tag_repo = SubjectTagRepository(db_session)
            tags = tag_repo.get_by_canonical_id(canonical_id)

            assert len(tags) > 0
            approved = load_subject_tags()
            for tag_row in tags:
                assert tag_row.subject_tag in approved
                assert tag_row.tag_confidence > 0

    def test_subject_tags_idempotent(self, db_session):
        """Saving tags for the same version twice does not create duplicates."""
        bill_repo = BillRepository(db_session)
        bill = bill_repo.upsert(2026, "HB00099", "Tag Idempotent Test")
        fc_repo = FileCopyRepository(db_session)
        fc_repo.create_if_new(bill.id, 2026, "HB00099", 1, "http://example.com/t.pdf")
        db_session.commit()

        from src.schemas.scoring import SubjectTagResult

        tag_result = SubjectTagResult(
            bill_id="HB00099",
            version_id="2026-HB00099-FC00001",
            subject_tags=["transportation", "education"],
            change_flags=[],
            tag_confidence=0.7,
            rationale=["transportation: matched kw1, kw2", "education: matched kw3, kw4"],
        )

        tag_repo = SubjectTagRepository(db_session)
        tags1 = tag_repo.save_tags(tag_result)
        db_session.commit()

        tags2 = tag_repo.save_tags(tag_result)
        db_session.commit()

        assert len(tags1) == len(tags2)
        count = (
            db_session.query(BillSubjectTag)
            .filter_by(canonical_version_id="2026-HB00099-FC00001")
            .count()
        )
        assert count == 2  # exactly 2 tags, not 4

    def test_all_pipeline_tags_are_canonical(self, db_session):
        """All tags emitted during a full pipeline run are in the approved vocabulary."""
        daily_html = DAILY_FIXTURE.read_text()
        pdf_bytes = _create_fake_pdf(
            "Section 1. An act concerning education school student teacher "
            "and health care hospital medical medicaid mental health "
            "and tax revenue assessment income tax "
            "and energy environment pollution climate conservation."
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            fetcher = _make_mock_fetcher(daily_html, pdf_bytes)
            pipeline = Pipeline(
                db_session=db_session, storage=storage,
                fetcher=fetcher, session_year=2026,
            )

            results = pipeline.run_daily()
            assert len(results) > 0

            approved = load_subject_tags()
            for result in results:
                tag_result = result["tags"]
                for tag in tag_result.subject_tags:
                    assert tag in approved, f"Pipeline emitted non-canonical tag: {tag}"


# ---------------------------------------------------------------------------
# Phase 3: Client scoring, alert decisioning, and suppression tests
# ---------------------------------------------------------------------------


class TestClientScorePersistence:
    def test_scores_persisted_after_pipeline(self, db_session, tmp_path):
        """After pipeline with client profiles, scores are stored in DB."""
        daily_html = DAILY_FIXTURE.read_text()
        pdf_bytes = _create_fake_pdf(
            "Section 1. This act shall take effect July 1, 2026.\n"
            "The Commissioner of Transportation shall establish "
            "a municipal transit pilot program for microtransit."
        )

        # Create a client profile in temp dir
        import yaml

        client_dir = tmp_path / "clients"
        client_dir.mkdir()
        profile_data = {
            "client_id": "test_transport",
            "client_name": "Test Transport Co",
            "is_active": True,
            "alert_threshold": 30,
            "digest_threshold": 20,
            "positive_keywords": ["transportation", "transit", "microtransit"],
            "subject_priorities": {"transportation": 1.0},
            "committee_keywords": ["Transportation Committee"],
            "watched_bills": [],
        }
        with open(client_dir / "test_transport.yaml", "w") as f:
            yaml.dump(profile_data, f)

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            fetcher = _make_mock_fetcher(daily_html, pdf_bytes)
            pipeline = Pipeline(
                db_session=db_session,
                storage=storage,
                fetcher=fetcher,
                session_year=2026,
                client_config_dir=client_dir,
            )

            results = pipeline.run_daily()
            assert len(results) > 0

            # Verify client scores were persisted
            from src.db.repositories.scores import ClientBillScoreRepository

            score_repo = ClientBillScoreRepository(db_session)
            canonical_id = results[0]["canonical_id"]
            scores = score_repo.get_scores_for_version(canonical_id)
            assert len(scores) > 0

            score_row = scores[0]
            assert score_row.rules_score > 0
            assert score_row.urgency in ("low", "medium", "high", "critical")
            assert score_row.alert_disposition in (
                "no_alert", "digest", "immediate",
                "suppressed_below_threshold", "suppressed_duplicate",
                "suppressed_cooldown",
            )
            assert score_row.reasons_json is not None

    def test_client_synced_to_db(self, db_session, tmp_path):
        """Client profiles are synced to the clients table."""
        import yaml
        from src.db.repositories.clients import ClientRepository

        client_dir = tmp_path / "clients"
        client_dir.mkdir()
        with open(client_dir / "test_c.yaml", "w") as f:
            yaml.dump({
                "client_id": "test_c",
                "client_name": "Test Corp",
                "is_active": True,
                "alert_threshold": 70,
                "digest_threshold": 50,
            }, f)

        daily_html = DAILY_FIXTURE.read_text()
        pdf_bytes = _create_fake_pdf("Section 1. Test content.")

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            fetcher = _make_mock_fetcher(daily_html, pdf_bytes)
            pipeline = Pipeline(
                db_session=db_session,
                storage=storage,
                fetcher=fetcher,
                session_year=2026,
                client_config_dir=client_dir,
            )
            pipeline.run_daily()

        client_repo = ClientRepository(db_session)
        client = client_repo.get_by_client_id("test_c")
        assert client is not None
        assert client.display_name == "Test Corp"
        assert client.alert_threshold == 70

    def test_score_idempotent(self, db_session):
        """Saving the same score twice does not create duplicates."""
        from src.db.models import ClientBillScore
        from src.db.repositories.clients import ClientRepository
        from src.db.repositories.scores import ClientBillScoreRepository
        from src.schemas.scoring import ClientScoreResult

        bill_repo = BillRepository(db_session)
        bill = bill_repo.upsert(2026, "HB00050", "Score Idempotent Test")
        fc_repo = FileCopyRepository(db_session)
        fc_repo.create_if_new(bill.id, 2026, "HB00050", 1, "http://example.com/t.pdf")

        client_repo = ClientRepository(db_session)
        client = client_repo.upsert("idempotent_c", "Idempotent Client")
        db_session.commit()

        score = ClientScoreResult(
            client_id="idempotent_c",
            bill_id="HB00050",
            version_id="2026-HB00050-FC00001",
            rules_score=65.0,
            final_score=65.0,
            urgency="high",
            should_alert=True,
            alert_disposition="immediate",
            match_reasons=[],
        )

        score_repo = ClientBillScoreRepository(db_session)
        s1 = score_repo.save_score(score, client.id, bill.id)
        db_session.commit()
        s2 = score_repo.save_score(score, client.id, bill.id)
        db_session.commit()

        assert s1.id == s2.id
        count = (
            db_session.query(ClientBillScore)
            .filter_by(
                client_id_fk=client.id,
                canonical_version_id="2026-HB00050-FC00001",
            )
            .count()
        )
        assert count == 1


class TestAlertPersistence:
    def test_alert_created_for_high_score(self, db_session, tmp_path):
        """High-scoring bills create alert records."""
        import yaml
        from src.db.repositories.alerts import AlertRepository

        client_dir = tmp_path / "clients"
        client_dir.mkdir()
        with open(client_dir / "alert_test.yaml", "w") as f:
            yaml.dump({
                "client_id": "alert_test",
                "client_name": "Alert Test",
                "is_active": True,
                "alert_threshold": 20,
                "digest_threshold": 10,
                "positive_keywords": ["transportation", "transit", "microtransit",
                                       "paratransit", "mobility"],
                "subject_priorities": {"transportation": 1.0},
                "watched_bills": [],
            }, f)

        daily_html = DAILY_FIXTURE.read_text()
        pdf_bytes = _create_fake_pdf(
            "Section 1. An act concerning transportation transit "
            "microtransit paratransit mobility network companies."
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            fetcher = _make_mock_fetcher(daily_html, pdf_bytes)
            pipeline = Pipeline(
                db_session=db_session,
                storage=storage,
                fetcher=fetcher,
                session_year=2026,
                client_config_dir=client_dir,
            )

            results = pipeline.run_daily()
            assert len(results) > 0

        alert_repo = AlertRepository(db_session)
        from src.db.repositories.clients import ClientRepository

        client = ClientRepository(db_session).get_by_client_id("alert_test")
        assert client is not None

        # Check for alert records
        from src.db.models import Alert

        alerts = db_session.query(Alert).filter_by(client_id_fk=client.id).all()
        assert len(alerts) > 0
        alert = alerts[0]
        assert alert.alert_text != ""
        assert alert.suppression_key != ""

    def test_duplicate_alert_suppressed(self, db_session):
        """Running scoring twice does not create duplicate alerts."""
        from src.db.models import Alert
        from src.db.repositories.alerts import AlertRepository
        from src.db.repositories.clients import ClientRepository

        bill_repo = BillRepository(db_session)
        bill = bill_repo.upsert(2026, "HB00060", "Dedup Alert Test")
        fc_repo = FileCopyRepository(db_session)
        fc_repo.create_if_new(bill.id, 2026, "HB00060", 1, "http://example.com/t.pdf")

        client_repo = ClientRepository(db_session)
        client = client_repo.upsert("dedup_c", "Dedup Client")
        db_session.commit()

        alert_repo = AlertRepository(db_session)
        key = "test_dedup_key_12345"

        a1 = alert_repo.create_alert(
            client_db_id=client.id,
            bill_db_id=bill.id,
            canonical_version_id="2026-HB00060-FC00001",
            urgency="high",
            alert_disposition="immediate",
            alert_text="Test alert",
            suppression_key=key,
        )
        db_session.commit()

        a2 = alert_repo.create_alert(
            client_db_id=client.id,
            bill_db_id=bill.id,
            canonical_version_id="2026-HB00060-FC00001",
            urgency="high",
            alert_disposition="immediate",
            alert_text="Test alert",
            suppression_key=key,
        )
        db_session.commit()

        assert a1.id == a2.id
        count = db_session.query(Alert).filter_by(suppression_key=key).count()
        assert count == 1

    def test_suppression_key_check(self, db_session):
        """has_suppression_key returns correct boolean."""
        from src.db.repositories.alerts import AlertRepository
        from src.db.repositories.clients import ClientRepository

        bill_repo = BillRepository(db_session)
        bill = bill_repo.upsert(2026, "HB00070", "Suppression Test")
        fc_repo = FileCopyRepository(db_session)
        fc_repo.create_if_new(bill.id, 2026, "HB00070", 1, "http://example.com/t.pdf")
        client_repo = ClientRepository(db_session)
        client = client_repo.upsert("supp_c", "Supp Client")
        db_session.commit()

        alert_repo = AlertRepository(db_session)
        key = "suppression_test_key"

        assert alert_repo.has_suppression_key(key) is False

        alert_repo.create_alert(
            client_db_id=client.id,
            bill_db_id=bill.id,
            canonical_version_id="2026-HB00070-FC00001",
            urgency="medium",
            alert_disposition="digest",
            alert_text="Test",
            suppression_key=key,
        )
        db_session.commit()

        assert alert_repo.has_suppression_key(key) is True


class TestBillStatusEnrichment:
    def test_enrich_updates_bill_record(self, db_session):
        """Bill status enrichment updates committee name on the bill record."""
        bill_repo = BillRepository(db_session)
        bill = bill_repo.upsert(2026, "SB00093", "Test Transportation Bill")
        db_session.commit()

        # Mock a fetcher that returns a simple bill status page
        status_html = """
        <html><body>
        <div class="billtitleheader">AN ACT CONCERNING TRANSPORTATION</div>
        <table><tr>
            <td><b>Referred to Joint Committee on</b></td>
            <td>Transportation</td>
        </tr></table>
        </body></html>
        """
        fetcher = MagicMock()
        fetcher.fetch_html = MagicMock(return_value=(status_html, 200))

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            pipeline = Pipeline(
                db_session=db_session, storage=storage,
                fetcher=fetcher, session_year=2026,
            )
            metadata = pipeline.enrich_bill_status("SB00093", 2026)

        # Bill record should have status_url set
        updated_bill = bill_repo.get_by_bill_id(2026, "SB00093")
        assert updated_bill.bill_status_url is not None
