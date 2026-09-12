"""Size normalization: EU/US/UK/JP size strings (plus free text like "fits
like a large") into one canonical number per category.

Footwear and apparel are normalized completely separately and never share
a canonical scale -- the same bare number means unrelated things in each
(EU shoe size 46 is a large shoe; EU tailoring size 46 is a small jacket),
so conflating them would be worse than not normalizing at all.

  footwear canonical: an EU shoe-size float (e.g. 42.5). EU is used as the
      internal scale because it's the finest-grained, most consistently
      tagged system across these brands (Rick Owens footwear ships EU-
      tagged); US/UK/JP all have a documented conversion into it below.

  apparel canonical: either an EU tailoring-size int (Margiela mainline,
      Dior Homme, and Saint Laurent tailoring/outerwear are tagged in the
      EU 42-60ish scale) or a waist measurement in inches (denim, e.g.
      DRKSHDW). These two ranges don't overlap, so a bare number usually
      tells them apart; alpha sizes (S/M/L) and "fits like a large" style
      free text are mapped onto the nearer EU tailoring point, flagged
      `is_estimated` since that mapping is inherently approximate -- it's
      a seller's impression, not a number read off a tag.

Anything unparseable, or genuinely ambiguous (a seller writing "L/XL",
"one size", a bare number in a range two systems share, or a size with no
usable signal at all) keeps the raw string and returns canonical=None --
never a guessed number.
"""
import re
from dataclasses import dataclass
from typing import Literal, Optional

Category = Literal["footwear", "apparel"]


@dataclass
class NormalizedSize:
    raw: str
    category: Optional[Category]
    system_detected: Optional[str]  # "EU", "US", "UK", "JP", "ALPHA", "WAIST_IN", or None
    canonical: Optional[float]
    is_estimated: bool = False
    """True when `canonical` was inferred (an unlabeled bare number, an
    alpha size, or free text like "fits like a large") rather than read
    directly off an explicit, unit-tagged size."""


# ---------------------------------------------------------------- footwear

# Men's shoe size conversion tables. Approximate -- exact charts vary half
# a size by brand -- but internally consistent, which is what matters for
# comparing prices across listings run through the same table.
US_TO_EU_FOOTWEAR = {
    6.0: 38.5, 6.5: 39.0, 7.0: 40.0, 7.5: 40.5, 8.0: 41.0, 8.5: 42.0,
    9.0: 42.5, 9.5: 43.0, 10.0: 44.0, 10.5: 44.5, 11.0: 45.0, 11.5: 45.5,
    12.0: 46.0, 12.5: 46.5, 13.0: 47.0, 13.5: 47.5, 14.0: 48.0,
}
# UK men's runs one full size below US, onto the same EU targets.
UK_TO_EU_FOOTWEAR = {round(us - 1, 1): eu for us, eu in US_TO_EU_FOOTWEAR.items()}

# JP sizes are foot length in cm.
JP_TO_EU_FOOTWEAR = {
    24.0: 38.0, 24.5: 38.5, 25.0: 39.5, 25.5: 40.0, 26.0: 40.5, 26.5: 41.0,
    27.0: 42.0, 27.5: 42.5, 28.0: 43.0, 28.5: 44.0, 29.0: 44.5, 29.5: 45.5,
    30.0: 46.0,
}

EU_FOOTWEAR_RANGE = (35.0, 49.0)
US_UK_FOOTWEAR_RANGE = (5.0, 14.0)

_NUMBER_RE = re.compile(r"(\d{1,2}(?:\.\d)?)")
_EU_UNIT_RE = re.compile(r"\b(eu|eur|it|fr)\b", re.IGNORECASE)
_US_UNIT_RE = re.compile(r"\bus\b", re.IGNORECASE)
_UK_UNIT_RE = re.compile(r"\buk\b", re.IGNORECASE)
_JP_UNIT_RE = re.compile(r"\b(jp|jpn|japan)\b", re.IGNORECASE)
_CM_UNIT_RE = re.compile(r"cm\b", re.IGNORECASE)  # no leading \b: "27cm" has no boundary before c
# A seller hedging between two values ("9/9.5", "42 or 43", "S/M") is
# telling us they don't know either -- don't pick one for them.
_AMBIGUOUS_RE = re.compile(
    r"\d\s*/\s*\d|\bor\b|\b(xxs|xs|s|m|l|xl|xxl|xxxl|3xl)\s*/\s*(xxs|xs|s|m|l|xl|xxl|xxxl|3xl)\b",
    re.IGNORECASE,
)


def _extract_number(text: str) -> Optional[float]:
    match = _NUMBER_RE.search(text)
    return float(match.group(1)) if match else None


def normalize_footwear_size(raw: Optional[str]) -> NormalizedSize:
    """Normalize a footwear size string to a canonical EU size."""
    raw_str = raw or ""
    stripped = raw_str.strip()
    empty = NormalizedSize(raw=raw_str, category="footwear", system_detected=None, canonical=None)
    if not stripped:
        return empty
    if _AMBIGUOUS_RE.search(stripped):
        return empty

    number = _extract_number(stripped)
    if number is None:
        return empty

    if _EU_UNIT_RE.search(stripped):
        return NormalizedSize(raw_str, "footwear", "EU", number)
    if _US_UNIT_RE.search(stripped):
        return NormalizedSize(raw_str, "footwear", "US", US_TO_EU_FOOTWEAR.get(number))
    if _UK_UNIT_RE.search(stripped):
        return NormalizedSize(raw_str, "footwear", "UK", UK_TO_EU_FOOTWEAR.get(number))
    if _JP_UNIT_RE.search(stripped) or _CM_UNIT_RE.search(stripped):
        return NormalizedSize(raw_str, "footwear", "JP", JP_TO_EU_FOOTWEAR.get(number))

    # No explicit unit. EU and US/UK men's ranges don't overlap, so the
    # number alone is enough signal outside the US/UK band; inside it, US
    # and UK differ by a full size and we genuinely can't tell which was
    # meant, so we default to US (the overwhelming convention for
    # unlabeled sizes on eBay's US marketplace) but flag it as estimated.
    if EU_FOOTWEAR_RANGE[0] <= number <= EU_FOOTWEAR_RANGE[1]:
        # Not ambiguous in practice -- no US/UK men's shoe size reaches
        # this range unlabeled, so this is confident, not a guess.
        return NormalizedSize(raw_str, "footwear", "EU", number, is_estimated=False)
    if US_UK_FOOTWEAR_RANGE[0] <= number <= US_UK_FOOTWEAR_RANGE[1]:
        return NormalizedSize(
            raw_str, "footwear", "US", US_TO_EU_FOOTWEAR.get(number), is_estimated=True
        )
    return empty


# ----------------------------------------------------------------- apparel

ALPHA_TO_EU_APPAREL = {
    "XXS": 44, "XS": 46, "S": 48, "M": 50, "L": 52, "XL": 54, "XXL": 56,
    "XXXL": 58, "3XL": 58,
}
_ALPHA_WORD_TO_CODE = {
    "extra small": "XS", "small": "S", "medium": "M", "large": "L", "extra large": "XL",
}
_ALPHA_TOKEN_RE = re.compile(
    r"\b(xxs|xs|s|m|l|xl|xxl|xxxl|3xl|extra\s*small|small|medium|large|extra\s*large)\b",
    re.IGNORECASE,
)
_FIT_LIKE_RE = re.compile(
    r"fits?\s+(?:true\s+to\s+size\s+)?(?:like\s+an?\s+)?(.+)", re.IGNORECASE
)
_NO_SIZE_RE = re.compile(r"^(one\s*size|os|o/s|free\s*size)$", re.IGNORECASE)
# "runs small" / "runs large" is fit commentary, not a size assignment --
# strip it before looking for a bare alpha token so it isn't mistaken for
# one (distinct from "fits like a large", which IS an assignment).
_RUNS_FIT_COMMENT_RE = re.compile(r"\bruns?\s+(small|large|big|tight|loose)\b", re.IGNORECASE)

# Margiela mainline tailoring runs roughly EU 44-54; Dior Homme/Saint
# Laurent tailoring and outerwear use the same EU scale. Widened slightly
# on both ends to cover outliers without reaching into the denim range.
EU_TAILORING_RANGE = (42, 60)
# Denim waist, in inches -- a de facto universal convention that doesn't
# need US/EU conversion. Chosen not to overlap EU_TAILORING_RANGE; a bare
# "42" is treated as tailoring, not a 42" waist, since that's the far more
# common resale size for these brands.
DENIM_WAIST_RANGE = (26, 41)


def _alpha_code_from_token(token: str) -> Optional[str]:
    words = re.sub(r"\s+", " ", token.strip().lower())
    if words in _ALPHA_WORD_TO_CODE:
        return _ALPHA_WORD_TO_CODE[words]
    compact = token.strip().upper().replace(" ", "")
    if compact in ALPHA_TO_EU_APPAREL:
        return compact
    return None


def normalize_apparel_size(raw: Optional[str], brand: Optional[str] = None) -> NormalizedSize:
    """Normalize an apparel size string to a canonical EU tailoring size,
    or a denim waist measurement (its own, non-overlapping numeric range
    that needs no conversion).

    `brand` is accepted but not yet used by the logic -- which numeric
    scale applies is fundamentally a brand/line question (tailoring vs.
    denim vs. alpha-only streetwear), and future per-brand refinement
    belongs here rather than on a second parallel function.
    """
    raw_str = raw or ""
    stripped = raw_str.strip()
    empty = NormalizedSize(raw=raw_str, category="apparel", system_detected=None, canonical=None)
    if not stripped:
        return empty

    lowered = stripped.lower()
    if _NO_SIZE_RE.match(lowered):
        return empty
    if _AMBIGUOUS_RE.search(stripped):
        return empty  # e.g. "L/XL", "48/50", "42 or 44"

    fit_like_match = _FIT_LIKE_RE.search(stripped)
    if fit_like_match:
        candidate = fit_like_match.group(1)
        alpha_search = _ALPHA_TOKEN_RE.search(candidate)
        if alpha_search:
            alpha_code = _alpha_code_from_token(alpha_search.group(1))
            if alpha_code:
                return NormalizedSize(
                    raw_str, "apparel", "ALPHA", ALPHA_TO_EU_APPAREL[alpha_code], is_estimated=True
                )
        number = _extract_number(candidate)
        if number is not None and EU_TAILORING_RANGE[0] <= number <= EU_TAILORING_RANGE[1]:
            return NormalizedSize(raw_str, "apparel", "EU", number, is_estimated=True)
        return empty  # "fits true to size" with no actual size given

    if _EU_UNIT_RE.search(stripped):
        number = _extract_number(stripped)
        if number is not None:
            return NormalizedSize(raw_str, "apparel", "EU", number)

    if _US_UNIT_RE.search(stripped) or _UK_UNIT_RE.search(stripped):
        # US/UK numeric jacket sizing (34-50ish) overlaps closely enough
        # with the denim-waist range that guessing which scale applies
        # would be worse than saying nothing -- detected, not converted.
        system = "US" if _US_UNIT_RE.search(stripped) else "UK"
        return NormalizedSize(raw_str, "apparel", system, None)

    without_fit_comments = _RUNS_FIT_COMMENT_RE.sub("", stripped)
    alpha_token_match = _ALPHA_TOKEN_RE.search(without_fit_comments)
    if alpha_token_match:
        alpha_code = _alpha_code_from_token(alpha_token_match.group(1))
        if alpha_code:
            return NormalizedSize(
                raw_str, "apparel", "ALPHA", ALPHA_TO_EU_APPAREL[alpha_code], is_estimated=True
            )

    number = _extract_number(stripped)
    if number is None:
        return empty
    if EU_TAILORING_RANGE[0] <= number <= EU_TAILORING_RANGE[1]:
        return NormalizedSize(raw_str, "apparel", "EU", number)
    if DENIM_WAIST_RANGE[0] <= number <= DENIM_WAIST_RANGE[1]:
        return NormalizedSize(raw_str, "apparel", "WAIST_IN", number)
    return empty


def normalize_size(
    raw: Optional[str], category: Category, brand: Optional[str] = None
) -> NormalizedSize:
    """Dispatch to the right normalizer for `category`."""
    if category == "footwear":
        return normalize_footwear_size(raw)
    if category == "apparel":
        return normalize_apparel_size(raw, brand=brand)
    raise ValueError(f"Unknown category: {category!r}")
