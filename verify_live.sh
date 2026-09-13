#!/usr/bin/env bash
# verify_live.sh -- runs the resale-tracker pipeline end to end against a
# REAL Postgres and the REAL eBay API. Nothing in this repo has ever been
# exercised against either before this script exists: the test suite mocks
# eBay entirely, and the one test that touches Postgres
# (tests/test_db_integration.py) skips cleanly wherever Postgres isn't
# reachable -- which has been true in every environment this project was
# built in so far.
#
# Reports exactly which step failed and what that usually means, rather
# than a bare stack trace. Safe to re-run from the top after fixing
# whatever it points at -- seed/ingest/match are all idempotent, and this
# script never tears down docker compose when it's done.
#
# Usage:
#   ./verify_live.sh                          # query defaults to "rick owens geobasket"
#   ./verify_live.sh "maison margiela tabi"    # or supply your own

set -uo pipefail

QUERY="${1:-rick owens geobasket}"
PYTHON=".venv/bin/python"
STEP=0

step() {
    STEP=$((STEP + 1))
    echo
    echo "== [$STEP] $1 =="
}

ok() {
    echo "  OK: $1"
}

fail() {
    echo "  FAILED: $1" >&2
    if [ -n "${2:-}" ]; then
        echo "" >&2
        echo "$2" >&2
    fi
    echo "" >&2
    echo "verify_live.sh stopped at step $STEP. Fix the above and re-run from the top -- every step so far is safe to repeat." >&2
    exit 1
}

# --------------------------------------------------------------- preflight

step "Preflight: repo root"
if [ ! -f "main.py" ] || [ ! -f "docker-compose.yml" ] || [ ! -f "alembic.ini" ]; then
    fail "This doesn't look like the resale-tracker repo root (main.py, docker-compose.yml, or alembic.ini not found in $(pwd))." \
"Run this from the repo root:
    cd resale-tracker && ./verify_live.sh"
fi
ok "running from $(pwd)"

step "Preflight: .venv"
if [ ! -x "$PYTHON" ]; then
    fail "$PYTHON not found or not executable." \
"Create the virtualenv and install dependencies first:
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt -r requirements-dev.txt"
fi
ok "$PYTHON found"

step "Preflight: Docker"
if ! docker info >/dev/null 2>&1; then
    fail "Docker daemon isn't reachable (\`docker info\` failed)." \
"Start Docker Desktop (or the docker daemon on Linux: \`sudo systemctl start docker\`) and re-run this script."
fi
ok "Docker daemon is running"

step "Preflight: .env"
if [ ! -f ".env" ]; then
    fail ".env not found." \
"Copy the template and fill in real values:
    cp .env.example .env
At minimum EBAY_APP_ID and EBAY_CERT_ID need real values -- see README.md's
'Getting eBay credentials' section."
fi

EBAY_APP_ID_VAL="$(grep -E '^EBAY_APP_ID=' .env | head -1 | cut -d= -f2-)"
EBAY_CERT_ID_VAL="$(grep -E '^EBAY_CERT_ID=' .env | head -1 | cut -d= -f2-)"

if [ -z "$EBAY_APP_ID_VAL" ] || [ -z "$EBAY_CERT_ID_VAL" ]; then
    fail "EBAY_APP_ID and/or EBAY_CERT_ID are empty in .env." \
"Edit .env and fill in real values from https://developer.ebay.com/
(My Account -> Application Keys -> a Production keyset). See README.md's
'Getting eBay credentials' section."
fi
ok ".env present with non-empty EBAY_APP_ID and EBAY_CERT_ID"

# ------------------------------------------------------------------ docker

step "docker compose up -d --wait"
if ! docker compose up -d --wait; then
    fail "docker compose up -d --wait failed (see output above)." \
"Common causes: port 5432 already bound by another Postgres (stop it, or
change POSTGRES_PORT in .env and docker-compose.yml), or the postgres:16
image failing to pull (check network access / Docker Hub reachability)."
fi
ok "Postgres container is up and healthy"

# ----------------------------------------------------------- schema + seed

step "alembic upgrade head"
if ! "$PYTHON" -m alembic upgrade head; then
    fail "alembic upgrade head failed (see output above)." \
"If this is the first run against this Postgres, check for a connection
error (POSTGRES_* values in .env not matching docker-compose.yml) or a
DDL problem in the migration output. If tables already exist in a broken
half-migrated state from a previous attempt, the simplest fix for a
personal dev database is: docker compose down -v && docker compose up -d --wait
(this destroys the local Postgres volume -- fine for dev data, not for
anything you care about keeping)."
fi
ok "migrations applied"

step "main.py db-check (baseline, before any data)"
if ! "$PYTHON" main.py db-check; then
    fail "db-check failed immediately after migrations -- something is wrong with the DB connection or schema, not with any data yet."
fi

step "main.py seed"
if ! "$PYTHON" main.py seed; then
    fail "main.py seed failed (see output above)."
fi

# -------------------------------------------------------------- ingest x2
#
# Ingesting the same query twice is the specific thing
# tests/test_db_integration.py was written to verify but has never run
# against a real database: that upsert_listing's Postgres
# INSERT ... ON CONFLICT DO UPDATE updates existing rows in place rather
# than duplicating them. The on-disk response cache (common/cache.py, 15
# min TTL) means the second `ingest` call for the same query reuses the
# exact same cached eBay response rather than hitting the network again --
# so this is a clean test of the upsert logic itself, not a coin flip on
# eBay's live inventory changing between the two calls a few seconds apart.

step "main.py ingest \"$QUERY\" (first run)"
if ! "$PYTHON" main.py ingest "$QUERY"; then
    fail "main.py ingest failed (see traceback/output above)." \
"Likely causes, roughly in order of likelihood:
  1. Sandbox keys instead of Production keys. eBay's Sandbox environment
     needs different credentials and only returns fake test data; this
     project is built against Production. Double-check your keyset type
     at https://developer.ebay.com/my/keys.
  2. parse_listings() raised on a response shape that differs from the
     fixture it was actually tested against
     (tests/fixtures/ebay_item_summary_search.json is hand-written from
     eBay's docs, not a captured live response). Look for a
     KeyError/TypeError inside sources/ebay.py:parse_listings in the
     traceback above, and compare against the 'Sample raw eBay listing'
     JSON this command prints just before it.
  3. Zero results for this query is NOT a bug -- if you see
     '(no itemSummaries in response for query=...)' above rather than an
     exception, try a broader query, e.g.: ./verify_live.sh \"rick owens\""
fi

step "main.py db-check (after first ingest)"
if ! DB_CHECK_1="$("$PYTHON" main.py db-check)"; then
    fail "db-check failed after the first ingest."
fi
echo "$DB_CHECK_1"

step "main.py ingest \"$QUERY\" (second run, same query -- testing the upsert)"
if ! "$PYTHON" main.py ingest "$QUERY"; then
    fail "The second ingest run failed even though the first succeeded -- check the output above; this is unexpected and worth investigating directly rather than one of the three usual first-ingest causes."
fi

step "main.py db-check (after second ingest) -- comparing to the first"
if ! DB_CHECK_2="$("$PYTHON" main.py db-check)"; then
    fail "db-check failed after the second ingest."
fi
echo "$DB_CHECK_2"

if [ "$DB_CHECK_1" = "$DB_CHECK_2" ]; then
    ok "row counts are identical after re-ingesting the same query -- the Postgres upsert (INSERT ... ON CONFLICT) is deduplicating correctly."
else
    echo "" >&2
    echo "  Row counts differ between the two ingests:" >&2
    diff <(echo "$DB_CHECK_1") <(echo "$DB_CHECK_2") >&2
    fail "Re-ingesting the identical (cached) eBay response changed row counts in listings. Since the second call reused the on-disk cache rather than hitting eBay again, the input was guaranteed identical -- so this points at a real bug in upsert_listing's ON CONFLICT clause, not live-data drift. This is exactly the behavior tests/test_db_integration.py verifies but that has never run against a real database before now."
fi

# ------------------------------------------------------- rest of the pipeline

step "main.py match"
if ! "$PYTHON" main.py match; then
    fail "main.py match failed (see output above)."
fi

step "main.py prices"
if ! "$PYTHON" main.py prices; then
    fail "main.py prices failed (see output above)."
fi

step "main.py unmatched"
if ! "$PYTHON" main.py unmatched; then
    fail "main.py unmatched failed (see output above)."
fi

step "main.py alert --dry-run"
if ! "$PYTHON" main.py alert --dry-run; then
    fail "main.py alert --dry-run failed (see output above)."
fi

echo
echo "======================================================================"
echo "All $STEP steps passed against a real Postgres and the real eBay API."
echo "======================================================================"
