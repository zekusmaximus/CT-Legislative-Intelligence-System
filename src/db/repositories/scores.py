"""Repository for client bill score persistence."""

import json
import logging

from sqlalchemy.orm import Session

from src.db.models import ClientBillScore
from src.schemas.scoring import ClientScoreResult

logger = logging.getLogger(__name__)


class ClientBillScoreRepository:
    def __init__(self, session: Session):
        self.session = session

    def save_score(
        self, score: ClientScoreResult, client_db_id: int, bill_db_id: int
    ) -> ClientBillScore:
        """Persist a client bill score. Idempotent by (client, version)."""
        existing = (
            self.session.query(ClientBillScore)
            .filter_by(
                client_id_fk=client_db_id,
                canonical_version_id=score.version_id,
            )
            .first()
        )
        if existing:
            return existing

        reasons = [r.model_dump() for r in score.match_reasons]

        row = ClientBillScore(
            client_id_fk=client_db_id,
            bill_id_fk=bill_db_id,
            canonical_version_id=score.version_id,
            rules_score=score.rules_score,
            embedding_score=score.embedding_score,
            llm_score=score.llm_score,
            final_score=score.final_score,
            urgency=score.urgency,
            should_alert=score.should_alert,
            alert_disposition=score.alert_disposition,
            reasons_json=json.dumps(reasons),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def get_by_client_version(
        self, client_db_id: int, canonical_version_id: str
    ) -> ClientBillScore | None:
        return (
            self.session.query(ClientBillScore)
            .filter_by(
                client_id_fk=client_db_id,
                canonical_version_id=canonical_version_id,
            )
            .first()
        )

    def get_scores_for_version(
        self, canonical_version_id: str
    ) -> list[ClientBillScore]:
        return (
            self.session.query(ClientBillScore)
            .filter_by(canonical_version_id=canonical_version_id)
            .all()
        )

    def get_alertable_scores(
        self, canonical_version_id: str
    ) -> list[ClientBillScore]:
        """Get scores that should trigger alerts (above threshold)."""
        return (
            self.session.query(ClientBillScore)
            .filter_by(
                canonical_version_id=canonical_version_id,
                should_alert=True,
            )
            .all()
        )
