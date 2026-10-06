// "How the console works" (spec 08 AC-24): the analyst's flow drawn like /agent's architecture view
// (lib/agent-architecture.ts), from the inbox to the close, with what it runs on. Facts from this spec (AC-02 to AC-05,
// AC-10 to AC-22), spec 18 (auditor and judge), ADR 0010 (Postgres events, append-only), ADR 0017 (Cognito for
// analysts) and CLAUDE.md "Constraints" #4 and #6. Pure, so `npm test` covers it.
import { pathOf, type Point } from "./agent-motion.ts";

export type FlowGroup = "step" | "evidence" | "need";

export interface FlowBox {
  id: string;
  name: string;
  /** Short second line, hidden on a phone. */
  sub: string;
  group: FlowGroup;
  /** What the detail panel says: one or two plain sentences. */
  detail: string;
  /** Where it comes from in the repo or the specs. */
  source: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface FlowLink {
  from: string;
  to: string;
  label: string;
  /** "step" is the analyst's own path; "needs" is what a step runs on. */
  kind: "step" | "needs";
  points: Point[];
  path: string;
}

const W = 480;
const H = 350;
const STEP_X = 120;
const STEP_W = 200;
const BH = 44;
const ROWS = [40, 110, 180, 250, 320] as const;
const NEED_X = 360;
const NEED_W = 150;
const NEED_H = 40;

const step = (row: number) => ({ x: STEP_X, y: ROWS[row], w: STEP_W, h: BH });
const need = (row: number) => ({ x: NEED_X, y: ROWS[row], w: NEED_W, h: NEED_H });
const pill = (col: 0 | 1, row: 0 | 1) => ({ x: [300, 400][col], y: [93, 117][row], w: 90, h: 22 });

export const FLOW_LINE = "A case goes from the queue to a person's close; every action is checked against the record before it counts.";

export const FLOW_BOXES: FlowBox[] = [
  {
    id: "queue",
    name: "Queue",
    sub: "open cases · SLA light",
    group: "step",
    detail: "Open cases by status with zone, deadline and priority; each carries an SLA light from the days left to its nearest legal deadline.",
    source: "spec 08 AC-02, AC-07 to AC-09",
    ...step(0),
  },
  {
    id: "case",
    name: "Case card",
    sub: "evidence, not a chat",
    group: "step",
    detail: "The agent's summary, the handoff card, the customer's history, the auditor's checks and the case timeline, all read from tools and the store.",
    source: "spec 08 AC-03, AC-10 to AC-15",
    ...step(1),
  },
  {
    id: "action",
    name: "Analyst action",
    sub: "approve · ask · close",
    group: "step",
    detail: "The analyst decides: approve the credit or the block, ask the customer, or close. Supervised mode asks for a second confirmation; provisional credit is always a person's decision.",
    source: "spec 08 AC-04, AC-05, AC-13 · constitution #6",
    ...step(2),
  },
  {
    id: "verification",
    name: "Verification",
    sub: "read back, then shown",
    group: "step",
    detail: "The console shows an action as done only after it reads the case again: a case's status is its last event.",
    source: "constitution #4 · ADR 0010",
    ...step(3),
  },
  {
    id: "close",
    name: "Close",
    sub: "a person closes",
    group: "step",
    detail: "Resolved, then closed, always by a person; the case moves to the Closed tab with whether its legal deadline was met.",
    source: "spec 08 AC-09 · constitution #6",
    ...step(4),
  },
  {
    id: "receipt",
    name: "Receipt",
    sub: "",
    group: "evidence",
    detail: "The verified receipt the customer got: only facts returned by tools.",
    source: "constitution #5 · spec 04",
    ...pill(0, 0),
  },
  {
    id: "deadline",
    name: "Deadline",
    sub: "",
    group: "evidence",
    detail: "The nearest legal deadline with its countdown and its source; with no rule for the country, no date and a person decides.",
    source: "spec 08 AC-10 · ADR 0019",
    ...pill(1, 0),
  },
  {
    id: "handoff",
    name: "Handoff",
    sub: "",
    group: "evidence",
    detail: "The agent's handoff card: request, verified facts, actions with their verification, evidence and open questions.",
    source: "spec 08 AC-03 · handoff.schema.json",
    ...pill(0, 1),
  },
  {
    id: "opinion",
    name: "2nd opinion",
    sub: "",
    group: "evidence",
    detail: "Only when asked: an AI judge's advisory opinion with each reason tied to its evidence, after the deterministic auditor's A1–A7 checks.",
    source: "spec 08 AC-12, AC-18 · spec 18",
    ...pill(1, 1),
  },
  {
    id: "cognito",
    name: "Cognito",
    sub: "analyst sign-in",
    group: "need",
    detail: "The analyst signs in with Cognito; every console route asks for that token and records the user with each action.",
    source: "ADR 0017 · spec 08 AC-01, AC-21",
    ...need(2),
  },
  {
    id: "api",
    name: "api · FastAPI",
    sub: "analyst routes",
    group: "need",
    detail: "The console reads and acts only through the api's analyst routes; nothing in the browser decides.",
    source: "spec 01 §6.2 · spec 08 §6",
    ...need(3),
  },
  {
    id: "postgres",
    name: "Postgres events",
    sub: "append-only",
    group: "need",
    detail: "Every case change is an appended event with its actor; the status is the last one, and the audit trail is the same record.",
    source: "ADR 0010",
    ...need(4),
  },
];

/** The analyst's path, then what it runs on, in the order the walk-through plays them. */
export const FLOW_LINKS: FlowLink[] = (
  [
    { from: "queue", to: "case", label: "open a case", kind: "step", points: [[120, 62], [120, 88]] },
    { from: "case", to: "action", label: "decide", kind: "step", points: [[120, 132], [120, 158]] },
    { from: "action", to: "cognito", label: "signed in", kind: "needs", points: [[220, 180], [285, 180]] },
    { from: "cognito", to: "api", label: "token checked", kind: "needs", points: [[360, 200], [360, 230]] },
    { from: "api", to: "postgres", label: "append event", kind: "needs", points: [[360, 270], [360, 300]] },
    { from: "postgres", to: "verification", label: "read back", kind: "needs", points: [[285, 320], [250, 320], [250, 250], [220, 250]] },
    { from: "action", to: "verification", label: "check", kind: "step", points: [[120, 202], [120, 228]] },
    { from: "verification", to: "close", label: "close", kind: "step", points: [[120, 272], [120, 298]] },
  ] satisfies Omit<FlowLink, "path">[]
).map((l) => ({ ...l, path: pathOf(l.points) }));

/** The dashed frame that groups the case card's evidence, and its bracket from the card. */
export const EVIDENCE_FRAME = { x: 252, y: 79, w: 196, h: 52 };
export const EVIDENCE_BRACKET: Point[] = [[220, 110], [252, 110]];
/** The dashed frame around what the flow runs on. */
export const NEEDS_FRAME = { x: 272, y: 138, w: 176, h: 208, title: "What it runs on" };

export const FLOW_VIEW = { width: W, height: H, boxes: FLOW_BOXES, links: FLOW_LINKS };

export const boxOf = (id: string) => FLOW_BOXES.find((b) => b.id === id);
