from __future__ import annotations

import ast
import json
import logging
from pathlib import Path

import pytest

from workers.analysis.safe_log import ALLOWED_FIELDS, safe_log


def test_safe_log_emits_only_allowed_fields(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    safe_log(
        "scan_completed",
        job_id="test-123",
        status="completed",
        repo_count=5,
        evidence_count=2,
        duration_ms=20,
        rate_limit_remaining=4000,
        rate_limit_cost=3,
    )

    event, payload = caplog.records[-1].message.split(" ", maxsplit=1)
    record = json.loads(payload)
    assert event == "scan_completed"
    assert set(record) <= ALLOWED_FIELDS


def test_safe_log_rejects_unknown_fields_and_unsafe_values(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    with pytest.raises(ValueError):
        safe_log("scan_completed", repo_name="SENTINEL_REPO_NAME")
    with pytest.raises(ValueError):
        safe_log("scan_completed", job_id="SENTINEL/REPO")
    with pytest.raises(ValueError):
        safe_log("SENTINEL_REPO_NAME", status="completed")

    assert not caplog.records


def test_safe_log_obfuscates_user_supplied_job_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    safe_log("scan_completed", job_id="SENTINEL_REPO_NAME", status="completed")

    assert "SENTINEL_REPO_NAME" not in caplog.text


def test_scan_pipeline_logs_no_source_or_repository_identifiers(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    caplog.set_level(logging.INFO)
    from workers.analysis.etag_cache import ETagCache
    from workers.analysis.extractor import Signal
    from workers.analysis.github_client import Repository
    from workers.analysis.rate_limit import BudgetGuard
    from workers.analysis.scanner import scan_installation

    class FakeClient:
        def list_repositories(self) -> list[Repository]:
            return [
                Repository(
                    name_with_owner="owner/SENTINEL_REPO_NAME",
                    name="SENTINEL_REPO_NAME",
                    is_private=True,
                    is_fork=False,
                    is_archived=False,
                    pushed_at="2026-10-22T00:00:00Z",
                    primary_language="Python",
                    language_sizes={"Python": 100},
                    topics=(),
                    default_branch="main",
                )
            ]

        def get_tree(self, repository: Repository) -> tuple[list[dict[str, object]], bool]:
            return [
                {
                    "type": "blob",
                    "path": "SENTINEL_PATH/pyproject.toml",
                    "size": 30,
                }
            ], True

        def get_file_contents(self, repository: Repository, path: str) -> str:
            return 'dependencies = ["fastapi>=0.1"]\\n# SENTINEL_CONTENT'

    signals = (Signal("api-fastapi", ("fastapi",), (), (), {}),)
    result = scan_installation(
        FakeClient(),  # type: ignore[arg-type]
        signals,
        tmp_path / "out",
        ETagCache(tmp_path / ".cache" / "etags.json"),
        BudgetGuard(),
        job_id="test-job",
    )

    assert result.repo_count == 1
    assert result.evidence_count == 1
    assert result.usage is not None
    output = next((tmp_path / "out").glob("*.json")).read_text(encoding="utf-8")
    captured = capsys.readouterr()
    emitted = output + caplog.text + captured.out + captured.err
    for sentinel in ("SENTINEL_REPO_NAME", "SENTINEL_PATH", "SENTINEL_CONTENT"):
        assert sentinel not in emitted
    feature = json.loads(output)
    assert feature["tree_truncated"] is True
    assert feature["evidence"][0]["competency_key"] == "api-fastapi"


def test_scan_caps_files_fetched_per_repository() -> None:
    from workers.analysis.github_client import Repository
    from workers.analysis.scanner import _fetch_allowlisted_contents

    class FakeClient:
        calls: list[str] = []

        def get_file_contents(self, repository: Repository, path: str) -> str:
            self.calls.append(path)
            return "dependency = 'sample'"

    client = FakeClient()
    repository = Repository(
        name_with_owner="owner/repo",
        name="repo",
        is_private=False,
        is_fork=False,
        is_archived=False,
        pushed_at=None,
        primary_language=None,
        language_sizes={},
        topics=(),
        default_branch="main",
    )
    tree = [
        {"type": "blob", "path": f"services/{index}/pyproject.toml", "size": 20}
        for index in range(12)
    ]

    paths, contents = _fetch_allowlisted_contents(client, repository, tree)  # type: ignore[arg-type]

    assert len(paths) == 12
    assert len(contents) == 10
    assert len(client.calls) == 10


def test_worker_analysis_forbids_direct_print_and_logging_calls() -> None:
    logging_methods = {
        "debug",
        "info",
        "warning",
        "error",
        "exception",
        "critical",
        "log",
    }

    def is_logging_receiver(
        node: ast.expr,
        module_aliases: set[str],
        logger_factory_aliases: set[str],
    ) -> bool:
        if isinstance(node, ast.Name):
            return node.id in module_aliases | {"logger", "log"}
        if isinstance(node, ast.Attribute):
            return node.attr in {"logger", "log"} or is_logging_receiver(
                node.value, module_aliases, logger_factory_aliases
            )
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            return node.func.attr == "getLogger" and is_logging_receiver(
                node.func.value, module_aliases, logger_factory_aliases
            )
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            return node.func.id in logger_factory_aliases
        return False

    package_dir = Path(__file__).resolve().parents[1]
    for path in package_dir.glob("**/*.py"):
        if path.name == "safe_log.py" or "tests" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        module_aliases = {"logging"}
        logger_factory_aliases = {"getLogger"}
        logging_function_aliases: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                module_aliases.update(
                    alias.asname or alias.name
                    for alias in node.names
                    if alias.name == "logging"
                )
            elif isinstance(node, ast.ImportFrom) and node.module == "logging":
                for alias in node.names:
                    imported_name = alias.asname or alias.name
                    if alias.name == "getLogger":
                        logger_factory_aliases.add(imported_name)
                    elif alias.name in logging_methods:
                        logging_function_aliases.add(imported_name)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name):
                assert node.func.id != "print", f"direct print in {path.name}"
                assert node.func.id not in logging_function_aliases, (
                    f"direct logging call in {path.name}"
                )
            if isinstance(node.func, ast.Attribute) and node.func.attr in logging_methods:
                assert not is_logging_receiver(
                    node.func.value, module_aliases, logger_factory_aliases
                ), f"direct logging call in {path.name}"
