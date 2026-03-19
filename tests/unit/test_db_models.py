"""Tests for SQLAlchemy model creation and basic persistence."""

from src.db.models import Bill, Client, FileCopy


class TestBillModel:
    def test_create_bill(self, db_session):
        bill = Bill(
            session_year=2026,
            bill_id="SB00093",
            chamber="senate",
            bill_number_numeric=93,
            current_title="AN ACT CONCERNING TRANSPORTATION",
        )
        db_session.add(bill)
        db_session.commit()

        result = db_session.query(Bill).filter_by(bill_id="SB00093").first()
        assert result is not None
        assert result.chamber == "senate"
        assert result.bill_number_numeric == 93

    def test_unique_constraint(self, db_session):
        bill1 = Bill(
            session_year=2026,
            bill_id="SB00093",
            chamber="senate",
            bill_number_numeric=93,
            current_title="Title 1",
        )
        bill2 = Bill(
            session_year=2026,
            bill_id="SB00093",
            chamber="senate",
            bill_number_numeric=93,
            current_title="Title 2",
        )
        db_session.add(bill1)
        db_session.commit()
        db_session.add(bill2)
        try:
            db_session.commit()
            assert False, "Should have raised integrity error"
        except Exception:
            db_session.rollback()


class TestFileCopyModel:
    def test_create_with_bill(self, db_session):
        bill = Bill(
            session_year=2026,
            bill_id="HB05140",
            chamber="house",
            bill_number_numeric=5140,
            current_title="AN ACT CONCERNING EDUCATION",
        )
        db_session.add(bill)
        db_session.commit()

        fc = FileCopy(
            bill_id_fk=bill.id,
            session_year=2026,
            file_copy_number=1,
            canonical_version_id="2026-HB05140-FC00001",
            pdf_url="https://example.com/test.pdf",
        )
        db_session.add(fc)
        db_session.commit()

        result = db_session.query(FileCopy).first()
        assert result is not None
        assert result.canonical_version_id == "2026-HB05140-FC00001"
        assert result.bill.bill_id == "HB05140"


class TestClientModel:
    def test_create_client(self, db_session):
        client = Client(
            client_id="client_via",
            display_name="Via Transportation",
            is_active=True,
            alert_threshold=78,
            digest_threshold=58,
        )
        db_session.add(client)
        db_session.commit()

        result = db_session.query(Client).filter_by(client_id="client_via").first()
        assert result is not None
        assert result.alert_threshold == 78
