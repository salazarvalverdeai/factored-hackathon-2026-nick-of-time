# Contributing to Nick of Time

How the team builds: spec-driven development (SDD) with EARS acceptance criteria, Architecture Decision Records,
small pull requests and tagged releases. Three senior engineers, each working with an AI assistant, in parallel.
The durable context for AI agents is [`CLAUDE.md`](CLAUDE.md); read it first.

| Role | Person | Owns |
|---|---|---|
| Lead, agent and models | Freddy (`@salazarvalverdeai`) | contracts, specs and ADR approval, policy engine, MCP tools, agent graph, classifier, model benchmark, pitch |
| Full stack | GianMarco (`@gianzk`) | web foundation and front-end standard, backend API + Postgres, deploy and CI, customer and analyst UIs, notifications |
| Data and analytics | Diego (`@vldiego`) | demo and eval data, evaluation harness, analytics pages, operational lakehouse |

## 1. The loop
```
Spec (what) ──► Plan (how) ──► Tasks ──► Implement
   gate 1          gate 2                  gate 3
 clarification   plan review            review + CI
```
- **The spec is the main artifact; code is its output.** Decide *what* and *why* before building *how*.
- Define up front only what is expensive to change (architecture, contracts, data model). Everything else is defined
  just in time, in the spec of the feature that needs it.
- **One spec per person at a time.** People work in parallel because the integration contract (spec 01) is approved
  first; two specs that touch the same module are serialized.
- **Anti spec-drift:** if code changes, its spec changes in the same PR — or the spec is marked Superseded.
- AI agents can skip instructions they know. **A human reviews every gate; nothing is approved blind.**

## 2. Spec workflow, step by step
1. **Assignment.** The lead opens an issue per feature (owner, priority, size, acceptance criteria). The issue links the
   spec; it never copies it.
2. **Branch.** `git switch -c spec/05-platform-api`
3. **Draft.** The owner and their AI write `specs/05-platform-api.md` from [`specs/_template.md`](specs/_template.md).
   Status: **Draft**. Copy the issue's acceptance criteria with the same numbers; you may add criteria, never drop or
   weaken one without the lead's approval.
4. **Spec PR** `docs(spec): add spec 05 platform API` → reviewed by the lead (+ affected owners via CODEOWNERS).
   **Gate 1 — clarification:** section 8 (assumptions and open questions) is closed or turned into labeled assumptions.
5. **Merge = Approved.** The scope is agreed and recorded in the PR.
6. **Plan.** On `feat/05-…`, the AI proposes the plan and tasks (section 10). **Gate 2:** the human reviews it before
   any code.
7. **Implement** in small PRs that cite the criteria they cover. Status: **In progress**.
8. **Review + CI.** **Gate 3:** one approval and green CI → squash merge.
9. **Close.** The last PR carries the closing checklist: every AC has a passing test that cites it · status
   **Implemented** · ADR for any decision taken · lessons added to `CLAUDE.md`. `Closes #N` closes the issue.
10. **Release.** The lead tags the milestone; `CHANGELOG.md` and `STATUS.md` are updated.

Spec states: **Draft → Approved → In progress → Implemented → Superseded** (→ spec NN). A spec PR should be
reviewable in 15 minutes; if not, split it.

## 3. Acceptance criteria and tests
- Criteria use **EARS** notation and are numbered within their spec (`AC-01`…), cited as "spec 05 AC-03":
  - Ubiquitous: *The system shall …*
  - Event: *When <trigger>, the system shall …*
  - State: *While <state>, the system shall …*
  - Unwanted: *If <trigger>, then the system shall …*
  - Optional: *Where <feature>, the system shall …*
- Every P0 spec has at least one happy-path criterion and one error or security criterion.
- **Every criterion has evidence in the PR**, one of:
  **[T]** an automated test · **[C]** a command or `curl` with its output · **[U]** a screenshot or short video against
  the public URL · **[D]** a file or document in the repo.
- Tests for spec NN live in `tests/test_specNN_<topic>.py` (or the app's own test folder) and cite the criterion in the
  test name or docstring (`test_ac_03_blocks_once_per_idempotency_key`). **A criterion without evidence is unfinished
  work.** CI fails an Implemented spec when a non-P1 [T] criterion has no citing test.
- No coverage percentage target. Every criterion has a test or a check, and every fixed bug brings its test.

## 4. Architecture Decision Records
- Write an ADR for: a technology choice, anything hard to reverse, a contract change, a deviation from an earlier
  decision, or an explicit trade-off between autonomy, accuracy, latency, cost and human oversight. Feature-internal
  details belong in the spec's plan, not in an ADR.
- Format: [`docs/adr/_template.md`](docs/adr/_template.md) (context, decision, alternatives with pros and cons,
  consequences, confidence level). A simple decision can be a one-sentence Y-statement.
- One file per decision, `docs/adr/NNNN-short-title.md`, numbered globally. If two PRs take the same number, the one
  merged second renumbers on rebase.
- States: **Proposed → Accepted**, or **Superseded by NNNN**. **Amended by NNNN** marks a partial change where the
  decision still stands: the accepted ADR gets only that header line. Accepted ADRs are never edited or deleted; a
  new ADR supersedes or amends them. Written by the feature owner, approved by the lead. *If it is not in the log, it
  was not decided.*

## 5. Git
- **GitHub Flow.** `main` is always deployable. Short-lived branches (under a day) from `main`; `main` only changes
  through pull requests.
- **Branch names:** `spec/NN-slug` (spec PR) · `feat/NN-slug` · `fix/NN-slug` · `docs/…` · `chore/…` · `ci/…`.
- **Commits:** [Conventional Commits](https://www.conventionalcommits.org/) in English, imperative, ≤ 72 characters,
  with a `why:` line and bullets. Enable the template once with `git config commit.template .github/commit_template.txt`.
  ```
  feat(policy): compute MX debit credit deadline in business days

  why: the regulatory clock must not count weekends or MX bank holidays

  - add business-day calendar per country
  - cover spec 02 AC-03 and AC-04

  Refs: spec 02 · ADR: 0005
  ```
  Types: `feat` `fix` `docs` `test` `refactor` `chore` `ci` `build` `perf`. Scopes: `api` `agent` `mcp` `policy`
  `store` `web` `eval` `ml` `data` `infra` `spec` `adr`.
- **Push:** never to `main`. Push early and open a **draft PR** from the first push. `git pull --rebase origin main`
  before asking for review. `--force-with-lease` only on your own branch.
- **Hooks:** `make hooks` installs the gitleaks pre-commit hook. A commit with a secret is blocked.
- **Parallel agents:** if you run more than one agent, give each its own `git worktree`; never two agents on one tree.

## 6. Pull requests and approvals
- Two kinds: **spec PRs** (the spec only) and **implementation PRs** (code + tests; several per spec, each under ~400
  changed lines excluding lockfiles and generated files).
- Fill in [the PR template](.github/pull_request_template.md): spec and criteria covered, ADRs, testing evidence,
  risks and rollback, AI assistance.
- **The PR title must be a Conventional Commit:** PRs are squash-merged and the title becomes the commit on `main`.

| What the PR touches | Who approves |
|---|---|
| `specs/**`, `docs/adr/**`, `contracts/**`, `eval/PROTOCOL.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `.github/**`, `langgraph.json` | **The lead** |
| Spec 01 (integration contract) | **All three** (agreement; CODEOWNERS cannot require it) |
| Code in another person's area | That area's owner (CODEOWNERS) |
| Anything else | One teammate other than the author |
| The lead's own PRs | GianMarco or Diego; the lead may merge as admin once that approval exists |

- **Review time:** under 1 hour during the sprint; under 30 minutes when the PR unblocks someone. An AI review
  (`/code-review`) is a useful first pass; the approval is human.
- **The author merges** after approval and green CI. Squash only; the branch is deleted on merge.
- **Hotfix:** if the public URL is down or the deadline is under 6 hours away, the lead may merge with the `hotfix`
  label and the review happens within 2 hours after.
- **`main` is protected:** pull request required, one approval, code-owner review, required CI checks, linear history,
  no force pushes.

## 7. Versioning and releases
- [SemVer](https://semver.org/) tags `vX.Y.Z` on `main`, each with a GitHub Release (`gh release create vX.Y.Z
  --generate-notes`) and an entry in [`CHANGELOG.md`](CHANGELOG.md) ([Keep a Changelog](https://keepachangelog.com/)).
- Milestone tags: `v0.1.0` existing base · `v0.2.0` framework + integration contract with stubs · `v0.3.0` first case
  end to end · `v0.4.0` the three mandatory cases on the public URL · `v0.5.0` evaluation + model selection ·
  `v1.0.0` submission. PATCH for hotfixes.
- The lead tags; every tag refreshes [`STATUS.md`](STATUS.md) with the deployed SHA verified by `curl`.
- `/api/health` reports the app version, git SHA, gold version, `policies.yaml` version and the Platform revision.

## 8. Continuous integration
Every PR runs: pytest (offline, fixtures only), the web app's lint and build, and a secret scan. It also runs `ruff` and the AC-coverage job (`scripts/ci/ac_coverage.py`). PRs that touch
`apps/web/` also run the **Playwright** end-to-end and accessibility suite against the mock API (desktop and 390 px
mobile); its screenshots count as [U] evidence. CI never calls a real LLM (the `fake` provider) and never reads the real
gold (a small fixture). Target: under 5 minutes per job. The evaluation harness against the real LLM runs manually
(`eval/`), and a Playwright smoke runs after every deploy. Details: [`docs/testing.md`](docs/testing.md).

## 9. Definitions
- **Feature:** a unit of user-visible value with one owner and one spec (`specs/NN-slug.md`).
- **Ready:** the spec is merged (Approved), its dependencies exist at least as stubs, its open questions are closed.
- **Done:** closing checklist complete · CI green · if it runs in production, deployed and verified on the public URL ·
  no secrets · listed in the changelog when released.
- **Priorities:** **P0** no submission without it · **P1** adds points · **P2** only if time allows.
- **Sizes:** **S** small, one focused · **M** medium, few files · **L** large, split if you can. No hours (D-004).
- **Freeze:** when v0.4.0 is on the public URL — after that only `fix/` and `docs/` branches.

## 10. Team rules
- **Contracts first.** Nobody codes against something that is not in `contracts/` or in an approved spec.
- **One case end to end every day** on the public URL, even if it looks rough.
- **The harness belongs to everyone:** each person adds evaluation cases for their own area.
- **Every figure carries a label** (`[data]`, `[external]`, `[assumption]`, `[simulated]`, `[projected]`) and a query or
  link. Nothing enters the pitch without one.
- **Regulatory and external figures cite an official public source and a verification date** (`source_url`,
  `verified_on`), never memory or a secondary summary ([ADR 0019](docs/adr/0019-official-sources-for-regulatory-figures.md)).
- With scope frozen, nothing new enters until what is functional is closed.

## 11. Language
English for code, comments, specs, ADRs, docs, branch names, commits, PRs, issues, releases and the UI judges see.
Spanish and Portuguese only for customer-facing text (agent replies, notifications, evaluation messages). Dataset
values stay as they are. Personal drafts in other languages stay out of the repo.

## 12. Working with AI assistants
- Point your assistant at `CLAUDE.md`, this file, `contracts/` and your spec. It must not touch other owners' folders
  or `contracts/` without an approved spec.
- **The human owns the spec and the review; the AI drafts the plan, code and tests.** Read every line before asking
  for review.
- Declare the assistance in the PR ("AI assistance: Claude Code — drafted tests and the store module").
