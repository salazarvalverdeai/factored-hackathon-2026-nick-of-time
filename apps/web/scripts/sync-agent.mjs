// Generates lib/agent-reference.ts for /agent (spec 04 AC-08, spec 02 T6) from the repo's sources of truth:
// contracts/policies.yaml (policy ids, guardrails, score providers), contracts/tools.py (the 16 customer tools and the
// read that verifies each write), specs/01-integration-contract.md §6.3 (each tool's kind and purpose),
// apps/agent/agent/intake.py (the graph's nodes and edges) and packages/nick_of_time (model ids and NLU versions).
// The web image builds from apps/web alone, so the result is committed. Run: npm run sync:agent.
// `npm test` fails when the generated file drifts from those sources.
import { readFileSync, writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { parse } from "yaml";

const ROOT = new URL("../../../", import.meta.url);
const OUT = new URL("../lib/agent-reference.ts", import.meta.url);

export const SOURCES = {
  policies: "contracts/policies.yaml",
  tools: "contracts/tools.py",
  toolPurposes: "specs/01-integration-contract.md",
  graph: "apps/agent/agent/intake.py",
  config: "packages/nick_of_time/config/__init__.py",
  rules: "packages/nick_of_time/nlu/rules.py",
  learned: "packages/nick_of_time/nlu/learned.py",
};

const read = (key) => readFileSync(new URL(SOURCES[key], ROOT), "utf8");

function must(value, what) {
  if (value === undefined || value === null || (Array.isArray(value) && value.length === 0)) {
    throw new Error(`sync-agent: could not read ${what}; update scripts/sync-agent.mjs to the new source`);
  }
  return value;
}

/** Quoted names inside a Python tuple or list body. */
const quoted = (body) => [...body.matchAll(/"(\w+)"/g)].map((m) => m[1]);

export function policiesOf(text) {
  const yaml = parse(text);
  const rules = Object.entries(must(yaml.rules, "policies.yaml rules")).map(([id, rule]) => ({
    id,
    text: rule.text,
    guardrail: rule.guardrail ?? null,
  }));
  const guardrails = must(yaml.guardrails, "policies.yaml guardrails").map((g) => ({
    id: g.id,
    layer: g.layer,
    name: g.name,
    impl: g.impl,
  }));
  const deciding = must(yaml.scoring?.deciding_sources, "policies.yaml scoring.deciding_sources");
  const providers = Object.entries(must(yaml.scoring?.providers, "policies.yaml scoring.providers")).map(([name, p]) => ({
    name,
    version: p.version,
    note: p.note,
    decidesZone: deciding.includes(name),
  }));
  const zones = Object.entries(must(yaml.zones, "policies.yaml zones")).map(([name, z]) => ({
    name,
    scoreMin: z.score_min,
    scoreMax: z.score_max,
    includesNull: z.include_null === true,
  }));
  return {
    version: must(yaml.version, "policies.yaml version"),
    default: must(yaml.default, "policies.yaml default"),
    rules,
    guardrails,
    scoring: { provider: yaml.scoring.provider, providers },
    zones,
    customerTools: must(yaml.actors?.customer?.tools, "policies.yaml actors.customer.tools"),
  };
}

export function toolsOf(toolsPy, spec01) {
  const names = quoted(must(/CUSTOMER_TOOLS[^=]*=\s*\{tool: _models\(tool\) for tool in \(([\s\S]*?)\)\}/.exec(toolsPy)?.[1], "CUSTOMER_TOOLS"));
  const verifiedBody = must(/VERIFIED_WITH[^=]*=\s*\{([\s\S]*?)\}/.exec(toolsPy)?.[1], "VERIFIED_WITH");
  const verifiedWith = Object.fromEntries([...verifiedBody.matchAll(/"(\w+)":\s*"(\w+)"/g)].map((m) => [m[1], m[2]]));
  const rows = Object.fromEntries(
    [...spec01.matchAll(/^\| `(\w+)` \| ([RWN]) \| (.+?) \| .+? \| .+? \|$/gm)].map((m) => [m[1], { kind: m[2], purpose: m[3] }]),
  );
  return names.map((name) => {
    const row = must(rows[name], `the spec 01 §6.3 row of ${name}`);
    return { name, kind: row.kind, purpose: oneLine(row.purpose), verifiedWith: verifiedWith[name] ?? null };
  });
}

/** One line from a spec 01 purpose cell: version and decision tags in parentheses dropped, cut at the first ";"
 * that is not inside parentheses. */
export function oneLine(purpose) {
  const text = purpose.replace(/\s*\((?:\d+\.\d+\.\d+|D-\d+|task \w+|replaces [^)]*)\)/g, "");
  let depth = 0;
  for (let i = 0; i < text.length; i++) {
    if (text[i] === "(") depth++;
    else if (text[i] === ")") depth--;
    else if (text[i] === ";" && depth === 0) return text.slice(0, i).trim();
  }
  return text.trim();
}

export function graphOf(py) {
  const nodes = quoted(
    must(/for _node in \(([\s\S]*?)\):\s*\n\s*builder\.add_node/.exec(py)?.[1], "the add_node loop").replace(/(\w+)/g, '"$1"'),
  );
  const edges = [];
  for (const m of py.matchAll(/^builder\.add_edge\((START|"\w+"), (END|"\w+")\)/gm)) {
    edges.push({ from: m[1].replaceAll('"', ""), to: [m[2].replaceAll('"', "")], conditional: false });
  }
  for (const m of py.matchAll(/^builder\.add_conditional_edges\("(\w+)",[\s\S]*?\[([^\]]*)\]\)/gm)) {
    edges.push({ from: m[1], to: quoted(m[2]), conditional: true });
  }
  for (const m of py.matchAll(/^for _node in \(([^)]*)\):\s*\n\s*builder\.add_edge\(_node, "(\w+)"\)/gm)) {
    for (const from of quoted(m[1])) edges.push({ from, to: [m[2]], conditional: false });
  }
  const name = must(/^graph = builder\.compile\(name="(\w+)"\)/m.exec(py)?.[1], "the compiled graph's name");
  const known = new Set([...nodes, "START", "END"]);
  for (const e of edges) {
    for (const end of [e.from, ...e.to]) if (!known.has(end)) throw new Error(`sync-agent: edge to unknown node ${end}`);
  }
  for (const node of nodes) must(edges.find((e) => e.from === node), `the edges out of node ${node}`);
  const nlu = must(/^ENGINE, NLU = PolicyEngine\.load\(\), load_nlu\("(\w+)"\)/m.exec(py)?.[1], "the graph's NLU arm");
  return { name, nodes, edges: edges.sort((a, b) => order(nodes, a.from) - order(nodes, b.from)), nluArm: nlu };
}

const order = (nodes, node) => (node === "START" ? -1 : nodes.indexOf(node));

export function modelsOf(config, rules, learned) {
  const constant = (text, name, what) => must(new RegExp(`^${name}\\s*=\\s*"([^"]+)"`, "m").exec(text)?.[1], what);
  return {
    s1: constant(config, "HAIKU", "config HAIKU"),
    s2: constant(config, "SONNET", "config SONNET"),
    b0: must(/^ARM, VERSION = "B0", "([^"]+)"/m.exec(rules)?.[1], "nlu rules VERSION"),
    b1: constant(learned, "B1_VERSION", "nlu learned B1_VERSION"),
  };
}

export function extract() {
  return {
    sources: SOURCES,
    policies: policiesOf(read("policies")),
    tools: toolsOf(read("tools"), read("toolPurposes")),
    graph: graphOf(read("graph")),
    models: modelsOf(read("config"), read("rules"), read("learned")),
  };
}

export function render(data) {
  return `// Reference data for /agent (spec 04 AC-08, spec 02 T6), read from the repo's sources of truth (see SOURCES).
// GENERATED by scripts/sync-agent.mjs (npm run sync:agent): do not edit by hand. \`npm test\` fails if it drifts.

export const AGENT_REFERENCE = ${JSON.stringify(data, null, 2)} as const;
`;
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  const text = render(extract());
  if (process.argv.includes("--check")) {
    if (readFileSync(OUT, "utf8") !== text) {
      console.error("lib/agent-reference.ts is out of date with its sources: run `npm run sync:agent`");
      process.exit(1);
    }
  } else {
    writeFileSync(OUT, text);
  }
}
