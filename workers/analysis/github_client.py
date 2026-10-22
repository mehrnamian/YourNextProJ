"""Small GitHub API client for installation-scoped repository scans."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from workers.analysis.auth import API_VERSION, GITHUB_API, GitHubAppAuth
from workers.analysis.etag_cache import ETagCache
from workers.analysis.rate_limit import BudgetGuard

GRAPHQL_URL = "https://api.github.com/graphql"


class GitHubClientError(RuntimeError):
    """Raised for unexpected or malformed GitHub API responses."""


class NotModified(GitHubClientError):
    """Raised when a conditional REST request has no changed representation."""


@dataclass(frozen=True)
class Repository:
    name_with_owner: str
    name: str
    is_private: bool
    is_fork: bool
    is_archived: bool
    pushed_at: str | None
    primary_language: str | None
    language_sizes: dict[str, int]
    topics: tuple[str, ...]
    default_branch: str | None

    @property
    def owner(self) -> str:
        return self.name_with_owner.split("/", maxsplit=1)[0]


class GitHubClient:
    def __init__(
        self,
        auth: GitHubAppAuth,
        http: httpx.Client,
        etag_cache: ETagCache,
        budget: BudgetGuard,
    ) -> None:
        self.auth = auth
        self.http = http
        self.etag_cache = etag_cache
        self.budget = budget

    def list_repositories(self) -> list[Repository]:
        query = """
        query($first: Int!, $after: String) {
          viewer {
            repositories(
              first: $first
              after: $after
              affiliations: [OWNER, COLLABORATOR, ORGANIZATION_MEMBER]
              orderBy: {field: NAME, direction: ASC}
            ) {
              nodes {
                name
                nameWithOwner
                isPrivate
                isFork
                isArchived
                pushedAt
                primaryLanguage { name }
                languages(first: 100, orderBy: {field: SIZE, direction: DESC}) {
                  edges { size node { name } }
                }
                repositoryTopics(first: 20) { nodes { topic { name } } }
                defaultBranchRef { name }
              }
              pageInfo { hasNextPage endCursor }
            }
          }
          rateLimit { cost remaining limit }
        }
        """
        repositories: list[Repository] = []
        self.partial_repositories: list[Repository] = []
        cursor: str | None = None
        while True:
            payload = self._graphql(
                query,
                {"first": 100, "after": cursor},
            )
            try:
                data = payload["data"]
                connection = data["viewer"]["repositories"]
                page_info = connection["pageInfo"]
                nodes = connection["nodes"]
                if not isinstance(nodes, list):
                    raise TypeError
                repositories.extend(self._repository(node) for node in nodes)
                self.partial_repositories = list(repositories)
                if not page_info["hasNextPage"]:
                    break
                next_cursor = page_info["endCursor"]
                if not isinstance(next_cursor, str) or next_cursor == cursor:
                    raise GitHubClientError("GitHub returned an invalid repository cursor")
                cursor = next_cursor
            except (KeyError, TypeError, ValueError) as exc:
                raise GitHubClientError("GitHub returned an invalid repository listing") from exc
        return repositories

    def get_tree(
        self, repository: Repository, *, conditional: bool = True
    ) -> tuple[list[dict[str, Any]], bool]:
        if not repository.default_branch:
            return [], False
        url = (
            f"{GITHUB_API}/repos/{quote(repository.owner, safe='')}/"
            f"{quote(repository.name, safe='')}/git/trees/"
            f"{quote(repository.default_branch, safe='')}?recursive=1"
        )
        payload = self.get_json(url, conditional=conditional)
        try:
            entries = payload["tree"]
            truncated = payload["truncated"]
            if not isinstance(entries, list) or not isinstance(truncated, bool):
                raise TypeError
            return entries, truncated
        except (KeyError, TypeError) as exc:
            raise GitHubClientError("GitHub returned an invalid repository tree") from exc

    def get_file_contents(
        self, repository: Repository, path: str, *, conditional: bool = True
    ) -> str:
        url = (
            f"{GITHUB_API}/repos/{quote(repository.owner, safe='')}/"
            f"{quote(repository.name, safe='')}/contents/{quote(path, safe='/')}?"
            f"ref={quote(repository.default_branch or '', safe='')}"
        )
        payload = self.get_json(url, conditional=conditional)
        try:
            if not isinstance(payload, dict):
                raise TypeError
            if payload.get("encoding") != "base64" or not isinstance(
                payload.get("content"), str
            ):
                raise GitHubClientError("GitHub returned an unsupported file representation")
            encoded = "".join(payload["content"].split())
            if len(encoded) > ((256 * 1024 + 2) // 3) * 4:
                raise GitHubClientError("GitHub returned file contents above the size limit")
            content = base64.b64decode(encoded, validate=False)
            if len(content) > 256 * 1024:
                raise GitHubClientError("GitHub returned file contents above the size limit")
            return content.decode("utf-8")
        except (KeyError, TypeError, UnicodeDecodeError, ValueError) as exc:
            raise GitHubClientError("GitHub returned invalid file contents") from exc

    def get_json(self, url: str, *, conditional: bool = True) -> Any:
        self.budget.ensure_rest_budget()
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.auth.installation_token()}",
            "X-GitHub-Api-Version": API_VERSION,
        }
        etag = self.etag_cache.get(url) if conditional else None
        if etag is not None:
            headers["If-None-Match"] = etag
        self.budget.record_rest_attempt()
        try:
            response = self.http.get(url, headers=headers)
        except httpx.HTTPError as exc:
            self.budget.record_rest_failure()
            raise GitHubClientError("GitHub REST request failed") from exc

        remaining = _header_int(response, "x-ratelimit-remaining")
        limit = _header_int(response, "x-ratelimit-limit")
        self.budget.record_rest(
            status_code=response.status_code,
            remaining=remaining,
            limit=limit,
        )
        new_etag = response.headers.get("etag")
        if new_etag:
            self.etag_cache.put(url, new_etag)
        if response.status_code == 304:
            raise NotModified("GitHub returned an unchanged REST representation")
        if response.status_code != 200:
            raise GitHubClientError(
                f"GitHub REST request failed with HTTP {response.status_code}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise GitHubClientError("GitHub returned invalid JSON") from exc

    def _graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        self.budget.ensure_graphql_budget()
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.auth.installation_token()}",
            "X-GitHub-Api-Version": API_VERSION,
        }
        self.budget.record_graphql_attempt()
        try:
            response = self.http.post(
                GRAPHQL_URL,
                headers=headers,
                json={"query": query, "variables": variables},
            )
        except httpx.HTTPError as exc:
            raise GitHubClientError("GitHub GraphQL request failed") from exc
        if response.status_code != 200:
            raise GitHubClientError(
                f"GitHub GraphQL request failed with HTTP {response.status_code}"
            )
        try:
            payload: Any = response.json()
            if not isinstance(payload, dict) or payload.get("errors"):
                raise GitHubClientError("GitHub GraphQL returned an error")
            data = payload["data"]
            rate = data["rateLimit"]
            self.budget.record_graphql(
                cost=int(rate["cost"]),
                remaining=int(rate["remaining"]),
                limit=int(rate["limit"]),
            )
            if not isinstance(data, dict):
                raise TypeError
            return {"data": data}
        except (KeyError, TypeError, ValueError) as exc:
            raise GitHubClientError("GitHub returned an invalid GraphQL response") from exc

    @staticmethod
    def _repository(node: Any) -> Repository:
        if not isinstance(node, dict):
            raise GitHubClientError("GitHub returned an invalid repository record")
        try:
            language = node["primaryLanguage"]
            branch = node["defaultBranchRef"]
            languages = {
                edge["node"]["name"]: int(edge["size"])
                for edge in node["languages"]["edges"]
            }
            topics = tuple(
                item["topic"]["name"] for item in node["repositoryTopics"]["nodes"]
            )
            full_name = node["nameWithOwner"]
            if not isinstance(full_name, str) or full_name.count("/") != 1:
                raise TypeError
            return Repository(
                name_with_owner=full_name,
                name=str(node["name"]),
                is_private=bool(node["isPrivate"]),
                is_fork=bool(node["isFork"]),
                is_archived=bool(node["isArchived"]),
                pushed_at=node["pushedAt"],
                primary_language=language["name"] if language else None,
                language_sizes=languages,
                topics=topics,
                default_branch=branch["name"] if branch else None,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise GitHubClientError("GitHub returned an invalid repository record") from exc


def _header_int(response: httpx.Response, name: str) -> int | None:
    value = response.headers.get(name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None
