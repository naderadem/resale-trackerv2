"""Engine/session construction from .env.

Connection details: either a single DATABASE_URL, or discrete POSTGRES_*
vars (matching docker-compose.yml's defaults) that get assembled into one.
DATABASE_URL wins if both are set.
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

_engine = None
_SessionLocal = None


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url

    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "resale_tracker")
    user = os.environ.get("POSTGRES_USER", "resale_tracker")
    password = os.environ.get("POSTGRES_PASSWORD", "resale_tracker")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(get_database_url(), future=True)
    return _engine


def get_session() -> Session:
    """Return a new Session. Caller is responsible for closing/committing it."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), future=True, expire_on_commit=False)
    return _SessionLocal()
