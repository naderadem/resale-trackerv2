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
- **`matcher.py`**: rapidfuzz (`token_set_ratio` -- more forgiving than
  `WRatio` of the noise words real titles carry that a canonical item's
  short name doesn't) matching of a title against `canonical_items`,
  returning the best match + confidence or `None` (with a `reason`) below a
  configurable threshold (default 0.72). Two keyword-regex guards run
  *before* fuzzy scoring:
  - *Margiela line disambiguation*: Mainline/MM6/Replica narrowed by brand
    + line keywords in the title before scoring, so shared model names
    (e.g. "Tabi" exists in more than one line) can't cross-match. A bare
    "replica" mention with no Margiela brand token (e.g. "Rick Owens
    Geobasket replica") is refused outright rather than fuzzy-matched to
    the genuine item it's imitating -- same for other counterfeit language
    ("reps", "1:1", "AAA", etc.) wherever it appears.
  - *Hedi-era house separation*: candidates narrowed to the one house
    (Dior Homme / Saint Laurent / Celine) named in the title, if exactly
    one is; ambiguous titles naming more than one house fall through to
    unrestricted scoring rather than guessing.
- **`seed_data.py`**: 15 canonical items -- 4 Rick Owens, 3 Hedi-era Dior
  Homme, 3 Hedi-era Saint Laurent, 2 Margiela Mainline + 1 MM6 + 1 Replica,
  1 Carol Christian Poell. `seed_canonical_items(session)` inserts anything
  not already present (by brand+line+model), so it's safe to re-run.
- Tests (`tests/test_matcher.py`): the Margiela mainline/MM6/Replica
  disambiguation, the bare-"replica"-is-refused case and other counterfeit
  language, Dior Homme/Saint Laurent/Celine separation (including an
  ambiguous multi-house title), plus general match/no-match/threshold
  behavior. 14 tests, all against in-memory `CanonicalItem` objects -- no
  DB needed.
- **`pricing.py`**: `compute_price_stats` (median/p25/count via linear
  interpolation, returns `None` below a configurable minimum sample size --
  default 5 -- rather than a meaningless median from a handful of
  listings) and `classify_listing` ("deal" / "suspicious" / "normal" /
  "no_data"). A price far below median (below a configurable floor
  percentage, default 40%) is "suspicious" regardless of trust signals;
  a moderately-below-median price is only a "deal" when seller rating
  *and* photo count both clear configurable bars, otherwise it's still
  "suspicious" -- this tier is heavily counterfeited, so an unusually low
  price defaults to a red flag, not a bargain.
- Tests (`tests/test_pricing.py`): the minimum-sample-size cutoff (below,
  at, and using the default), median/p25 correctness on sorted/unsorted
  input, and every classify_listing branch (floor override, good vs. poor
  seller rating, missing signals, configurable floor_pct).
