from __future__ import annotations

from pathlib import Path

from workers.analysis.extractor import (
    Signal,
    Snapshot,
    extract_evidence,
    load_signals,
    repository_key,
)

ROOT = Path(__file__).resolve().parents[3]


def test_taxonomy_has_25_data_driven_signals() -> None:
    signals = load_signals(ROOT / "taxonomy" / "seed-signals.yaml")
    assert len(signals) == 25
    assert len({signal.key for signal in signals}) == 25


def test_extractor_matches_content_metadata_and_negative_cases() -> None:
    signals = (
        Signal("api-fastapi", ("fastapi",), (), (), {}),
        Signal("iac-terraform", (), ("*.tf",), (), {}),
        Signal("cloud-azure", (), (), ("azure",), {}),
        Signal("testing-python", (), (), (), {"python": 0.5}),
        Signal("never-seen", ("missing-package",), (), (), {}),
    )
    snapshot = Snapshot(
        name_with_owner="owner/public-repo",
        pushed_at=None,
        primary_language="Python",
        language_sizes={"Python": 80, "JavaScript": 20},
        topics=("azure",),
        file_paths=("infra/main.tf", "pyproject.toml"),
        file_contents={"pyproject.toml": 'dependencies = ["fastapi>=0.100"]'},
    )

    actual = extract_evidence(snapshot, signals)

    assert {(item.competency_key, item.matcher_type) for item in actual} == {
        ("api-fastapi", "dependency"),
        ("cloud-azure", "topic"),
        ("iac-terraform", "file_pattern"),
        ("testing-python", "language_threshold"),
    }
    assert all(item.repo_count == 1 for item in actual)
    assert repository_key("OWNER/Repo") == repository_key("owner/repo")
