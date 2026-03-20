"""Repository for bill text extraction records."""

import json

from sqlalchemy.orm import Session

from src.db.models import BillTextExtraction, BillTextPage
from src.schemas.extraction import ExtractedDocument


class ExtractionRepository:
    def __init__(self, session: Session):
        self.session = session

    def save_extraction(self, doc: ExtractedDocument) -> BillTextExtraction:
        """Persist an ExtractedDocument, including all pages.

        Idempotent: if an extraction already exists for this canonical_version_id,
        the existing record is returned unchanged.
        """
        existing = (
            self.session.query(BillTextExtraction)
            .filter_by(canonical_version_id=doc.canonical_version_id)
            .first()
        )
        if existing:
            return existing

        extraction = BillTextExtraction(
            canonical_version_id=doc.canonical_version_id,
            full_raw_text=doc.full_raw_text,
            full_cleaned_text=doc.full_cleaned_text,
            overall_extraction_confidence=doc.overall_extraction_confidence,
            extraction_warnings_json=json.dumps(doc.extraction_warnings) if doc.extraction_warnings else None,
        )
        self.session.add(extraction)
        self.session.flush()

        for page in doc.pages:
            page_row = BillTextPage(
                extraction_id=extraction.id,
                page_number=page.page_number,
                raw_text=page.raw_text,
                cleaned_text=page.cleaned_text,
                extraction_method=page.extraction_method,
                extraction_confidence=page.extraction_confidence,
            )
            self.session.add(page_row)

        self.session.flush()
        return extraction

    def get_by_canonical_id(self, canonical_version_id: str) -> BillTextExtraction | None:
        return (
            self.session.query(BillTextExtraction)
            .filter_by(canonical_version_id=canonical_version_id)
            .first()
        )

    def get_pages(self, extraction_id: int) -> list[BillTextPage]:
        return (
            self.session.query(BillTextPage)
            .filter_by(extraction_id=extraction_id)
            .order_by(BillTextPage.page_number)
            .all()
        )
