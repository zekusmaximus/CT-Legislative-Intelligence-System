"""Repository for bill summary persistence."""

import json
import logging

from sqlalchemy.orm import Session

from src.db.models import BillSummary
from src.schemas.summary import InternalSummary

logger = logging.getLogger(__name__)


class SummaryRepository:
    def __init__(self, session: Session):
        self.session = session

    def save_summary(self, summary: InternalSummary) -> BillSummary:
        """Persist an InternalSummary. Idempotent by canonical_version_id."""
        existing = (
            self.session.query(BillSummary)
            .filter_by(canonical_version_id=summary.version_id)
            .first()
        )
        if existing:
            return existing

        row = BillSummary(
            canonical_version_id=summary.version_id,
            bill_id=summary.bill_id,
            one_sentence_summary=summary.one_sentence_summary,
            deep_summary=summary.deep_summary,
            key_sections_json=json.dumps(summary.key_sections_to_review),
            practical_takeaways_json=json.dumps(summary.practical_takeaways),
            confidence=summary.confidence,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def get_by_canonical_id(self, canonical_version_id: str) -> BillSummary | None:
        """Retrieve summary by canonical version ID."""
        return (
            self.session.query(BillSummary)
            .filter_by(canonical_version_id=canonical_version_id)
            .first()
        )

    def to_internal_summary(self, row: BillSummary) -> InternalSummary:
        """Convert a DB row back to an InternalSummary schema object."""
        return InternalSummary(
            bill_id=row.bill_id,
            version_id=row.canonical_version_id,
            one_sentence_summary=row.one_sentence_summary,
            deep_summary=row.deep_summary,
            key_sections_to_review=json.loads(row.key_sections_json) if row.key_sections_json else [],
            practical_takeaways=json.loads(row.practical_takeaways_json) if row.practical_takeaways_json else [],
            confidence=row.confidence,
        )
