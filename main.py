"""resale-tracker CLI.

Subcommands:
    seed                 populate canonical_items with seed data (idempotent)
    ingest <query>        search eBay and upsert results into listings
    match                 match unprocessed listings against canonical_items
    rematch               clear all matches/unmatched rows and match everything again
    prices                show price stats + flagged listings per canonical item
    unmatched              list listings the matcher couldn't confidently place
    db-check               print row counts for every table

Run `python main.py <subcommand> --help` for per-command options.
"""
import argparse
import sys

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

import config
from db.models import CanonicalItem, ListingMatch, ListingRecord, UnmatchedListing
from db.repository import (
    get_canonical_items,
    get_matched_listings_for_canonical_item,
    get_unmatched_listings,
    get_unprocessed_listings,
    record_match,
    record_unmatched,
    upsert_listing,
)
from db.session import get_session
from matcher import match_listing
from pricing import classify_listing, compute_price_stats
from seed_data import CANONICAL_ITEMS, seed_canonical_items
from sources.ebay import EbayAuthError, EbaySearchError, EbaySource


def _get_session_or_exit():
    """Open a DB session, failing with a friendly hint rather than a traceback."""
    session = get_session()
    try:
        session.execute(text("SELECT 1"))
    except OperationalError as exc:
        print("Could not connect to Postgres. Is it running?")
        print("  Try: docker compose up -d   (then: alembic upgrade head)")
        print(f"  ({exc})")
        sys.exit(1)
    return session


def _item_label(item) -> str:
    parts = [item.brand]
    if item.line_or_era:
        parts.append(item.line_or_era)
    parts.append(item.model_name)
    return " ".join(parts)


def cmd_seed(args) -> None:
    session = _get_session_or_exit()
    inserted = seed_canonical_items(session)
    already_present = len(CANONICAL_ITEMS) - inserted
    print(f"Seeded {inserted} new canonical item(s), {already_present} already present.")


def cmd_ingest(args) -> None:
    try:
        source = EbaySource()
    except ValueError as exc:
        print(f"Config error: {exc}")
        sys.exit(1)

    try:
        listings = source.search(args.query)
    except (EbayAuthError, EbaySearchError) as exc:
        print(f"eBay request failed: {exc}")
        sys.exit(1)

    session = _get_session_or_exit()
    for listing in listings:
        upsert_listing(session, listing)

    print(f"Ingested {len(listings)} listing(s) for query {args.query!r}.")


def _run_matching(session, listings, canonical_items, threshold, dry_run):
    """Shared core of `match` and `rematch`. In dry-run mode, nothing is
    written -- each listing's match (or lack of one) is just printed.
    """
    matched_count = 0
    unmatched_count = 0
    for listing in listings:
        result = match_listing(listing.title, canonical_items, threshold=threshold)

        if dry_run:
            if result.canonical_item is not None:
                print(
                    f"  MATCH    conf={result.confidence:.2f}  {listing.title!r}\n"
                    f"           -> {_item_label(result.canonical_item)}"
                )
                matched_count += 1
            else:
                near_miss = (
                    f" (closest: {_item_label(result.best_candidate)}, conf={result.confidence:.2f})"
                    if result.best_candidate
                    else ""
                )
                print(f"  NO MATCH reason={result.reason} {listing.title!r}{near_miss}")
                unmatched_count += 1
            continue

        if result.canonical_item is not None:
            record_match(
                session, listing.id, result.canonical_item.id, result.confidence, result.method
            )
            matched_count += 1
        else:
            best_score = result.confidence if result.method == "rapidfuzz" else None
            best_candidate_id = result.best_candidate.id if result.best_candidate else None
            record_unmatched(
                session,
                listing.id,
                listing.title,
                best_score=best_score,
                best_candidate_id=best_candidate_id,
                reason=result.reason,
            )
            unmatched_count += 1

    return matched_count, unmatched_count


def cmd_match(args) -> None:
    session = _get_session_or_exit()
    canonical_items = get_canonical_items(session)
    if not canonical_items:
        print("No canonical items yet -- run `python main.py seed` first.")
        sys.exit(1)

    listings = get_unprocessed_listings(session)
    if not listings:
        print("No unprocessed listings to match. Run `python main.py ingest <query>` first.")
        return

    if args.dry_run:
        print(f"Dry run against {len(listings)} unprocessed listing(s) -- nothing will be written.")
    matched, unmatched = _run_matching(session, listings, canonical_items, args.threshold, args.dry_run)

    verb = "Would match" if args.dry_run else "Matched"
    print(f"{verb} {matched}, unmatched {unmatched} (of {len(listings)} processed).")


def cmd_rematch(args) -> None:
    session = _get_session_or_exit()
    canonical_items = get_canonical_items(session)
    if not canonical_items:
        print("No canonical items yet -- run `python main.py seed` first.")
        sys.exit(1)

    deleted_matches = session.query(ListingMatch).delete()
    deleted_unmatched = session.query(UnmatchedListing).delete()
    session.commit()
    print(f"Cleared {deleted_matches} match(es) and {deleted_unmatched} unmatched row(s).")

    listings = session.query(ListingRecord).order_by(ListingRecord.id).all()
    if not listings:
        print("No listings in the database to match.")
        return

    matched, unmatched = _run_matching(session, listings, canonical_items, args.threshold, dry_run=False)
    print(f"Rematched {len(listings)} listing(s): {matched} matched, {unmatched} unmatched.")


def cmd_prices(args) -> None:
    session = _get_session_or_exit()
    canonical_items = get_canonical_items(session)
    if not canonical_items:
        print("No canonical items yet -- run `python main.py seed` first.")
        sys.exit(1)

    for item in canonical_items:
        listing_records = get_matched_listings_for_canonical_item(session, item.id)
        stats = compute_price_stats(
            [lr.price for lr in listing_records], min_sample_size=args.min_sample_size
        )

        if stats is None:
            print(
                f"{_item_label(item)}: insufficient data "
                f"(n={len(listing_records)}, need >= {args.min_sample_size})"
            )
            continue

        print(
            f"{_item_label(item)}: median=${stats.median:.2f} "
            f"p25=${stats.p25:.2f} n={stats.count}"
        )
        for lr in listing_records:
            classification = classify_listing(
                lr.price,
                stats,
                seller_rating=lr.seller_rating,
                photo_count=lr.photo_count,
                floor_pct=args.floor_pct,
                min_seller_rating=args.min_seller_rating,
                min_photo_count=args.min_photo_count,
            )
            if classification in ("deal", "suspicious"):
                print(f"    [{classification.upper()}] ${lr.price:.2f} - {lr.title} ({lr.url})")


def cmd_unmatched(args) -> None:
    session = _get_session_or_exit()
    rows = get_unmatched_listings(session)
    if not rows:
        print("No unmatched listings.")
        return

    for row in rows:
        listing = row.listing
        near_miss = f" near_miss={_item_label(row.best_candidate)}" if row.best_candidate else ""
        print(
            f"#{row.id} reason={row.reason} best_score={row.best_score}{near_miss}\n"
            f"    title={row.raw_title!r}\n"
            f"    price=${listing.price:.2f} url={listing.url}"
        )


def cmd_db_check(args) -> None:
    session = _get_session_or_exit()
    counts = [
        ("listings", session.query(ListingRecord).count()),
        ("canonical_items", session.query(CanonicalItem).count()),
        ("listing_matches", session.query(ListingMatch).count()),
        ("unmatched_listings", session.query(UnmatchedListing).count()),
    ]
    width = max(len(name) for name, _ in counts)
    for name, count in counts:
        print(f"{name:<{width}}  {count}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="resale-tracker CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_seed = sub.add_parser("seed", help="Populate canonical_items with seed data")
    p_seed.set_defaults(func=cmd_seed)

    p_ingest = sub.add_parser("ingest", help="Search eBay and upsert results into listings")
    p_ingest.add_argument("query", help="Search query, e.g. \"rick owens geobasket\"")
    p_ingest.set_defaults(func=cmd_ingest)

    p_match = sub.add_parser("match", help="Match unprocessed listings against canonical_items")
    p_match.add_argument("--threshold", type=float, default=config.MATCH_THRESHOLD)
    p_match.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Print what would match to what, without writing to the database",
    )
    p_match.set_defaults(func=cmd_match)

    p_rematch = sub.add_parser(
        "rematch",
        help="Clear listing_matches/unmatched_listings and match every listing again",
    )
    p_rematch.add_argument("--threshold", type=float, default=config.MATCH_THRESHOLD)
    p_rematch.set_defaults(func=cmd_rematch)

    p_prices = sub.add_parser(
        "prices", help="Show price stats and flagged listings per canonical item"
    )
    p_prices.add_argument(
        "--min-sample-size", type=int, default=config.MIN_SAMPLE_SIZE, dest="min_sample_size"
    )
    p_prices.add_argument(
        "--floor-pct", type=float, default=config.SUSPICIOUS_FLOOR_PCT, dest="floor_pct"
    )
    p_prices.add_argument(
        "--min-seller-rating",
        type=float,
        default=config.MIN_SELLER_RATING,
        dest="min_seller_rating",
    )
    p_prices.add_argument(
        "--min-photo-count", type=int, default=config.MIN_PHOTO_COUNT, dest="min_photo_count"
    )
    p_prices.set_defaults(func=cmd_prices)

    p_unmatched = sub.add_parser(
        "unmatched", help="List listings the matcher couldn't confidently place"
    )
    p_unmatched.set_defaults(func=cmd_unmatched)

    p_db_check = sub.add_parser("db-check", help="Print row counts for every table")
    p_db_check.set_defaults(func=cmd_db_check)

    return parser


def main() -> None:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
