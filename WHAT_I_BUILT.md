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
