"""Database engine and session factory."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from config.settings import get_settings


def get_engine(database_url: str | None = None):
    url = database_url or get_settings().database_url
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(url, connect_args=connect_args, echo=False)


def get_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    engine = get_engine(database_url)
    return sessionmaker(bind=engine, expire_on_commit=False)


def create_all_tables(database_url: str | None = None) -> None:
    """Create all tables — use for dev/testing only. Use Alembic in production."""
    from src.db.models import Base

    engine = get_engine(database_url)
    Base.metadata.create_all(engine)
