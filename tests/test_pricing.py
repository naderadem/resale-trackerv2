import pytest

from pricing import PriceStats, classify_listing, compute_price_stats


class TestComputePriceStats:
    def test_returns_none_below_minimum_sample_size(self):
        assert compute_price_stats([500, 550, 600], min_sample_size=5) is None

    def test_returns_stats_at_exactly_the_minimum_sample_size(self):
        stats = compute_price_stats([500, 550, 600, 650, 700], min_sample_size=5)
        assert stats is not None
        assert stats.count == 5

    def test_median_and_p25_are_correct(self):
        prices = [400, 500, 600, 700, 800]  # already sorted, odd count
        stats = compute_price_stats(prices, min_sample_size=5)
        assert stats.median == 600
        assert stats.p25 == 500  # linear-interpolation p25 of this set

    def test_unsorted_input_is_handled(self):
        prices = [800, 400, 700, 500, 600]
        stats = compute_price_stats(prices, min_sample_size=5)
        assert stats.median == 600

    def test_none_values_are_ignored_when_counting(self):
        prices = [500, 550, 600, None, None]
        assert compute_price_stats(prices, min_sample_size=5) is None
        assert compute_price_stats(prices, min_sample_size=3) is not None

    def test_default_min_sample_size_is_five(self):
        assert compute_price_stats([100, 200, 300, 400]) is None
        assert compute_price_stats([100, 200, 300, 400, 500]) is not None


class TestClassifyListing:
    @pytest.fixture
    def stats(self) -> PriceStats:
        return PriceStats(median=1000.0, p25=800.0, count=10)

    def test_no_stats_means_no_data(self):
        assert classify_listing(500, None) == "no_data"

    def test_at_or_above_median_is_normal(self, stats):
        assert classify_listing(1000, stats) == "normal"
        assert classify_listing(1200, stats) == "normal"

    def test_far_below_floor_is_suspicious_even_with_great_signals(self, stats):
        # 300 / 1000 = 0.3, below the default 0.4 floor -- suspicious no
        # matter how trustworthy the seller looks.
        result = classify_listing(
            300, stats, seller_rating=100.0, photo_count=20, floor_pct=0.4
        )
        assert result == "suspicious"

    def test_below_median_with_good_signals_is_a_deal(self, stats):
        # 850 / 1000 = 0.85 -- below median but above the floor, and the
        # seller looks legit.
        result = classify_listing(
            850, stats, seller_rating=99.0, photo_count=8, min_seller_rating=95.0, min_photo_count=3
        )
        assert result == "deal"

    def test_below_median_with_poor_seller_rating_is_suspicious(self, stats):
        result = classify_listing(
            850, stats, seller_rating=80.0, photo_count=8, min_seller_rating=95.0, min_photo_count=3
        )
        assert result == "suspicious"

    def test_below_median_with_too_few_photos_is_suspicious(self, stats):
        result = classify_listing(
            850, stats, seller_rating=99.0, photo_count=1, min_seller_rating=95.0, min_photo_count=3
        )
        assert result == "suspicious"

    def test_below_median_with_missing_signals_is_suspicious(self, stats):
        # No seller_rating/photo_count data at all -- can't vouch for it.
        assert classify_listing(850, stats) == "suspicious"

    def test_floor_pct_is_configurable(self, stats):
        # 600/1000 = 0.6 -- suspicious under a strict 0.7 floor, but a
        # plain below-median case (needing good signals) under 0.4.
        assert classify_listing(600, stats, floor_pct=0.7) == "suspicious"
        result = classify_listing(
            600, stats, floor_pct=0.4, seller_rating=99.0, photo_count=10
        )
        assert result == "deal"
