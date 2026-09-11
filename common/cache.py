"""A small on-disk response cache, keyed by an arbitrary string key.

Used to avoid re-hitting a marketplace's API/site for a request that was
already made recently (e.g. the same search query run twice while
developing). Each namespace (typically one per source) gets its own
subdirectory under `cache_dir` so different sources never collide.

This is intentionally simple: one JSON file per cache entry, a TTL checked
on read, no eviction beyond that. Fine for the low request volumes this
project targets; not meant to scale beyond that.
"""
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Optional


class ResponseCache:
    def __init__(self, namespace: str, cache_dir: str = ".cache", ttl_seconds: int = 900):
        self.dir = Path(cache_dir) / namespace
        self.dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_seconds

    def _path_for(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.dir / f"{digest}.json"

    def get(self, key: str) -> Optional[Any]:
        """Return the cached value for `key`, or None if missing/expired/unreadable."""
        path = self._path_for(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None
        if time.time() - payload.get("cached_at", 0) > self.ttl_seconds:
            return None
        return payload.get("data")

    def set(self, key: str, data: Any) -> None:
        """Cache `data` (must be JSON-serializable) under `key`."""
        path = self._path_for(key)
        payload = {"cached_at": time.time(), "data": data}
        path.write_text(json.dumps(payload))
