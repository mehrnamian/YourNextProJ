# Stage 1 scan runbook

## Before scanning

1. Confirm the GitHub App is installed on the intended account and has only the
   read-only repository permissions needed for metadata, trees, and contents. The
   installation token can see only repositories included in that installation.
2. Create encrypted repository secrets `APP_ID` and `APP_PRIVATE_KEY`. Keep the
   private key out of the repository, shell history, logs, and artifacts.
3. Do not use a personal access token for repository scanning. The `gh` CLI is used
   only to dispatch and time the workflow; the worker itself authenticates with the
   GitHub App.
4. Confirm `.gitignore` excludes local feature output, ETags, labels, and credentials.
   Do not commit scan output or labels for private repositories.

## Run locally (no clone)

From the repository root in PowerShell:

```powershell
python -m pip install -r requirements-dev.txt
$env:APP_ID = "<GitHub App ID>"
$env:PRIVATE_KEY = Get-Content -Raw "C:\secure\github-app-private-key.pem"
$env:INSTALLATION_ID = "<installation ID>"
python -m spikes.stage1.run_scan --job-id local-stage1
```

The scan uses GraphQL for paginated repository metadata. REST tree and file GETs use
`If-None-Match` when an ETag is available. Small allowlisted files are processed in
memory and discarded after evidence extraction. At most ten files (256 KiB each) are
fetched per repository. Only feature JSON and opaque-key ETags are written locally
under `spikes/stage1/out/` and `spikes/stage1/.cache/`; both paths are ignored by Git.
The rate-limit budget is read from the live GraphQL `rateLimit` result and REST
`X-RateLimit-*` headers, not a fixed quota.

## Run through GitHub Actions

1. Add the App credentials as repository secrets. Do not add an App key as a workflow
   input or variable.
2. In Actions, select **scan-worker**, choose **Run workflow**, and provide a
   non-sensitive `job_id` and the installation ID.
3. The worker writes only counts, status, duration, and API usage to logs and the
   workflow summary. Job IDs are hashed before display. No feature artifact is uploaded;
   output stays on the ephemeral runner and is discarded when the job ends.
4. For repeated timing measurements, from a machine with authenticated `gh` CLI access
   run:

   ```powershell
   python -m spikes.stage1.dispatch_and_time --runs 5 --installation-id "<ID>"
   ```

   Record dispatch delay and total duration. If dispatch delay alone is over two
   minutes, reconsider Actions. Do not run this command until the App, workflow, and
   installation are configured.

## Hand-label and compare

1. Label 20 **public** repositories yourself. Do not include private repositories. Copy
   `spikes/stage1/labels/template.yaml` to the ignored file
   `spikes/stage1/labels/labels.yaml`, then enter each public GitHub URL and the
   competency keys you verified manually. Do not guess labels.
2. Run a local scan so output exists under `spikes/stage1/out/`.
3. Compare without printing repository names:

   ```powershell
   python -m spikes.stage1.compare_labels
   ```

4. Record overall recall, precision, misses, and false positives in the Stage 1 report.
   Recall is the fraction of labeled competencies found (the 80% target); precision
   is informational.

## Clean handling and decision

- Never copy fetched file contents, repo names, file paths, usernames, tokens, or keys
  into logs, labels, reports, or commits.
- Keep `spikes/stage1/out/`, `spikes/stage1/.cache/`, and custom label files local.
- Once measurements exist, fill in the report criteria and decide in ADR 002 whether
  Actions remains the worker. Do not claim a criterion passes before you have evidence.
