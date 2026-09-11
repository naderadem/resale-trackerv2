import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def ebay_search_response() -> dict:
    """A realistic (trimmed) eBay Browse API item_summary/search response."""
    return json.loads((FIXTURES_DIR / "ebay_item_summary_search.json").read_text())
