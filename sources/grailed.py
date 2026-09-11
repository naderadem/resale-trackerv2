"""Grailed adapter -- NOT IMPLEMENTED.

Grailed has no public search API. Before writing anything that talks to it,
two things happened instead:

  1. robots.txt was fetched and reviewed (see docs/grailed_robots.txt and the
     README). Notably, `Disallow: /search` -- the search results page itself
     is disallowed for crawlers, alongside /users/*, /sell/, /sold, and others.
  2. docs/grailed_devtools_inspection.md has step-by-step devtools instructions
     for inspecting, by hand, what network requests the Grailed search page
     actually makes -- so you can see for yourself what's publicly served
     before deciding whether, and how, to implement this adapter.

Do not implement search() below until you've done that review and made a
deliberate decision about it.
"""
from sources.base import Listing, ListingSource


class GrailedSource(ListingSource):
    """Stub. Implements the ListingSource interface shape only."""

    def __init__(self, *args, **kwargs):
        pass

    def search(self, query: str) -> list[Listing]:
        raise NotImplementedError(
            "GrailedSource is not implemented. See the module docstring in "
            "sources/grailed.py and docs/grailed_devtools_inspection.md."
        )
