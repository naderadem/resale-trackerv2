"""Offline matcher evaluation against the hand-labeled corpus in
labeled_titles.py.

Run via `python main.py matcher-eval` (single threshold) or
`python main.py matcher-eval --sweep` (a range of thresholds). Fully
offline -- no database, no network -- since it only needs the labeled
corpus and an in-memory canonical item catalog.

Precision/recall/F1 treat "should match a specific item" as the positive
class:
  - true positive:  expected an item, matcher returned that exact item
  - false positive: matcher returned an item but expected None, OR
                     returned a *different* item than expected (also
                     listed separately under `confused`, since matching
                     the wrong item is worse than matching nothing --
                     it's the failure mode that corrupts pricing data)
  - false negative: expected an item, matcher returned None
  - true negative:  expected None, matcher returned None

Do not lower the threshold to inflate these numbers. A bad score here is
real signal about the threshold, the canonical item catalog, or
(occasionally) a label in the corpus -- not something to tune away.
"""
from dataclasses import dataclass, field

from labeled_titles import LABELED_TITLES
from matcher import match_listing

ItemKey = tuple  # (brand, line_or_era, model_name)


@dataclass
class EvalResult:
    threshold: float
    total: int
    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int
    precision: float
    recall: float
    f1: float
    confused: list = field(default_factory=list)
    """[(title, expected_key, actual_key), ...] -- cases where the matcher
    returned a real item, but the wrong one."""


def _item_key(item) -> ItemKey:
    return (item.brand, item.line_or_era, item.model_name)


def evaluate(canonical_items, threshold: float) -> EvalResult:
    """Run the matcher over the whole labeled corpus at one threshold."""
    tp = fp = fn = tn = 0
    confused = []

    for title, expected in LABELED_TITLES:
        result = match_listing(title, canonical_items, threshold=threshold)
        actual = _item_key(result.canonical_item) if result.canonical_item else None

        if expected is None and actual is None:
            tn += 1
        elif expected is None and actual is not None:
            fp += 1
        elif expected is not None and actual is None:
            fn += 1
        elif expected == actual:
            tp += 1
        else:
            fp += 1
            confused.append((title, expected, actual))

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    return EvalResult(
        threshold=threshold,
        total=len(LABELED_TITLES),
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        true_negatives=tn,
        precision=precision,
        recall=recall,
        f1=f1,
        confused=confused,
    )


def sweep(canonical_items, thresholds) -> list:
    """Evaluate at every threshold in `thresholds`, in order."""
    return [evaluate(canonical_items, t) for t in thresholds]


def frange(start: float, stop: float, step: float):
    """Like range(), but for floats, inclusive of `stop` (within float error)."""
    n = int(round((stop - start) / step))
    return [round(start + i * step, 4) for i in range(n + 1)]
