"""Repository for file copy records."""

from sqlalchemy.orm import Session

from src.db.models import FileCopy
from src.utils.bill_id import make_canonical_version_id


class FileCopyRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_if_new(
        self,
        bill_db_id: int,
        session_year: int,
        bill_id: str,
        file_copy_number: int,
        pdf_url: str,
        listing_date: str | None = None,
    ) -> tuple[FileCopy, bool]:
        """Create a file copy record if the canonical version ID doesn't exist.

        Returns (FileCopy, created: bool).
        """
        canonical_id = make_canonical_version_id(session_year, bill_id, file_copy_number)

        existing = self.session.query(FileCopy).filter_by(canonical_version_id=canonical_id).first()
        if existing:
            return existing, False

        fc = FileCopy(
            bill_id_fk=bill_db_id,
            session_year=session_year,
            file_copy_number=file_copy_number,
            canonical_version_id=canonical_id,
            listing_date=listing_date,
            pdf_url=pdf_url,
        )
        self.session.add(fc)
        self.session.flush()
        return fc, True

    def get_by_canonical_id(self, canonical_version_id: str) -> FileCopy | None:
        return (
            self.session.query(FileCopy)
            .filter_by(canonical_version_id=canonical_version_id)
            .first()
        )

    def get_prior_version(self, bill_db_id: int, file_copy_number: int) -> FileCopy | None:
        """Find the most recent file copy for the same bill before the given file copy number."""
        return (
            self.session.query(FileCopy)
            .filter(
                FileCopy.bill_id_fk == bill_db_id,
                FileCopy.file_copy_number < file_copy_number,
            )
            .order_by(FileCopy.file_copy_number.desc())
            .first()
        )

    def update_pdf_info(
        self,
        canonical_version_id: str,
        local_pdf_path: str,
        pdf_sha256: str,
        page_count: int | None = None,
    ) -> None:
        fc = self.get_by_canonical_id(canonical_version_id)
        if fc:
            fc.local_pdf_path = local_pdf_path
            fc.pdf_sha256 = pdf_sha256
            if page_count is not None:
                fc.page_count = page_count
            self.session.flush()
