"""Repository for bill records."""

from datetime import datetime

from sqlalchemy.orm import Session

from src.db.models import Bill
from src.utils.bill_id import bill_id_to_chamber, bill_id_to_number


class BillRepository:
    def __init__(self, session: Session):
        self.session = session

    def upsert(
        self,
        session_year: int,
        bill_id: str,
        title: str,
        committee: str | None = None,
        status_url: str | None = None,
    ) -> Bill:
        """Create or update a bill record. Returns the Bill."""
        existing = (
            self.session.query(Bill).filter_by(session_year=session_year, bill_id=bill_id).first()
        )
        if existing:
            existing.current_title = title
            if committee:
                existing.committee_name = committee
            if status_url:
                existing.bill_status_url = status_url
            existing.updated_at = datetime.now()
            self.session.flush()
            return existing

        bill = Bill(
            session_year=session_year,
            bill_id=bill_id,
            chamber=bill_id_to_chamber(bill_id),
            bill_number_numeric=bill_id_to_number(bill_id),
            current_title=title,
            committee_name=committee,
            bill_status_url=status_url,
        )
        self.session.add(bill)
        self.session.flush()
        return bill

    def get_by_bill_id(self, session_year: int, bill_id: str) -> Bill | None:
        return (
            self.session.query(Bill).filter_by(session_year=session_year, bill_id=bill_id).first()
        )
