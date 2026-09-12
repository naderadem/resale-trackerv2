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

## Stage 2

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
- **CLI** (`main.py`, `config.py`): subcommands `ingest <query>`, `match`,
  `prices`, `unmatched` as specified, plus one addition beyond the spec --
  **`seed`**, since seed data needs some way to actually reach the
  database; it wraps `seed_data.seed_canonical_items` and is idempotent.
  `config.py` reads matcher/pricing thresholds from `.env` with defaults
  matching `matcher.py`/`pricing.py`; every subcommand that uses them also
  takes a CLI flag override (`--threshold`, `--min-sample-size`,
  `--floor-pct`, `--min-seller-rating`, `--min-photo-count`). All DB-backed
  commands fail with a friendly "is Postgres running?" hint instead of a
  raw traceback when the connection fails.
  `match` also records the matcher's *near-miss* candidate
  (`best_candidate`) on unmatched rows, not just the fact that nothing
  cleared the threshold -- useful when reviewing `unmatched` to see what
  the matcher was close to guessing.

  **Verification**: `db/repository.py`'s query functions (everything
  except the Postgres-specific `upsert_listing`, which uses `INSERT ...
  ON CONFLICT`) were exercised end-to-end against a real, if temporary,
  database -- SQLite in-memory standing in for Postgres, since none was
  available in this environment. Seeded 15 canonical items, ran 7 listings
  (5 genuine Geobasket titles in different phrasings, one bare-"replica"
  counterfeit mention, one unrelated Nike title) through `match_listing` +
  `record_match`/`record_unmatched`, confirmed `get_unprocessed_listings`
  goes to empty afterward (the idempotency `match` relies on), computed
  price stats over the 5 matched listings, and classified each by seller
  rating/photo count -- all matched expectations. `upsert_listing` and the
  real `ingest` round trip (which also needs a real Postgres) are the one
  piece not exercised here; run `docker compose up -d && alembic upgrade
  head` yourself and try `ingest`/`match`/`prices` for real.

## Verification and tuning pass

- **Confirmed** (no fix needed): `db/repository.py:upsert_listing` already
  used `sqlalchemy.dialects.postgresql.insert(...).on_conflict_do_update(...)`,
  not a generic insert. `.venv/` was confirmed gitignored and never
  committed (`git log --all -- .venv` returns nothing).
- **`tests/test_db_integration.py`**: the specific gap from the last pass --
  runs the real `search() -> parse_listings() -> upsert_listing()` pipeline
  against the same mocked eBay fixture twice, against a real Postgres, and
  asserts the row count for those listings is unchanged after the second
  round and `fetched_at` moved forward. Skips cleanly (`pytest.skip`, not a
  failure) when Postgres isn't reachable -- still true in the environment
  this was written in, so it has run to completion nowhere yet. Run
  `docker compose up -d --wait && alembic upgrade head && pytest` locally
  to actually exercise it; if it fails, that's a real bug, not a false
  negative from being skipped.
- **`db-check` subcommand**: prints row counts for all four tables, so you
  can sanity-check ingest/match state without opening `psql`.
- **Reliability of `docker compose up` -> `alembic upgrade head`**: the
  Postgres service already had a healthcheck (`pg_isready`, 5s interval, 10
  retries) from the persistence-layer commit. Added to it:
  - `alembic/env.py` now retries its initial connection (10 attempts, 1.5s
    apart, ~15s total) before raising, so a migration run immediately after
    `docker compose up -d` doesn't fail outright on a container that's
    started but not yet accepting connections. Verified by pointing it at
    a closed port and confirming it logs 9 retries before raising the real
    connection error on the 10th.
  - README now recommends `docker compose up -d --wait` (blocks until the
    healthcheck passes) as the primary path, with the retry loop as a
    backstop for the plain `&&` version.
- **Matcher tuning support**:
  - `--threshold` on `match` already read its default from
    `config.MATCH_THRESHOLD` (itself `.env`-configurable) -- this was
    already in place from the CLI-wiring commit, not new.
  - **`match --dry-run`**: prints each listing's would-be match (or its
    reason for not matching, plus the closest candidate considered) without
    calling `record_match`/`record_unmatched`. Verified directly against an
    in-memory DB that dry-run leaves `listing_matches`/`unmatched_listings`
    at zero rows while reporting the same match/unmatched counts a real run
    would.
  - **`rematch`**: clears `listing_matches` and `unmatched_listings`
    entirely (not just unprocessed listings) and re-matches every row in
    `listings`, so editing `seed_data.py` or sweeping a threshold can be
    tested against already-ingested data instead of re-hitting eBay.
    Verified the clear-then-redo sequence against an in-memory DB.
  - `matcher.MatchResult.best_candidate` (added in the CLI-wiring commit)
    is what makes dry-run's "closest candidate" output possible.

## CI, size normalization, and (in progress) matcher eval tooling

- **`size_normalization.py`**: converts EU/US/UK/JP size strings (plus
  free text like "fits like a large") to one canonical number, kept
  completely separate for footwear (canonical: EU shoe-size float) and
  apparel (canonical: EU tailoring size, or a denim waist in inches --
  two non-overlapping numeric ranges). Bare numbers are resolved by range
  where that's unambiguous (EU vs. US/UK shoe ranges don't overlap; EU
  tailoring vs. denim waist don't either) and flagged `is_estimated` where
  it isn't (a bare US/UK-band shoe size; any alpha size or "fits like"
  free text, since those are approximations by nature). A bare US/UK-
  tagged jacket number is deliberately detected-but-not-converted rather
  than guessed as a denim waist, since the ranges are close enough to
  collide. 66 tests, including the ambiguous cases (`"L/XL"`, `"9/9.5"`,
  `"one size"`, "runs small" fit commentary with no real size given).
- **CI** (`.github/workflows/ci.yml`): runs on push and PR. A `lint` job
  runs `ruff check .` (config in `pyproject.toml`; fixed the 6 pre-existing
  violations -- import ordering and a few `l` ambiguous-variable-name
  lints in test files -- to get a clean baseline). A `test` job runs
  against a real Postgres 16 service container (with a healthcheck GitHub
  Actions waits on before starting the job), runs `alembic upgrade head`
  against it, then `pytest --junitxml=report.xml`, then
  `.github/scripts/check_no_skipped_db_test.py` -- which parses the junit
  XML and fails the job if `tests/test_db_integration.py` shows a
  `<skipped>` result, since a silent skip there would be a false-negative
  green build for the one test that verifies the real upsert against a
  real database. Verified the checker script standalone against this
  environment's own junit output (which does skip, no Postgres here) and
  confirmed it exits 1 with the expected error message. **Not yet verified
  on an actual GitHub Actions runner** -- no way to trigger one from this
  environment; push this and watch the Actions tab the first time to
  confirm the service container step and health-wait behave as expected.
- **Seed data expanded 15 -> 43 items** (`seed_data.py`): Rick Owens 12
  (added Dunk Low, Cyclops, Megatooth, Stooges Leather Jacket, Performa
  Tee, plus DRKSHDW Duke Jean/Geobasket/Ramones alongside the existing
  Detroit Jean), Dior Homme 8, Saint Laurent 8, Margiela 12 (4 each across
  Mainline/MM6/Replica), Carol Christian Poell 3.
- **Found and fixed a real matcher bug while expanding Rick Owens**:
  DRKSHDW and mainline share model names (Geobasket, Ramones) the same way
  Margiela's lines do, and before this fix the matcher had no narrowing
  for it -- a title explicitly saying "Rick Owens DRKSHDW Geobasket"
  matched the *mainline* item instead, because both candidates scored a
  perfect 1.00 and `process.extractOne` broke the tie by list order, not
  by what the title said. Added a `_rick_owens_line_hint` guard mirroring
  the Margiela one (narrows to DRKSHDW when that word appears, else
  mainline, whenever "Rick Owens" is named at all). Verified directly
  (printed match results before/after) and covered with 3 new tests in
  `TestRickOwensLineDisambiguation`.

## Fixture corpus + matcher eval harness

- **`labeled_titles.py`**: 67 hand-labeled realistic listing titles (44
  expected to match a specific canonical item, 23 expected to match
  nothing) across Rick Owens (mainline + DRKSHDW), Margiela (all three
  lines), Hedi-era Dior Homme/Saint Laurent, and CCP. Includes
  misspellings ("Rick Owns", "Margiella", "Poel", a misspelled "Repica"),
  the MM6-vs-"Maison Margiela" wording variants, bare-"replica"
  counterfeit-ambiguity cases, wrong-designer noise (Off-White, Balenciaga,
  a bare "Dior" cologne mention, CDG, Undercover, Yohji), plain unrelated
  listings (Nike, Levi's, Adidas...), and Celine -- a real Hedi-era house
  that is deliberately *not* on the seeded catalog, to check it doesn't
  fall back onto a similarly-worded Dior Homme/Saint Laurent item.
- **`eval_matcher.py`** + `python main.py matcher-eval` (`--sweep` for a
  threshold range): precision/recall/F1 over the corpus, treating "should
  match a specific item" as the positive class, plus a `confused` list for
  cases where the matcher matched the *wrong* real item (worse than no
  match, since it corrupts pricing data). Fully offline -- builds the
  catalog straight from `seed_data.py`, no database.
- **Ran it honestly and found a real bug, not a threshold problem**: at
  the production default (0.72), the first run scored P=0.967 R=0.674
  F1=0.795, with 14 false negatives -- and 13 of those 14 had the
  *correct* item as the closest candidate, just short of the bar. Dug into
  why: `_searchable_text` included `line_or_era` in the *scored* string,
  and multi-word era labels like "Hedi Slimane Era" are essentially never
  typed by a real seller, so every Dior Homme/Saint Laurent candidate
  carried 2-3 tokens no title would ever contain -- `token_set_ratio`
  penalizes candidate-side-only tokens (unlike title-side-only ones, which
  is the entire reason it was chosen over `WRatio` last time), so this
  systematically depressed that whole category's scores for zero
  disambiguation benefit (narrowing already handles disambiguation via the
  brand/line hints, before scoring ever runs). Fixed by dropping
  `line_or_era` from the scored text entirely -- confirmed line-by-line
  that this doesn't weaken narrowing anywhere, then verified no
  regressions (one existing test needed fixing: it asserted a Celine
  title cleared the *production* default threshold when what it was
  actually testing was disambiguation from Dior Homme/Saint Laurent, a
  separate concern -- see its updated comment).
  **After the fix, still at threshold 0.72, no threshold change**:
  P=0.943 R=0.786 F1=0.857 (FN 14 -> 9). Remaining false negatives and
  the 2 confused cases are reported to the user categorized (threshold
  problem vs. catalog gap vs. genuinely-not-tracked), not just as raw
  numbers. Full sweep (0.50-0.95, step 0.05) is in the CLI output; F1
  peaks at threshold 0.60 (0.952) on this corpus and falls off sharply
  above 0.70, which is real evidence about the current default, not a
  recommendation acted on here -- changing the production threshold is a
  call for the user to make, not something this pass changed unilaterally.
