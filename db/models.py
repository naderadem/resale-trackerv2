"""SQLAlchemy ORM models.

Table <-> concept mapping:
  listings            one row per marketplace listing ever ingested
                       (unique on source+external_id, so re-ingesting the
                       same query later upserts instead of duplicating)
  canonical_items     the "real" products we track prices for (e.g. Rick
                       Owens Geobasket) -- see seed_data.py
  listing_matches     a listing matched to a canonical item, with how
                       confident that match was and what method made it
  unmatched_listings  listings the matcher couldn't confidently place,
                       kept (with their raw title) for manual review
"""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ListingRecord(Base):
    """A single marketplace listing. Mirrors sources.base.Listing's fields.

    Named ListingRecord (not Listing) to keep it visually distinct from the
    plain dataclass every source adapter returns -- this is the persisted
    form of one.
    """

    __tablename__ = "listings"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_listings_source_external_id"),
    )

    id = Column(Integer, primary_key=True)
    source = Column(String(50), nullable=False)
    external_id = Column(String(255), nullable=False)
    title = Column(Text, nullable=False)
    brand = Column(String(150), nullable=True)
    price = Column(Float, nullable=False)
    currency = Column(String(10), nullable=False)
    size = Column(String(50), nullable=True)
    condition = Column(String(150), nullable=True)
    seller_rating = Column(Float, nullable=True)
    photo_count = Column(Integer, nullable=True)
    url = Column(Text, nullable=False)
    fetched_at = Column(DateTime(timezone=True), nullable=False)

    match = relationship(
        "ListingMatch", back_populates="listing", uselist=False, cascade="all, delete-orphan"
    )
    unmatched = relationship(
        "UnmatchedListing", back_populates="listing", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<ListingRecord {self.source}:{self.external_id} {self.title!r}>"


class CanonicalItem(Base):
    """A real product we track historical prices for, e.g. "Rick Owens Geobasket"."""

    __tablename__ = "canonical_items"

    id = Column(Integer, primary_key=True)
    brand = Column(String(150), nullable=False)
    # Product line (Margiela: Mainline/MM6/Replica) or era/house for the
    # Hedi Slimane brands (Dior Homme/Saint Laurent/Celine). Nullable for
    # brands where it doesn't apply (Rick Owens, CCP).
    line_or_era = Column(String(100), nullable=True)
    model_name = Column(String(200), nullable=False)
    notes = Column(Text, nullable=True)

    matches = relationship("ListingMatch", back_populates="canonical_item")

    def __repr__(self) -> str:
        return f"<CanonicalItem {self.brand} {self.line_or_era or ''} {self.model_name!r}>".replace(
            "  ", " "
        )


class ListingMatch(Base):
    """A listing matched to a canonical item."""

    __tablename__ = "listing_matches"

    id = Column(Integer, primary_key=True)
    listing_id = Column(
        Integer, ForeignKey("listings.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    canonical_item_id = Column(
        Integer, ForeignKey("canonical_items.id", ondelete="RESTRICT"), nullable=False
    )
    confidence = Column(Float, nullable=False)  # 0.0-1.0
    method = Column(String(50), nullable=False)  # e.g. "rapidfuzz"
    matched_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    listing = relationship("ListingRecord", back_populates="match")
    canonical_item = relationship("CanonicalItem", back_populates="matches")


class UnmatchedListing(Base):
    """A listing the matcher couldn't confidently place, kept for review."""

    __tablename__ = "unmatched_listings"

    id = Column(Integer, primary_key=True)
    listing_id = Column(
        Integer, ForeignKey("listings.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    raw_title = Column(Text, nullable=False)
    best_score = Column(Float, nullable=True)  # best confidence seen, even though it lost
    best_candidate_id = Column(
        Integer, ForeignKey("canonical_items.id", ondelete="SET NULL"), nullable=True
    )
    reason = Column(String(100), nullable=True)  # e.g. "below_threshold", "ambiguous_replica"
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    listing = relationship("ListingRecord", back_populates="unmatched")
    best_candidate = relationship("CanonicalItem")
