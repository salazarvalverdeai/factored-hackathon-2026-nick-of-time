// Offline checks for /agent's services architecture (spec 04 AC-08): the drawn services are the documented ones
// (docs/infrastructure.md, CLAUDE.md stack, infra/compose.yml), the routes are the Caddyfile's, and the drawing holds
// together (every path starts and ends on its boxes, crosses no other box, stays inside the drawing).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { parse } from "yaml";
import { ARCH_FLOWS, ARCH_SERVICES, ARCH_VIEW, EC2_BOX, flowsOf } from "./agent-architecture.ts";
import { AGENT_REFERENCE } from "./agent-reference.ts";
import { pointAt } from "./agent-motion.ts";

const repo = (path: string) => readFileSync(new URL(`../../../${path}`, import.meta.url), "utf8");
const COMPOSE = parse(repo("infra/compose.yml")) as { services: Record<string, { volumes?: string[] }> };
const CADDY = repo("infra/caddy/Caddyfile");
const INFRA = repo("docs/infrastructure.md");
const CLAUDE = repo("CLAUDE.md");
const has = (from: string, to: string) => ARCH_FLOWS.some((f) => f.from === from && f.to === to);

test("spec 04 AC-08: the drawn services are the documented ones", () => {
  assert.deepEqual(
    ARCH_SERVICES.map((s) => s.id).sort(),
    ["api", "bedrock", "browser", "caddy", "github", "gold", "mcp", "platform", "postgres", "web"],
  );
  for (const [needle, doc] of [
    ["LangGraph Platform", INFRA],
    ["Bedrock", INFRA],
    ["Caddy", INFRA],
    ["GitHub Actions", INFRA],
    ["FastMCP", CLAUDE],
    ["FastAPI", CLAUDE],
    ["Postgres", CLAUDE],
    ["Next.js", CLAUDE],
    ["DuckDB", CLAUDE],
  ] as const) {
    assert.ok(doc.includes(needle), `${needle} is not documented`);
    assert.ok(ARCH_SERVICES.some((s) => `${s.name} ${s.sub} ${s.role}`.includes(needle) || s.name.includes(needle.split(" ")[0])), needle);
  }
  assert.ok(ARCH_SERVICES.find((s) => s.id === "mcp")!.sub.startsWith(`${AGENT_REFERENCE.tools.length} `), "the tool count is read from the contract");
  assert.match(AGENT_REFERENCE.models.s1, /haiku-4-5/);
  assert.match(AGENT_REFERENCE.models.s2, /sonnet-4-6/);
});

test("spec 04 AC-08: the EC2 boxes are exactly the infra/compose.yml services, and gold is its read-only mount", () => {
  const drawn = ARCH_SERVICES.filter((s) => s.compose).map((s) => s.compose!);
  assert.deepEqual(drawn.sort(), Object.keys(COMPOSE.services).sort());
  for (const s of ARCH_SERVICES) assert.equal(s.zone === "ec2", Boolean(s.compose) || s.id === "gold", s.id);
  assert.ok(COMPOSE.services.mcp.volumes?.some((v) => v.endsWith(":/gold/v1:ro")), "mcp mounts gold read-only");
  assert.ok(INFRA.includes(EC2_BOX.title.split(" ")[1]), "the instance name is the documented one");
});

test("spec 04 AC-08: the request paths follow the Caddyfile and the documented deploy", () => {
  assert.match(CADDY, /handle \/api\/\* \{\s*reverse_proxy api:/);
  assert.match(CADDY, /handle \{\s*reverse_proxy web:/);
  assert.match(CADDY, /mcp\.nickoftime\.[^{]+\{\s*reverse_proxy mcp:/);
  for (const [from, to] of [
    ["browser", "caddy"],
    ["caddy", "web"],
    ["caddy", "api"],
    ["api", "platform"],
    ["platform", "bedrock"],
    ["platform", "mcp"],
    ["mcp", "gold"],
    ["mcp", "postgres"],
    ["api", "postgres"],
    ["github", "ec2"],
    ["github", "platform"],
  ]) {
    assert.ok(has(from, to), `${from} → ${to}`);
  }
  assert.equal(ARCH_FLOWS.length, 11);
  assert.ok(!has("web", "postgres") && !has("platform", "postgres") && !has("platform", "gold"), "the agent reaches data only through MCP");
  assert.deepEqual(flowsOf("platform").out.map((f) => f.to), ["bedrock", "mcp"]);
  for (const f of ARCH_FLOWS) assert.ok(f.text.length > 0 && f.label.length > 0, `${f.from} → ${f.to}`);
});

type Rect = { x0: number; y0: number; x1: number; y1: number };
const rectOf = (id: string): Rect => {
  if (id === "ec2") return { x0: EC2_BOX.x, y0: EC2_BOX.y, x1: EC2_BOX.x + EC2_BOX.w, y1: EC2_BOX.y + EC2_BOX.h };
  const s = ARCH_SERVICES.find((x) => x.id === id)!;
  return { x0: s.x - s.w / 2, y0: s.y - s.h / 2, x1: s.x + s.w / 2, y1: s.y + s.h / 2 };
};
const onBorder = ([x, y]: readonly [number, number], r: Rect) =>
  ((x === r.x0 || x === r.x1) && y >= r.y0 && y <= r.y1) || ((y === r.y0 || y === r.y1) && x >= r.x0 && x <= r.x1);

test("spec 04 AC-08: every path starts on its source box, ends on its target box and crosses no other box", () => {
  const { width, height } = ARCH_VIEW;
  for (const f of ARCH_FLOWS) {
    const name = `${f.from} → ${f.to}`;
    assert.ok(onBorder(f.points[0], rectOf(f.from)), `${name} does not start on ${f.from}`);
    assert.ok(onBorder(f.points.at(-1)!, rectOf(f.to)), `${name} does not end on ${f.to}`);
    for (let i = 1; i < f.points.length; i++) assert.ok(f.points[i][0] === f.points[i - 1][0] || f.points[i][1] === f.points[i - 1][1], `${name} is not orthogonal`);
    for (const s of ARCH_SERVICES) {
      if (s.id === f.from || s.id === f.to) continue;
      const r = rectOf(s.id);
      for (let t = 0; t <= 1; t += 0.01) {
        const p = pointAt(f.points, t);
        assert.ok(!(p.x > r.x0 && p.x < r.x1 && p.y > r.y0 && p.y < r.y1), `${name} crosses ${s.id}`);
      }
    }
    for (const [x, y] of f.points) assert.ok(x >= 0 && x <= width && y >= 0 && y <= height, name);
  }
  for (const s of ARCH_SERVICES) {
    const r = rectOf(s.id);
    assert.ok(r.x0 >= 0 && r.x1 <= width && r.y0 >= 0 && r.y1 <= height, s.id);
    const e = rectOf("ec2");
    const inside = r.x0 >= e.x0 && r.x1 <= e.x1 && r.y0 >= e.y0 && r.y1 <= e.y1;
    assert.equal(inside, s.zone === "ec2", `${s.id} is ${inside ? "inside" : "outside"} the EC2 box`);
  }
});
