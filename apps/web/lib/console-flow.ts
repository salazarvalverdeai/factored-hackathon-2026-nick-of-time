// "How the console works" (spec 08 AC-24): the analyst's flow in /agent's diagram language, from the inbox to the
// close, with what it runs on. Laid out on a CSS grid (column 1 the steps, 2 the edges across, 3 what it runs on) so it
// reflows at 390 px; the edges are the motion kit's FlowConnector (components/motion). The words are in
// messages/console.ts (`console.flow.box.<id>`, `console.flow.link.<label>`) in EN, ES and PT; the facts come from this
// spec (AC-02 to AC-05, AC-10 to AC-22), spec 18, ADR 0010, ADR 0017 and CLAUDE.md "Constraints" #4 to #6.

export type FlowGroup = "step" | "evidence" | "need";

export const FLOW_IDS = [
  "queue",
  "case",
  "action",
  "verification",
  "close",
  "receipt",
  "deadline",
  "handoff",
  "opinion",
  "cognito",
  "api",
  "postgres",
] as const;
export type FlowId = (typeof FLOW_IDS)[number];

export interface FlowBox {
  id: FlowId;
  group: FlowGroup;
  /** Where its detail comes from in the specs and ADRs (not translated). */
  source: string;
  /** Grid cell; evidence has none, it sits inside the case card's cell. */
  col: 1 | 3 | null;
  row: number | null;
}

export const LINK_LABELS = ["openCase", "decide", "signedIn", "tokenChecked", "appendEvent", "readBack", "check", "close"] as const;

export interface FlowLink {
  from: FlowId;
  to: FlowId;
  label: (typeof LINK_LABELS)[number];
  /** "step" is the analyst's own path; "needs" is what a step runs on. */
  kind: "step" | "needs";
  /** Which way the arrow points on the grid. */
  direction: "down" | "right" | "left";
  col: 1 | 2 | 3;
  row: number;
  /** Rows the edge spans (the long step edge passes the rows of what it runs on). */
  rows: number;
}

const at = (col: 1 | 3, row: number) => ({ col, row });
const inCase = { col: null, row: null };

export const FLOW_BOXES: FlowBox[] = [
  { id: "queue", group: "step", source: "spec 08 AC-02, AC-07 to AC-09", ...at(1, 1) },
  { id: "case", group: "step", source: "spec 08 AC-03, AC-10 to AC-15", ...at(1, 3) },
  { id: "action", group: "step", source: "spec 08 AC-04, AC-05, AC-13 · constitution #6", ...at(1, 5) },
  { id: "verification", group: "step", source: "constitution #4 · ADR 0010", ...at(1, 9) },
  { id: "close", group: "step", source: "spec 08 AC-09 · constitution #6", ...at(1, 11) },
  { id: "receipt", group: "evidence", source: "constitution #5 · spec 04", ...inCase },
  { id: "deadline", group: "evidence", source: "spec 08 AC-10 · ADR 0019", ...inCase },
  { id: "handoff", group: "evidence", source: "spec 08 AC-03 · handoff.schema.json", ...inCase },
  { id: "opinion", group: "evidence", source: "spec 08 AC-12, AC-18 · spec 18", ...inCase },
  { id: "cognito", group: "need", source: "ADR 0017 · spec 08 AC-01, AC-21", ...at(3, 5) },
  { id: "api", group: "need", source: "spec 01 §6.2 · spec 08 §6", ...at(3, 7) },
  { id: "postgres", group: "need", source: "ADR 0010", ...at(3, 9) },
];

/** The analyst's path, then what it runs on, in the order the edges play (once, on entering the viewport). */
export const FLOW_LINKS: FlowLink[] = [
  { from: "queue", to: "case", label: "openCase", kind: "step", direction: "down", col: 1, row: 2, rows: 1 },
  { from: "case", to: "action", label: "decide", kind: "step", direction: "down", col: 1, row: 4, rows: 1 },
  { from: "action", to: "cognito", label: "signedIn", kind: "needs", direction: "right", col: 2, row: 5, rows: 1 },
  { from: "cognito", to: "api", label: "tokenChecked", kind: "needs", direction: "down", col: 3, row: 6, rows: 1 },
  { from: "api", to: "postgres", label: "appendEvent", kind: "needs", direction: "down", col: 3, row: 8, rows: 1 },
  { from: "postgres", to: "verification", label: "readBack", kind: "needs", direction: "left", col: 2, row: 9, rows: 1 },
  { from: "action", to: "verification", label: "check", kind: "step", direction: "down", col: 1, row: 6, rows: 3 },
  { from: "verification", to: "close", label: "close", kind: "step", direction: "down", col: 1, row: 10, rows: 1 },
];

/** The cell of the heading over what the flow runs on (its frame runs from here to the last need's row). */
export const NEEDS_TITLE = { col: 3 as const, row: 4 };
