# Portfolio Gap Bot: staged build plan

## Project overview

Portfolio Gap Bot analyzes repositories that a user has authorized through a GitHub
App, identifies evidence of technical skills, and will eventually recommend projects
that address gaps. Development is divided into stages so that API limits, evidence
quality, and operating costs can be tested before a user interface or production
service is built.

The initial operating target is a $0 budget with no payment card. Free-tier terms and
quotas change; verify them before starting each stage. Free services have no service
level agreement. Any availability percentage is an internal measurement, not a promise
to users.

The repository is public. Treat source history, workflow output, logs, artifacts, and
reports as public. Never commit credentials, private keys, real user data, database
dumps, source code fetched from scanned repositories, or features derived from private
repositories.

## Stage process

Complete stages in order. Before moving on, meet the stage's success criteria or
document an explicit waiver with its rationale and evidence. Record each criterion as
**Pass**, **Fail**, or **Not yet measured** in a report under `docs/stages/`. If a stage
fails its criteria twice, pause implementation and reconsider the design before adding
more features.

Stages 1 and 2 are deliberately limited experiments: they have no user interface.
Their purpose is to validate the riskiest assumptions before building product features.

## Stage overview

| Stage | Focus | Risk addressed |
|---|---|---|
| 0 | Repository, CI, GitHub App, and logging safeguards | Unsafe practices embedded early |
| 1 | Repository scan and skill-evidence extraction | GitHub API limits and Actions worker viability |
| 2 | Role taxonomy and deterministic scoring | Suggestions that are not useful |
| 3 | Searchable open-source project index | Search limits and storage |
| 4 | Versioned API and data layer | Data isolation, API stability, and rate limiting |
| 5 | Frontend and progress tracking | End-to-end usability |
| 6 | Hardening and closed beta | Data exposure and failure modes |
| 7 | Public launch | Operation within free-tier limits |

## Stage 0: Foundations

**Goal:** Establish a protected public repository and repeatable checks before product
code is added.

**Work:** Create the monorepo; enable branch protection and available secret-scanning
controls; configure linting, type checking, tests, secret scanning, CodeQL, and
Dependabot; register a read-only GitHub App and store its private key only as an
encrypted secret; document the logging policy; and verify that the chosen service
accounts do not require a payment card.

**Exit criteria:** Secret scanning blocks or flags a fake secret; CI passes on the
empty repository in under five minutes; a fork pull request cannot access secrets;
service accounts are available without a payment method; and ADR 001 records the
budget decision and monitored limits.

## Stage 1: Scan spike

**Goal:** Verify that an installation-scoped GitHub App can read a profile, extract
useful skill evidence within API limits, and run scans through GitHub Actions.

**Work:** Install the read-only App on the intended account, including one private test
repository. Use GraphQL to paginate installation repository metadata. Use ETags and
`If-None-Match` only for REST requests; GraphQL requests do not support conditional
requests. Inspect repository trees and a small, allowlisted set of files for languages,
dependency manifests, infrastructure-as-code, Docker configuration, CI workflows,
test files, and topics. Hand-label 20 public repositories, trigger workflow scans, and
measure the results.

**Starting exit targets:**

- A scan of about 50 repositories uses less than 20% of the applicable hourly rate-limit
  budget.
- Extracted evidence matches at least 80% of the manually labeled competencies.
- Median time from workflow dispatch to completion is under five minutes. If median
  queue delay alone exceeds two minutes, reconsider Actions as the worker.
- Automated tests reject unapproved log fields and verify that repository names, file
  paths, and file contents do not appear in logs or feature output.
- No repository source or file contents are stored; only extracted features are kept
  locally for analysis.
- A written decision records whether Actions remains the scan worker.

### GitHub rate-limit reference

The GitHub documentation checked on 2026-10-22 describes a minimum 5,000 REST requests
per hour and 5,000 GraphQL points per hour for a non-Enterprise installation, with
installation limits scaling by repository and organization-user counts up to 12,500.
Correctly authorized REST requests that return `304 Not Modified` do not count against
the primary REST limit. The scanner reads live REST response headers and GraphQL
`rateLimit` values rather than relying on fixed quotas. Confirm current limits before
measurement because GitHub may change them.

- [REST API rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)
- [GraphQL API rate and query limits](https://docs.github.com/en/graphql/overview/rate-limits-and-query-limits-for-the-graphql-api)
- [REST conditional requests](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api#conditional-requests)

## Stage 2: Roles and scoring

**Goal:** Convert evidence into skill gaps and ranked suggestions without requiring an
LLM.

**Work:** Define a versioned taxonomy for two initial roles; calculate competency
coverage as none, weak, or solid; rank suggestions using gap weight, coverage shortfall,
and fit, with a bonus for projects addressing multiple gaps; build a golden set of ten
consenting profiles; and optionally add a cached, feature-flagged LLM explanation.

**Starting exit targets:** Identical input always produces identical output; at least
70% of golden-set gaps are identified; at least 60% of the top five suggestions per
profile are actionable on review; and every scoring change runs the golden set in CI
with a visible result diff.

## Stage 3: Open-source project index

**Goal:** Search a maintained project index instead of relying on live GitHub search
for every recommendation.

**Work:** Ingest candidates at a low rate; store topics, languages, activity, issue
counts, licenses, and maintainer responsiveness; add topic-similarity embeddings; and
use scheduled jobs only to enqueue refresh work.

**Starting exit targets:** At least 5,000 indexed repositories under 150 MB; refresh
uses under 30% of the daily queue budget; at least seven of ten gap queries return a
relevant project in the top five; archived and stale projects are excluded; and p95
query time is under one second, including database wake-up.

## Stage 4: API and data layer

**Goal:** Provide a versioned service with tenant isolation and predictable behavior.

**Work:** Write an OpenAPI specification; implement versioned Worker routes and
GitHub sign-in; make scans asynchronous; create a PostgreSQL schema with row-level
security and forward-only migrations; add per-key rate limits, signed outbound
webhooks, idempotency keys, and verified inbound GitHub push webhooks.

**Exit criteria:** All endpoints are specified and schemathesis/oasdiff pass in CI;
tests prove that one user cannot read another user's rows in any table; rate-limited
requests return 429 with `Retry-After`; invalid signatures and replayed old events are
rejected; 1,000 simulated daily jobs use under half the daily queue budget; and account
deletion removes all user data.

## Stage 5: Frontend and progress tracking

**Goal:** Let a new user complete a scan and understand the results without assistance.

**Work:** Build a Next.js frontend on Cloudflare Pages with sign-in, clear explanations
of public and private repository access, role selection, skill gaps, ranked
recommendations and rationales, historical coverage snapshots, empty and error states,
and cached-result access during service outages.

**Starting exit targets:** A new user reaches first recommendations in under ten
minutes including scan time; a new commit followed by a rescan changes progress;
cached results remain available during GitHub or database outages; keyboard navigation
and contrast checks pass; and key-page Lighthouse performance is at least 85.

## Stage 6: Hardening and closed beta

**Goal:** Find security, reliability, and usability failures before public launch.

**Work:** Run ZAP against an ephemeral deployment and k6 load tests; practice restoring
an encrypted database backup; assess prompt-injection risks from third-party README
text; publish a privacy page; and run a closed beta with 10–20 users.

**Exit criteria:** No open high-severity ZAP findings; a backup restores to a fresh
Neon branch in under one hour with verified row counts; queue saturation never silently
drops jobs; beta logs contain no sensitive strings; at least 70% of beta users complete
a scan and every user can delete their data; and at least 20 hostile README samples
fail to change scoring or expose data.

## Stage 7: Launch

**Goal:** Operate publicly within free-tier limits and report service availability
honestly.

**Work:** Add uptime monitoring and alerts at 80% of each tracked limit, publish a
static status page, write a limit-exhaustion runbook, and announce the service.

**Exit criteria:** Alerts are tested for each monitored limit; intake pauses gracefully
when a budget is exhausted; 30 days of measured availability are reported against the
internal 99.9% target; and a written note identifies what to pay for first if usage
justifies spending.

## Repository layout

```text
apps/web/                 Next.js frontend
apps/api/                 TypeScript Worker API
workers/analysis/         Python analysis jobs
taxonomy/                 Versioned role and competency data
db/migrations/            Forward-only SQL migrations
infra/                    Deployment configuration
.github/workflows/        CI and worker workflows
docs/plan.md              This plan
docs/adr/                 Architecture decisions
docs/stages/              Stage reports
spikes/                   Temporary experiments and measurement tools
```

Keep private-repository labels and all scan output out of version control. Local
Stage 1 feature output, ETag caches, and custom labels are ignored by Git. Never upload
plaintext features from a public workflow.

## Contribution and release process

Use a short-lived branch for each logical change and Conventional Commit messages.
Changes should build and pass checks before they are committed. Merge through a pull
request after CI passes; keep the default branch deployable and do not rewrite its
history. Include documentation updates with related code changes and add an ADR when
an architectural decision changes.

When a stage meets its exit criteria, commit its report under `docs/stages/` and tag
the release as `v0.N.0`. Deploy merges to staging; production deployment requires a
release tag and manual approval. Roll back with a revert pull request. If a secret is
committed, rotate it before cleaning up the repository history.

## Open items to verify

- Whether a future Python hosting option, such as Render, requires a payment card.
- Current free-tier limits for Workers AI or another LLM provider.
- Availability of gradual Worker deployments on the free plan.
- Current GitHub Actions limits for public repositories.
- Which two roles should be used for Stage 2.

## Deferred work

Internal gRPC, learned ranking, multi-region deployment, SOC 2, and Kubernetes are out
of scope until later stages justify them.
