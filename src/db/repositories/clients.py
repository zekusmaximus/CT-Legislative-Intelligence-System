"""Repository for client persistence."""

import logging

from sqlalchemy.orm import Session

from src.db.models import Client, ClientInterestProfile

logger = logging.getLogger(__name__)


class ClientRepository:
    def __init__(self, session: Session):
        self.session = session

    def upsert(
        self,
        client_id: str,
        display_name: str,
        is_active: bool = True,
        alert_threshold: int = 78,
        digest_threshold: int = 58,
    ) -> Client:
        """Create or update a client record. Returns the Client row."""
        existing = (
            self.session.query(Client)
            .filter_by(client_id=client_id)
            .first()
        )
        if existing:
            existing.display_name = display_name
            existing.is_active = is_active
            existing.alert_threshold = alert_threshold
            existing.digest_threshold = digest_threshold
            self.session.flush()
            return existing

        client = Client(
            client_id=client_id,
            display_name=display_name,
            is_active=is_active,
            alert_threshold=alert_threshold,
            digest_threshold=digest_threshold,
        )
        self.session.add(client)
        self.session.flush()
        return client

    def get_by_client_id(self, client_id: str) -> Client | None:
        return (
            self.session.query(Client)
            .filter_by(client_id=client_id)
            .first()
        )

    def get_active_clients(self) -> list[Client]:
        return (
            self.session.query(Client)
            .filter_by(is_active=True)
            .all()
        )

    def save_profile(
        self, client_db_id: int, profile_yaml: str, profile_version: int = 1
    ) -> ClientInterestProfile:
        """Save a client interest profile. Idempotent by client + version."""
        existing = (
            self.session.query(ClientInterestProfile)
            .filter_by(client_id_fk=client_db_id, profile_version=profile_version)
            .first()
        )
        if existing:
            existing.profile_yaml = profile_yaml
            self.session.flush()
            return existing

        profile = ClientInterestProfile(
            client_id_fk=client_db_id,
            profile_yaml=profile_yaml,
            profile_version=profile_version,
        )
        self.session.add(profile)
        self.session.flush()
        return profile
