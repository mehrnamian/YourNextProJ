"""Structured logging restricted to non-sensitive scan metrics."""

from __future__ import annotations

import hashlib
import json
import logging
import re

type LogValue = str | int | float | bool | None

ALLOWED_FIELDS = frozenset(
    {
        "job_id",
        "status",
        "repo_count",
        "evidence_count",
        "duration_ms",
        "rate_limit_remaining",
        "rate_limit_cost",
        "http_status",
        "error_class",
    }
)

_STRING_FIELDS = {"job_id", "status", "error_class"}
_SAFE_TEXT = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_STATUS_VALUES = {
    "started",
    "completed",
    "budget_stopped",
    "failed",
    "skipped",
}
_EVENTS = {"scan_started", "scan_completed", "scan_failed"}

logger = logging.getLogger("portfolio_gap_bot")


def safe_log(event: str, **fields: LogValue) -> None:
    """Emit one JSON log line containing only approved metric fields."""
    if event not in _EVENTS:
        raise ValueError("event is not an allowed scan event")

    unknown = fields.keys() - ALLOWED_FIELDS
    if unknown:
        raise ValueError(f"unsupported log field: {sorted(unknown)[0]}")

    for name, value in fields.items():
        if name in _STRING_FIELDS and value is not None:
            if not isinstance(value, str) or not _SAFE_TEXT.fullmatch(value):
                raise ValueError(f"{name} must be a short, safe identifier")
        elif value is not None and not isinstance(value, (int, float, bool)):
            raise ValueError(f"{name} must be a scalar metric")

    if fields.get("status") not in (None, *_STATUS_VALUES):
        raise ValueError("status is not an allowed scan status")

    job_id = fields.get("job_id")
    if isinstance(job_id, str):
        fields["job_id"] = safe_job_id(job_id)
    logger.info("%s %s", event, json.dumps(fields, separators=(",", ":")))


def safe_job_id(value: str) -> str:
    """Return a stable non-reversible identifier for logs and public summaries."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
