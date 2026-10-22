from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from spikes.stage1 import dispatch_and_time


def test_measure_one_uses_created_started_and_updated_timestamps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_datetime = datetime
    dispatched_at = real_datetime(2026, 10, 22, 0, 0, tzinfo=UTC)

    class FixedDateTime:
        @classmethod
        def now(cls, tz: object = None) -> datetime:
            return dispatched_at

        @staticmethod
        def fromisoformat(value: str) -> datetime:
            return real_datetime.fromisoformat(value)

    run = {
        "createdAt": (dispatched_at + timedelta(seconds=5)).isoformat(),
        "startedAt": (dispatched_at + timedelta(seconds=35)).isoformat(),
        "updatedAt": (dispatched_at + timedelta(seconds=185)).isoformat(),
        "conclusion": "success",
    }
    dispatched: list[list[str]] = []
    monkeypatch.setattr(dispatch_and_time, "datetime", FixedDateTime)
    monkeypatch.setattr(dispatch_and_time, "_run_ids", lambda ref: {1})
    monkeypatch.setattr(dispatch_and_time, "_wait_for_new_run", lambda ids, ref: run)

    def fake_gh(arguments: list[str]) -> str:
        dispatched.append(arguments)
        return ""

    monkeypatch.setattr(dispatch_and_time, "_gh", fake_gh)

    delay, duration = dispatch_and_time.measure_one(1, "123", "main")

    assert delay == 30
    assert duration == 180
    assert len(dispatched) == 1
    assert "installation_id=123" in dispatched[0]


def test_time_parser_rejects_missing_timestamps() -> None:
    with pytest.raises(dispatch_and_time.DispatchError, match="omitted"):
        dispatch_and_time._parse_time(None)
