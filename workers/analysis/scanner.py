"""Installation repository scan orchestration; file bodies stay in memory."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from workers.analysis.etag_cache import ETagCache
from workers.analysis.extractor import (
    Signal,
    Snapshot,
    evidence_to_json,
    extract_evidence,
    metadata_fingerprint,
    repository_key,
)
from workers.analysis.github_client import (
    GitHubClient,
    NotModified,
    Repository,
)
from workers.analysis.rate_limit import BudgetExceeded, BudgetGuard, UsageCounters
from workers.analysis.safe_log import safe_log

MAX_FILE_BYTES = 256 * 1024
MAX_FILES_PER_REPOSITORY = 10
ALLOWED_BASENAMES = {
    "requirements.txt",
    "pyproject.toml",
    "package.json",
    "pipfile",
    "poetry.lock",
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
}


@dataclass(frozen=True)
class ScanResult:
    repo_count: int
    skipped_repo_count: int
    evidence_count: int
    budget_stopped: bool
    duration_ms: int
    usage: UsageCounters


def scan_installation(
    client: GitHubClient,
    signals: tuple[Signal, ...],
    feature_dir: Path,
    etag_cache: ETagCache,
    budget: BudgetGuard,
    *,
    include_forks: bool = False,
    include_archived: bool = False,
    job_id: str = "local-scan",
) -> ScanResult:
    started = time.monotonic()
    repos: list[Repository] = []
    skipped = 0
    evidence_count = 0
    budget_stopped = False
    safe_log("scan_started", job_id=job_id)
    try:
        repos = client.list_repositories()
        feature_dir.mkdir(parents=True, exist_ok=True)
        for repository in repos:
            if (repository.is_fork and not include_forks) or (
                repository.is_archived and not include_archived
            ):
                skipped += 1
                continue
            fingerprint = metadata_fingerprint(
                primary_language=repository.primary_language,
                language_sizes=repository.language_sizes,
                topics=repository.topics,
                default_branch=repository.default_branch,
            )
            destination = feature_dir / f"{repository_key(repository.name_with_owner)}.json"
            cached = _read_feature_cache(destination)
            if (
                cached is not None
                and cached.get("pushed_at") == repository.pushed_at
                and cached.get("metadata_fingerprint") == fingerprint
            ):
                evidence_count += _evidence_count(cached)
                continue

            tree, truncated = _get_tree(client, repository)
            paths, contents = _fetch_allowlisted_contents(client, repository, tree)
            snapshot = Snapshot(
                name_with_owner=repository.name_with_owner,
                pushed_at=repository.pushed_at,
                primary_language=repository.primary_language,
                language_sizes=repository.language_sizes,
                topics=repository.topics,
                file_paths=tuple(paths),
                file_contents=contents,
                tree_truncated=truncated,
            )
            evidence = extract_evidence(snapshot, signals)
            _write_feature_cache(
                destination,
                evidence_to_json(snapshot, evidence, fingerprint),
            )
            evidence_count += len(evidence)
            contents.clear()
            paths.clear()
            tree.clear()
            del snapshot
        etag_cache.save()
    except BudgetExceeded:
        if not repos:
            repos = client.partial_repositories
        budget_stopped = True
        etag_cache.save()
    duration_ms = int((time.monotonic() - started) * 1000)
    safe_log(
        "scan_completed",
        job_id=job_id,
        status="budget_stopped" if budget_stopped else "completed",
        repo_count=len(repos),
        evidence_count=evidence_count,
        duration_ms=duration_ms,
        rate_limit_remaining=budget.counters.rate_limit_remaining,
        rate_limit_cost=budget.counters.rate_limit_cost,
    )
    return ScanResult(
        repo_count=len(repos),
        skipped_repo_count=skipped,
        evidence_count=evidence_count,
        budget_stopped=budget_stopped,
        duration_ms=duration_ms,
        usage=budget.counters,
    )


def _get_tree(
    client: GitHubClient, repository: Repository
) -> tuple[list[dict[str, Any]], bool]:
    try:
        return client.get_tree(repository)
    except NotModified:
        return client.get_tree(repository, conditional=False)


def _fetch_allowlisted_contents(
    client: GitHubClient, repository: Repository, tree: list[dict[str, Any]]
) -> tuple[list[str], dict[str, str]]:
    paths: list[str] = []
    contents: dict[str, str] = {}
    candidates: list[tuple[int, str, int]] = []
    for item in tree:
        if item.get("type") != "blob":
            continue
        path = item.get("path")
        size = item.get("size")
        if not isinstance(path, str) or not isinstance(size, int) or size < 0:
            continue
        paths.append(path)
        if size <= MAX_FILE_BYTES and _is_allowlisted(path):
            candidates.append((_file_priority(path), path, size))
    for _, path, _ in sorted(candidates)[:MAX_FILES_PER_REPOSITORY]:
        try:
            content = client.get_file_contents(repository, path)
        except NotModified:
            content = client.get_file_contents(repository, path, conditional=False)
        contents[path] = content
    return paths, contents


def _is_allowlisted(path: str) -> bool:
    normalized = path.casefold()
    basename = normalized.rsplit("/", maxsplit=1)[-1]
    if basename in ALLOWED_BASENAMES:
        return True
    if normalized.startswith(".github/workflows/") and basename.endswith((".yml", ".yaml")):
        return True
    return normalized.endswith((".tf", ".tfvars", ".bicep")) or (
        basename.startswith("dockerfile") or basename.startswith("docker-compose.")
    )


def _file_priority(path: str) -> int:
    normalized = path.casefold()
    basename = normalized.rsplit("/", maxsplit=1)[-1]
    if basename in ALLOWED_BASENAMES:
        return 0
    if normalized.startswith(".github/workflows/"):
        return 1
    if basename.startswith(("dockerfile", "docker-compose.", "compose.")):
        return 2
    return 3


def _read_feature_cache(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("feature cache has an invalid format")
    if payload.get("repo_key") != path.stem:
        raise ValueError("feature cache repository key does not match its filename")
    return payload


def _write_feature_cache(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")


def _evidence_count(payload: dict[str, Any]) -> int:
    evidence = payload.get("evidence")
    return len(evidence) if isinstance(evidence, list) else 0
