import pytest

from size_normalization import (
    normalize_apparel_size,
    normalize_footwear_size,
    normalize_size,
)


class TestFootwearExplicitUnits:
    @pytest.mark.parametrize(
        "raw,expected_eu",
        [
            ("EU 42", 42.0),
            ("42 EU", 42.0),
            ("IT 42", 42.0),
            ("FR 43.5", 43.5),
        ],
    )
    def test_eu_is_used_directly(self, raw, expected_eu):
        result = normalize_footwear_size(raw)
        assert result.system_detected == "EU"
        assert result.canonical == expected_eu
        assert result.is_estimated is False

    @pytest.mark.parametrize(
        "raw,expected_eu",
        [("US 9", 42.5), ("US 9.5", 43.0), ("9 US", 42.5), ("US 10.5", 44.5)],
    )
    def test_us_converts_to_eu(self, raw, expected_eu):
        result = normalize_footwear_size(raw)
        assert result.system_detected == "US"
        assert result.canonical == expected_eu
        assert result.is_estimated is False

    def test_uk_converts_to_eu(self):
        result = normalize_footwear_size("UK 8")
        assert result.system_detected == "UK"
        assert result.canonical == 42.5  # UK8 == US9 target

    @pytest.mark.parametrize(
        "raw,expected_eu",
        [("JP 27", 42.0), ("27cm", 42.0), ("27.5 JP", 42.5)],
    )
    def test_jp_converts_to_eu(self, raw, expected_eu):
        result = normalize_footwear_size(raw)
        assert result.system_detected == "JP"
        assert result.canonical == expected_eu

    def test_us_size_outside_table_is_detected_but_not_converted(self):
        result = normalize_footwear_size("US 15")
        assert result.system_detected == "US"
        assert result.canonical is None  # detected the system, no table entry to convert with


class TestFootwearBareNumbers:
    def test_bare_number_in_eu_range_is_confident(self):
        result = normalize_footwear_size("42")
        assert result.system_detected == "EU"
        assert result.canonical == 42.0
        assert result.is_estimated is False

    def test_bare_half_size_in_eu_range(self):
        result = normalize_footwear_size("44.5")
        assert result.canonical == 44.5
        assert result.is_estimated is False

    def test_bare_number_in_us_uk_band_defaults_to_us_and_is_flagged_estimated(self):
        result = normalize_footwear_size("9")
        assert result.system_detected == "US"
        assert result.canonical == 42.5  # US9 -> EU42.5
        assert result.is_estimated is True  # could plausibly have meant UK9 instead

    def test_bare_number_out_of_all_ranges_is_unparseable(self):
        result = normalize_footwear_size("60")
        assert result.canonical is None
        assert result.raw == "60"


class TestFootwearUnparseable:
    @pytest.mark.parametrize("raw", ["", None, "one size", "XL"])
    def test_no_usable_number_returns_none(self, raw):
        result = normalize_footwear_size(raw)
        assert result.canonical is None
        assert result.category == "footwear"

    def test_slash_ambiguity_is_not_guessed(self):
        result = normalize_footwear_size("9/9.5")
        assert result.canonical is None

    def test_or_ambiguity_is_not_guessed(self):
        result = normalize_footwear_size("42 or 43")
        assert result.canonical is None

    def test_raw_string_is_always_preserved(self):
        result = normalize_footwear_size("garbage nonsense")
        assert result.raw == "garbage nonsense"
        assert result.canonical is None


class TestApparelAlpha:
    @pytest.mark.parametrize(
        "raw,expected_eu",
        [("S", 48), ("M", 50), ("L", 52), ("XL", 54), ("XXL", 56), ("3XL", 58), ("XXS", 44)],
    )
    def test_alpha_codes_map_to_eu_tailoring_scale(self, raw, expected_eu):
        result = normalize_apparel_size(raw)
        assert result.system_detected == "ALPHA"
        assert result.canonical == expected_eu
        assert result.is_estimated is True  # alpha->EU is always approximate

    @pytest.mark.parametrize(
        "raw,expected_eu", [("Medium", 50), ("Large", 52), ("Extra Large", 54), ("small", 48)]
    )
    def test_alpha_words_map_the_same_as_codes(self, raw, expected_eu):
        result = normalize_apparel_size(raw)
        assert result.canonical == expected_eu

    def test_alpha_embedded_in_a_longer_string(self):
        result = normalize_apparel_size("size L")
        assert result.canonical == 52


class TestApparelFitsLikePhrasing:
    def test_fits_like_a_large(self):
        result = normalize_apparel_size("fits like a large")
        assert result.system_detected == "ALPHA"
        assert result.canonical == 52
        assert result.is_estimated is True

    def test_fits_like_an_xl(self):
        result = normalize_apparel_size("fits like an XL")
        assert result.canonical == 54

    def test_fits_true_to_size_with_no_size_given_is_unparseable(self):
        result = normalize_apparel_size("fits true to size")
        assert result.canonical is None

    def test_fits_true_to_size_48(self):
        result = normalize_apparel_size("fits true to size 48")
        assert result.canonical == 48
        assert result.is_estimated is True


class TestApparelNumericScales:
    @pytest.mark.parametrize("raw,expected", [("48", 48), ("52", 52), ("EU 48", 48), ("IT 50", 50)])
    def test_bare_and_eu_tagged_numbers_are_tailoring_scale(self, raw, expected):
        result = normalize_apparel_size(raw)
        assert result.system_detected == "EU"
        assert result.canonical == expected

    @pytest.mark.parametrize("raw,expected", [("32", 32), ("30", 30), ("34", 34)])
    def test_bare_numbers_in_denim_range_are_waist_measurements(self, raw, expected):
        result = normalize_apparel_size(raw)
        assert result.system_detected == "WAIST_IN"
        assert result.canonical == expected

    def test_boundary_42_is_tailoring_not_denim(self):
        result = normalize_apparel_size("42")
        assert result.system_detected == "EU"
        assert result.canonical == 42

    def test_boundary_41_is_denim_not_tailoring(self):
        result = normalize_apparel_size("41")
        assert result.system_detected == "WAIST_IN"
        assert result.canonical == 41

    def test_us_tagged_jacket_size_is_detected_but_not_converted(self):
        # This is the case that would otherwise be silently (and wrongly)
        # misread as a 38" denim waist -- US jacket sizing is a different
        # scale from EU tailoring, and we don't have a confident table for
        # it, so we say "detected US" rather than guess a number.
        result = normalize_apparel_size("US 38")
        assert result.system_detected == "US"
        assert result.canonical is None

    def test_uk_tagged_jacket_size_is_detected_but_not_converted(self):
        result = normalize_apparel_size("UK 40")
        assert result.system_detected == "UK"
        assert result.canonical is None


class TestApparelUnparseable:
    @pytest.mark.parametrize("raw", ["", None, "one size", "OS", "O/S", "free size"])
    def test_no_size_phrases_return_none(self, raw):
        result = normalize_apparel_size(raw)
        assert result.canonical is None
        assert result.category == "apparel"

    @pytest.mark.parametrize("raw", ["L/XL", "48/50", "42 or 44"])
    def test_ambiguous_dual_sizes_are_not_guessed(self, raw):
        result = normalize_apparel_size(raw)
        assert result.canonical is None

    def test_number_outside_every_known_range_is_unparseable(self):
        result = normalize_apparel_size("15")  # not a plausible tailoring or denim size
        assert result.canonical is None

    def test_free_text_with_no_signal_is_unparseable(self):
        result = normalize_apparel_size("runs small, would size up")
        assert result.canonical is None

    def test_raw_is_always_preserved(self):
        result = normalize_apparel_size("some unrecognizable text")
        assert result.raw == "some unrecognizable text"


class TestDispatch:
    def test_normalize_size_dispatches_to_footwear(self):
        result = normalize_size("EU 42", category="footwear")
        assert result.category == "footwear"
        assert result.canonical == 42.0

    def test_normalize_size_dispatches_to_apparel(self):
        result = normalize_size("L", category="apparel")
        assert result.category == "apparel"
        assert result.canonical == 52

    def test_normalize_size_rejects_unknown_category(self):
        with pytest.raises(ValueError):
            normalize_size("42", category="hats")  # type: ignore[arg-type]
