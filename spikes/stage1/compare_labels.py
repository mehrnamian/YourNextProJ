"""Compare manually supplied public-repository labels with extracted feature files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from workers.analysis.extractor import repository_key

ROOT = Path(__file__).resolve().parents[2]


def compare(labels_path: Path, feature_dir: Path) -> dict[str, Any]:
    labels_payload: Any = yaml.safe_load(labels_path.read_text(encoding="utf-8"))
    if not isinstance(labels_payload, dict) or not isinstance(labels_payload.get("repos"), list):
        raise ValueError("labels file must contain a repos list")
    features = _load_features(feature_dir)
    repo_results: list[dict[str, Any]] = []
    totals = {"labeled": 0, "found": 0, "extracted": 0, "matched": 0}

    for item in labels_payload["repos"]:
        if not isinstance(item, dict):
            raise ValueError("each label entry must be a mapping")
        repo_url = item.get("repo_url")
        keys = item.get("competency_keys")
        if not isinstance(repo_url, str) or not isinstance(keys, list) or any(
            not isinstance(key, str) for key in keys
        ):
            raise ValueError("each label needs repo_url and competency_keys")
        repo_hash = _repository_key_from_public_url(repo_url)
        expected = set(keys)
        actual = features.get(repo_hash, set())
        found = expected & actual
        misses = sorted(expected - actual)
        false_positives = sorted(actual - expected)
        totals["labeled"] += len(expected)
        totals["found"] += len(found)
        totals["extracted"] += len(actual)
        totals["matched"] += len(found)
        repo_results.append(
            {
                "repo_key": repo_hash,
                "recall": _ratio(len(found), len(expected)),
                "precision": _ratio(len(found), len(actual)),
                "misses": misses,
                "false_positives": false_positives,
            }
        )

    return {
        "per_repo": repo_results,
        "overall": {
            "recall": _ratio(totals["found"], totals["labeled"]),
            "precision": _ratio(totals["matched"], totals["extracted"]),
            "labeled_items": totals["labeled"],
            "found_items": totals["found"],
            "extracted_items": totals["extracted"],
        },
    }


def _load_features(feature_dir: Path) -> dict[str, set[str]]:
    features: dict[str, set[str]] = {}
    if not feature_dir.exists():
        raise FileNotFoundError("feature output directory does not exist")
    for path in sorted(feature_dir.glob("*.json")):
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("repo_key") != path.stem:
            raise ValueError("feature file has an invalid opaque repository key")
        evidence = payload.get("evidence")
        if not isinstance(evidence, list):
            raise ValueError("feature file has an invalid evidence list")
        keys: set[str] = set()
        for item in evidence:
            if not isinstance(item, dict) or not isinstance(item.get("competency_key"), str):
                raise ValueError("feature file contains invalid evidence")
            keys.add(item["competency_key"])
        features[path.stem] = keys
    return features


def _repository_key_from_public_url(repo_url: str) -> str:
    parsed = urlparse(repo_url)
    if parsed.scheme != "https" or parsed.netloc.casefold() != "github.com":
        raise ValueError("label repository URLs must use https://github.com")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2 or parsed.query or parsed.fragment:
        raise ValueError("label URL must identify one GitHub owner/repository pair")
    repository = parts[1].removesuffix(".git")
    return repository_key(f"{parts[0]}/{repository}")


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--labels",
        type=Path,
        default=ROOT / "spikes" / "stage1" / "labels" / "labels.yaml",
    )
    parser.add_argument(
        "--features",
        type=Path,
        default=ROOT / "spikes" / "stage1" / "out",
    )
    args = parser.parse_args()
    result = compare(args.labels, args.features)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
