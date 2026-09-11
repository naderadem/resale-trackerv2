"""eBay Browse API adapter.

Implements the OAuth2 client-credentials flow and search against eBay's
Browse API (item_summary/search), and maps the raw JSON response onto
Listing objects in `parse_listings`.
"""
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from common.cache import ResponseCache
from common.rate_limiter import RateLimiter
from sources.base import Listing, ListingSource

EBAY_OAUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"
EBAY_BROWSE_SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
EBAY_OAUTH_SCOPE = "https://api.ebay.com/oauth/api_scope"

# Brands we care about, used only as a last-resort regex fallback against
# the title when eBay doesn't give us a structured brand aspect. Order
# matters: longer/more specific names are checked before things they
# contain (e.g. "Maison Margiela" before "MM6").
KNOWN_BRANDS = [
    "Maison Margiela",
    "MM6",
    "Rick Owens DRKSHDW",
    "Rick Owens",
    "Carol Christian Poell",
    "Dior Homme",
    "Yves Saint Laurent",
    "Saint Laurent",
    "Celine",
]

# Tried in order; the first capturing group is taken as the size string.
# Deliberately conservative -- these are meant to catch common resale-title
# conventions ("Size 42", "EU 42", "US 9.5", "sz M"), not every possible
# way a seller might write a size.
SIZE_PATTERNS = [
    re.compile(r"\bsize[:\s]+([a-z0-9./]{1,6})\b", re.IGNORECASE),
    re.compile(r"\bsz[:\s]+([a-z0-9./]{1,6})\b", re.IGNORECASE),
    re.compile(r"\b(?:eu|eur)[:\s]?(\d{2}(?:\.\d)?)\b", re.IGNORECASE),
    re.compile(r"\b(?:us|uk)[:\s]?(\d{1,2}(?:\.\d)?)\b", re.IGNORECASE),
]


def _get_aspect(item: dict, name: str) -> Optional[str]:
    """Look up `name` in an item's localizedAspects list, case-insensitively."""
    for aspect in item.get("localizedAspects") or []:
        if str(aspect.get("name", "")).strip().lower() == name.lower():
            value = aspect.get("value")
            return str(value).strip() if value not in (None, "") else None
    return None


def _guess_brand_from_title(title: str) -> Optional[str]:
    """Last-resort brand guess by matching known brand names against the title."""
    lowered = title.lower()
    for brand in KNOWN_BRANDS:
        if brand.lower() in lowered:
            return brand
    return None


def _guess_size_from_title(title: str) -> Optional[str]:
    """Last-resort size guess via regex against the title."""
    for pattern in SIZE_PATTERNS:
        match = pattern.search(title)
        if match:
            return match.group(1)
    return None


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
        GET /buy/browse/v1/item_summary/search -- see the eBay docs:
        https://developer.ebay.com/api-docs/buy/browse/resources/item_summary/methods/search

        Brand and size are pulled from `localizedAspects` first (eBay
        sometimes includes these for fashion categories), then a top-level
        field of the same name if present, and only as a last resort by
        regexing the title against a list of known brands/size patterns.
        Fields are left as None rather than guessed when none of those find
        anything -- a wrong guess is worse than a missing value here, since
        it would quietly corrupt matching and pricing downstream.

        Items missing a required field (id/title/price/url) are skipped
        rather than raising, so one malformed item doesn't drop an entire
        batch of otherwise-good results.
        """
        items = raw_response.get("itemSummaries") or []
        fetched_at = datetime.now(timezone.utc)
        listings: list[Listing] = []

        for item in items:
            try:
                external_id = item["itemId"]
                title = item["title"]
                price = float(item["price"]["value"])
                currency = item["price"]["currency"]
                url = item["itemWebUrl"]
            except (KeyError, TypeError, ValueError):
                continue

            brand = (
                _get_aspect(item, "Brand")
                or item.get("brand")
                or _guess_brand_from_title(title)
            )
            size = (
                _get_aspect(item, "Size")
                or _get_aspect(item, "US Shoe Size")
                or item.get("size")
                or _guess_size_from_title(title)
            )
            condition = item.get("condition")

            seller = item.get("seller") or {}
            seller_rating_raw = seller.get("feedbackPercentage")
            try:
                seller_rating = (
                    float(seller_rating_raw) if seller_rating_raw not in (None, "") else None
                )
            except (TypeError, ValueError):
                seller_rating = None

            thumbnail_images = item.get("thumbnailImages") or []
            additional_images = item.get("additionalImages") or []
            total_images = len(thumbnail_images) + len(additional_images)
            photo_count = total_images if total_images > 0 else None

            listings.append(
                Listing(
                    source="ebay",
                    external_id=external_id,
                    title=title,
                    brand=brand,
                    price=price,
                    currency=currency,
                    size=size,
                    condition=condition,
                    seller_rating=seller_rating,
                    photo_count=photo_count,
                    url=url,
                    fetched_at=fetched_at,
                )
            )

        return listings
