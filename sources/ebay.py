"""eBay Browse API adapter.

Implements the OAuth2 client-credentials flow and search against eBay's
Browse API (item_summary/search). Mapping the raw JSON response onto
Listing objects is left for you to implement -- see `parse_listings` below.
"""
import json
import os
import time
from typing import Any, Optional

import httpx

from common.cache import ResponseCache
from common.rate_limiter import RateLimiter
from sources.base import Listing, ListingSource

EBAY_OAUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"
EBAY_BROWSE_SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
EBAY_OAUTH_SCOPE = "https://api.ebay.com/oauth/api_scope"


class EbayAuthError(Exception):
    """Raised when fetching an eBay OAuth access token fails."""


class EbaySearchError(Exception):
    """Raised when a Browse API search request fails."""


class EbaySource(ListingSource):
    """ListingSource implementation backed by eBay's Browse API."""

    def __init__(
        self,
        app_id: Optional[str] = None,
        cert_id: Optional[str] = None,
        rate_limiter: Optional[RateLimiter] = None,
        cache: Optional[ResponseCache] = None,
        marketplace_id: str = "EBAY_US",
    ):
        self.app_id = app_id or os.environ.get("EBAY_APP_ID")
        self.cert_id = cert_id or os.environ.get("EBAY_CERT_ID")
        if not self.app_id or not self.cert_id:
            raise ValueError(
                "EBAY_APP_ID and EBAY_CERT_ID must be set, either as env vars "
                "(see .env.example) or passed directly to EbaySource()."
            )

        self.marketplace_id = marketplace_id
        # Shared across both the OAuth endpoint and the search endpoint, so
        # total request volume to eBay stays capped at one instance's limit.
        self.rate_limiter = rate_limiter or RateLimiter(min_interval_seconds=1.0)
        self.cache = cache or ResponseCache(namespace="ebay")

        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._client = httpx.Client(timeout=15.0)

    def _get_access_token(self) -> str:
        """Return a valid OAuth2 access token, fetching a new one if needed.

        Tokens are cached in memory for the process lifetime (not on disk --
        they're short-lived credentials, not response data) and refreshed a
        minute before they actually expire.
        """
        if self._access_token and time.monotonic() < self._token_expires_at:
            return self._access_token

        self.rate_limiter.wait()
        try:
            response = self._client.post(
                EBAY_OAUTH_URL,
                auth=(self.app_id, self.cert_id),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={"grant_type": "client_credentials", "scope": EBAY_OAUTH_SCOPE},
            )
        except httpx.HTTPError as exc:
            raise EbayAuthError(f"Failed to reach eBay's OAuth endpoint: {exc}") from exc

        if response.status_code != 200:
            raise EbayAuthError(
                f"eBay OAuth token request failed ({response.status_code}): {response.text}"
            )

        payload = response.json()
        try:
            token = payload["access_token"]
            expires_in = payload["expires_in"]
        except KeyError as exc:
            raise EbayAuthError(f"Unexpected OAuth response shape: {payload}") from exc

        self._access_token = token
        self._token_expires_at = time.monotonic() + expires_in - 60
        return token

    def search(self, query: str) -> list[Listing]:
        """Search eBay's Browse API for `query` and return normalized Listings.

        Checks the on-disk cache first; on a miss, authenticates, calls the
        Browse API, and caches the raw response. Either way the raw response
        is handed to `parse_listings`, which is not implemented yet.
        """
        cache_key = f"search:{self.marketplace_id}:{query}"
        raw_response = self.cache.get(cache_key)

        if raw_response is None:
            token = self._get_access_token()
            self.rate_limiter.wait()
            try:
                response = self._client.get(
                    EBAY_BROWSE_SEARCH_URL,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "X-EBAY-C-MARKETPLACE-ID": self.marketplace_id,
                    },
                    params={"q": query, "limit": "50"},
                )
            except httpx.HTTPError as exc:
                raise EbaySearchError(f"Failed to reach eBay's Browse API: {exc}") from exc

            if response.status_code != 200:
                raise EbaySearchError(
                    f"eBay search failed ({response.status_code}): {response.text}"
                )

            raw_response = response.json()
            self.cache.set(cache_key, raw_response)

        items = raw_response.get("itemSummaries", [])
        if items:
            print("=== Sample raw eBay listing (itemSummaries[0]) ===")
            print(json.dumps(items[0], indent=2))
            print("=== end sample ===\n")
        else:
            print(f"(no itemSummaries in response for query={query!r})")

        return self.parse_listings(raw_response)

    def parse_listings(self, raw_response: dict[str, Any]) -> list[Listing]:
        """Map a raw Browse API search response onto a list of Listing objects.

        `raw_response` is the parsed JSON body of a call to
        GET /buy/browse/v1/item_summary/search -- look at the sample printed
        by `search()` above to see its actual shape, or the eBay docs:
        https://developer.ebay.com/api-docs/buy/browse/resources/item_summary/methods/search

        Implement this by:
          - reading raw_response.get("itemSummaries", []) (a list of item dicts)
          - for each item, building a Listing(...) with:
              source="ebay"
              external_id = item["itemId"]
              title = item["title"]
              brand = look in item.get("localizedAspects", []) for an aspect
                  named "Brand" (Browse API search results don't always
                  include this -- fall back to None if it's missing)
              price = float(item["price"]["value"])
              currency = item["price"]["currency"]
              size = same idea as brand, via localizedAspects, may be None
              condition = item.get("condition")
              seller_rating = item.get("seller", {}).get("feedbackPercentage"),
                  cast to float, or None
              photo_count = len(item.get("thumbnailImages", [])) plus any
                  images under item.get("additionalImages", []), or None
              url = item["itemWebUrl"]
              fetched_at = datetime.now(timezone.utc)
          - returning the list of Listings

        Raises NotImplementedError until you write the above yourself.
        """
        raise NotImplementedError(
            "parse_listings is not implemented yet -- see the docstring above "
            "and the sample raw listing printed by search()."
        )
