"""Query and upsert functions the CLI uses. Keeps raw SQLAlchemy out of main.py."""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from db.models import CanonicalItem, ListingMatch, ListingRecord, SentAlert, UnmatchedListing
from sources.base import Listing


def upsert_listing(session: Session, listing: Listing) -> ListingRecord:
    """Insert a listing, or update it in place if (source, external_id) exists.

    Uses Postgres's INSERT ... ON CONFLICT so repeated ingests of the same
    query update price/condition/etc. on existing rows instead of piling up
    duplicates.
    """
    values = dict(
        source=listing.source,
        external_id=listing.external_id,
        title=listing.title,
        brand=listing.brand,
        price=listing.price,
        currency=listing.currency,
        size=listing.size,
        condition=listing.condition,
        seller_rating=listing.seller_rating,
        photo_count=listing.photo_count,
        url=listing.url,
        fetched_at=listing.fetched_at,
    )
    stmt = pg_insert(ListingRecord).values(**values)
    update_cols = {
        col: getattr(stmt.excluded, col)
        for col in values
        if col not in ("source", "external_id")
    }
    stmt = stmt.on_conflict_do_update(
        index_elements=["source", "external_id"],
        set_=update_cols,
    ).returning(ListingRecord.id)

    listing_id = session.execute(stmt).scalar_one()
    session.commit()
    return session.get(ListingRecord, listing_id)


def get_canonical_items(session: Session) -> list[CanonicalItem]:
    return list(session.execute(select(CanonicalItem)).scalars())


def get_unprocessed_listings(session: Session) -> list[ListingRecord]:
    """Listings with neither a match nor an unmatched-review row yet.

    This is what `match` operates on by default, so re-running it is cheap
    and idempotent -- it only ever processes new listings.
    """
    stmt = (
        select(ListingRecord)
        .outerjoin(ListingMatch, ListingMatch.listing_id == ListingRecord.id)
        .outerjoin(UnmatchedListing, UnmatchedListing.listing_id == ListingRecord.id)
        .where(ListingMatch.id.is_(None), UnmatchedListing.id.is_(None))
    )
    return list(session.execute(stmt).scalars())


def record_match(
    session: Session, listing_id: int, canonical_item_id: int, confidence: float, method: str
) -> ListingMatch:
    match = ListingMatch(
        listing_id=listing_id,
        canonical_item_id=canonical_item_id,
        confidence=confidence,
        method=method,
    )
    session.add(match)
    session.commit()
    return match


def record_unmatched(
    session: Session,
    listing_id: int,
    raw_title: str,
    best_score: Optional[float] = None,
    best_candidate_id: Optional[int] = None,
    reason: Optional[str] = None,
) -> UnmatchedListing:
    row = UnmatchedListing(
        listing_id=listing_id,
        raw_title=raw_title,
        best_score=best_score,
        best_candidate_id=best_candidate_id,
        reason=reason,
    )
    session.add(row)
    session.commit()
    return row


def get_matched_listings_for_canonical_item(
    session: Session, canonical_item_id: int
) -> list[ListingRecord]:
    stmt = (
        select(ListingRecord)
        .join(ListingMatch, ListingMatch.listing_id == ListingRecord.id)
        .where(ListingMatch.canonical_item_id == canonical_item_id)
    )
    return list(session.execute(stmt).scalars())


def get_unmatched_listings(session: Session) -> list[UnmatchedListing]:
    stmt = select(UnmatchedListing).order_by(UnmatchedListing.created_at.desc())
    return list(session.execute(stmt).scalars())


def has_been_alerted(session: Session, listing_id: int) -> bool:
    """True if this listing has already triggered an alert.

    Callers must check this before sending -- record_alert doesn't guard
    against being called twice for the same listing (that's the caller's
    job, same as the rest of this module).
    """
    stmt = select(SentAlert.id).where(SentAlert.listing_id == listing_id)
    return session.execute(stmt).first() is not None


def record_alert(session: Session, listing_id: int, classification: str) -> SentAlert:
    row = SentAlert(listing_id=listing_id, classification=classification)
    session.add(row)
    session.commit()
    return row
