"""Shared test fixtures."""

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.db.models import Base


@pytest.fixture(scope="session", autouse=True)
def _set_test_env():
    """Ensure test environment variables are set."""
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
    os.environ.setdefault("APP_ENV", "development")


@pytest.fixture
def db_session() -> Session:
    """Create an in-memory SQLite database and yield a session."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
