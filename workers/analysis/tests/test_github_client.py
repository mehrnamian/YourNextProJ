from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from workers.analysis.etag_cache import ETagCache
from workers.analysis.github_client import GitHubClient, NotModified
from workers.analysis.rate_limit import BudgetGuard


class FakeAuth:
    def installation_token(self) -> str:
        return "SENTINEL_FAKE_TOKEN"


def _node(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "nameWithOwner": f"owner/{name}",
        "isPrivate": True,
        "isFork": False,
        "isArchived": False,
        "pushedAt": "2026-10-22T00:00:00Z",
        "primaryLanguage": {"name": "Python"},
        "languages": {"edges": [{"size": 100, "node": {"name": "Python"}}]},
        "repositoryTopics": {"nodes": [{"topic": {"name": "automation"}}]},
        "defaultBranchRef": {"name": "main"},
    }


def test_graphql_paginates_and_rest_uses_etag_only(
    tmp_path: Path,
) -> None:
    seen_graphql: list[httpx.Request] = []
    seen_rest: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/graphql":
            seen_graphql.append(request)
            variables = json.loads(request.content)["variables"]
            page_after = variables["after"] is None
            cursor = "cursor-1" if page_after else None
            node = _node("first" if page_after else "second")
            return httpx.Response(
                200,
                json={
                    "data": {
                        "viewer": {
                            "repositories": {
                                "nodes": [node],
                                "pageInfo": {
                                    "hasNextPage": page_after,
                                    "endCursor": cursor,
                                },
                            }
                        },
                        "rateLimit": {
                            "cost": 2,
                            "remaining": 4998,
                            "limit": 5000,
                        },
                    }
                },
            )
        seen_rest.append(request)
        if request.headers.get("If-None-Match") == '"etag-1"':
            return httpx.Response(
                304,
                headers={
                    "ETag": '"etag-1"',
                    "X-RateLimit-Limit": "5000",
                    "X-RateLimit-Remaining": "4999",
                },
            )
        return httpx.Response(
            200,
            json={
                "tree": [{"path": "pyproject.toml", "type": "blob", "size": 30}],
                "truncated": False,
            },
            headers={
                "ETag": '"etag-1"',
                "X-RateLimit-Limit": "5000",
                "X-RateLimit-Remaining": "4999",
            },
        )

    cache = ETagCache(tmp_path / "etags.json")
    budget = BudgetGuard()
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = GitHubClient(FakeAuth(), http, cache, budget)  # type: ignore[arg-type]
        repositories = client.list_repositories()
        entries, truncated = client.get_tree(repositories[0])
        cache.save()
        with pytest.raises(NotModified):
            client.get_tree(repositories[0])

    assert [repo.name for repo in repositories] == ["first", "second"]
    assert len(seen_graphql) == 2
    assert all("If-None-Match" not in request.headers for request in seen_graphql)
    assert seen_rest[0].headers.get("If-None-Match") is None
    assert seen_rest[1].headers["If-None-Match"] == '"etag-1"'
    assert len(entries) == 1 and truncated is False
    assert budget.counters.graphql_requests == 2
    assert budget.counters.graphql_cost == 4
    assert budget.counters.rest_requests == 2
    cache_text = (tmp_path / "etags.json").read_text(encoding="utf-8")
    assert "pyproject.toml" not in cache_text
    assert "owner/first" not in cache_text


def test_rest_file_content_is_capped_before_evidence_extraction(
    tmp_path: Path,
) -> None:
    encoded = "A" * (((256 * 1024 + 2) // 3) * 4 + 4)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"encoding": "base64", "content": encoded},
            headers={"X-RateLimit-Limit": "5000", "X-RateLimit-Remaining": "4999"},
        )

    from workers.analysis.github_client import GitHubClientError

    repository = _node("large-content")
    repository_model = GitHubClient._repository(repository)
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = GitHubClient(FakeAuth(), http, ETagCache(tmp_path / "etags.json"), BudgetGuard())  # type: ignore[arg-type]
        with pytest.raises(GitHubClientError, match="size limit"):
            client.get_file_contents(repository_model, "pyproject.toml")
