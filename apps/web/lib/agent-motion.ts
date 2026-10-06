// Motion timing and highlight logic of /agent's drawings (spec 04 AC-08), kept free of React so `npm test` checks it.
// BRAND.md asks for calm and precise: every transition is 150–400 ms and eases out, nothing bounces or glows, and with
// `prefers-reduced-motion: reduce` nothing moves (the drawings render their final state). The components that use it
// are components/agent/graph-view.tsx and components/agent/architecture-view.tsx.

/** Seconds. Each single transition stays within 150–400 ms; only the stagger between items adds up. */
export const TIMING = { node: 0.24, edge: 0.32, label: 0.2, stagger: 0.06, highlight: 0.2 } as const;
/** Ease-out (cubic-bezier), the only curve the drawings use. */
export const EASE_OUT = [0.22, 1, 0.36, 1] as const;

export interface Link {
  from: string;
  to: string;
}

export const linkKey = (e: Link) => `${e.from}->${e.to}`;

/**
 * Nodes in topological order (Kahn), ties broken by the order they are given in (rank, then left to right), so START
 * comes first and END last. A cycle would leave nodes out, so they are appended in their given order.
 */
export function topologicalOrder(nodes: readonly string[], edges: readonly Link[]): string[] {
  const indegree = new Map(nodes.map((n) => [n, 0]));
  for (const e of edges) indegree.set(e.to, (indegree.get(e.to) ?? 0) + 1);
  const position = new Map(nodes.map((n, i) => [n, i]));
  const ready = nodes.filter((n) => indegree.get(n) === 0);
  const order: string[] = [];
  while (ready.length) {
    ready.sort((a, b) => position.get(a)! - position.get(b)!);
    const n = ready.shift()!;
    order.push(n);
    for (const e of edges) {
      if (e.from !== n) continue;
      const left = indegree.get(e.to)! - 1;
      indegree.set(e.to, left);
      if (left === 0) ready.push(e.to);
    }
  }
  return [...order, ...nodes.filter((n) => !order.includes(n))];
}

export interface RevealSchedule {
  order: string[];
  /** Delay in seconds before each node, edge (by linkKey) and branch label starts. */
  node: Record<string, number>;
  edge: Record<string, number>;
  label: Record<string, number>;
  /** When the last transition ends. */
  total: number;
}

/**
 * The reveal of a graph: nodes appear in topological order, one stagger apart; an edge draws once its source node has
 * appeared, and its branch label fades in once the edge is drawn.
 */
export function revealSchedule(nodes: readonly string[], edges: readonly Link[], t = TIMING): RevealSchedule {
  const order = topologicalOrder(nodes, edges);
  const node = Object.fromEntries(order.map((n, i) => [n, round(i * t.stagger)]));
  const edge: Record<string, number> = {};
  const label: Record<string, number> = {};
  for (const e of edges) {
    edge[linkKey(e)] = round(node[e.from] + t.node);
    label[linkKey(e)] = round(edge[linkKey(e)] + t.edge);
  }
  const total = Math.max(...order.map((n) => node[n] + t.node), ...Object.values(label).map((d) => d + t.label), 0);
  return { order, node, edge, label, total: round(total) };
}

const round = (s: number) => Math.round(s * 1000) / 1000;

/**
 * What a drawing shows: "final" (everything in place: the server render, reduced motion, after a reveal), "hidden"
 * (armed below the fold, waiting to scroll into view) or "play" (revealing).
 */
export type RevealPhase = "final" | "hidden" | "play";

/**
 * The phase a drawing takes when it is first observed. Reduced motion, or a drawing already on screen, stays final:
 * the page never hides what the reader is already looking at.
 */
export function firstPhase({ reducedMotion, visible }: { reducedMotion: boolean; visible: boolean }): RevealPhase {
  return reducedMotion || visible ? "final" : "hidden";
}

/** The phase after a Replay press: reduced motion never plays. */
export function replayPhase(reducedMotion: boolean): RevealPhase {
  return reducedMotion ? "final" : "play";
}

/** Delay and duration for one element in a phase: only "play" waits or takes time. */
export function transitionFor(phase: RevealPhase, delay: number, duration: number) {
  return phase === "play" ? { delay, duration, ease: EASE_OUT } : { duration: 0 };
}

export interface Highlight {
  /** Nodes and edges (by linkKey) to emphasize; empty when nothing is highlighted. */
  nodes: Set<string>;
  edges: Set<string>;
  /** The node marked as current, if it exists in the graph. */
  current: string | null;
  /** True when the rest of the drawing should step back. */
  dims: boolean;
}

/**
 * The highlight of a run: `path` is the nodes it went through in order (each consecutive pair that is an edge is
 * highlighted), `activeNode` the node it is on now. Unknown ids are ignored, so a stale id never breaks the drawing.
 */
export function highlightOf(
  { activeNode, path }: { activeNode?: string | null; path?: readonly string[] | null },
  nodes: readonly string[],
  edges: readonly Link[],
): Highlight {
  const known = new Set(nodes);
  const keys = new Set(edges.map(linkKey));
  const onPath = (path ?? []).filter((n) => known.has(n));
  const current = activeNode && known.has(activeNode) ? activeNode : null;
  const edgeSet = new Set<string>();
  for (let i = 1; i < onPath.length; i++) {
    const key = linkKey({ from: onPath[i - 1], to: onPath[i] });
    if (keys.has(key)) edgeSet.add(key);
  }
  const nodeSet = new Set([...onPath, ...(current ? [current] : [])]);
  return { nodes: nodeSet, edges: edgeSet, current, dims: onPath.length > 0 };
}

export type Point = readonly [number, number];

/** Length of a polyline. */
export function polylineLength(points: readonly Point[]): number {
  let length = 0;
  for (let i = 1; i < points.length; i++) length += Math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]);
  return length;
}

/** The point at fraction `t` (0–1, clamped) of a polyline's length: where a flow's travelling dot is. */
export function pointAt(points: readonly Point[], t: number): { x: number; y: number } {
  const target = Math.min(1, Math.max(0, t)) * polylineLength(points);
  let walked = 0;
  for (let i = 1; i < points.length; i++) {
    const [ax, ay] = points[i - 1];
    const [bx, by] = points[i];
    const step = Math.hypot(bx - ax, by - ay);
    if (walked + step >= target && step > 0) {
      const f = (target - walked) / step;
      return { x: ax + (bx - ax) * f, y: ay + (by - ay) * f };
    }
    walked += step;
  }
  const [x, y] = points.at(-1) ?? [0, 0];
  return { x, y };
}

/** An SVG path through a polyline's points. */
export function pathOf(points: readonly Point[]): string {
  return points.map(([x, y], i) => `${i ? "L" : "M"}${x} ${y}`).join(" ");
}
