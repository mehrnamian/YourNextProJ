# Stage 1 scan runbook

This guide describes how to configure and run the Stage 1 GitHub repository scan,
compare extracted evidence with manually verified labels, and record measurements.
The scan reads repositories available to a GitHub App installation. It does not clone
repositories or retain fetched file contents.

## Prerequisites

Before scanning:

1. Merge the Stage 1 branch into the repository's default branch so the
   `scan-worker` workflow is available there.
2. Register a GitHub App and grant only the read permissions needed for repository
   metadata and contents. Install it only on accounts and repositories authorized for
   this scan. Include a private test repository if required by the Stage 1 plan.
3. Add `APP_ID` and `APP_PRIVATE_KEY` as repository Actions secrets under
   **Settings → Secrets and variables → Actions**. Do not place credentials in workflow
   inputs, repository variables, source files, or chat. Keep the private key securely
   stored outside the repository.
4. Confirm that `gh` is installed and authenticated if using the workflow timing
   utility. Its GitHub CLI access is used to dispatch and inspect workflow runs only;
   the scanner authenticates through the GitHub App.
5. Verify that `.gitignore` excludes scan output, the ETag cache, custom labels, and
   environment files. Never commit scan output or labels for private repositories.

Do not use a personal access token to read repositories. The scan is scoped to
repositories available to the installed GitHub App.

## Run a local scan

From the repository root in PowerShell:

```powershell
python -m pip install -r requirements-dev.txt
$env:APP_ID = "<GitHub App ID>"
$env:PRIVATE_KEY = Get-Content -Raw "C:\secure\github-app-private-key.pem"
$env:INSTALLATION_ID = "<installation ID>"
python -m spikes.stage1.run_scan --job-id local-stage1
```

Use a secure local key-file path and do not add the private key to shell commands,
scripts, or repository files. Close the PowerShell session after the scan to clear its
environment variables.

The scanner uses GraphQL for paginated repository metadata. REST tree and file
requests use `If-None-Match` when a cached ETag is available; GraphQL requests are not
conditional. The API budget is calculated from live GraphQL `rateLimit` data and REST
`X-RateLimit-*` response headers. Each repository fetches no more than ten allowlisted
files, each capped at 256 KiB. File contents are processed in memory, then discarded.

The local scan writes extracted feature JSON to `spikes/stage1/out/` and ETags to
`spikes/stage1/.cache/`. These paths are ignored by Git. Feature output uses opaque
repository keys; do not publish or commit it.

## Run a scan in GitHub Actions

1. In the repository, open **Actions → scan-worker → Run workflow**.
2. Enter a non-sensitive `job_id` and the GitHub App installation ID.
3. Start the workflow and review its status and summary.

The workflow uses the App credentials stored as repository secrets. Logs and summaries
include only permitted counts, status, duration, and API usage; displayed job IDs are
hashed. The workflow uploads no feature artifacts, and scan output on the temporary
runner is discarded when the job ends.

Do not dispatch a real scan until the App installation and secrets are configured and
the selected repositories are authorized for scanning.

## Measure workflow dispatch and duration

On a machine with authenticated `gh` CLI access, run the following from the repository
root:

```powershell
python -m spikes.stage1.dispatch_and_time --runs 5 --installation-id "<ID>"
```

The utility dispatches the workflow repeatedly, then reports median and worst-case
dispatch delay and total duration. Record the results in the [Stage 1 report](../../docs/stages/stage-1.md).
If median dispatch delay alone exceeds two minutes, reconsider Actions as the worker.
Do not run this utility until the workflow is on the default branch and the App
installation is ready.

## Hand-label public repositories and compare results

1. Select 20 public repositories and verify their demonstrated competencies yourself.
   Do not label private repositories or infer labels without evidence.
2. Copy `spikes/stage1/labels/template.yaml` to the ignored local file
   `spikes/stage1/labels/labels.yaml`.
3. For each repository, enter its public GitHub URL and the verified competency keys.
   Keep the completed label file local; it is excluded from version control.
4. Run a local scan so feature records are available in `spikes/stage1/out/`.
5. Compare the labels and features:

   ```powershell
   python -m spikes.stage1.compare_labels
   ```

The report contains opaque repository keys, recall, precision, missed competencies,
and false positives. Recall is the proportion of labeled competencies found and is the
80% Stage 1 target. Precision is informational. Record aggregate results and supporting
evidence in the Stage 1 report; do not publish repository-level labels or scan output.

## Data-handling requirements

- Do not copy fetched source, file contents, repository names, file paths, usernames,
  tokens, or private keys into logs, workflow summaries, reports, or commits.
- Keep `spikes/stage1/out/`, `spikes/stage1/.cache/`, and custom label files local.
- Do not upload scan features as workflow artifacts.
- Do not claim a success criterion passes until the required measurement or test
  provides evidence.

## Completing Stage 1

Update the Stage 1 report with measured rate-limit usage, hand-label accuracy, and
workflow timings. Then update ADR 002 with a decision on the worker choice and explain
the evidence supporting it. Stage 1 is complete only after its criteria are satisfied
or an explicit, evidence-based waiver is documented.
