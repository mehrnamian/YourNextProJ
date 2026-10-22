# ADR 002: GitHub Actions as the scan worker

- **Status:** Proposed; decision deferred until Stage 1 timing measurements
- **Date:** 2026-10-22

## Context

Stage 1 evaluates whether GitHub Actions can run an installation-scoped repository scan
with acceptable dispatch delay and total duration. The scan should process about 50
repositories, remain within the GitHub App installation's rate limits, and avoid
persisting repository source code or file contents.

This repository is public. Workflow logs and summaries must therefore contain only
approved, non-sensitive metrics. Scan features are not uploaded as workflow artifacts.

## Options considered

1. **GitHub Actions:** Dispatchable workflow with no always-on worker. Dispatch delay
   and execution time must be measured before accepting this option.
2. **Another free worker host:** Consider only if Actions fails the timing or
   operational criteria. Verify current free-tier quotas and payment-card requirements
   before selecting a provider.
3. **Defer the worker decision:** Run scans locally until enough evidence exists to
   choose a hosted worker.

## Measurements

| Measurement | Result |
|---|---|
| Repositories scanned | Not yet measured |
| GraphQL query cost and REST billable requests | Not yet measured |
| Share of hourly rate-limit budget used | Not yet measured |
| Dispatch delay, median and worst case | Not yet measured |
| End-to-end duration, median and worst case | Not yet measured |

## Decision

Deferred. Select an option after the required scan and workflow timing measurements have
been collected and documented in the [Stage 1 report](../stages/stage-1.md).

## Consequences

No worker-host commitment is made by this record. Until the decision is updated, the
Actions workflow is an experiment and must not be treated as a production service.
