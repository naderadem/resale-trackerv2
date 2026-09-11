"""Stage 1 CLI: run a single search against a source and print results.

Usage:
    python main.py "rick owens geobasket"

Currently only the eBay adapter is wired up here. Since parse_listings()
in sources/ebay.py isn't implemented yet, this will authenticate, hit the
Browse API, print one sample raw listing as JSON, and then stop with a
NotImplementedError -- that's expected until you implement parse_listings.
"""
import sys

from dotenv import load_dotenv

from sources.ebay import EbayAuthError, EbaySearchError, EbaySource


def main() -> None:
    load_dotenv()

    if len(sys.argv) < 2:
        print('Usage: python main.py "<search query>"')
        sys.exit(1)

    query = " ".join(sys.argv[1:])

    try:
        source = EbaySource()
    except ValueError as exc:
        print(f"Config error: {exc}")
        sys.exit(1)

    try:
        listings = source.search(query)
    except NotImplementedError:
        print(
            "\nsearch() reached parse_listings(), which isn't implemented yet.\n"
            "See the sample raw listing printed above and sources/ebay.py."
        )
        return
    except (EbayAuthError, EbaySearchError) as exc:
        print(f"eBay request failed: {exc}")
        sys.exit(1)

    for listing in listings:
        print(listing)


if __name__ == "__main__":
    main()
