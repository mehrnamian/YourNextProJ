# Stage 1: Scan spike

Status: **in progress; real measurements not run**

No scan was run against a GitHub account. The project folder was empty when this work
started, so Stage 0 service setup, repository protection, registered App, and pre-existing
CI could not be verified here. The implementation does not contain credentials and
requires a user-provided read-only GitHub App installation to run.

| Success criterion | Result | Evidence | Notes |
|---|---|---|---|
| About 50 repositories use under 20% of one hourly rate-limit budget | Not yet measured | `spikes/stage1/run_scan.py`; `workers/analysis/rate_limit.py` | Run against the installed App and record GraphQL cost and REST billable requests against the response limits. |
| At least 80% of hand-labeled evidence is found | Not yet measured | `spikes/stage1/compare_labels.py`; `spikes/stage1/labels/template.yaml` | The 20 public-repository labels and scan output are user-supplied and currently absent. |
| Median dispatch-to-completion is under five minutes | Not yet measured | `spikes/stage1/dispatch_and_time.py` | No workflow dispatch was performed. Reconsider Actions if median dispatch delay alone exceeds two minutes. |
| Tests reject log fields and strings outside the allowed set | Pass | `test_safe_log_emits_only_allowed_fields`; `test_safe_log_rejects_unknown_fields_and_unsafe_values`; `test_scan_pipeline_logs_no_source_or_repository_identifiers`; `test_worker_analysis_forbids_direct_print_and_logging_calls` | Verified with synthetic data; no real account scan was run. |
| No source code or file contents are stored; only extracted features | Pass | `test_scan_pipeline_logs_no_source_or_repository_identifiers`; `test_rest_file_content_is_capped_before_evidence_extraction`; `test_graphql_paginates_and_rest_uses_etag_only`; `.gitignore` | Synthetic test run verifies feature output and URL-hashed ETag cache contain no sentinel content, paths, or repository names. Real scan output is not included. |
| A written decision says whether Actions remains the worker | Not yet measured | `docs/adr/002-actions-as-worker.md` | Decision is intentionally blank until dispatch measurements exist. |

### Implementation notes

- Local validation on Python 3.12.3: 18 tests passed; Ruff and mypy passed. CLI `--help`
  smoke checks passed. The GitHub Actions workflow itself has not been dispatched.
- Repository listing is GraphQL; conditional requests and ETags are used on REST requests
  only.
- ETag cache keys are SHA-256 hashes of request URLs; the cache stores ETags, not URLs,
  response bodies, repository names, or file paths.
- Each repository fetches at most ten allowlisted files (256 KiB maximum each) to bound
  request and memory use; evidence can still match all file paths from the tree response.
- Feature files use an opaque SHA-256 repository key and contain evidence only. Local
  results and cache are ignored by Git and are not uploaded by the workflow.
- User-supplied job IDs are hashed before they appear in logs or public job summaries.
- The report's measurements remain placeholders until the account owner runs the
  measurement steps and supplies hand labels.
