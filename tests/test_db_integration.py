"""Integration test against a real Postgres -- the one thing unit tests
with mocked/SQLite substitutes can't verify: that upsert_listing's
Postgres-dialect INSERT ... ON CONFLICT actually upserts against a real
Postgres, not just that the generated SQL looks right.

Skips cleanly if Postgres isn't reachable (e.g. `docker compose up -d`
hasn't been run) rather than failing the whole suite -- run
`docker compose up -d && alembic upgrade head` first to actually exercise
this one.
"""
from unittest.mock import MagicMock

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from common.cache import ResponseCache
from db.models import Base, ListingRecord
from db.repository import upsert_listing
from db.session import get_engine
from sources.ebay import EbaySource


@pytest.fixture
def pg_session():
    engine = get_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError:
        pytest.skip(
            "Postgres not reachable -- run `docker compose up -d && alembic "
            "upgrade head` to exercise this test (see .env for connection details)"
        )

    Base.metadata.create_all(engine)  # no-op if alembic already created these
    session = sessionmaker(bind=engine, future=True)()
    yield session
    session.close()


@pytest.fixture
def mocked_ebay_source(tmp_path):
    cache = ResponseCache(namespace="ebay-pg-test", cache_dir=str(tmp_path))
    source = EbaySource(app_id="dummy-app-id", cert_id="dummy-cert-id", cache=cache)

    token_response = MagicMock(spec=httpx.Response)
    token_response.status_code = 200
    token_response.json.return_value = {"access_token": "fake-token", "expires_in": 7200}
    source._client.post = MagicMock(return_value=token_response)
    source.rate_limiter.wait = lambda: None
    return source, cache


def _search_with_response(source, cache, raw_response, query):
    """Force a fresh search() call against `raw_response`, bypassing the cache
    (so a second call re-parses instead of silently reusing the first's
    already-cached raw JSON -- what matters here is that parse_listings runs
    again and upsert_listing is called again with a fresh fetched_at).
    """
    cache.set(f"search:{source.marketplace_id}:{query}", raw_response)
    return source.search(query)


def test_ingesting_the_same_mocked_response_twice_upserts_not_duplicates(
    pg_session, mocked_ebay_source, ebay_search_response
):
    """The specific scenario that was never verified: run the same search
    response through search() -> upsert_listing() twice and confirm rows
    were updated in place, not duplicated, with fetched_at moving forward.
    """
    source, cache = mocked_ebay_source
    query = "pg-roundtrip-test-query"
    external_ids = [item["itemId"] for item in ebay_search_response["itemSummaries"] if "price" in item]

    try:
        first_listings = _search_with_response(source, cache, ebay_search_response, query)
        assert len(first_listings) == len(external_ids)  # one item has no price and is skipped
        first_records = {r.external_id: r for r in (upsert_listing(pg_session, l) for l in first_listings)}

        row_count_after_first = (
            pg_session.query(ListingRecord)
            .filter(ListingRecord.source == "ebay", ListingRecord.external_id.in_(external_ids))
            .count()
        )
        assert row_count_after_first == len(external_ids)

        # Re-run the identical response through the pipeline again -- as if
        # `ingest` were run a second time for the same query.
        second_listings = _search_with_response(source, cache, ebay_search_response, query)
        second_records = {r.external_id: r for r in (upsert_listing(pg_session, l) for l in second_listings)}

        row_count_after_second = (
            pg_session.query(ListingRecord)
            .filter(ListingRecord.source == "ebay", ListingRecord.external_id.in_(external_ids))
            .count()
        )
        assert row_count_after_second == row_count_after_first, "row count must not grow on re-ingest"

        for external_id in external_ids:
            assert second_records[external_id].id == first_records[external_id].id, (
                f"{external_id}: upsert must update the existing row, not insert a new one"
            )
            assert second_records[external_id].fetched_at > first_records[external_id].fetched_at, (
                f"{external_id}: fetched_at must be updated on re-ingest"
            )
    finally:
        pg_session.query(ListingRecord).filter(
            ListingRecord.source == "ebay", ListingRecord.external_id.in_(external_ids)
        ).delete(synchronize_session=False)
        pg_session.commit()
