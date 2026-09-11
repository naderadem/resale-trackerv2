"""Shared interface that every marketplace adapter implements.

The rest of resale-tracker (matching against historical medians, alerting,
storage once those exist) only ever talks to `ListingSource` and `Listing`.
It never needs to know whether a given result came from eBay, Grailed, or
anywhere else -- that knowledge is fully contained in each adapter.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Listing:
    """A single normalized marketplace listing.

    Every adapter maps whatever shape its source's API/HTML returns onto
    this dataclass. Fields that a given source can't provide should be
    left as None rather than guessed.
    """

    source: str  # e.g. "ebay", "grailed"
    external_id: str  # the source's own id for this listing
    title: str
    brand: Optional[str]
    price: float
    currency: str
    size: Optional[str]
    condition: Optional[str]
    seller_rating: Optional[float]
    photo_count: Optional[int]
    url: str
    fetched_at: datetime


class ListingSource(ABC):
    """Abstract base class for a marketplace adapter."""

    @abstractmethod
    def search(self, query: str) -> list[Listing]:
        """Search this source for `query` and return normalized Listings.

        Implementations are responsible for their own auth, rate limiting,
        caching, and error handling -- callers should only ever see a
        list[Listing] come back (or an exception documented by that
        adapter), never a source-specific response object.
        """
        raise NotImplementedError
