# What I built

A running log of what's actually implemented, stage by stage, kept honest as
the code changes (as opposed to README, which documents how to use it).

## Stage 1

- `sources/base.py`: `Listing` dataclass + `ListingSource` ABC.
- `sources/ebay.py`: `EbaySource` -- OAuth client-credentials flow, Browse
  API search, error handling. `parse_listings` left as a stub.
- `sources/grailed.py`: `GrailedSource` stub, `NotImplementedError`.
  `docs/grailed_robots.txt` + `docs/grailed_devtools_inspection.md` for
  manual review before implementing.
- `common/rate_limiter.py`, `common/cache.py`: shared min-interval throttle
  and on-disk JSON response cache, used by `EbaySource` from the start.
- `main.py`: single-shot CLI (`python main.py "<query>"`).

## Stage 2 (in progress)

- **`sources/ebay.py`: `parse_listings` implemented.** Brand/size resolution
  order: `localizedAspects` (structured data eBay sometimes returns for
  fashion categories) -> a top-level field of the same name, if present ->
  regex against the title as a last resort. Left `None` at every step rather
  than guessed, since a wrong guess would quietly corrupt matching and
  pricing downstream. Items missing a required field (id/title/price/url)
  are skipped, not fatal.
- Tests (`tests/test_ebay_parser.py`): pytest, eBay responses faked via a
  fixture file + `unittest.mock` (no network, including for the OAuth/search
  round trip in `search()` itself). Covers every branch of the brand/size
  fallback chain, malformed-item skipping, and auth/search error handling.
- **Persistence** (`db/`): SQLAlchemy models (`db/models.py`) for
  `listings` (unique on `source, external_id` so re-ingesting upserts),
  `canonical_items`, `listing_matches`, and `unmatched_listings`.
  `db/session.py` builds the connection URL from `.env` (`DATABASE_URL`, or
  discrete `POSTGRES_*` vars defaulting to match `docker-compose.yml`).
  `db/repository.py` holds the upsert/query functions (upsert via Postgres's
  `INSERT ... ON CONFLICT`).
- **Migrations**: Alembic (`alembic.ini`, `alembic/env.py`), pulling its DB
  URL from the same `db.session.get_database_url()` the app uses so
  credentials live in one place. The initial revision
  (`alembic/versions/0001_initial.py`) is hand-written to match the models
  exactly, since there's no live Postgres in the environment this was built
  in to run `alembic revision --autogenerate` against. Verified with
  `alembic upgrade head --sql` (offline mode, generates SQL without
  connecting) -- the DDL it produces matches the models field-for-field.
  **Not actually applied to a running Postgres** -- do that yourself with
  `docker compose up -d && alembic upgrade head` and confirm; future schema
  changes can go back to the normal autogenerate flow against a live db.
- **`docker-compose.yml`**: local Postgres 16, env-driven, matching
  `.env.example` defaults, with a healthcheck.
