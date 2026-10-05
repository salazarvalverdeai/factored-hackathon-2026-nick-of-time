# Spec 12 — Insight pages: `/evaluation`, `/analytics`, `/data`

- **Feature:** three pages where a judge sees the results, the business numbers and the data quality without reading
  code. `/evaluation` is P0; `/analytics` and `/data` are P1.
- **Status:** Draft
- **Owner:** @vldiego · **Priority:** P0 / P1 · **Size:** M
- **Challenge dimension:** Data Analytics
- **Depends on:** 16 (web foundation), 10, 11, 15, 17 (result files), 14 (operational KPIs, P1) · **Enables:** E1
  (pitch) · **ADRs:** 0007, 0014, 0015
- **Issue:** #14

> Minimal profile plus sections 7 and 8. The pages add no API: they read static JSON files (spec 01 §6.2).

---

## 1. Introduction
Each page answers one question. `/evaluation`: does the system work, and how do we know? `/analytics`: why this
problem, and why this design? `/data`: can the data be trusted? Every figure carries its label and its source, and
every chart shows the detail behind a value on hover and on keyboard focus, with a table view for the same values.

`/analytics` already shows the four problem charts (PR #72, merged before this spec); this spec records its criteria
and closes its follow-ups.

## 3. Acceptance criteria (EARS)
AC-01 to AC-03 come from issue #14 with the same numbers; AC-01 carries the lead's definitions of 2026-10-04 (issue
comment). AC-04 onward are added by this spec. Evidence: [T] test · [C] command · [U] screenshot · [D] file.

- **AC-01 (P0)** — `/evaluation` shall show the harness results with n, S0 against S1 against S2, the benchmark
  cost-quality chart, the classifier table and the fraud-model comparison, labeled `[simulated]`, with a link to
  `eval/PROTOCOL.md`. · [U]
- **AC-02 (P1)** — `/analytics` shall show the pitch numbers with their `[data]` label and source, plus the
  operational KPIs of spec 14. · [U] (pitch numbers done in PR #72; the KPIs wait for spec 14)
- **AC-03 (P1)** — `/data` shall show the medallion, the quality report, the manifest versions and the late-arrival
  fixture result. · [U]
- **AC-04** — While a result file of §7.1 does not exist, its section shall show "Results pending" with what is
  missing, and no figure. · [T] `apps/web/lib/evaluation.test.ts`
- **AC-05** — If the protocol status in `evaluation_summary.json` is not `SEALED`, or its set is not `heldout`, then
  `/evaluation` shall show a visible "development run, not the final result" notice above the figures. · [T]
  `apps/web/lib/evaluation.test.ts`
- **AC-06** — Every rate on `/evaluation` shall be shown with its numerator, its denominator and its interval, in the
  chart tooltip and in the table view. · [U]
- **AC-07** — Every chart shall give the same detail on hover and on keyboard focus, and offer a table view. · [U]
- **AC-08** — `tests/test_spec12_pitch_numbers.py` shall rebuild the pitch data from `queries/pitch/*.csv` and fail if
  it differs from the `data` of the committed `pitch_numbers.json`. · [T]
- **AC-09** — The pages shall render in the dark and the light theme and at 390 px without the page scrolling
  sideways. · [U]

## 7. Data model touched
Reads only static files under `apps/web/public/data/`; creates `data_quality.json` and the page files under
`apps/web/app/{evaluation,analytics,data}/`.

### 7.1 Files each page reads
| Page | File | Produced by | Shape |
|---|---|---|---|
| `/evaluation` | `evaluation_summary.json` | spec 10 | spec 10 §7.2 |
| `/evaluation` | `benchmark.json` | spec 15 | fixed by spec 15 (Q1) |
| `/evaluation` | `classifier.json` | spec 11 | fixed by spec 11 (Q1) |
| `/evaluation` | `fraud_benchmark.json` | spec 17 | fixed by spec 17 (Q1) |
| `/analytics` | `pitch_numbers.json` | `queries/pitch/export_web.py` (PR #72) | that script |
| `/analytics` | `ops_kpis.json` | spec 14 (P1) | fixed by spec 14 |
| `/data` | `data_quality.json` | this spec, `data/pipeline` report | §7.2 |

Every file is `{generated_at, git_sha, source, data}`. The page shows `source`, the date and the commit under each
section.

**No placeholder result files.** `eval/PROTOCOL.md` treats `classifier.json`, `benchmark.json` and
`fraud_benchmark.json` as results: once one exists the protocol can no longer be `UNSEALED` and the test fails. So the
pages are built against sample files kept in `apps/web/app/evaluation/__fixtures__/` (used only by tests), and show
the empty state of AC-04 until the real files arrive.

### 7.2 `data_quality.json`
`data`: `label`, `layers` (bronze, silver, gold: tables, rows, bytes; silver has no size, it is not measured), `gold_rules` (G1–G5 with value and result, from
`data/gold/manifest.json`), `checks` (name, rows affected, action taken, from `data/quality_report.md` §3),
`manifest` (version, pipeline version, contract version, run date) and `late_arrival` (rows added, column added and
checks re-run between `delivery_1` and `delivery_2` of the fixture). Built by a new `--json` output of `python -m data.pipeline report`.

### 7.3 What each page shows
- **`/evaluation`** — (1) a run header: set, cases, runs per case, arms, case-file hash, protocol status; (2) one row
  of headline figures per arm: safe automated resolution, unsafe outcomes, pass^4, p95 latency, cost per case;
  (3) S0 against S1 against S2 on each metric of spec 10 §4.1, with intervals; (4) the breakdown by language × type ×
  segment as a table with n, small cells flagged; (5) the benchmark cost-quality chart; (6) the classifier table per
  arm and language; (7) the fraud model against the bank's score.
- **`/analytics`** — the four charts of PR #72 (share of complaints, complaint contacts against the bank, precision
  and recall by score threshold, labeled frauds by zone) and, when spec 14 delivers, the operational KPIs per day.
- **`/data`** — the three layers with their counts, the gold rules, the checks with counts, the manifest versions and
  the late-arrival result.

## 8. Assumptions and open questions (gate 1 — to close in this PR)
- **Q1 (@salazarvalverdeai) — shapes.** Spec 01 says the producing spec fixes the shape of `data`, and specs 11, 15 and
  17 do not state it yet. Can each add a short JSON example? Until then the page code for those three sections waits.
- **Q2 (@gianzk) — chart component.** The charts of PR #72 are plain SVG and HTML with no new dependency. When #51
  lands, do you want them moved onto `BarChartCard` (Recharts), or kept as they are?
- **Q3 (@salazarvalverdeai) — teal.** The second series uses `#0d9488`; the brand teal `#0F766E` falls below the
  chroma floor of the palette check on the light surface (0.086, it reads gray next to violet). Keep the lighter
  step for charts and say so in `docs/brand/BRAND.md`?
- **Q4 (@salazarvalverdeai) — P2 items.** Auditor findings per 100 runs and judge–analyst agreement (spec 18) are left
  out of this spec. Agreed?
- Assumption: `/evaluation` can be built and merged before the held-out run, showing the empty state (AC-04).
- Assumption: results from a development run may be shown only under the notice of AC-05. `[assumption]`

## 9. Out of scope
Power BI · computing any metric in the browser (the pages only display) · the operational lakehouse (spec 14) · the
landing page and the slides (E1) · P2: auditor findings and judge–analyst agreement.

## 10. Plan, tasks and verification
Implementation goes in `feat/12-…` branches once this spec is approved.
- [x] T1 — `/analytics` with the four problem charts and `pitch_numbers.json` · covers AC-02 (part), AC-07, AC-09 ·
      done in PR #72
- [ ] T2 — drift test for `pitch_numbers.json` (done, `tests/test_spec12_pitch_numbers.py`); note on the teal step
      (waits for Q3: `docs/brand/BRAND.md` is the lead's) · covers AC-08 · follow-ups of PR #72
- [x] T3 — `/evaluation` run header, headline figures, arm comparison and breakdown from `evaluation_summary.json`,
      with the empty state and the development notice · covers AC-01 (part), AC-04, AC-05, AC-06, AC-07
- [ ] T4 — `/evaluation` benchmark, classifier and fraud sections · covers AC-01 · needs Q1
- [x] T5 — `data_quality.json` (`python -m data.pipeline report --json`) and `/data` · covers AC-03 ([T]
      `tests/test_spec12_data_quality.py`; [U] comes with T7)
- [ ] T6 — operational KPIs on `/analytics` · covers AC-02 · needs spec 14
- [ ] T7 — screenshots on the public URL, both themes and 390 px · covers AC-01, AC-03, AC-09

**Closing checklist:** every AC has its evidence · status → Implemented · every figure on the three pages carries its
label · lessons added to `CLAUDE.md`.
