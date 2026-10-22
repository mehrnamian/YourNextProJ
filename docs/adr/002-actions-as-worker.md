# ADR 002: GitHub Actions as the scan worker

- Status: Draft; decision pending Stage 1 measurements
- Date: 2026-10-22

## Context

Stage 1 must scan roughly 50 repositories through a read-only GitHub App, stay within
the rate-limit budget, avoid persisting source code, and complete quickly enough for
Actions to be a practical worker. The public repository requires logs and summaries to
contain only non-sensitive metrics.

## Options

1. **GitHub Actions:** dispatchable workflow; no always-on host; queue delay and
   execution time must be measured.
2. **Another free host:** consider only if Actions timing or constraints fail; verify
   current free-tier and card requirements before selection.
3. **Defer worker selection:** keep the scan local until measurement is possible.

## Measurements

- Repositories scanned: not yet measured
- GraphQL query cost and REST billable requests: not yet measured
- Hourly rate-limit budget used: not yet measured
- Dispatch delay (median / worst): not yet measured
- End-to-end duration (median / worst): not yet measured

## Decision


## Consequences

Pending measurement and decision.
