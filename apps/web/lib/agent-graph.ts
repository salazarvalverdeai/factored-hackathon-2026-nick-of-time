// The drawn graph of /agent (spec 04 AC-08): nodes, edges, branch labels and coordinates all come from
// lib/agent-reference.ts, which scripts/sync-agent.mjs reads from apps/agent/agent/intake.py and lays out at sync
// time, so the page needs no layout library. This file only joins them with the one-liners of lib/agent.ts.
import { AGENT_REFERENCE } from "./agent-reference.ts";
import { NODE_INFO, type GraphNode } from "./agent.ts";
import { highlightOf, revealSchedule, type Highlight } from "./agent-motion.ts";

const { graph } = AGENT_REFERENCE;

export type BranchKind = (typeof graph.branches)[number]["kind"];

/** What decides a branch, by the kind sync-agent gives the values its condition reads (BRANCH_KINDS). */
export const KIND_TEXT: Record<BranchKind, string> = {
  policy: "policy engine decision",
  tool: "tool read or verification result",
  input: "understood input",
};

export interface GraphEdge {
  from: string;
  to: string;
  /** The deciding clause drawn on a branch edge; null on an unconditional edge. */
  label: string | null;
  kind: BranchKind | null;
  /** The full condition read from the router, outer clause first. */
  when: string | null;
  path: string;
  labelBox: { x: number; y: number; w: number; h: number } | null;
}

export interface GraphViewNode {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  terminal: boolean;
  info: string;
}

/** What START and END stand for; every other node's one-liner is NODE_INFO's. */
export function infoOf(id: string): string {
  if (id === "START") return "Where every turn enters the graph.";
  if (id === "END") return "The turn is over: the reply, receipt or handoff card has been sent.";
  return NODE_INFO[id as GraphNode];
}

export const GRAPH_VIEW = {
  name: graph.name,
  width: graph.layout.width,
  height: graph.layout.height,
  /** In rank order, then left to right, which is the tab order. */
  nodes: graph.layout.nodes.map(
    (n): GraphViewNode => ({ id: n.id, x: n.x, y: n.y, w: n.w, h: n.h, terminal: n.id === "START" || n.id === "END", info: infoOf(n.id) }),
  ),
  edges: graph.layout.edges.map((e): GraphEdge => {
    const branch = graph.branches.find((b) => b.from === e.from && b.to === e.to);
    return { from: e.from, to: e.to, label: e.label, kind: e.kind, when: branch?.when ?? null, path: e.path, labelBox: e.labelBox };
  }),
};

/** The edges out of and into a node, in edge order. */
export function linksOf(id: string): { out: GraphEdge[]; in: GraphEdge[] } {
  return { out: GRAPH_VIEW.edges.filter((e) => e.from === id), in: GRAPH_VIEW.edges.filter((e) => e.to === id) };
}

/** A node's accessible name: its id, what it does and where it can go. */
export function ariaLabelOf(id: string): string {
  const out = linksOf(id).out.map((e) => (e.label ? `${e.to} when ${e.label}` : e.to));
  return `${id}: ${infoOf(id)}${out.length ? ` Next: ${out.join("; ")}.` : ""}`;
}

/** The drawing's reveal (lib/agent-motion.ts): nodes in topological order, each edge after its source, labels last. */
export const GRAPH_REVEAL = revealSchedule(
  GRAPH_VIEW.nodes.map((n) => n.id),
  GRAPH_VIEW.edges,
);

/** What a run highlights on the drawing: the node it is on and the path it took (graph-view's activeNode and path). */
export function graphHighlight(activeNode?: string | null, path?: readonly string[] | null): Highlight {
  return highlightOf({ activeNode, path }, GRAPH_VIEW.nodes.map((n) => n.id), GRAPH_VIEW.edges);
}
