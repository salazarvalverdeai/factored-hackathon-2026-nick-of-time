// Offline checks for the "how it's built" diagrams and the /data cards (spec 12). Run with `npm test`.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { REPO_BLOB } from "./evaluation.ts";
import { GOLD_CONSUMERS, OPS_STEPS, datasetLimits, medallionSteps, type PipelineStep } from "./pipelines.ts";

const read = (f: string) => readFileSync(new URL(`../${f}`, import.meta.url), "utf-8");
const QUALITY = JSON.parse(read("public/data/data_quality.json"));
const ALL: PipelineStep[] = [...medallionSteps(QUALITY.data), ...GOLD_CONSUMERS, ...OPS_STEPS];
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
    assert.ok(step.href.startsWith(REPO_BLOB) && step.tip.length > 0, step.title);
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
