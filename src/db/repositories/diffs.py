"""Repository for bill diff and change event records."""

from sqlalchemy.orm import Session

from src.db.models import BillChangeEvent, BillDiff
from src.schemas.diff import BillDiffResult


class DiffRepository:
    def __init__(self, session: Session):
        self.session = session

    def save_diff(self, diff: BillDiffResult, bill_db_id: int) -> BillDiff:
        """Persist a BillDiffResult including all change events.

        Idempotent: if a diff already exists for this bill + current_version_id,
        the existing record is returned unchanged.
        """
        existing = (
            self.session.query(BillDiff)
            .filter_by(
                bill_id_fk=bill_db_id,
                current_version_id=diff.current_version_id,
            )
            .first()
        )
        if existing:
            return existing

        diff_row = BillDiff(
            bill_id_fk=bill_db_id,
            current_version_id=diff.current_version_id,
            prior_version_id=diff.prior_version_id,
            compared_against=diff.compared_against,
            sections_added=diff.sections_added,
            sections_removed=diff.sections_removed,
            sections_modified=diff.sections_modified,
            effective_date_old=diff.effective_date_old,
            effective_date_new=diff.effective_date_new,
        )
        self.session.add(diff_row)
        self.session.flush()

        for event in diff.change_events:
            event_row = BillChangeEvent(
                bill_diff_id=diff_row.id,
                change_flag=event.change_flag,
                section_id=event.section_id,
                old_text_summary=event.old_text_summary,
                new_text_summary=event.new_text_summary,
                practical_effect=event.practical_effect,
                confidence=event.confidence,
            )
            self.session.add(event_row)

        self.session.flush()
        return diff_row

    def get_by_version_id(self, canonical_version_id: str) -> BillDiff | None:
        return (
            self.session.query(BillDiff)
            .filter_by(current_version_id=canonical_version_id)
            .first()
        )

    def get_change_events(self, diff_id: int) -> list[BillChangeEvent]:
        return (
            self.session.query(BillChangeEvent)
            .filter_by(bill_diff_id=diff_id)
            .order_by(BillChangeEvent.id)
            .all()
        )
