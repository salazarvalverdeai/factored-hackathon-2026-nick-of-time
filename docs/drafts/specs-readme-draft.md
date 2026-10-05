# Specs index draft: proposed statuses (for the lead's review)

Proposal to refresh the `Status` column of `specs/README.md` (which still says Draft for most rows). Basis: the `## 10`
task checkboxes of each spec on `origin/main` at `4ca799a` (2026-10-05) and the merged PRs listed in
`CHANGELOG-draft.md`. States follow `specs/README.md`: Draft, Approved, In progress, Implemented, Superseded. The closing
checklist of CLAUDE.md applies to Implemented: every AC has a passing test that cites it, spec marked Implemented, ADR
for any decision, lessons added to `CLAUDE.md`.

Result: **no spec is ready for Implemented today.** Two header fields also disagree with their own checkboxes (noted in
the last column) and should be reconciled in the same PR that moves the status.

| # | Feature | Header today | Proposed | What blocks "Implemented" (unchecked in section 10, or other) |
|---|---|---|---|---|
| 01 | Integration contract | Draft | **In progress** | T8 tests `tests/test_spec01_*.py` citing AC-02, 03, 04, 06, 07, 08. Contract is at 1.4.0 and used by merged code, so it is effectively approved; the lead approves the Draft header. Open PR #149 moves it to 1.5.0 |
| 02 | Policy engine and clock | In progress | **In progress** | T3 clock for PE and CL plus holiday files (MX, AR, CO, BR rows merged in #67, #68); T6 policy ids listed in `/agent`; T7 `clock.today` time zones and `fx_reference` |
| 03 | MCP server, 16 tools | Draft | **In progress** | T8 entry point, Dockerfile and compose service verified (the image runs `python -m mcp_server`, PR #122, but the box is unchecked). T1-T7 are checked. Header says Draft while the tools are merged |
| 04 | Agent graph | Draft | **In progress** | T1 skeleton boxes, T6 status and connect nodes and returning customer (code is in `intake.py`; box unchecked), T7 progress stream and S1/S2 (PR #133 merged; box unchecked), T7a, T8 Platform deployment and `/agent` content, the `tests/test_spec04_*` item; INT3 on the public URL gates `v0.4.0` |
| 05 | Backend API | In progress | **In progress** | Task 7 run on Postgres and the public URL, Cognito pool values, gold catalog. Open PRs #148, #150, #151, #152 add rate limits, outage turn and demo sessions (AC-14 to AC-18) |
| 06 | Deploy and CI | Draft | **In progress** | T1-T6 boxes all unchecked although the stack, deploy workflow and backup merged (#41, #136, #129, #119) and the public URL answers `/api/health` with the deployed SHA. Remaining evidence: T6 rollback drill and the TLS check recorded in the spec; then check the boxes. Index row also says "Not started" |
| 07 | Customer chat | In progress | **In progress** | Task 4 call the live agent proxy |
| 08 | Analyst console | In progress | **In progress** | Task 5 Cognito login and `POST /api/cases/{id}/action` against the live API |
| 09 | Demo and eval data | Draft | **In progress** | T5 classifier set reviewed line by line (drafts in #118, #144), T6 second labeling of 20 cases (kit in #143), M02 review and seal `eval/PROTOCOL.md`, tag `protocol-v1`. Open PR #128 proposes this status |
| 10 | Evaluation harness | Draft | **In progress** | T6 `make eval` and dev set on S0/S1 (open PR #127), T7 held-out run on S0/S1/S2 after M02; T5 label cross is tested on a fixture only. Open PR #128 proposes this status |
| 11 | Intent classifier | Draft | **In progress** | T1 `eval/PROTOCOL.md` floors sealed, T3 B1 training, T4 B2 prompt, T5 injection LR arm, T6 evaluation script and model-selection ADR. B0 rules and the date parser are merged (#55, #74, #139) |
| 12 | Insight pages | Draft | **In progress** | T4 benchmark, classifier and fraud sections (open PR #130), T6 operational KPIs (needs spec 14), T7 screenshots on the public URL. Open PR #128 proposes this status |
| 13 | Case page and notifications | In progress | **In progress** | Task 4 real webhook, Telegram bot and Resend; Task 5 flow diagrams |
| 14 | Ops lakehouse | Draft | **Approved** (then In progress when #145 and #146 merge) | T1-T7 unchecked; bronze/silver and gold/KPIs are in open PRs #145 and #146; T5 needs spec 05 on Postgres; T6 and T7 are P2 and may stay deferred. Open PR #128 proposes "approve and defer" |
| 15 | Model benchmark | Draft | **In progress** | T2 B1 runner, T3 live smoke run (pending Bedrock), T3b B2 runner, T5 table and JSON, T6 lean rule in `eval/PROTOCOL.md` and the model-selection ADR |
| 16 | Web foundation | In progress | **In progress** | Task 5 wire live mode on the spec 05 API |
| 17 | Fraud model vs bank score | Draft | **In progress** | T3b protocol sync, T4 test-window evaluation and `fraud_benchmark.json`, T5 `model_score` in `get_fraud_score` (P1) |
| 18 | Outcome auditor and judge | Draft | **In progress** | T1 box is unchecked although A1-A7 are merged (#54, #79, #85); T2 harness uses the library, T3 api background task (P1), T5 and T5b console panels, T6 (P2) |

## Housekeeping to do with the status change
- Update the index table in `specs/README.md` and each spec's own `Status:` line together (spec 06 shows the largest gap
  between checkboxes and merged code).
- The size legend in `specs/README.md` ("S < 1 h", "M 1-2 h") contains hours; the working agreement is sizes only
  (S/M/L) without hours, so the lead may want to drop the hour ranges.
- Deliverables without a spec stay as issues: E1 pitch (#19), E2 submission package (#20) (`specs/README.md`).
