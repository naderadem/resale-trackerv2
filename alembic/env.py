"""Alembic environment.

Builds the DB URL from .env via db.session.get_database_url() (same source
of truth the app uses) instead of reading sqlalchemy.url out of alembic.ini,
so credentials only ever live in one place.
"""
import time
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool
from sqlalchemy.exc import OperationalError

from db.models import Base
from db.session import get_database_url

# `docker compose up -d` returns as soon as the container starts, not once
# Postgres is actually accepting connections -- so `docker compose up -d &&
# alembic upgrade head` run back-to-back can hit a database that isn't ready
# yet. Retry the initial connection for a few seconds instead of failing
# immediately on that race.
CONNECT_RETRY_ATTEMPTS = 10
CONNECT_RETRY_DELAY_SECONDS = 1.5

load_dotenv()

config = context.config
config.set_main_option("sqlalchemy.url", get_database_url())

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _connect_with_retry(connectable):
    for attempt in range(1, CONNECT_RETRY_ATTEMPTS + 1):
        try:
            return connectable.connect()
        except OperationalError:
            if attempt == CONNECT_RETRY_ATTEMPTS:
                raise
            print(
                f"Database not ready yet (attempt {attempt}/{CONNECT_RETRY_ATTEMPTS}), "
                f"retrying in {CONNECT_RETRY_DELAY_SECONDS}s..."
            )
            time.sleep(CONNECT_RETRY_DELAY_SECONDS)


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with _connect_with_retry(connectable) as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
