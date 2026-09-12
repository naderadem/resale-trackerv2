"""Tunable defaults for matching and pricing, overridable via .env.

CLI flags (see main.py --help) override these; these override the
hardcoded defaults in matcher.py/pricing.py.
"""
import os


def _float_env(name: str, default: float) -> float:
    val = os.environ.get(name)
    return float(val) if val not in (None, "") else default


def _int_env(name: str, default: int) -> int:
    val = os.environ.get(name)
    return int(val) if val not in (None, "") else default


MATCH_THRESHOLD = _float_env("MATCH_THRESHOLD", 0.72)
MIN_SAMPLE_SIZE = _int_env("MIN_SAMPLE_SIZE", 5)
SUSPICIOUS_FLOOR_PCT = _float_env("SUSPICIOUS_FLOOR_PCT", 0.4)
MIN_SELLER_RATING = _float_env("MIN_SELLER_RATING", 95.0)
MIN_PHOTO_COUNT = _int_env("MIN_PHOTO_COUNT", 3)
