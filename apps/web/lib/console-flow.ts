// "How the console works" (spec 08 AC-24): the analyst's flow in /agent's diagram language, from the inbox to the
// close, with what it runs on. Laid out on a CSS grid (column 1 the steps, 2 the edges across, 3 what it runs on) so it
// reflows at 390 px; the edges are the motion kit's FlowConnector (components/motion). Facts from this spec (AC-02 to
// AC-05, AC-10 to AC-22), spec 18 (auditor and judge), ADR 0010 (Postgres events, append-only), ADR 0017 (Cognito for
// analysts) and CLAUDE.md "Constraints" #4 and #6. Pure, so `npm test` covers it.

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
  /** Grid cell; evidence has none, it sits inside the case card's cell. */
  col: 1 | 3 | null;
  row: number | null;
}

export interface FlowLink {
  from: string;
  to: string;
  label: string;
  /** "step" is the analyst's own path; "needs" is what a step runs on. */
  kind: "step" | "needs";
  /** Which way the arrow points on the grid. */
  direction: "down" | "right" | "left";
  col: 1 | 2 | 3;
  row: number;
  /** Rows the edge spans (the long step edge passes the rows of what it runs on). */
  rows: number;
}

const step = (row: number) => ({ col: 1 as const, row });
const need = (row: number) => ({ col: 3 as const, row });
const pill = { col: null, row: null };

export const FLOW_LINE = "A case goes from the queue to a person's close; every action is checked against the record before it counts.";

export const FLOW_BOXES: FlowBox[] = [
  {
    id: "queue",
    name: "Queue",
    sub: "open cases · SLA light",
    group: "step",
    detail: "Open cases by status with zone, deadline and priority; each carries an SLA light from the days left to its nearest legal deadline.",
    source: "spec 08 AC-02, AC-07 to AC-09",
    ...step(1),
  },
  {
    id: "case",
    name: "Case card",
    sub: "evidence, not a chat",
    group: "step",
    detail: "The agent's summary, the handoff card, the customer's history, the auditor's checks and the case timeline, all read from tools and the store.",
    source: "spec 08 AC-03, AC-10 to AC-15",
    ...step(3),
  },
  {
    id: "action",
    name: "Analyst action",
    sub: "approve · ask · close",
    group: "step",
    detail: "The analyst decides: approve the credit or the block, ask the customer, or close. Supervised mode asks for a second confirmation; provisional credit is always a person's decision.",
    source: "spec 08 AC-04, AC-05, AC-13 · constitution #6",
    ...step(5),
  },
  {
    id: "verification",
    name: "Verification",
    sub: "read back, then shown",
    group: "step",
    detail: "The console shows an action as done only after it reads the case again: a case's status is its last event.",
    source: "constitution #4 · ADR 0010",
    ...step(9),
  },
  {
    id: "close",
    name: "Close",
    sub: "a person closes",
    group: "step",
    detail: "Resolved, then closed, always by a person; the case moves to the Closed tab with whether its legal deadline was met.",
    source: "spec 08 AC-09 · constitution #6",
    ...step(11),
  },
  {
    id: "receipt",
    name: "Receipt",
    sub: "",
    group: "evidence",
    detail: "The verified receipt the customer got: only facts returned by tools.",
    source: "constitution #5 · spec 04",
    ...pill,
  },
  {
    id: "deadline",
    name: "Deadline",
    sub: "",
    group: "evidence",
    detail: "The nearest legal deadline with its countdown and its source; with no rule for the country, no date and a person decides.",
    source: "spec 08 AC-10 · ADR 0019",
    ...pill,
  },
  {
    id: "handoff",
    name: "Handoff",
    sub: "",
    group: "evidence",
    detail: "The agent's handoff card: request, verified facts, actions with their verification, evidence and open questions.",
    source: "spec 08 AC-03 · handoff.schema.json",
    ...pill,
  },
  {
    id: "opinion",
    name: "2nd opinion",
    sub: "",
    group: "evidence",
    detail: "Only when asked: an AI judge's advisory opinion with each reason tied to its evidence, after the deterministic auditor's A1–A7 checks.",
    source: "spec 08 AC-12, AC-18 · spec 18",
    ...pill,
  },
  {
    id: "cognito",
    name: "Cognito",
    sub: "analyst sign-in",
    group: "need",
    detail: "The analyst signs in with Cognito; every console route asks for that token and records the user with each action.",
    source: "ADR 0017 · spec 08 AC-01, AC-21",
    ...need(5),
  },
  {
    id: "api",
    name: "api",
    sub: "analyst routes",
    group: "need",
    detail: "The console reads and acts only through the api's analyst routes (FastAPI); nothing in the browser decides.",
    source: "spec 01 §6.2 · spec 08 §6",
    ...need(7),
  },
  {
    id: "postgres",
    name: "Postgres events",
    sub: "append-only",
    group: "need",
    detail: "Every case change is an appended event with its actor; the status is the last one, and the audit trail is the same record.",
    source: "ADR 0010",
    ...need(9),
  },
];

/** The analyst's path, then what it runs on, in the order the edges play (once, on entering the viewport). */
export const FLOW_LINKS: FlowLink[] = [
  { from: "queue", to: "case", label: "open a case", kind: "step", direction: "down", col: 1, row: 2, rows: 1 },
  { from: "case", to: "action", label: "decide", kind: "step", direction: "down", col: 1, row: 4, rows: 1 },
  { from: "action", to: "cognito", label: "signed in", kind: "needs", direction: "right", col: 2, row: 5, rows: 1 },
  { from: "cognito", to: "api", label: "token checked", kind: "needs", direction: "down", col: 3, row: 6, rows: 1 },
  { from: "api", to: "postgres", label: "append event", kind: "needs", direction: "down", col: 3, row: 8, rows: 1 },
  { from: "postgres", to: "verification", label: "read back", kind: "needs", direction: "left", col: 2, row: 9, rows: 1 },
  { from: "action", to: "verification", label: "check", kind: "step", direction: "down", col: 1, row: 6, rows: 3 },
  { from: "verification", to: "close", label: "close", kind: "step", direction: "down", col: 1, row: 10, rows: 1 },
];

/** The heading over what the flow runs on, in the column's free row above it. */
export const NEEDS_TITLE = { text: "What it runs on", col: 3 as const, row: 4 };

export const boxOf = (id: string) => FLOW_BOXES.find((b) => b.id === id);
