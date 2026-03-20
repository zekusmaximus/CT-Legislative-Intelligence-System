"""Repository for bill section records."""

from sqlalchemy.orm import Session

from src.db.models import BillSection
from src.schemas.extraction import ExtractedDocument


class SectionRepository:
    def __init__(self, session: Session):
        self.session = session

    def save_sections(self, doc: ExtractedDocument) -> list[BillSection]:
        """Persist all sections from an ExtractedDocument.

        Idempotent: if sections already exist for this canonical_version_id,
        the existing records are returned unchanged.
        """
        existing = (
            self.session.query(BillSection)
            .filter_by(canonical_version_id=doc.canonical_version_id)
            .all()
        )
        if existing:
            return existing

        rows: list[BillSection] = []
        for section in doc.sections:
            row = BillSection(
                canonical_version_id=doc.canonical_version_id,
                section_id=section.section_id,
                heading=section.heading,
                start_page=section.start_page,
                end_page=section.end_page,
                start_char=section.start_char,
                end_char=section.end_char,
                text=section.text,
            )
            self.session.add(row)
            rows.append(row)

        self.session.flush()
        return rows

    def get_by_canonical_id(self, canonical_version_id: str) -> list[BillSection]:
        return (
            self.session.query(BillSection)
            .filter_by(canonical_version_id=canonical_version_id)
            .order_by(BillSection.id)
            .all()
        )
