"""GitHub API usage counters and a per-scan rate-limit budget guard."""

from __future__ import annotations

from dataclasses import dataclass


class BudgetExceeded(RuntimeError):
    """Raised when the scan's configured API budget has been consumed."""


@dataclass
class UsageCounters:
    graphql_cost: int = 0
    graphql_requests: int = 0
    graphql_limit: int | None = None
    graphql_remaining: int | None = None
    rest_requests: int = 0
    rest_billable_requests: int = 0
    rest_limit: int | None = None
    rest_remaining: int | None = None
    rate_limit_remaining: int | None = None
    rate_limit_cost: int = 0


class BudgetGuard:
    def __init__(self, share: float = 0.5) -> None:
        if not 0 < share <= 1:
            raise ValueError("budget share must be greater than 0 and at most 1")
        self.share = share
        self.graphql_limit: int | None = None
        self.rest_limit: int | None = None
        self.counters = UsageCounters()

    def record_graphql_attempt(self) -> None:
        self.counters.graphql_requests += 1

    def record_graphql(self, cost: int, remaining: int, limit: int) -> None:
        self.counters.graphql_cost += cost
        self.counters.graphql_limit = limit
        self.counters.graphql_remaining = remaining
        self.counters.rate_limit_remaining = remaining
        self.counters.rate_limit_cost = cost
        self.graphql_limit = limit
        self._check_graphql_budget()

    def ensure_graphql_budget(self) -> None:
        if (
            self.graphql_limit is not None
            and self.counters.graphql_cost >= self._maximum(self.graphql_limit)
        ):
            raise BudgetExceeded("GraphQL API scan budget reached")

    def record_rest(
        self, *, status_code: int, remaining: int | None, limit: int | None
    ) -> None:
        if status_code != 304:
            self.counters.rest_billable_requests += 1
        if remaining is not None:
            self.counters.rate_limit_remaining = remaining
            self.counters.rest_remaining = remaining
        if limit is not None:
            self.rest_limit = limit
            self.counters.rest_limit = limit
        self.counters.rate_limit_cost = int(status_code != 304)
        self._check_rest_budget()

    def ensure_rest_budget(self) -> None:
        if (
            self.rest_limit is not None
            and self.counters.rest_billable_requests >= self._maximum(self.rest_limit)
        ):
            raise BudgetExceeded("REST API scan budget reached")

    def record_rest_attempt(self) -> None:
        self.counters.rest_requests += 1

    def record_rest_failure(self) -> None:
        self.counters.rest_billable_requests += 1
        self.counters.rate_limit_cost = 1
        self._check_rest_budget()

    def _check_graphql_budget(self) -> None:
        if (
            self.graphql_limit is not None
            and self.counters.graphql_cost > self._maximum(self.graphql_limit)
        ):
            raise BudgetExceeded("GraphQL API scan budget reached")

    def _check_rest_budget(self) -> None:
        if (
            self.rest_limit is not None
            and self.counters.rest_billable_requests > self._maximum(self.rest_limit)
        ):
            raise BudgetExceeded("REST API scan budget reached")

    def _maximum(self, limit: int) -> int:
        return max(0, int(limit * self.share))
