# Stage 1 report: scan spike

## Status

**In progress.** Automated implementation checks pass. GitHub API usage, hand-labeled
evidence accuracy, and workflow dispatch timing have not yet been measured. No scan
has been run against a GitHub account.

Stage 1 implementation is available on the `feat/stage1-scan-spike` branch. The
workflow must be merged into the default branch before it can be dispatched there.
Before scanning, configure a read-only GitHub App installation and its repository
secrets as described in the [scan runbook](../../spikes/stage1/RUNBOOK.md).

## Success criteria

| Criterion | Result | Evidence | Notes |
|---|---|---|---|
| Scan about 50 repositories using less than 20% of the hourly rate-limit budget | Not yet measured | `spikes/stage1/run_scan.py`; `workers/analysis/rate_limit.py` | Record GraphQL cost and REST billable requests against the live API limits. |
| Find at least 80% of manually labeled competencies | Not yet measured | `spikes/stage1/compare_labels.py`; `spikes/stage1/labels/template.yaml` | Requires hand labels for 20 public repositories and local scan output. |
| Median dispatch-to-completion time below five minutes | Not yet measured | `spikes/stage1/dispatch_and_time.py` | If median dispatch delay alone exceeds two minutes, reconsider Actions as the worker. |
| Automated tests reject unsafe log fields and strings | Pass | `test_safe_log_emits_only_allowed_fields`; `test_safe_log_rejects_unknown_fields_and_unsafe_values`; `test_safe_log_obfuscates_user_supplied_job_id`; `test_scan_pipeline_logs_no_source_or_repository_identifiers`; `test_worker_analysis_forbids_direct_print_and_logging_calls` | Synthetic tests only; no account scan was performed. |
| Store no repository source or file contents; retain extracted features only | Pass | `test_scan_pipeline_logs_no_source_or_repository_identifiers`; `test_rest_file_content_is_capped_before_evidence_extraction`; `test_graphql_paginates_and_rest_uses_etag_only`; `.gitignore` | Tests verify that sentinel repository names, paths, and contents are absent from feature output, logs, and the URL-hashed ETag cache. No real scan output is included. |
| Record whether Actions remains the worker | Not yet measured | [ADR 002](../adr/002-actions-as-worker.md) | The decision is deferred until dispatch measurements are available. |

## Validation performed

- Python 3.12.3: 18 automated tests passed locally.
- Ruff lint: passed.
- Mypy type checking: passed.
- GitHub Actions CI: passed on the Stage 1 branch in workflow run
  [39700891094](https://github.com/mehrnamian/YourNextProJ/actions/runs/39700891094).
- The Actions scan workflow has not been dispatched.

## Data handling and implementation

- GraphQL is used for paginated installation repository metadata. ETags and
  `If-None-Match` are used only for REST requests.
- The local ETag cache contains URL hashes and ETags, not URLs, response bodies,
  repository names, or file paths.
- At most ten allowlisted files of up to 256 KiB each are fetched from a repository.
  File contents are processed in memory and discarded after evidence extraction.
- Feature records use an opaque SHA-256 repository key and contain extracted
  competencies, not source contents or repository names.
- Local feature output, ETag cache, and custom label files are excluded from version
  control. The Actions workflow uploads no scan output.
- User-supplied job identifiers are hashed before being written to logs or workflow
  summaries.

## Outstanding measurements

Use the runbook to configure the App, run the scan, hand-label public repositories,
compare results, and measure Actions dispatch timing. Update each criterion above with
the measured value and supporting evidence before deciding whether Stage 1 is complete.
