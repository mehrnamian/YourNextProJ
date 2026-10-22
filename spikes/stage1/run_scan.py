"""Run one local scan against repositories visible to the GitHub App installation."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import httpx

from workers.analysis.auth import AuthenticationError, GitHubAppAuth
from workers.analysis.etag_cache import ETagCache
from workers.analysis.extractor import load_signals
from workers.analysis.github_client import GitHubClient, GitHubClientError
from workers.analysis.rate_limit import BudgetGuard
from workers.analysis.safe_log import safe_job_id, safe_log
from workers.analysis.scanner import ScanResult, scan_installation

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-forks", action="store_true")
    parser.add_argument("--include-archived", action="store_true")
    parser.add_argument(
        "--job-id",
        default=os.environ.get("SCAN_JOB_ID", "local-scan"),
    )
    parser.add_argument(
        "--budget-share",
        type=float,
        default=float(os.environ.get("SCAN_BUDGET_SHARE", "0.5")),
    )
    args = parser.parse_args()
    try:
        budget = BudgetGuard(args.budget_share)
        etag_cache = ETagCache(ROOT / "spikes" / "stage1" / ".cache" / "etags.json")
        signals = load_signals(ROOT / "taxonomy" / "seed-signals.yaml")
        with httpx.Client(timeout=httpx.Timeout(30.0), follow_redirects=False) as http:
            auth = GitHubAppAuth.from_environment(http)
            client = GitHubClient(auth, http, etag_cache, budget)
            logging.basicConfig(
                stream=sys.stdout,
                level=logging.INFO,
                format="%(message)s",
            )
            result = scan_installation(
                client,
                signals,
                ROOT / "spikes" / "stage1" / "out",
                etag_cache,
                budget,
                include_forks=args.include_forks,
                include_archived=args.include_archived,
                job_id=args.job_id,
            )
        _append_github_summary(args.job_id, result)
        return 0
    except (AuthenticationError, GitHubClientError, OSError, ValueError) as exc:
        safe_log("scan_failed", status="failed", error_class=type(exc).__name__)
        return 1


def _append_github_summary(job_id: str, result: ScanResult) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    usage = result.usage
    lines = [
        "## Stage 1 scan",
        "",
        f"- Job ID: `{safe_job_id(job_id)}`",
        f"- Status: `{'budget_stopped' if result.budget_stopped else 'completed'}`",
        f"- Repositories: {result.repo_count}",
        f"- Skipped repositories: {result.skipped_repo_count}",
        f"- Evidence items: {result.evidence_count}",
        f"- Duration (ms): {result.duration_ms}",
        f"- GraphQL requests: {usage.graphql_requests}",
        f"- GraphQL cost: {usage.graphql_cost}",
        f"- GraphQL hourly limit: {usage.graphql_limit}",
        f"- GraphQL remaining: {usage.graphql_remaining}",
        f"- REST requests: {usage.rest_requests}",
        f"- REST billable requests: {usage.rest_billable_requests}",
        f"- REST hourly limit: {usage.rest_limit}",
        f"- REST remaining: {usage.rest_remaining}",
        "",
    ]
    with Path(summary_path).open("a", encoding="utf-8") as summary:
        summary.write("\n".join(lines))


if __name__ == "__main__":
    sys.exit(main())
