# resale-tracker

A personal tool that monitors resale fashion listings and alerts on items
priced below their historical median. Focused on Rick Owens, Maison
Margiela, Carol Christian Poell, and Hedi Slimane-era Dior Homme and Saint
Laurent.

## Status: Stage 1

This stage only sets up the foundation:

- A `ListingSource` interface ([sources/base.py](sources/base.py)) and a
  `Listing` dataclass that every marketplace adapter normalizes onto, so the
  rest of the system never needs to know which source a listing came from.
- A working `EbaySource` adapter ([sources/ebay.py](sources/ebay.py)):
  OAuth2 client-credentials auth + Browse API search, with error handling
  for both. **`parse_listings` is intentionally left unimplemented** --
  `search()` will authenticate, call eBay, print one raw listing as
  formatted JSON so you can see the real response shape, then raise
  `NotImplementedError`. Implement `parse_listings` yourself using that
  printed sample and the docstring in the file as a guide.
- A `GrailedSource` stub ([sources/grailed.py](sources/grailed.py)) that
  raises `NotImplementedError`. Grailed has no public search API; before
  writing anything real here, see [docs/grailed_robots.txt](docs/grailed_robots.txt)
  (notably: `Disallow: /search`) and
  [docs/grailed_devtools_inspection.md](docs/grailed_devtools_inspection.md)
  for how to inspect its network requests yourself.
- A shared rate limiter ([common/rate_limiter.py](common/rate_limiter.py))
  and on-disk response cache ([common/cache.py](common/cache.py)), used by
  every adapter from the start to keep request volume low.

No database, no web framework, no scheduling yet -- those come in later
stages.

## Setup

Requires Python 3.10+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# then edit .env and fill in EBAY_APP_ID / EBAY_CERT_ID
```

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
python main.py "rick owens geobasket"
```

This will authenticate against eBay, run the search, print one sample raw
listing as JSON, and then stop with a `NotImplementedError` from
`parse_listings` -- that's expected at this stage.

Responses are cached on disk under `.cache/` (gitignored) for 15 minutes by
default, and requests are throttled by a shared rate limiter, so re-running
the same query repeatedly won't hammer eBay.
