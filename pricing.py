"""Price statistics and the suspicious-listing flag.

Two deliberate design choices here, both driven by the fact that this price
tier (resale designer fashion) is heavily counterfeited:

  1. compute_price_stats refuses to return a median/p25 below a minimum
     sample size. A "median" of two listings isn't a market price, it's
     noise, and presenting it as one invites acting on it.

  2. classify_listing does NOT treat "below median" as "deal". A price far
     below median is flagged "suspicious" instead -- in this market, an
     unusually low price is a stronger signal of a counterfeit or a scam
     than of a genuine bargain. Only a moderately-below-median price backed
     by decent trust signals (seller rating, photo count) is called a
     "deal"; the same price from a low-rating, few-photo seller is still
     "suspicious".
"""
import statistics
from dataclasses import dataclass
from typing import Literal, Optional, Sequence

DEFAULT_MIN_SAMPLE_SIZE = 5
DEFAULT_FLOOR_PCT = 0.4
DEFAULT_MIN_SELLER_RATING = 95.0
DEFAULT_MIN_PHOTO_COUNT = 3

Classification = Literal["deal", "suspicious", "normal", "no_data"]


@dataclass
class PriceStats:
    median: float
    p25: float
    count: int


def _percentile(ordered: Sequence[float], pct: float) -> float:
    """Linear-interpolation percentile over an already-sorted, non-empty sequence."""
    if len(ordered) == 1:
        return ordered[0]
    k = (pct / 100) * (len(ordered) - 1)
    lower = int(k)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (k - lower)


def compute_price_stats(
    prices: Sequence[float], min_sample_size: int = DEFAULT_MIN_SAMPLE_SIZE
) -> Optional[PriceStats]:
    """Median/p25/count for a set of matched listing prices.

    Returns None -- not a computed-but-meaningless stat -- when there are
    fewer than `min_sample_size` observations.
    """
    clean = [p for p in prices if p is not None]
    if len(clean) < min_sample_size:
        return None
    ordered = sorted(clean)
    return PriceStats(
        median=statistics.median(ordered),
        p25=_percentile(ordered, 25),
        count=len(ordered),
    )


def classify_listing(
    price: float,
    stats: Optional[PriceStats],
    seller_rating: Optional[float] = None,
    photo_count: Optional[int] = None,
    floor_pct: float = DEFAULT_FLOOR_PCT,
    min_seller_rating: float = DEFAULT_MIN_SELLER_RATING,
    min_photo_count: int = DEFAULT_MIN_PHOTO_COUNT,
) -> Classification:
    """Classify a matched listing's price against its canonical item's stats.

      "no_data"    -- no reliable price stats yet (see compute_price_stats)
      "suspicious" -- price is below `floor_pct` of median (regardless of
                      trust signals), or below median without strong-enough
                      seller rating and photo count
      "deal"       -- below median, but seller rating and photo count both
                      clear their bars
      "normal"     -- at or above median
    """
    if stats is None:
        return "no_data"
    if stats.median <= 0:
        return "no_data"

    ratio = price / stats.median

    if ratio < floor_pct:
        return "suspicious"

    if ratio < 1.0:
        trustworthy = (
            seller_rating is not None
            and seller_rating >= min_seller_rating
            and photo_count is not None
            and photo_count >= min_photo_count
        )
        return "deal" if trustworthy else "suspicious"

    return "normal"
