# resale-tracker

A personal tool that monitors resale fashion listings and alerts on items
priced below their historical median. Focused on Rick Owens, Maison
Margiela, Carol Christian Poell, and Hedi Slimane-era Dior Homme and Saint
Laurent.

## Status

Stage 1 built the source-adapter interface and the eBay adapter. Since
then: `parse_listings` was implemented, Postgres persistence + Alembic
migrations were added, a rapidfuzz matcher with brand/line disambiguation,
a pricing module with a suspicious-listing flag, EU/US/UK/JP size
normalization, a hand-labeled evaluation corpus for the matcher, Discord
alerting with dedup, and CI. Full detail, including honest before/after
numbers from the matcher eval pass, is in
[WHAT_I_BUILT.md](WHAT_I_BUILT.md) -- this section is just the map:

- **`sources/ebay.py`**: OAuth + Browse API search;`parse_listings` maps
  brand/size via `localizedAspects` -> a top-level field -> a title regex,
  `None` if none of those find anything.
- **`db/`**: SQLAlchemy models (`listings`, `canonical_items`,
  `listing_matches`, `unmatched_listings`, `sent_alerts`), upserted on
  `source, external_id`. Migrations via Alembic (`alembic/`); local
  Postgres via `docker-compose.yml`.
- **`matcher.py`**: rapidfuzz-based, with keyword-regex guards before
  scoring for Margiela's Mainline/MM6/Replica ambiguity, Rick Owens
  mainline-vs-DRKSHDW, and Hedi-era house separation (Dior Homme / Saint
  Laurent / Celine) -- see its module docstring.
- **`seed_data.py`**: 43 canonical items.
- **`pricing.py`**: median/p25 with a minimum sample size, and a
  suspicious-listing flag (this tier is heavily counterfeited, so an
  unusually low price defaults to a red flag, not a deal).
- **`size_normalization.py`**: EU/US/UK/JP size strings (plus "fits like a
  large") to one canonical number, kept separate for footwear vs. apparel.
- **`labeled_titles.py`** + **`eval_matcher.py`**: a 67-title hand-labeled
  corpus and an offline precision/recall/F1 harness for the matcher
  (`python main.py matcher-eval`).
- **`alerting.py`**: Discord webhook alerts, deduped via a `sent_alerts`
  table so the same listing never alerts twice.
- **CLI** (`main.py`): `seed`, `ingest`, `match` (`--dry-run`), `rematch`,
  `prices`, `unmatched`, `db-check`, `matcher-eval` (`--sweep`), `alert`
  (`--dry-run`).
- **CI** (`.github/workflows/ci.yml`): ruff lint + a Postgres-backed test
  job on push/PR.
- **Tests** (`tests/`): pytest, no network required anywhere; one test
  needs a real Postgres and skips cleanly if none is reachable (CI fails
  loudly instead of skipping there).

Still no web framework or scheduling -- this is a CLI you run by hand.

Grailed is still just a stub -- see
[docs/grailed_robots.txt](docs/grailed_robots.txt) (notably:
`Disallow: /search`) and
[docs/grailed_devtools_inspection.md](docs/grailed_devtools_inspection.md).

## Setup

Requires Python 3.10+ and Docker (for local Postgres).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt        # add -r requirements-dev.txt for pytest
cp .env.example .env
# then edit .env and fill in EBAY_APP_ID / EBAY_CERT_ID
# (the Postgres defaults in .env.example already match docker-compose.yml)

docker compose up -d --wait              # starts local Postgres, waits for the healthcheck
alembic upgrade head                     # creates the tables
python main.py seed                      # populates canonical_items
```

`--wait` (Docker Compose v2.17+) blocks until the `postgres` service reports
healthy before returning, so the `alembic upgrade head` right after it isn't
racing container startup. `alembic upgrade head` also retries its own
initial connection for ~15s on top of that, so plain `docker compose up -d
&& alembic upgrade head` (no `--wait`) works too -- it just risks a few
retry-log lines while Postgres finishes starting.

### Getting eBay credentials

1. Sign up / log in at the [eBay Developers Program](https://developer.ebay.com/).
2. Go to **My Account -> Application Keys** and create a keyset.
3. This project uses the **Production** App ID (Client ID) and Cert ID
   (Client Secret) with the Browse API's OAuth2 **client credentials** grant
   (application-level access -- no user login/consent flow needed for
   public search).
4. Copy the App ID and Cert ID into `.env` as `EBAY_APP_ID` and
   `EBAY_CERT_ID`.
5. Make sure the Browse API is enabled for your keyset (it is by default for
   most new keysets under the Buy APIs).

## Running it

```bash
python main.py seed                                # once, or after adding new canonical items
python main.py ingest "rick owens geobasket"        # search eBay, upsert into listings
python main.py match                                # match new listings against canonical_items
python main.py prices                               # print stats + flagged listings
python main.py unmatched                            # review what the matcher couldn't place
python main.py db-check                             # row counts per table, no psql needed
```

`ingest` prints one sample raw listing as JSON on its way through (same as
stage 1). `match` only processes listings that don't already have a match
or an unmatched-review row, so it's safe to re-run after every `ingest`.
`prices` prints median/p25/n per canonical item (or "insufficient data" if
below the minimum sample size) and, underneath, any matched listing that's
classified `DEAL` or `SUSPICIOUS`. All of the matcher/pricing thresholds are
configurable, either via `.env` (see `.env.example`) or per-command flags,
e.g.:

```bash
python main.py match --threshold 0.8
python main.py prices --min-sample-size 3 --floor-pct 0.35
```

### Tuning the matcher

```bash
python main.py match --dry-run                      # see what would match, write nothing
python main.py match --dry-run --threshold 0.6       # sweep a threshold without touching the db
python main.py rematch --threshold 0.68              # re-match EVERY listing from scratch
```

`match --dry-run` prints each listing's would-be match (or its reason for
not matching, plus the closest candidate it considered) without writing
anything -- use it to sweep thresholds or check the effect of an edited
`seed_data.py` before committing to it.

`rematch` clears `listing_matches` and `unmatched_listings` entirely and
re-matches every listing in `listings` from scratch. Use it after editing
`seed_data.py` or changing the threshold, so you can iterate against
listings you've already ingested instead of re-hitting the eBay API.

Responses are cached on disk under `.cache/` (gitignored) for 15 minutes by
default, and requests are throttled by a shared rate limiter, so re-running
the same `ingest` query repeatedly won't hammer eBay.

### Evaluating the matcher offline

```bash
python main.py matcher-eval                 # precision/recall/F1 at the default threshold
python main.py matcher-eval --threshold 0.6
python main.py matcher-eval --sweep         # the same, across a threshold range
```

Runs the matcher against the hand-labeled corpus in `labeled_titles.py` --
no database needed. Reports precision/recall/F1 and a list of "confused"
cases (matched, but to the *wrong* item). See WHAT_I_BUILT.md for what the
last eval run found and fixed, and for the honest numbers -- this tool is
meant to give real signal, not a number to chase by lowering the threshold.

### Alerts

```bash
python main.py alert --dry-run              # print what would be sent, write nothing
python main.py alert                        # actually post to DISCORD_WEBHOOK_URL
```

Set `DISCORD_WEBHOOK_URL` in `.env` (a channel's Server Settings ->
Integrations -> Webhooks). Sends one message per matched listing currently
classified `deal` or `suspicious` that hasn't already triggered an alert
(tracked in the `sent_alerts` table, so re-running `alert` never repeats
itself) -- not required for `--dry-run`, which only prints.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
ruff check .
```

No network calls required anywhere -- eBay and Discord are both mocked,
and the matcher/pricing/size tests run against in-memory objects. One test
(`tests/test_db_integration.py`) needs a real Postgres to actually run
(via `docker compose up -d --wait && alembic upgrade head`) and skips
cleanly otherwise -- it's the only thing that verifies the upsert's
`INSERT ... ON CONFLICT` against a real database rather than mocked/
in-memory substitutes. CI (`.github/workflows/ci.yml`) runs both ruff and
the full suite against a real Postgres service container on every push and
PR, and fails the build outright if that one test skips instead of
running.
