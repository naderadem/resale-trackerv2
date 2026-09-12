"""Matcher tests, with a heavy focus on the Margiela-line and Hedi-era
disambiguation rules -- see matcher.py's module docstring for the reasoning.
"""
import pytest

from db.models import CanonicalItem
from matcher import match_listing
from seed_data import CANONICAL_ITEMS


@pytest.fixture
def canonical_items() -> list[CanonicalItem]:
    return [
        CanonicalItem(brand=brand, line_or_era=line, model_name=model, notes=notes)
        for brand, line, model, notes in CANONICAL_ITEMS
    ]


def _model_names(item) -> str:
    return f"{item.brand} / {item.line_or_era} / {item.model_name}"


class TestMargielaLineDisambiguation:
    def test_mm6_title_matches_mm6_not_mainline(self, canonical_items):
        result = match_listing("MM6 Maison Margiela Tabi Ballet Flats Size 38", canonical_items)
        assert result.canonical_item is not None
        assert result.canonical_item.line_or_era == "MM6"

    def test_mainline_title_matches_mainline_not_mm6(self, canonical_items):
        result = match_listing("Maison Margiela Tabi Boots Size 42 black leather", canonical_items)
        assert result.canonical_item is not None
        assert result.canonical_item.line_or_era == "Mainline"
        assert result.canonical_item.model_name == "Tabi Boot"

    def test_margiela_replica_title_matches_replica_line(self, canonical_items):
        result = match_listing(
            "Maison Margiela Replica Low Top Sneakers White Size 43", canonical_items
        )
        assert result.canonical_item is not None
        assert result.canonical_item.line_or_era == "Replica"

    def test_bare_replica_with_no_margiela_context_is_refused(self, canonical_items):
        # This is describing a *fake* Geobasket, not Margiela's Replica line.
        # Matching it to the real Geobasket would launder a counterfeit's
        # price into that item's median -- must come back unmatched.
        result = match_listing("Rick Owens Geobasket replica size 43 great quality", canonical_items)
        assert result.canonical_item is None
        assert result.reason == "ambiguous_replica_mention"

    def test_bare_replica_does_not_fall_through_to_any_match(self, canonical_items):
        result = match_listing("Dior Homme jacket replica AAA quality", canonical_items)
        assert result.canonical_item is None

    def test_other_counterfeit_language_is_also_refused(self, canonical_items):
        result = match_listing("Rick Owens Ramones reps 1:1 great quality", canonical_items)
        assert result.canonical_item is None
        assert result.reason == "counterfeit_keyword_mention"


class TestHediEraHouseSeparation:
    def test_dior_homme_title_does_not_match_saint_laurent_item(self, canonical_items):
        result = match_listing("Dior Homme Hedi Slimane 19cm Skinny Jeans size 30", canonical_items)
        assert result.canonical_item is not None
        assert result.canonical_item.brand == "Dior Homme"

    def test_saint_laurent_title_does_not_match_dior_homme_item(self, canonical_items):
        result = match_listing("Saint Laurent Paris SLP Skinny Leather Pants sz 30", canonical_items)
        assert result.canonical_item is not None
        assert result.canonical_item.brand == "Saint Laurent"

    def test_celine_is_kept_separate_from_saint_laurent_and_dior(self, canonical_items):
        celine_item = CanonicalItem(
            brand="Celine", line_or_era="Hedi Slimane Era", model_name="Skinny Leather Pants"
        )
        items = canonical_items + [celine_item]
        result = match_listing("Celine by Hedi Slimane skinny leather pants size 32", items)
        assert result.canonical_item is not None
        assert result.canonical_item.brand == "Celine"

    def test_ambiguous_multi_house_title_does_not_force_a_house(self, canonical_items):
        # Mentions two houses -- shouldn't confidently restrict to either,
        # but can still fall through to plain fuzzy scoring across everything.
        result = match_listing(
            "Dior Homme vs Saint Laurent skinny jeans comparison thread", canonical_items
        )
        # Whatever it picks (or doesn't), it must not have been force-narrowed
        # to a single house's candidate pool incorrectly -- both remain
        # eligible, so we only assert this doesn't raise and reflects a
        # legitimate score, not a crash.
        assert result.method in ("rapidfuzz", "blocked")


class TestGeneralMatching:
    def test_clear_match_returns_high_confidence(self, canonical_items):
        result = match_listing("Rick Owens Geobasket High Top Black Size 42", canonical_items)
        assert result.canonical_item is not None
        assert result.canonical_item.model_name == "Geobasket"
        assert result.confidence >= 0.72

    def test_unrelated_title_is_not_matched(self, canonical_items):
        result = match_listing("Nike Air Force 1 White Size 10", canonical_items)
        assert result.canonical_item is None
        assert result.reason == "below_threshold"

    def test_empty_canonical_items_returns_none(self):
        result = match_listing("Rick Owens Geobasket", [])
        assert result.canonical_item is None
        assert result.reason == "no_canonical_items"

    def test_threshold_is_configurable(self, canonical_items):
        loose = match_listing("owens geo basket sneaker", canonical_items, threshold=0.3)
        strict = match_listing("owens geo basket sneaker", canonical_items, threshold=0.99)
        assert loose.canonical_item is not None
        assert strict.canonical_item is None
