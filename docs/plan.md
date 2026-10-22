# Portfolio Gap Bot: staged build plan

Working copy of the relevant sections from the supplied staged-build plan. Stage 1 uses
an installation-scoped GitHub App, costs $0, and stores no repository source or file
contents. The supplied source is a draft; limits and measurement targets must be
rechecked before each stage.

## 1. Purpose and constraints

- One builder working part time; no credit card and a $0 budget.
- The public repository makes logs, artifacts, and history readable by anyone.
- Planned stack: Cloudflare Pages and Workers, Neon Postgres with pgvector, Upstash
  Redis, Cloudflare Queues, Python analysis jobs on GitHub Actions, and a free-tier LLM
  used sparingly in later stages.
- Free-tier limits change; verify them at the start of each stage. Free tiers have no
  SLA, so 99.9% availability is an internal measured target, not a user promise.
- Workers log job IDs, counts, and status only. Never log source, repository or file
  names, usernames, tokens, private keys, or exception messages.

## 2. How the stages work

Stages run in order. Do not begin the next stage until the current success criteria are
met or a waiver is documented. Each stage ends with a report in `docs/stages/` listing
each criterion, result, and evidence. If a stage fails its criteria twice, reconsider the
design before adding more code. Stages 1 and 2 intentionally have no UI or polish.

## 5. Stage 1: Scan spike

**Goal:** Prove that the bot can read a profile and extract useful evidence within
GitHub's limits, and that Actions can act as the worker.

**Tasks:** Install the read-only GitHub App on the account, including one private test
repository. Use GraphQL to list all installation repositories. Use ETags and
`If-None-Match` only for REST calls; GraphQL listing requests are not conditional. Extract
languages, dependency manifests, Bicep and Terraform, Dockerfiles, CI configuration,
test presence, and repository topics. Hand-label 20 public repositories as ground truth.
Dispatch a scan through a workflow and measure its timing.

**Starting success targets:** A scan of about 50 repositories uses under 20% of one
hourly rate-limit budget; evidence matches at least 80% of hand-labeled items; median
dispatch-to-completion is under five minutes; an automated test rejects unsafe log
fields and strings; no source code is stored, only extracted features; and a written
decision records whether Actions remains the worker.

**Rate-limit reference checked 2026-10-22:** GitHub currently documents a minimum
5,000 REST requests per hour and 5,000 GraphQL points per hour per non-Enterprise
installation, with scaling based on repository and organization-user counts up to
12,500. REST `304 Not Modified` responses to correctly authenticated conditional
requests do not count against the primary REST limit. The scanner reads the actual
REST response headers and GraphQL `rateLimit` fields instead of hard-coding these
starting figures.

References: [REST rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api),
[GraphQL rate and query limits](https://docs.github.com/en/graphql/overview/rate-limits-and-query-limits-for-the-graphql-api),
and [REST conditional requests](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api#conditional-requests).

## 12. Where to commit

The intended public monorepo layout is:

```text
apps/web/
apps/api/
workers/analysis/
taxonomy/
db/migrations/
infra/
.github/workflows/
docs/plan.md
docs/adr/
docs/stages/
spikes/
```

Never commit secrets or private keys, real user data, information derived from private
repositories, or database dumps. Encrypted backups may exist only as short-lived
workflow artifacts. Stage 1 local feature output and ETag cache are gitignored.

## 13. When to commit

Commit one logical change at a time, only when it builds and tests pass. Use a
short-lived branch and Conventional Commits. Merge through a PR after CI passes; keep
main deployable and do not rewrite its history. Update docs and add an ADR whenever a
decision changes. When a stage passes, commit its report and tag the release.
