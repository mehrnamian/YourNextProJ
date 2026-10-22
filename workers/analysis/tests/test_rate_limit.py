from __future__ import annotations

import pytest

from workers.analysis.rate_limit import BudgetExceeded, BudgetGuard


def test_budget_guard_stops_before_next_rest_call() -> None:
    budget = BudgetGuard(share=0.2)
    budget.record_rest(status_code=200, remaining=4999, limit=5000)
    for _ in range(999):
        budget.record_rest(status_code=200, remaining=4000, limit=5000)

    with pytest.raises(BudgetExceeded):
        budget.ensure_rest_budget()


def test_graphql_budget_records_cost_then_stops() -> None:
    budget = BudgetGuard(share=0.2)
    budget.record_graphql(cost=1000, remaining=4000, limit=5000)

    assert budget.counters.graphql_cost == 1000
    with pytest.raises(BudgetExceeded):
        budget.record_graphql(cost=1, remaining=3998, limit=5000)
