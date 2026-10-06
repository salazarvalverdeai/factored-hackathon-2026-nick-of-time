// Generates lib/agent-reference.ts for /agent (spec 04 AC-08, spec 02 T6) from the repo's sources of truth:
// contracts/policies.yaml (policy ids, guardrails, score providers), contracts/tools.py (the 16 customer tools and the
// read that verifies each write), specs/01-integration-contract.md §6.3 (each tool's kind and purpose),
// apps/agent/agent/intake.py (the graph's nodes, edges and what decides each branch, plus the drawn graph's layout)
// and packages/nick_of_time (model ids and NLU versions).
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
  const routers = [];
  for (const m of py.matchAll(/^builder\.add_conditional_edges\("(\w+)",\s*([\s\S]*?),\s*\[([^\]]*)\]\)/gm)) {
    edges.push({ from: m[1], to: quoted(m[3]), conditional: true });
    routers.push({ from: m[1], router: m[2].replace(/\s+/g, " ").trim(), to: quoted(m[3]) });
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
  const sorted = edges.sort((a, b) => order(nodes, a.from) - order(nodes, b.from));
  const branches = routers
    .sort((a, b) => order(nodes, a.from) - order(nodes, b.from))
    .flatMap(({ from, router, to }) => branchesOf(py, from, router, to));
  return { name, nodes, edges: sorted, branches, nluArm: nlu, layout: layoutOf(nodes, sorted, branches) };
}

const order = (nodes, node) => (node === "START" ? -1 : nodes.indexOf(node));

// ---- Branch labels: what decides each conditional edge, read from the router of add_conditional_edges ----------------
// A router is followed through the few Python shapes intake.py uses: a string literal, `A if C else B`, a dict lookup on
// a policy engine decision (`BRANCH[decision.decision]`, `{...}.get(decision.decision) or …`), a state key the source
// node returns (`state["branch"]`), a local variable or a module function (`call_or_respond`). Anything else stops the
// sync, so a label can never drift from the code: change a router and `npm test` fails until this is re-run.

/** What reads each value a branch condition names: the policy engine, a tool read or its verification, or the input. */
export const BRANCH_KINDS = {
  policy: ["screen()", "decide()", "decision", "request_call", "allowed_actions"],
  tool: ["read_failed", "existing_case", "row"],
  input: ["intent", "other_language", "session_state", "injection_flagged", "cross_customer"],
};

/** Walks a Python snippet outside string literals, calling visit(char, index, depth); returns the final depth. */
function scan(text, visit) {
  let depth = 0;
  let quote = null;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quote) {
      if (c === "\\") i++;
      else if (c === quote) quote = null;
      continue;
    }
    if (c === '"' || c === "'") {
      quote = c;
      continue;
    }
    if ("([{".includes(c)) depth++;
    else if (")]}".includes(c)) depth--;
    if (visit(c, i, depth) === false) return depth;
  }
  return depth;
}

/** Indices where `token` starts at bracket depth 0, outside strings. */
function topLevel(text, token) {
  const at = [];
  scan(text, (c, i, depth) => {
    if (depth === 0 && !"([{".includes(c) && text.startsWith(token, i)) at.push(i);
  });
  return at;
}

function stripParens(text) {
  let t = text.trim();
  while (t.startsWith("(") && t.endsWith(")")) {
    let closes = -1;
    scan(t, (c, i, depth) => {
      if (c === ")" && depth === 0) {
        closes = i;
        return false;
      }
    });
    if (closes !== t.length - 1) break;
    t = t.slice(1, -1).trim();
  }
  return t;
}

function stripComment(line) {
  let cut = line.length;
  scan(line, (c, i) => {
    if (c === "#") {
      cut = i;
      return false;
    }
  });
  return line.slice(0, cut);
}

/** The logical statements of a function body (continuation lines joined, docstrings and comments dropped). */
function statements(lines) {
  const out = [];
  let buf = null;
  let indent = 0;
  let inDoc = false;
  for (const raw of lines) {
    const t = raw.trim();
    if (inDoc) {
      if (t.includes('"""')) inDoc = false;
      continue;
    }
    if (buf === null) {
      if (!t || t.startsWith("#")) continue;
      if (t.startsWith('"""')) {
        inDoc = !t.slice(3).includes('"""');
        continue;
      }
      indent = raw.length - raw.trimStart().length;
      buf = "";
    }
    buf += (buf ? " " : "") + stripComment(raw).trim();
    if (scan(buf, () => {}) === 0) {
      out.push({ indent, text: buf.replace(/\s+/g, " ").trim() });
      buf = null;
    }
  }
  return out;
}

/** A module-level function's statements. */
function fnScope(py, name) {
  const def = must(new RegExp(`^(?:async )?def ${name}\\(`, "m").exec(py), `the function ${name} in intake.py`);
  const lines = py.slice(def.index).split("\n");
  let i = 0;
  while (!/\)(?:\s*->\s*[^:]+)?:\s*(?:#.*)?$/.test(lines[i])) i++;
  const body = [];
  for (let j = i + 1; j < lines.length && !(lines[j].trim() && !/^\s/.test(lines[j])); j++) body.push(lines[j]);
  return { name, stmts: statements(body) };
}

/** The one expression a local variable is assigned in a scope, or null. */
function assigned(scope, name) {
  const hits = (scope?.stmts ?? []).filter((s) => s.text.startsWith(`${name} = `));
  return hits.length === 1 ? hits[0].text.slice(name.length + 3) : null;
}

/** `A if C else B` at the top level, or null. */
function ternary(expr) {
  const ifAt = topLevel(expr, " if ")[0];
  if (ifAt === undefined) return null;
  const elseAt = must(topLevel(expr, " else ").find((i) => i > ifAt), `the else of ${expr}`);
  return { a: expr.slice(0, ifAt), c: expr.slice(ifAt + 4, elseAt), b: expr.slice(elseAt + 6) };
}

const note = (refs, name) => (refs.add(name), name);

/** `screen()` when a local variable holds `ENGINE.screen(…)`. */
function engineCall(scope, name) {
  const m = /^ENGINE\.(\w+)\(/.exec(assigned(scope, name) ?? "");
  return m ? `${m[1]}()` : null;
}

/** The name a value reference reads: the last key of a state lookup, an attribute, or a policy engine call. */
function ref(expr, scope, refs) {
  const t = stripParens(expr);
  let m;
  if ((m = /\.get\("(\w+)"\)$/.exec(t)) || (m = /\["(\w+)"\]$/.exec(t))) return note(refs, m[1]);
  if ((m = /^(\w+)\.(\w+)$/.exec(t))) {
    const engine = engineCall(scope, m[1]);
    return note(refs, engine && m[2] === "decision" ? engine : m[2]);
  }
  if (/^\w+$/.test(t) && engineCall(scope, t)) return note(refs, engineCall(scope, t));
  throw new Error(`sync-agent: cannot read the branch value ${expr}; update scripts/sync-agent.mjs`);
}

/** A branch condition in words, recording the values it reads in `refs`. */
function cond(expr, scope, refs) {
  const t = stripParens(expr);
  const tern = ternary(t);
  if (tern) {
    const [a, b] = [cond(tern.a, scope, refs), cond(tern.b, scope, refs)];
    if (a !== b) throw new Error(`sync-agent: the condition ${expr} reads two different values`);
    return a;
  }
  for (const op of [" or ", " and "]) {
    const at = topLevel(t, op);
    if (at.length) {
      const parts = [...at, t.length].map((end, i) => t.slice(i ? at[i - 1] + op.length : 0, end));
      return parts.map((p) => cond(p, scope, refs)).join(op);
    }
  }
  let m;
  if ((m = /^not (.+)$/.exec(t))) return neg(cond(m[1], scope, refs));
  if ((m = /^(.+) is None$/.exec(t))) {
    const name = ref(m[1], scope, refs);
    return name.endsWith("()") ? `${name} = none` : `no ${name}`;
  }
  if ((m = /^(.+) == "(\w+)"$/.exec(t))) return `${ref(m[1], scope, refs)} = ${m[2]}`;
  if ((m = /^"(\w+)" in (.+)$/.exec(t))) return `${m[1]} in ${ref(m[2], scope, refs)}`;
  if (/^\w+$/.test(t) && !engineCall(scope, t) && assigned(scope, t)) return cond(assigned(scope, t), scope, refs);
  return ref(t, scope, refs);
}

function neg(text) {
  let m;
  if ((m = /^no (\S+)$/.exec(text))) return m[1];
  if ((m = /^(\S+) = (\S+)$/.exec(text))) return `${m[1]} ≠ ${m[2]}`;
  if (/^[\w()]+$/.test(text)) return `no ${text}`;
  return `not (${text})`;
}

/** A condition: its text, the short form drawn on the edge (its first clause) and the values it reads. */
function clause(text, refs, short = text.split(/ and | or /)[0]) {
  return { text, short, refs: [...refs] };
}

/** Dict entries `"key": "node"` of a Python dict literal. */
const pairsOf = (body) => [...body.matchAll(/"(\w+)":\s*"(\w+)"/g)].map((m) => [m[1], m[2]]);

/** A lookup of the next node by a decision: one clause per node, with every key that leads to it. */
function lookup(mapping, keyExpr, scope) {
  const refs = new Set();
  const key = ref(keyExpr, scope, refs);
  const byNode = new Map();
  for (const [k, node] of must(mapping, `the entries of ${keyExpr}'s lookup`)) byNode.set(node, [...(byNode.get(node) ?? []), k]);
  return [...byNode].map(([to, keys]) => ({ to, conds: [clause(`${key} = ${keys.join(" | ")}`, refs, keys.join(" | "))] }));
}

/** The nodes an expression can return, each with the conditions (outer first) under which it does. */
function targets(py, expr, scope, from) {
  const t = stripParens(expr.replace(/^lambda \w+:\s*/, ""));
  let m;
  const tern = ternary(t);
  if (tern) {
    const refs = new Set();
    const c = cond(tern.c, scope, refs);
    const [yes, no] = [clause(c, refs), clause(neg(c), refs)];
    return [
      ...targets(py, tern.a, scope, from).map((x) => ({ ...x, conds: [yes, ...x.conds] })),
      ...targets(py, tern.b, scope, from).map((x) => ({ ...x, conds: [no, ...x.conds] })),
    ];
  }
  const or = topLevel(t, " or ");
  if (or.length === 1) return [...targets(py, t.slice(0, or[0]), scope, from), ...targets(py, t.slice(or[0] + 4), scope, from)];
  if ((m = /^"(\w+)"$/.exec(t))) return [{ to: m[1], conds: [] }];
  if ((m = /^\{([^{}]*)\}\.get\((.+)\)$/.exec(t))) return lookup(pairsOf(m[1]), m[2], scope);
  if ((m = /^([A-Z_]+)\[(.+)\]$/.exec(t))) {
    const body = must(new RegExp(`^${m[1]} = \\{([^}]*)\\}`, "m").exec(py)?.[1], `the dict ${m[1]} in intake.py`);
    return lookup(pairsOf(body), m[2], scope);
  }
  if ((m = /^state(?:\["(\w+)"\]|\.get\("(\w+)"\))$/.exec(t))) return stateKey(py, from, m[1] ?? m[2]);
  if ((m = /^(\w+)$/.exec(t)) && assigned(scope, m[1])) return targets(py, assigned(scope, m[1]), scope, from);
  if ((m = /^(\w+)(?:\(.*\))?$/.exec(t))) {
    const fn = fnScope(py, m[1]);
    const returns = fn.stmts.filter((s) => s.text.startsWith("return "));
    if (returns.length !== 1) throw new Error(`sync-agent: ${m[1]} must have one return to label its branches`);
    return targets(py, returns[0].text.slice(7), fn, from);
  }
  throw new Error(`sync-agent: cannot read the router ${expr}; update scripts/sync-agent.mjs`);
}

/** A router that reads a state key: every return of the source node that sets it, under its enclosing ifs. */
function stateKey(py, from, key) {
  const scope = fnScope(py, from);
  const base = scope.stmts[0].indent;
  const out = [];
  scope.stmts.forEach((s, i) => {
    const at = s.text.indexOf(`"${key}": `);
    if (!s.text.startsWith("return {") || at < 0) return;
    const rest = s.text.slice(at + key.length + 4);
    let end = rest.length;
    scan(rest, (c, k, depth) => {
      if ((c === "," && depth === 0) || depth < 0) {
        end = k;
        return false;
      }
    });
    const guards = [];
    for (let j = i - 1, indent = s.indent; j >= 0 && indent > base; j--) {
      const g = scope.stmts[j];
      if (g.indent >= indent) continue;
      indent = g.indent;
      const head = must(/^(?:if|elif) (.+):$/.exec(g.text)?.[1], `the if around "${s.text}"`);
      const refs = new Set();
      guards.unshift(clause(cond(head, scope, refs), refs));
    }
    for (const x of targets(py, rest.slice(0, end), scope, from)) out.push({ ...x, conds: [...guards, ...x.conds] });
  });
  return must(out, `the returns of ${from} that set ${key}`);
}

function kindOf(refs) {
  const known = Object.values(BRANCH_KINDS).flat();
  for (const r of refs) if (!known.includes(r)) throw new Error(`sync-agent: the branch value ${r} has no kind; add it to BRANCH_KINDS`);
  return must(Object.keys(BRANCH_KINDS).find((kind) => refs.some((r) => BRANCH_KINDS[kind].includes(r))), "a branch kind");
}

const unique = (list) => [...new Set(list)];

/** One row per conditional edge: the label drawn on it (the deciding clause of each way in), its kind and the full
 * condition. A router that can return a node its edge list lacks, or a node it never returns, stops the sync. */
export function branchesOf(py, from, router, to) {
  const found = targets(py, router, null, from);
  for (const x of found) if (!to.includes(x.to)) throw new Error(`sync-agent: ${from} can return ${x.to}, not in its edge list`);
  return to.map((node) => {
    const ways = must(found.filter((x) => x.to === node), `what sends ${from} to ${node}`);
    for (const way of ways) must(way.conds, `the condition that sends ${from} to ${node}`);
    const last = ways.map((w) => w.conds.at(-1));
    return {
      from,
      to: node,
      label: unique(last.map((c) => c.short)).join(" | "),
      kind: kindOf(last[0].refs),
      when: unique(ways.map((w) => w.conds.map((c) => c.text).join(", "))).join("; or "),
    };
  });
}

// ---- Layout: a layered drawing computed here, so the page needs no layout library at runtime -------------------------
// Ranks by longest path, then each node moved to the rank that shortens its edges; ranks doubled so each branch label
// sits on its own row right below its source; barycenter sweeps order each row (fewest crossings kept); x by isotonic
// regression toward the neighbors' mean. Text widths assume JetBrains Mono (0.6 em per character), the font drawn.

export const GRAPH_STYLE = { nodeFont: 12, labelFont: 10, nodeH: 30, labelH: 18, gap: 16, dummyGap: 8, rowGap: 8, bendH: 6, bendTolerance: 12, margin: 8 };

const nodeW = (id) => Math.round(id.length * GRAPH_STYLE.nodeFont * 0.6 + 24);
const labelW = (text) => Math.round(text.length * GRAPH_STYLE.labelFont * 0.6 + 12);
const r1 = (n) => Math.round(n * 10) / 10;

export function layoutOf(nodes, edges, branches) {
  const ids = ["START", ...nodes, "END"];
  const pairs = edges.flatMap((e) =>
    e.to.map((to) => {
      const b = branches.find((x) => x.from === e.from && x.to === to);
      if (e.conditional && !b) throw new Error(`sync-agent: no label for ${e.from} → ${to}`);
      return { from: e.from, to, label: b?.label ?? null, kind: b?.kind ?? null };
    }),
  );
  const preds = (v) => pairs.filter((p) => p.to === v).map((p) => p.from);
  const succs = (v) => pairs.filter((p) => p.from === v).map((p) => p.to);

  // ranks: longest path from START, then each node to the rank that shortens its edges
  const rank = {};
  const pending = new Set(ids);
  while (pending.size) {
    const ready = [...pending].find((v) => preds(v).every((p) => !pending.has(p)));
    if (!ready) throw new Error("sync-agent: the graph has a cycle; the layered drawing needs a DAG");
    rank[ready] = Math.max(-1, ...preds(ready).map((p) => rank[p])) + 1;
    pending.delete(ready);
  }
  for (let pass = 0, moved = true; moved && pass < 50; pass++) {
    moved = false;
    for (const v of ids) {
      const [ps, ss] = [preds(v), succs(v)];
      if (!ps.length || !ss.length) continue;
      const lo = Math.max(...ps.map((p) => rank[p])) + 1;
      const hi = Math.min(...ss.map((s) => rank[s])) - 1;
      const want = ps.length > ss.length ? lo : ss.length > ps.length ? hi : Math.min(Math.max(rank[v], lo), hi);
      if (want !== rank[v]) {
        rank[v] = want;
        moved = true;
      }
    }
  }

  // rows: nodes on even rows; the odd row after a source holds its branch labels, other odd rows hold bend points
  const verts = {};
  const rows = [];
  const put = (v) => {
    verts[v.id] = v;
    (rows[v.row] ??= []).push(v.id);
  };
  for (const id of ids) put({ id, type: "node", row: rank[id] * 2, w: nodeW(id), h: GRAPH_STYLE.nodeH });
  const chains = pairs.map((p, e) => {
    const chain = [p.from];
    for (let row = rank[p.from] * 2 + 1; row < rank[p.to] * 2; row++) {
      const label = row === rank[p.from] * 2 + 1 && p.label;
      put({ id: `e${e}:${row}`, type: label ? "label" : "dummy", row, w: label ? labelW(p.label) : 0, h: label ? GRAPH_STYLE.labelH : 0 });
      chain.push(`e${e}:${row}`);
    }
    return [...chain, p.to];
  });
  const up = {};
  const down = {};
  for (const chain of chains) {
    for (let i = 1; i < chain.length; i++) {
      (down[chain[i - 1]] ??= []).push(chain[i]);
      (up[chain[i]] ??= []).push(chain[i - 1]);
    }
  }

  // order: depth-first visit order, then barycenter sweeps, keeping the order with the fewest crossings
  const seen = new Map();
  const visit = (v) => {
    if (seen.has(v)) return;
    seen.set(v, seen.size);
    for (const w of down[v] ?? []) visit(w);
  };
  visit("START");
  for (const row of rows) row.sort((a, b) => seen.get(a) - seen.get(b));
  const index = () => Object.fromEntries(rows.flatMap((row) => row.map((v, i) => [v, i])));
  const crossings = () => {
    const at = index();
    let n = 0;
    for (let r = 0; r + 1 < rows.length; r++) {
      const segs = rows[r].flatMap((v) => (down[v] ?? []).map((w) => [at[v], at[w]]));
      for (let i = 0; i < segs.length; i++)
        for (let j = i + 1; j < segs.length; j++) if ((segs[i][0] - segs[j][0]) * (segs[i][1] - segs[j][1]) < 0) n++;
    }
    return n;
  };
  let best = { n: crossings(), rows: rows.map((r) => [...r]) };
  for (let sweep = 0; sweep < 24; sweep++) {
    const downward = sweep % 2 === 0;
    const order = rows.map((_, r) => r);
    for (const r of downward ? order.slice(1) : order.slice(0, -1).reverse()) {
      const at = index();
      const bary = (v) => {
        const ns = (downward ? up[v] : down[v]) ?? [];
        return ns.length ? ns.reduce((s, w) => s + at[w], 0) / ns.length : at[v];
      };
      rows[r] = rows[r]
        .map((v) => [v, bary(v), at[v]])
        .sort((a, b) => a[1] - b[1] || a[2] - b[2])
        .map(([v]) => v);
    }
    const n = crossings();
    if (n < best.n) best = { n, rows: rows.map((r) => [...r]) };
  }
  rows.splice(0, rows.length, ...best.rows);

  // x: each row as close as its order allows to the mean of its neighbors (weighted isotonic regression, PAV)
  const sep = (a, b) =>
    (verts[a].w + verts[b].w) / 2 + (verts[a].type === "dummy" && verts[b].type === "dummy" ? GRAPH_STYLE.dummyGap : GRAPH_STYLE.gap);
  const x = {};
  for (const row of rows) row.forEach((v, i) => (x[v] = i ? x[row[i - 1]] + sep(row[i - 1], v) : 0));
  const place = (row, want) => {
    const offset = [0];
    for (let i = 1; i < row.length; i++) offset[i] = offset[i - 1] + sep(row[i - 1], row[i]);
    const weight = (v) => (verts[v].type === "node" ? 1 : 6);
    const blocks = [];
    row.forEach((v, i) => {
      blocks.push({ sum: (want[i] - offset[i]) * weight(v), w: weight(v), n: 1 });
      while (blocks.length > 1 && blocks.at(-2).sum / blocks.at(-2).w > blocks.at(-1).sum / blocks.at(-1).w) {
        const last = blocks.pop();
        const prev = blocks.at(-1);
        Object.assign(prev, { sum: prev.sum + last.sum, w: prev.w + last.w, n: prev.n + last.n });
      }
    });
    let i = 0;
    for (const b of blocks) for (let k = 0; k < b.n; k++, i++) x[row[i]] = b.sum / b.w + offset[i];
  };
  const mean = (list) => list.reduce((s, v) => s + x[v], 0) / list.length;
  for (let it = 0; it < 60; it++) {
    const downward = it % 2 === 0;
    const order = rows.map((_, r) => r);
    for (const r of downward ? order : order.reverse()) {
      const row = rows[r];
      const want = row.map((v) => {
        const ns = it >= 50 ? [...(up[v] ?? []), ...(down[v] ?? [])] : ((downward ? up[v] : down[v]) ?? []);
        return ns.length ? mean(ns) : x[v];
      });
      place(row, want);
    }
  }

  // y: row heights (a row of bend points only keeps a thin band for the arrowheads), then shifted to the margin
  const rowH = rows.map((row) => Math.max(GRAPH_STYLE.bendH, ...row.map((v) => verts[v].h)));
  const top = [];
  rows.forEach((_, r) => (top[r] = r ? top[r - 1] + rowH[r - 1] + GRAPH_STYLE.rowGap : 0));
  const all = Object.values(verts);
  const left = Math.min(...all.map((v) => x[v.id] - v.w / 2));
  const cx = (v) => r1(x[v] - left + GRAPH_STYLE.margin);
  const cy = (v) => r1(top[verts[v].row] + rowH[verts[v].row] / 2 + GRAPH_STYLE.margin);
  const width = Math.ceil(Math.max(...all.map((v) => cx(v.id) + v.w / 2)) + GRAPH_STYLE.margin);
  const height = Math.ceil(top.at(-1) + rowH.at(-1) + GRAPH_STYLE.margin * 2);

  // bend points that sit almost on the line between their neighbors are dropped (Douglas-Peucker), so a long edge is
  // one smooth curve instead of a wiggle through every row
  const simplify = (pts, keep) => {
    if (pts.length < 3) return pts;
    const [a, b] = [pts[0], pts.at(-1)];
    let worst = 0;
    let at = -1;
    for (let i = 1; i < pts.length - 1; i++) {
      const t = (pts[i][1] - a[1]) / (b[1] - a[1] || 1);
      const off = Math.abs(pts[i][0] - (a[0] + t * (b[0] - a[0])));
      const must = keep.has(i) ? Infinity : off;
      if (must > worst) [worst, at] = [must, i];
    }
    if (worst < GRAPH_STYLE.bendTolerance) return [a, b];
    const shift = (set, by) => new Set([...set].map((k) => k - by).filter((k) => k >= 0));
    return [...simplify(pts.slice(0, at + 1), keep).slice(0, -1), ...simplify(pts.slice(at), shift(keep, at))];
  };
  const curve = (pts) => {
    let d = `M${pts[0][0]} ${pts[0][1]}`;
    for (let i = 1; i < pts.length; i++) {
      const [[x0, y0], [x1, y1]] = [pts[i - 1], pts[i]];
      const dy = r1((y1 - y0) / 2);
      d += x0 === x1 ? ` L${x1} ${y1}` : ` C${x0} ${r1(y0 + dy)} ${x1} ${r1(y1 - dy)} ${x1} ${y1}`;
    }
    return d;
  };
  return {
    width,
    height,
    nodes: ids
      .map((id) => ({ id, x: cx(id), y: cy(id), w: verts[id].w, h: verts[id].h, rank: rank[id] }))
      .sort((a, b) => a.rank - b.rank || a.x - b.x),
    edges: pairs.map((p, e) => {
      const chain = chains[e];
      const pts = chain.map((v, i) => [cx(v), r1(cy(v) + (i === 0 ? verts[v].h / 2 : i === chain.length - 1 ? -verts[v].h / 2 : 0))]);
      const lv = verts[chain[1]];
      return {
        ...p,
        path: curve(simplify(pts, new Set(lv.type === "label" ? [1] : []))),
        labelBox: lv.type === "label" ? { x: r1(cx(lv.id) - lv.w / 2), y: r1(cy(lv.id) - lv.h / 2), w: lv.w, h: lv.h } : null,
      };
    }),
  };
}


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
