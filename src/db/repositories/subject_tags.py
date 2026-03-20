"""Repository for bill subject tag persistence."""

import logging

from sqlalchemy.orm import Session

from src.db.models import BillSubjectTag
from src.schemas.scoring import SubjectTagResult

logger = logging.getLogger(__name__)


class SubjectTagRepository:
    def __init__(self, session: Session):
        self.session = session

    def save_tags(self, tag_result: SubjectTagResult) -> list[BillSubjectTag]:
        """Persist subject tags for a bill version. Idempotent by (version, tag)."""
        version_id = tag_result.version_id
        saved: list[BillSubjectTag] = []

        # Build rationale lookup
        rationale_map: dict[str, str] = {}
        for r in tag_result.rationale:
            # Format is "tag_name: matched kw1, kw2, kw3"
            if ": " in r:
                tag_name, detail = r.split(": ", 1)
                rationale_map[tag_name] = detail

        for tag in tag_result.subject_tags:
            existing = (
                self.session.query(BillSubjectTag)
                .filter_by(
                    canonical_version_id=version_id,
                    subject_tag=tag,
                )
                .first()
            )
            if existing:
                saved.append(existing)
                continue

            row = BillSubjectTag(
                canonical_version_id=version_id,
                subject_tag=tag,
                tag_confidence=tag_result.tag_confidence,
                rationale=rationale_map.get(tag),
            )
            self.session.add(row)
            saved.append(row)

        self.session.flush()
        return saved

    def get_by_canonical_id(self, canonical_version_id: str) -> list[BillSubjectTag]:
        """Get all subject tags for a version."""
        return (
            self.session.query(BillSubjectTag)
            .filter_by(canonical_version_id=canonical_version_id)
            .all()
        )
