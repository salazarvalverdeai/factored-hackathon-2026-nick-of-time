// The services architecture drawn on /agent (spec 04 AC-08): what runs where and how a request travels. Facts from
// docs/infrastructure.md (EC2, domains, Caddy, deploy, LangGraph Platform, Bedrock), CLAUDE.md "Stack" (ADRs 0004,
// 0008–0011), infra/compose.yml (the services on the EC2) and infra/caddy/Caddyfile (the routes); the static drawing it
// replaces is docs/assets/architecture_option_a.svg. lib/agent-architecture.test.ts checks the services against
// compose.yml and the routes against the Caddyfile, so the drawing fails a test when the deployment changes.
import { AGENT_REFERENCE } from "./agent-reference.ts";
import { pathOf, type Point } from "./agent-motion.ts";

export type Zone = "client" | "ec2" | "managed" | "delivery";
export type FlowKind = "request" | "agent" | "llm" | "data" | "deploy";

export interface ArchService {
  id: string;
  name: string;
  /** A short second line under the name. */
  sub: string;
  /** One line: what it does in the system. */
  role: string;
  zone: Zone;
  /** The infra/compose.yml service it runs as, when it runs on the EC2. */
  compose: string | null;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface ArchFlow {
  from: string;
  to: string;
  /** Short label for the step list. */
  label: string;
  /** One sentence for the walk-through panel. */
  text: string;
  kind: FlowKind;
  points: Point[];
  path: string;
}

const W = 472;
const H = 436;
const COL = [82, 238, 398] as const;
const ROW = [30, 112, 196, 290, 384] as const;
const BW = 136;
const BH = 48;

/** The EC2 boundary drawn around the Compose services. */
export const EC2_BOX = { x: 6, y: 72, w: 312, h: 356, title: "EC2 nickoftime-app", sub: "Docker Compose · us-east-2" };

const box = (col: 0 | 1 | 2, row: 0 | 1 | 2 | 3 | 4) => ({ x: COL[col], y: ROW[row], w: BW, h: BH });

const { tools } = AGENT_REFERENCE;

export const ARCH_SERVICES: ArchService[] = [
  {
    id: "browser",
    name: "Browser",
    sub: "customer · analyst",
    role: "The customer's chat and case page and the analyst's console; HTTPS to one origin, so no CORS.",
    zone: "client",
    compose: null,
    ...box(1, 0),
  },
  {
    id: "github",
    name: "GitHub",
    sub: "Actions · repo",
    role: "A merge to main builds web, api and mcp to GHCR and deploys them through OIDC and SSM, with no SSH; Platform builds the graph from the same repo.",
    zone: "delivery",
    compose: null,
    ...box(2, 0),
  },
  {
    id: "caddy",
    name: "Caddy",
    sub: "TLS + routing",
    role: "Let's Encrypt TLS for both hosts; routes /api/* to api, every other path to web, and the mcp host to mcp.",
    zone: "ec2",
    compose: "caddy",
    ...box(1, 1),
  },
  {
    id: "web",
    name: "web · Next.js",
    sub: "pages",
    role: "The chat, case, console and these pages; it reads and acts only through the api.",
    zone: "ec2",
    compose: "web",
    ...box(0, 2),
  },
  {
    id: "api",
    name: "api · FastAPI",
    sub: "sessions · cases",
    role: "Sessions with OTP, cases and analyst actions, customer notifications; it proxies agent runs with the session injected server-side.",
    zone: "ec2",
    compose: "api",
    ...box(1, 2),
  },
  {
    id: "platform",
    name: "LangGraph",
    sub: "Platform · LangSmith",
    role: "Runs the dispute_intake graph with a managed checkpointer and traces in LangSmith (ADR 0008).",
    zone: "managed",
    compose: null,
    ...box(2, 2),
  },
  {
    id: "mcp",
    name: "mcp · FastMCP",
    sub: `${tools.length} customer tools`,
    role: "The agent's only way to data: customer_id from the session only, idempotent writes, post-conditions read back; API key required.",
    zone: "ec2",
    compose: "mcp",
    ...box(1, 3),
  },
  {
    id: "postgres",
    name: "Postgres",
    sub: "case state · audit",
    role: "Cases and their append-only events, sessions, notifications, policy denials and LLM calls (ADR 0010).",
    zone: "ec2",
    compose: "postgres",
    ...box(0, 4),
  },
  {
    id: "gold",
    name: "gold · DuckDB",
    sub: "Parquet, read-only",
    role: "The bank's customers, cards and transactions as gold Parquet, mounted read-only at /gold/v1 (ADR 0004).",
    zone: "ec2",
    compose: null,
    ...box(1, 4),
  },
  {
    id: "bedrock",
    name: "Amazon Bedrock",
    sub: "Claude · us-east-2",
    role: "Claude Haiku 4.5 (arm S1) and Sonnet 4.6 (arm S2) for understanding only; the rules decide (ADR 0009).",
    zone: "managed",
    compose: null,
    ...box(2, 4),
  },
];

/** The request paths, in the order the walk-through plays them. */
export const ARCH_FLOWS: ArchFlow[] = (
  [
    {
      from: "browser",
      to: "caddy",
      label: "HTTPS",
      text: "The browser opens nickoftime.salazarvalverdeai.com over HTTPS; Caddy terminates TLS.",
      kind: "request",
      points: [[238, 54], [238, 88]],
    },
    {
      from: "caddy",
      to: "web",
      label: "pages",
      text: "Every path outside /api/* is a page, served by web.",
      kind: "request",
      points: [[206, 136], [206, 154], [82, 154], [82, 172]],
    },
    {
      from: "caddy",
      to: "api",
      label: "/api/*",
      text: "Calls under /api/* go to the api on the same origin.",
      kind: "request",
      points: [[254, 136], [254, 172]],
    },
    {
      from: "api",
      to: "platform",
      label: "agent run",
      text: "A chat turn becomes a run of the dispute_intake graph; the api injects the session, never the customer's text.",
      kind: "agent",
      points: [[306, 196], [330, 196]],
    },
    {
      from: "platform",
      to: "bedrock",
      label: "LLM call",
      text: "Below the rules' confidence the understand node asks Claude on Bedrock for intent and slots; it never decides.",
      kind: "llm",
      points: [[414, 220], [414, 360]],
    },
    {
      from: "platform",
      to: "mcp",
      label: "tools · API key",
      text: "The graph reads, acts and verifies only through the MCP tools, at mcp.nickoftime.… behind Caddy with an API key.",
      kind: "agent",
      points: [[366, 220], [366, 290], [306, 290]],
    },
    {
      from: "mcp",
      to: "gold",
      label: "read",
      text: "Tools read the customer's own transactions and cards from gold, read-only.",
      kind: "data",
      points: [[254, 314], [254, 360]],
    },
    {
      from: "mcp",
      to: "postgres",
      label: "write case",
      text: "Writes open the case and block the card in Postgres; each is read back before it is reported as verified.",
      kind: "data",
      points: [[206, 314], [206, 336], [102, 336], [102, 360]],
    },
    {
      from: "api",
      to: "postgres",
      label: "sessions · events",
      text: "The api keeps sessions and the case events the console and the case page read.",
      kind: "data",
      points: [[186, 220], [186, 246], [62, 246], [62, 360]],
    },
    {
      from: "github",
      to: "ec2",
      label: "deploy via SSM",
      text: "A merge to main pushes images to GHCR and runs infra/deploy.sh on the EC2 through OIDC and SSM.",
      kind: "deploy",
      points: [[346, 54], [346, 63], [306, 63], [306, 72]],
    },
    {
      from: "github",
      to: "platform",
      label: "langgraph.json",
      text: "LangGraph Platform builds the graph from the repository's langgraph.json.",
      kind: "deploy",
      points: [[430, 54], [430, 172]],
    },
  ] satisfies Omit<ArchFlow, "path">[]
).map((f) => ({ ...f, path: pathOf(f.points) }));

export const ARCH_VIEW = { width: W, height: H, services: ARCH_SERVICES, flows: ARCH_FLOWS, ec2: EC2_BOX };

/** The flows that start or end at a service. */
export function flowsOf(id: string): { out: ArchFlow[]; in: ArchFlow[] } {
  return { out: ARCH_FLOWS.filter((f) => f.from === id), in: ARCH_FLOWS.filter((f) => f.to === id) };
}

export const nameOf = (id: string) => (id === "ec2" ? EC2_BOX.title : (ARCH_SERVICES.find((s) => s.id === id)?.name ?? id));
