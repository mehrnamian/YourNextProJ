"""Persistent ETag cache that never stores request URLs or response bodies."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class ETagCache:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._values: dict[str, str] = {}
        if path.exists():
            payload: Any = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or any(
                not isinstance(key, str)
                or not isinstance(value, str)
                or len(key) != 64
                for key, value in payload.items()
            ):
                raise ValueError("ETag cache has an invalid format")
            self._values = payload

    @staticmethod
    def _key(url: str) -> str:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    def get(self, url: str) -> str | None:
        return self._values.get(self._key(url))

    def put(self, url: str, etag: str) -> None:
        self._values[self._key(url)] = etag

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._values, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
