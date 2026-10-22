"""Pure evidence extraction from repository metadata and in-memory allowlisted files."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Signal:
    key: str
    dependencies: tuple[str, ...]
    file_patterns: tuple[str, ...]
    topics: tuple[str, ...]
    languages: dict[str, float]


@dataclass(frozen=True)
class Evidence:
    competency_key: str
    matcher_type: str
    confidence: str
    repo_count: int


@dataclass(frozen=True)
class Snapshot:
    name_with_owner: str
    pushed_at: str | None
    primary_language: str | None
    language_sizes: dict[str, int]
    topics: tuple[str, ...]
    file_paths: tuple[str, ...]
    file_contents: dict[str, str]
    tree_truncated: bool = False


def repository_key(name_with_owner: str) -> str:
    """Return a stable opaque reference instead of persisting repository names."""
    canonical_name = name_with_owner.strip().casefold()
    if canonical_name.count("/") != 1 or any(
        part in {"", ".", ".."} for part in canonical_name.split("/")
    ):
        raise ValueError("repository identity must be an owner/name pair")
    return hashlib.sha256(canonical_name.encode("utf-8")).hexdigest()


def load_signals(path: Path) -> tuple[Signal, ...]:
    payload: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("signals"), list):
        raise ValueError("signal taxonomy must contain a signals list")
    signals: list[Signal] = []
    seen: set[str] = set()
    for item in payload["signals"]:
        if not isinstance(item, dict):
            raise ValueError("each signal must be a mapping")
        key = item.get("key")
        matchers = item.get("matchers")
        if not isinstance(key, str) or not re.fullmatch(r"[a-z0-9-]+", key):
            raise ValueError("signal keys must be lowercase kebab-case")
        if key in seen or not isinstance(matchers, dict):
            raise ValueError("signal keys must be unique and matchers must be a mapping")
        seen.add(key)
        dependencies = _string_tuple(matchers.get("dependencies", []))
        file_patterns = _string_tuple(matchers.get("file_patterns", []))
        topics = _string_tuple(matchers.get("topics", []))
        languages_value = matchers.get("languages", {})
        if not isinstance(languages_value, dict):
            raise ValueError(f"languages for {key} must be a mapping")
        languages: dict[str, float] = {}
        for name, threshold in languages_value.items():
            if not isinstance(name, str) or not isinstance(threshold, (int, float)):
                raise ValueError(f"invalid language threshold for {key}")
            if not 0 < float(threshold) <= 1:
                raise ValueError(f"language threshold for {key} must be in (0, 1]")
            languages[name.casefold()] = float(threshold)
        signals.append(
            Signal(
                key=key,
                dependencies=tuple(value.casefold() for value in dependencies),
                file_patterns=tuple(value.casefold() for value in file_patterns),
                topics=tuple(value.casefold() for value in topics),
                languages=languages,
            )
        )
    return tuple(signals)


def extract_evidence(snapshot: Snapshot, signals: tuple[Signal, ...]) -> tuple[Evidence, ...]:
    """Match evidence without retaining or returning any fetched file contents."""
    files = tuple(path.casefold() for path in snapshot.file_paths)
    topics = {topic.casefold() for topic in snapshot.topics}
    language_sizes = {name.casefold(): size for name, size in snapshot.language_sizes.items()}
    total_language_bytes = sum(language_sizes.values())
    dependency_names: set[str] = set()
    for content in snapshot.file_contents.values():
        dependency_names.update(_dependency_tokens(content))

    evidence: list[Evidence] = []
    for signal in signals:
        hits = (
            ("dependency", sum(name in dependency_names for name in signal.dependencies), "high"),
            (
                "file_pattern",
                sum(
                    any(fnmatch.fnmatchcase(path, pattern) for pattern in signal.file_patterns)
                    for path in files
                ),
                "medium",
            ),
            ("topic", sum(topic in topics for topic in signal.topics), "low"),
            (
                "language_threshold",
                sum(
                    total_language_bytes > 0
                    and language_sizes.get(language, 0) / total_language_bytes >= threshold
                    for language, threshold in signal.languages.items()
                ),
                "low",
            ),
        )
        evidence.extend(
            Evidence(signal.key, matcher_type, confidence, count)
            for matcher_type, count, confidence in hits
            if count > 0
        )
    return tuple(sorted(evidence, key=lambda item: (item.competency_key, item.matcher_type)))


def evidence_to_json(
    snapshot: Snapshot, evidence: tuple[Evidence, ...], metadata_fingerprint: str
) -> dict[str, Any]:
    """Build a feature-only cache record with an opaque repository key."""
    return {
        "repo_key": repository_key(snapshot.name_with_owner),
        "pushed_at": snapshot.pushed_at,
        "metadata_fingerprint": metadata_fingerprint,
        "tree_truncated": snapshot.tree_truncated,
        "evidence": [asdict(item) for item in evidence],
        "evidence_count": len(evidence),
    }


def metadata_fingerprint(
    *,
    primary_language: str | None,
    language_sizes: dict[str, int],
    topics: tuple[str, ...],
    default_branch: str | None,
) -> str:
    payload = {
        "primary_language": primary_language,
        "language_sizes": language_sizes,
        "topics": sorted(topics),
        "default_branch": default_branch,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _dependency_tokens(content: str) -> set[str]:
    return {
        token.casefold().replace("_", "-")
        for token in re.findall(
            r"(?<![A-Za-z0-9_.-])[A-Za-z0-9][A-Za-z0-9_.-]*(?![A-Za-z0-9_.-])",
            content,
        )
    }


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("matcher values must be lists of strings")
    return tuple(value)
