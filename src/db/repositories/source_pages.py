"""Repository for source page records."""

from sqlalchemy.orm import Session

from src.db.models import SourcePage
from src.schemas.intake import SourcePageRecord


class SourcePageRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, record: SourcePageRecord, raw_html_path: str | None = None) -> SourcePage:
        page = SourcePage(
            source_type=record.source_type,
            source_url=str(record.source_url),
            session_year=record.session_year,
            fetched_at=record.fetched_at,
            http_status=record.http_status,
            content_sha256=record.content_sha256,
            raw_html_path=raw_html_path,
        )
        self.session.add(page)
        self.session.flush()
        return page

    def exists_by_hash(self, content_sha256: str) -> bool:
        return (
            self.session.query(SourcePage).filter_by(content_sha256=content_sha256).first()
            is not None
        )
