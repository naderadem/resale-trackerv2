"""Fuzzy-matches a listing title against canonical_items using rapidfuzz.

Plain fuzzy scoring alone isn't safe for this catalog because of three
brand-specific ambiguities, all handled with keyword-regex guards *before*
any fuzzy scoring happens:

  Margiela lines: Mainline, MM6, and Replica are distinct canonical items
  that often share model names (e.g. "Tabi" appears in more than one line),
  and "replica" is both the name of a real Margiela line and a generic
  word for a counterfeit ("Rick Owens Geobasket replica"). A bare mention
  of "replica" with no Margiela brand token nearby is refused outright --
  fuzzy-matching it to *some* canonical item (most likely the genuine
  product it claims to imitate) would quietly launder a counterfeit's
  price into that item's median.

  Rick Owens mainline vs. DRKSHDW: the same problem as Margiela's lines,
  smaller in scope -- DRKSHDW shares model names with mainline (Geobasket,
  Ramones), so a title naming only the shared model scores a perfect
  fuzzy match against *both* lines' candidates. Without narrowing first,
  the tie is broken arbitrarily by list order rather than by what the
  title says, so a title that explicitly says "DRKSHDW" could silently
  match the (usually pricier) mainline item instead.

  Hedi Slimane-era houses: Dior Homme, Saint Laurent, and Celine are
  distinct canonical items that can have superficially similar model names
  across houses (skinny jeans, biker jackets, etc.). Candidates are
  filtered to the house named in the title before scoring, so a
  fuzzy-similar item from the wrong house can't win purely on text
  similarity.

Any canonical-item-like object works as input (CanonicalItem ORM rows or
anything else with .brand / .line_or_era / .model_name) -- this module has
no DB dependency, which is what makes it straightforward to unit test.
"""
import re
from dataclasses import dataclass
from typing import Iterable, Optional

from rapidfuzz import fuzz, process

DEFAULT_THRESHOLD = 0.72

MARGIELA_BRAND_RE = re.compile(r"\bmaison\s*margiela\b|\bmm6\b|\bmargiela\b", re.IGNORECASE)
MM6_RE = re.compile(r"\bmm6\b", re.IGNORECASE)
REPLICA_WORD_RE = re.compile(r"\breplica\b", re.IGNORECASE)
COUNTERFEIT_WORD_RE = re.compile(
    r"\b(reps?|fake|aaa\+?|1:1|dhgate|unauthentic|not\s*authentic|knockoff)\b", re.IGNORECASE
)

RICK_OWENS_BRAND_RE = re.compile(r"\brick\s*owens\b", re.IGNORECASE)
DRKSHDW_RE = re.compile(r"\bdrkshdw\b", re.IGNORECASE)

DIOR_HOMME_RE = re.compile(r"\bdior\s*homme\b|\bdior\b", re.IGNORECASE)
SAINT_LAURENT_RE = re.compile(
    r"\bsaint\s*laurent\b|\byves\s*saint\s*laurent\b|\bysl\b|\bslp\b", re.IGNORECASE
)
CELINE_RE = re.compile(r"\bc[eé]line\b", re.IGNORECASE)

HOUSE_PATTERNS = {
    "Dior Homme": DIOR_HOMME_RE,
    "Saint Laurent": SAINT_LAURENT_RE,
    "Celine": CELINE_RE,
}


@dataclass
class MatchResult:
    canonical_item: Optional[object]  # None when nothing cleared the bar
    confidence: float  # 0.0-1.0
    method: str  # "rapidfuzz", or "blocked" when refused before scoring
    reason: Optional[str] = None  # populated whenever canonical_item is None
    best_candidate: Optional[object] = None
    """The top-scoring candidate even when it didn't clear the threshold
    (None when scoring never ran at all, e.g. a "blocked" result) -- kept
    so a human reviewing unmatched_listings can see what the matcher was
    closest to guessing, not just that it gave up."""


def _is_margiela(item) -> bool:
    return "margiela" in (item.brand or "").lower()


def _is_rick_owens(item) -> bool:
    return (item.brand or "").strip().lower() == "rick owens"


# line_or_era values that are pure internal categorization, not something
# a real seller ever types -- excluded from the *scored* text below. Values
# NOT in this set (MM6, Replica, DRKSHDW) are real words sellers commonly
# do include in a title, and are kept: they're useful signal, not noise.
_NON_VERBAL_LINE_LABELS = {"Mainline", "Hedi Slimane Era"}


def _searchable_text(item) -> str:
    # line_or_era is already used for candidate-pool narrowing above (the
    # Margiela/Rick Owens hints, and brand-level narrowing for the
    # Hedi-era houses) -- by the time we score, narrowing has already done
    # the disambiguation work, so the *scored* text doesn't need it to
    # disambiguate. But some line labels ARE real words sellers write
    # ("MM6", "Replica", "DRKSHDW") and help the score; only labels no one
    # actually types (a multi-word era qualifier like "Hedi Slimane Era",
    # or "Mainline" -- nobody clarifies a listing isn't MM6) get dropped.
    # Found via eval_matcher.py in two passes: dropping ALL line_or_era
    # first fixed the Hedi-era case but broke MM6/Replica/DRKSHDW matches
    # the same way; narrowing to just the non-verbal labels got both:
    # F1 0.795 -> 0.857 -> 0.900 at threshold 0.72 on the labeled corpus,
    # with no false-positive regressions on the disambiguation tests.
    line = item.line_or_era if item.line_or_era not in _NON_VERBAL_LINE_LABELS else None
    return " ".join(filter(None, [item.brand, line, item.model_name]))


def _margiela_line_hint(title: str) -> Optional[str]:
    """Guess which Margiela line a title refers to, given a Margiela brand token.

    Returns None if the title has no Margiela brand token at all -- that's
    not "ambiguous Margiela", it's "not Margiela" (or, see
    `_bare_replica_mention`, a bare counterfeit mention).
    """
    if not MARGIELA_BRAND_RE.search(title):
        return None
    if MM6_RE.search(title):
        return "MM6"
    if REPLICA_WORD_RE.search(title):
        return "Replica"
    return "Mainline"


def _rick_owens_line_hint(title: str) -> Optional[str]:
    """Guess whether a Rick Owens title means mainline or DRKSHDW.

    Returns None if the title has no "Rick Owens" token at all -- same
    reasoning as the Margiela hint: no signal means no narrowing, not "it
    must be mainline".
    """
    if not RICK_OWENS_BRAND_RE.search(title):
        return None
    return "DRKSHDW" if DRKSHDW_RE.search(title) else "Mainline"


def _bare_replica_mention(title: str) -> bool:
    """True when "replica" appears with no Margiela brand context.

    That combination overwhelmingly means "this is a fake of some other
    brand's item" rather than a reference to Margiela's Replica line.
    """
    return bool(REPLICA_WORD_RE.search(title)) and not MARGIELA_BRAND_RE.search(title)


def _house_hint(title: str) -> Optional[str]:
    """Guess which Hedi Slimane-era house a title names, if exactly one is named."""
    hits = [house for house, pattern in HOUSE_PATTERNS.items() if pattern.search(title)]
    return hits[0] if len(hits) == 1 else None


def match_listing(
    title: str,
    canonical_items: Iterable,
    threshold: float = DEFAULT_THRESHOLD,
) -> MatchResult:
    """Score `title` against every canonical item and return the best match.

    Returns a MatchResult with canonical_item=None (and a `reason`) when:
      - the title bears a counterfeit marker with no legitimate-line context
        (see module docstring)
      - there are no canonical items to compare against
      - the best fuzzy score doesn't clear `threshold`
    """
    canonical_items = list(canonical_items)
    if not canonical_items:
        return MatchResult(None, 0.0, "rapidfuzz", reason="no_canonical_items")

    if _bare_replica_mention(title):
        return MatchResult(None, 0.0, "blocked", reason="ambiguous_replica_mention")
    if COUNTERFEIT_WORD_RE.search(title):
        return MatchResult(None, 0.0, "blocked", reason="counterfeit_keyword_mention")

    candidates = canonical_items

    margiela_hint = _margiela_line_hint(title)
    if margiela_hint is not None:
        narrowed = [
            c
            for c in candidates
            if _is_margiela(c) and (c.line_or_era or "").strip().lower() == margiela_hint.lower()
        ]
        if narrowed:
            candidates = narrowed

    rick_owens_hint = _rick_owens_line_hint(title)
    if rick_owens_hint is not None:
        target_line = "DRKSHDW" if rick_owens_hint == "DRKSHDW" else None
        narrowed = [c for c in candidates if _is_rick_owens(c) and c.line_or_era == target_line]
        if narrowed:
            candidates = narrowed

    house_hint = _house_hint(title)
    if house_hint is not None:
        narrowed = [c for c in candidates if (c.brand or "").strip().lower() == house_hint.lower()]
        if narrowed:
            candidates = narrowed

    # token_set_ratio, not WRatio: listing titles carry a lot of noise
    # words (size, color, condition, "great quality!") that a short
    # canonical string doesn't have, and token_set_ratio is far more
    # forgiving of extra words in one side than WRatio is.
    choices = [_searchable_text(c) for c in candidates]
    best = process.extractOne(title, choices, scorer=fuzz.token_set_ratio)
    if best is None:
        return MatchResult(None, 0.0, "rapidfuzz", reason="no_candidates")

    _, score, idx = best
    confidence = score / 100.0
    top_candidate = candidates[idx]
    if confidence < threshold:
        return MatchResult(
            None,
            confidence,
            "rapidfuzz",
            reason="below_threshold",
            best_candidate=top_candidate,
        )

    return MatchResult(top_candidate, confidence, "rapidfuzz", best_candidate=top_candidate)
