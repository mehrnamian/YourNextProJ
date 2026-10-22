from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from spikes.stage1.compare_labels import compare
from workers.analysis.extractor import repository_key


def test_label_comparison_reports_recall_precision_misses_and_false_positives(
    tmp_path: Path,
) -> None:
    features_dir = tmp_path / "out"
    features_dir.mkdir()
    repo_key = repository_key("owner/public-repo")
    (features_dir / f"{repo_key}.json").write_text(
        json.dumps(
            {
                "repo_key": repo_key,
                "evidence": [
                    {"competency_key": "testing-python"},
                    {"competency_key": "containers-docker"},
                ],
            }
        ),
        encoding="utf-8",
    )
    labels = tmp_path / "labels.yaml"
    labels.write_text(
        yaml.safe_dump(
            {
                "repos": [
                    {
                        "repo_url": "https://github.com/owner/public-repo",
                        "competency_keys": ["testing-python", "iac-terraform"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = compare(labels, features_dir)

    assert result["overall"]["recall"] == 0.5
    assert result["overall"]["precision"] == 0.5
    assert result["per_repo"][0]["misses"] == ["iac-terraform"]
    assert result["per_repo"][0]["false_positives"] == ["containers-docker"]


def test_comparison_rejects_non_github_label_urls(tmp_path: Path) -> None:
    labels = tmp_path / "labels.yaml"
    labels.write_text("repos:\n  - repo_url: http://example.com/repo\n    competency_keys: []\n")
    with pytest.raises(ValueError, match="https://github.com"):
        compare(labels, tmp_path)
