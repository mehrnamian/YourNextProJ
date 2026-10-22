from __future__ import annotations

from pathlib import Path

from workers.analysis.extractor import (
    Signal,
    Snapshot,
    extract_evidence,
    load_signals,
    metadata_fingerprint,
    repository_key,
)

ROOT = Path(__file__).resolve().parents[3]


def test_taxonomy_has_25_data_driven_signals() -> None:
    signals = load_signals(ROOT / "taxonomy" / "seed-signals.yaml")
    assert len(signals) == 25
    assert len({signal.key for signal in signals}) == 25
    by_key = {signal.key: signal for signal in signals}
    assert by_key["data-pandas"].languages == {}
    assert by_key["testing-python"].languages == {}
    assert by_key["testing-js"].languages == {}


def test_extractor_matches_content_metadata_and_negative_cases() -> None:
    signals = (
        Signal("api-fastapi", ("fastapi",), (), (), {}),
        Signal("iac-terraform", (), ("*.tf",), (), {}),
        Signal("cloud-azure", (), (), ("azure",), {}),
        Signal("testing-python", ("pytest",), ("**/test_*.py",), (), {}),
        Signal("never-seen", ("missing-package",), (), (), {}),
    )
    snapshot = Snapshot(
        name_with_owner="owner/public-repo",
        pushed_at=None,
        primary_language="Python",
        language_sizes={"Python": 80, "JavaScript": 20},
        topics=("azure",),
        file_paths=("infra/main.tf", "pyproject.toml", "tests/test_api.py"),
        file_contents={
            "pyproject.toml": 'dependencies = ["fastapi>=0.100", "pytest"]',
        },
    )

    actual = extract_evidence(snapshot, signals)

    assert {(item.competency_key, item.matcher_type) for item in actual} == {
        ("api-fastapi", "dependency"),
        ("cloud-azure", "topic"),
        ("iac-terraform", "file_pattern"),
        ("testing-python", "dependency"),
        ("testing-python", "file_pattern"),
    }
    assert all(item.repo_count == 1 for item in actual)
    assert repository_key("OWNER/Repo") == repository_key("owner/repo")


def test_python_or_javascript_language_share_does_not_imply_packages_or_tests() -> None:
    signals = load_signals(ROOT / "taxonomy" / "seed-signals.yaml")
    snapshot = Snapshot(
        name_with_owner="owner/language-only",
        pushed_at=None,
        primary_language="Python",
        language_sizes={"Python": 800, "JavaScript": 200, "TypeScript": 100},
        topics=(),
        file_paths=(),
        file_contents={},
    )

    evidence = extract_evidence(snapshot, signals)

    assert not {
        item.competency_key
        for item in evidence
    } & {"data-pandas", "testing-python", "testing-js"}


def test_metadata_fingerprint_changes_when_signal_rules_change() -> None:
    base_signal = Signal("data-pandas", ("pandas",), (), ("pandas",), {})
    updated_signal = Signal(
        "data-pandas",
        ("pandas", "pandera"),
        (),
        ("pandas",),
        {},
    )
    original = metadata_fingerprint(
        primary_language="Python",
        language_sizes={"Python": 100},
        topics=(),
        default_branch="main",
        signals=(base_signal,),
    )
    updated = metadata_fingerprint(
        primary_language="Python",
        language_sizes={"Python": 100},
        topics=(),
        default_branch="main",
        signals=(updated_signal,),
    )

    assert original != updated
