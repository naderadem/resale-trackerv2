"""Tests for EbaySource.parse_listings and its brand/size fallback chain.

These operate purely on an in-memory dict standing in for a Browse API
response -- no network involved.
"""
from unittest.mock import MagicMock

import httpx
import pytest

from common.cache import ResponseCache
from sources.ebay import EbayAuthError, EbaySearchError, EbaySource


@pytest.fixture
def ebay_source(tmp_path) -> EbaySource:
    # Use a throwaway cache dir per test so tests never share state with each
    # other or with the project's real .cache/ebay/ directory.
    cache = ResponseCache(namespace="ebay-test", cache_dir=str(tmp_path))
    return EbaySource(app_id="dummy-app-id", cert_id="dummy-cert-id", cache=cache)


def _by_id(listings, external_id):
    return next(listing for listing in listings if listing.external_id == external_id)


class TestParseListings:
    def test_uses_localized_aspects_when_present(self, ebay_source, ebay_search_response):
        listings = ebay_source.parse_listings(ebay_search_response)
        geobasket = _by_id(listings, "v1|110001|0")

        assert geobasket.source == "ebay"
        assert geobasket.title == "Rick Owens Geobasket High Top Sneakers Black Size 42"
        assert geobasket.brand == "Rick Owens"
        assert geobasket.size == "42"
        assert geobasket.price == 650.00
        assert geobasket.currency == "USD"
        assert geobasket.condition == "Pre-owned"
        assert geobasket.seller_rating == 99.5
        assert geobasket.photo_count == 3  # 1 thumbnail + 2 additional
        assert geobasket.url == "https://www.ebay.com/itm/110001"

    def test_falls_back_to_title_regex_when_aspects_empty(self, ebay_source, ebay_search_response):
        listings = ebay_source.parse_listings(ebay_search_response)
        mm6 = _by_id(listings, "v1|110002|0")

        # localizedAspects is present but empty -> must fall back to title regex.
        assert mm6.brand == "Maison Margiela"
        assert mm6.size == "38"
        assert mm6.photo_count == 1

    def test_falls_back_to_title_regex_when_aspects_key_missing(
        self, ebay_source, ebay_search_response
    ):
        listings = ebay_source.parse_listings(ebay_search_response)
        dior = _by_id(listings, "v1|110003|0")

        assert dior.brand == "Dior Homme"
        # no size pattern anywhere in this title -- must stay None, not guessed
        assert dior.size is None
        assert dior.photo_count is None

    def test_leaves_brand_and_size_none_when_undetectable(self, ebay_source):
        raw = {
            "itemSummaries": [
                {
                    "itemId": "v1|999|0",
                    "title": "Some obscure item nobody can identify",
                    "price": {"value": "50.00", "currency": "USD"},
                    "itemWebUrl": "https://www.ebay.com/itm/999",
                }
            ]
        }
        listings = ebay_source.parse_listings(raw)
        assert listings[0].brand is None
        assert listings[0].size is None

    def test_skips_items_missing_required_fields(self, ebay_source, ebay_search_response):
        listings = ebay_source.parse_listings(ebay_search_response)
        # item 110004 has no "price" key and must be dropped, not raise.
        ids = [listing.external_id for listing in listings]
        assert "v1|110004|0" not in ids
        assert len(listings) == 4  # 5 items in, 1 skipped

    def test_handles_unparseable_seller_rating_gracefully(self, ebay_source, ebay_search_response):
        listings = ebay_source.parse_listings(ebay_search_response)
        ccp = _by_id(listings, "v1|110005|0")
        assert ccp.seller_rating is None  # "N/A" must not raise or become 0

    def test_empty_item_summaries_returns_empty_list(self, ebay_source):
        assert ebay_source.parse_listings({}) == []
        assert ebay_source.parse_listings({"itemSummaries": []}) == []


class TestSearchEndToEnd:
    """search() with httpx fully mocked -- must never touch the network."""

    def test_search_authenticates_calls_browse_api_and_parses(
        self, ebay_source, ebay_search_response, monkeypatch
    ):
        token_response = MagicMock(spec=httpx.Response)
        token_response.status_code = 200
        token_response.json.return_value = {"access_token": "fake-token", "expires_in": 7200}

        search_response = MagicMock(spec=httpx.Response)
        search_response.status_code = 200
        search_response.json.return_value = ebay_search_response

        mock_post = MagicMock(return_value=token_response)
        mock_get = MagicMock(return_value=search_response)
        monkeypatch.setattr(ebay_source._client, "post", mock_post)
        monkeypatch.setattr(ebay_source._client, "get", mock_get)
        # Don't actually sleep in tests.
        monkeypatch.setattr(ebay_source.rate_limiter, "wait", lambda: None)

        listings = ebay_source.search("rick owens")

        assert mock_post.called  # OAuth token request happened
        assert mock_get.called  # Browse API search request happened
        assert len(listings) == 4
        assert ebay_source._access_token == "fake-token"

        # Second call should hit the on-disk cache and not re-request a token.
        mock_get.reset_mock()
        mock_post.reset_mock()
        listings_again = ebay_source.search("rick owens")
        assert not mock_post.called
        assert not mock_get.called
        assert len(listings_again) == 4

    def test_auth_failure_raises_ebay_auth_error(self, ebay_source, monkeypatch):
        failed_response = MagicMock(spec=httpx.Response)
        failed_response.status_code = 401
        failed_response.text = "invalid client credentials"
        monkeypatch.setattr(ebay_source._client, "post", MagicMock(return_value=failed_response))
        monkeypatch.setattr(ebay_source.rate_limiter, "wait", lambda: None)

        with pytest.raises(EbayAuthError):
            ebay_source.search("rick owens")

    def test_search_failure_raises_ebay_search_error(self, ebay_source, monkeypatch):
        token_response = MagicMock(spec=httpx.Response)
        token_response.status_code = 200
        token_response.json.return_value = {"access_token": "fake-token", "expires_in": 7200}

        failed_search_response = MagicMock(spec=httpx.Response)
        failed_search_response.status_code = 500
        failed_search_response.text = "internal server error"

        monkeypatch.setattr(ebay_source._client, "post", MagicMock(return_value=token_response))
        monkeypatch.setattr(
            ebay_source._client, "get", MagicMock(return_value=failed_search_response)
        )
        monkeypatch.setattr(ebay_source.rate_limiter, "wait", lambda: None)

        with pytest.raises(EbaySearchError):
            ebay_source.search("rick owens")
