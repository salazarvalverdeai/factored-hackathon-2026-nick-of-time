// Offline checks for the "how it's built" diagrams and the /data cards (spec 12). Run with `npm test`.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { REPO_BLOB } from "./evaluation.ts";
import { ANALYTICS_STEPS, DATA_CARDS, EVALUATION_OTHER_FILES, EVALUATION_STEPS, GOLD_CONSUMERS, OPS_STEPS, datasetLimits, medallionSteps, type Detail, type PipelineStep } from "./pipelines.ts";

const read = (f: string) => readFileSync(new URL(`../${f}`, import.meta.url), "utf-8");
const QUALITY = JSON.parse(read("public/data/data_quality.json"));
const ALL: PipelineStep[] = [...medallionSteps(QUALITY.data), ...GOLD_CONSUMERS, ...OPS_STEPS, ...EVALUATION_STEPS, ...ANALYTICS_STEPS];
const LABEL = /\[(data|external|assumption|simulated|projected)\]/;

test("spec 12 AC-03: the medallion shows source, bronze, silver and gold with the real tables and rows of data_quality.json", () => {
  const steps = medallionSteps(QUALITY.data);
  assert.deepEqual(steps.map((s) => s.title), ["Source CSV files", "Bronze", "Silver", `Gold v${QUALITY.data.manifest.gold_version}`]);
  QUALITY.data.layers.forEach((layer: { tables: { table: string; rows: number }[] }, i: number) => {
    const rows = layer.tables.reduce((a, t) => a + t.rows, 0);
    assert.ok(steps[i + 1].lines[0].includes(`${layer.tables.length} tables · ${rows.toLocaleString("en-US")} rows [data]`));
    for (const t of layer.tables) assert.ok(steps[i + 1].tip.some(([k, v]) => k === t.table && v === `${t.rows.toLocaleString("en-US")} rows`));
  });
  assert.ok(steps[0].lines[0].startsWith(QUALITY.data.manifest.source_files.toLocaleString("en-US")));
  assert.deepEqual(GOLD_CONSUMERS.map((s) => s.title), ["MCP tools at runtime", "Evaluation cases", "Analytics queries", "Operational lakehouse"]);
});

test("spec 12 AC-03: the dataset limits are plain sentences built from the committed query output, a label beside each figure", () => {
  const link = QUALITY.data.complaint_link;
  assert.equal(link.query, "queries/data/d01_complaint_transaction_link.sql");
  const limits = datasetLimits(link.rows);
  assert.equal(limits.length, 4);
  const people = link.rows.find((r: { metric: string }) => r.metric === "w3_complainants_with_card_txn_30d");
  assert.ok(limits[0].includes(`(${people.numerator.toLocaleString("en-US")} of ${people.denominator.toLocaleString("en-US")}) [data]`));
  for (const s of limits) {
    if (LABEL.test(s)) assert.match(s, /\d[^[]*\[data\]/); // a label always follows a figure
    else assert.doesNotMatch(s, /\d/);
  }
  assert.deepEqual(datasetLimits([]), []);
});

test("spec 12 AC-11: every step has one or two plain lines, a Detail link to the repo and a label only beside a figure", () => {
  for (const step of ALL) {
    assert.ok(step.lines.length >= 1 && step.lines.length <= 2, step.title);
    assert.ok(step.tip.length > 0, step.title);
    for (const line of step.lines) if (LABEL.test(line)) assert.match(line, /\d.*\[/, `${step.title}: ${line}`);
  }
});

test("spec 12 AC-07, AC-09: each diagram step takes keyboard focus with the same tooltip as hover, and stacks below lg", () => {
  const diagram = read("components/pipeline-diagram.tsx");
  assert.match(diagram, /tabIndex=\{0\}[^]*?\{\.\.\.bind\(<TipBody/); // hover and focus share bind()
  assert.match(diagram, /className="grid gap-5 lg:grid-cols-/); // one column at 390 px, a row from lg
  assert.doesNotMatch(diagram, /\b(min-)?w-\[\d{3,}px\]|#[0-9a-f]{6}/i); // no fixed width, colors from the theme tokens
  const page = read("app/data/page.tsx");
  assert.match(page, /<PipelineDiagram label="Medallion pipeline"[^]*?<TableView/); // the counts also as a table
  assert.match(page, /href="\/agent"/); // the system architecture is not redrawn here
  assert.match(page, /title="Operational lakehouse"[^]*?"Pending"/);
  assert.doesNotMatch(page.slice(page.indexOf('<p className="mb-4'), page.indexOf('<div className="space-y-4">')), LABEL); // AC-11: no tag in prose
});

/** What a side panel must hold: 1–3 plain sentences of method, a source, the figures' label and a spec link. */
function assertDetail(name: string, d: Detail) {
  const sentences = d.method.split(/(?<=\.)\s+/).filter(Boolean);
  assert.ok(sentences.length >= 1 && sentences.length <= 3, `${name}: ${sentences.length} sentences`);
  assert.doesNotMatch(d.method, LABEL, name); // the label sits in its own field, not in the prose
  assert.ok(d.source.length > 0 && ["[data]", "[simulated]", "[projected]"].includes(d.label), name);
  assert.match(d.spec, new RegExp(`^${REPO_BLOB.replace(/[.]/g, "\\.")}.+\\.md(#[\\w-]+)?$`), name);
}

test("spec 12 AC-03, AC-11: every Detail of /data and of the diagrams opens a panel with method, source, label and spec", () => {
  for (const step of ALL) assertDetail(step.title, step.detail);
  for (const [name, d] of Object.entries(DATA_CARDS)) assertDetail(name, d);
  assert.equal(DATA_CARDS.limits.source, QUALITY.data.complaint_link.query);
  for (const d of [...OPS_STEPS.map((s) => s.detail), DATA_CARDS.ops]) assert.equal(d.label, "[simulated]"); // spec 14 figures
  const button = read("components/detail-button.tsx");
  assert.match(button, /onClick=\{\(\) => setOpen\(true\)\}/); // Detail → opens the panel
  assert.match(button, /<DetailPanel\s+open=\{open\}\s+onClose=\{\(\) => setOpen\(false\)\}/); // Escape and close call onClose
  assert.match(button, /Read the spec →/);
  assert.match(read("components/detail-panel.tsx"), /e\.key === "Escape"[^]*?close\.current\(\)/);
  assert.match(read("components/pipeline-diagram.tsx"), /<DetailButton title=\{step\.title\} detail=\{step\.detail\}/);
  const page = read("app/data/page.tsx");
  assert.equal((page.match(/detail=\{DATA_CARDS\.\w+\}/g) ?? []).length, Object.keys(DATA_CARDS).length);
});

test("spec 12 AC-11: /evaluation and /analytics say how their figures are built with the same diagram, each step's panel linked to its spec", () => {
  assert.deepEqual(EVALUATION_STEPS.map((s) => s.title), [
    "Case files", "Seed", "Graph turns", "FinalState", "Compare with expected", "Metrics", "evaluation_summary.json", "This page",
  ]);
  assert.match(EVALUATION_STEPS[0].detail.spec, /09-demo-eval-data\.md#77-seal$/);
  assert.match(EVALUATION_STEPS[4].lines[0], /A5 and A6/);
  assert.match(EVALUATION_STEPS[5].lines[0], /Wilson/);
  for (const file of ["classifier.json", "benchmark.json", "fraud_benchmark.json"]) assert.ok(EVALUATION_OTHER_FILES.includes(file));
  assert.deepEqual(ANALYTICS_STEPS.map((s) => s.title), ["Full dataset", "queries/pitch/*.sql", "pitch_numbers.json", "Charts"]);
  const evaluation = read("app/evaluation/page.tsx"), analytics = read("app/analytics/page.tsx");
  assert.match(evaluation, /<PipelineDiagram label="How the agent evaluation is built" steps=\{EVALUATION_STEPS\}/);
  assert.match(evaluation, /href="\/agent"/); // the architecture lives on /agent, not here
  const end = analytics.slice(analytics.indexOf("{pitch.git_sha}")); // the new block sits after the page's last line
  assert.match(end, /<PipelineDiagram label="How the problem numbers are built" steps=\{ANALYTICS_STEPS\}/);
});
