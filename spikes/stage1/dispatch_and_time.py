"""Dispatch scan-worker runs with gh and measure queue delay and total duration."""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from typing import Any

WORKFLOW = "scan-worker.yml"


class DispatchError(RuntimeError):
    """Raised when gh cannot dispatch a run or return its timing data."""


def measure_one(run_number: int, installation_id: str, ref: str) -> tuple[float, float]:
    job_id = f"stage1-{int(time.time())}-{run_number}"
    previous_ids = _run_ids(ref)
    dispatched_at = datetime.now(UTC)
    _gh(
        [
            "workflow",
            "run",
            WORKFLOW,
            "--ref",
            ref,
            "-f",
            f"job_id={job_id}",
            "-f",
            f"installation_id={installation_id}",
        ]
    )
    run = _wait_for_new_run(previous_ids, ref)
    created_at = _parse_time(run["createdAt"])
    started_at = _parse_time(run["startedAt"])
    completed_at = _parse_time(run["updatedAt"])
    dispatch_delay = max(0.0, (started_at - created_at).total_seconds())
    total_duration = max(0.0, (completed_at - created_at).total_seconds())
    if run.get("conclusion") != "success":
        raise DispatchError("scan workflow did not complete successfully")
    if created_at < dispatched_at:
        raise DispatchError("the observed workflow run predates this dispatch")
    return dispatch_delay, total_duration


def _run_ids(ref: str) -> set[int]:
    runs = _gh_json(
        [
            "run",
            "list",
            "--workflow",
            WORKFLOW,
            "--event",
            "workflow_dispatch",
            "--branch",
            ref,
            "--limit",
            "100",
            "--json",
            "databaseId",
        ]
    )
    if not isinstance(runs, list):
        raise DispatchError("gh returned an invalid workflow run list")
    run_ids: set[int] = set()
    for run in runs:
        if not isinstance(run, dict) or not isinstance(run.get("databaseId"), int):
            raise DispatchError("gh returned invalid workflow run identifiers")
        run_ids.add(run["databaseId"])
    return run_ids


def _wait_for_new_run(previous_ids: set[int], ref: str) -> dict[str, Any]:
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        runs = _gh_json(
            [
                "run",
                "list",
                "--workflow",
                WORKFLOW,
                "--event",
                "workflow_dispatch",
                "--branch",
                ref,
                "--limit",
                "20",
                "--json",
                "databaseId,createdAt,startedAt,updatedAt,status,conclusion",
            ]
        )
        if not isinstance(runs, list):
            raise DispatchError("gh returned an invalid workflow run list")
        for run in runs:
            if not isinstance(run, dict) or not isinstance(run.get("databaseId"), int):
                raise DispatchError("gh returned invalid workflow run data")
            candidate: dict[str, Any] = {
                key: value for key, value in run.items() if isinstance(key, str)
            }
            if candidate["databaseId"] in previous_ids:
                continue
            if candidate.get("status") == "completed":
                return candidate
            if candidate.get("startedAt") is not None:
                while candidate.get("status") != "completed" and time.monotonic() < deadline:
                    time.sleep(3)
                    candidate = _workflow_run(int(candidate["databaseId"]))
                if candidate.get("status") == "completed":
                    return candidate
        time.sleep(3)
    raise DispatchError("timed out waiting for the workflow run")


def _workflow_run(run_id: int) -> dict[str, Any]:
    run = _gh_json(
        [
            "run",
            "view",
            str(run_id),
            "--json",
            "databaseId,createdAt,startedAt,updatedAt,status,conclusion",
        ]
    )
    if not isinstance(run, dict) or any(not isinstance(key, str) for key in run):
        raise DispatchError("gh returned invalid workflow timing data")
    return {key: value for key, value in run.items() if isinstance(key, str)}


def _gh_json(arguments: list[str]) -> Any:
    output = _gh(arguments)
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise DispatchError("gh returned invalid JSON") from exc


def _gh(arguments: list[str]) -> str:
    try:
        result = subprocess.run(
            ["gh", *arguments],
            capture_output=True,
            check=False,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DispatchError("gh could not complete the requested operation") from exc
    if result.returncode != 0:
        raise DispatchError("gh command failed")
    return result.stdout


def _parse_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise DispatchError("gh omitted a workflow timestamp")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError as exc:
        raise DispatchError("gh returned an invalid workflow timestamp") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--installation-id", required=True)
    parser.add_argument("--ref", default="main")
    args = parser.parse_args()
    if args.runs < 1 or args.runs > 20:
        parser.error("--runs must be between 1 and 20")
    if not re.fullmatch(r"[0-9]+", args.installation_id):
        parser.error("--installation-id must be numeric")
    results = [
        measure_one(index, args.installation_id, args.ref)
        for index in range(1, args.runs + 1)
    ]
    delays = [item[0] for item in results]
    durations = [item[1] for item in results]
    print(
        json.dumps(
            {
                "runs": len(results),
                "dispatch_delay_seconds": {
                    "median": statistics.median(delays),
                    "worst": max(delays),
                },
                "total_duration_seconds": {
                    "median": statistics.median(durations),
                    "worst": max(durations),
                },
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DispatchError as exc:
        print(type(exc).__name__, file=sys.stderr)
        raise SystemExit(1) from exc
