// The live graph beside /chat (spec 07 AC-28): which node of dispute_intake the agent is on while a turn runs, folded
// from the same stream frames the chat shows (spec 01 §6.4.1). The node ids come from lib/agent-reference.ts (synced
// from apps/agent/agent/intake.py); the event → node wiring below mirrors where intake.py emits each progress key and
// tool event. Pure and tested offline (lib/chat-graph.test.ts): the drawing (components/agent/graph-view.tsx) only
// receives `activeNode` and `path`.
import { AGENT_REFERENCE } from "./agent-reference.ts";
import type { EnterKind } from "./chat-motion.ts";

const { graph } = AGENT_REFERENCE;

/** Every node the drawing knows: the graph's nodes plus START and END. */
export const GRAPH_NODES: readonly string[] = ["START", ...graph.nodes, "END"];

/** intake.py `progress(state, key)`: the node that streams each progress key (WRITING's keys stream from `act`). */
export const PROGRESS_NODE: Record<string, string> = {
  reading_account: "greet",
  reading_message: "understand",
  searching: "retrieve",
  deciding: "decide",
  opening_case: "act",
  blocking_card: "act",
  verifying: "verify",
  requesting_call: "connect",
  checking_status: "status",
  writing: "respond",
};

/**
 * intake.py `tool_event(state, step, …)`: the node that runs each tool. A write starts (and may fail) in `act`, and its
 * `done` comes from `verify`, after the read-back. A read made inside another step (`get_case` while retrieving,
 * connecting or verifying; `compute_deadline`) keeps the step the agent is on.
 */
export const TOOL_NODE: Record<string, string> = {
  search_transaction: "retrieve",
  list_recent_transactions: "retrieve",
  evaluate_policy: "decide",
  open_case: "act",
  block_card: "act",
  request_call: "connect",
  get_case: "status",
  get_case_status: "status",
};
const WRITES = new Set(["open_case", "block_card"]);
const READ_INSIDE = new Set(["retrieve", "connect", "verify", "act"]);

/** Where every turn enters: the session check runs first, then the account read and the message read. */
export const TURN_START = ["START", "identity"] as const;

export interface GraphRun {
  /** The node the agent is on now; null before a turn and once it ends. */
  active: string | null;
  /** The nodes passed this turn, in order, START first (END once the turn is over). */
  path: string[];
}

export const EMPTY_RUN: GraphRun = { active: null, path: [] };

/** A new turn: START → identity, with identity current. */
export function startRun(): GraphRun {
  return { active: "identity", path: [...TURN_START] };
}

const NEXT = new Map<string, string[]>(graph.edges.map((e) => [e.from, [...e.to]]));

/** The shortest way along the graph's edges from one node to another, both ends included; null if there is none. */
export function routeBetween(from: string, to: string): string[] | null {
  if (from === to) return [from];
  const back = new Map<string, string>([[from, from]]);
  const queue = [from];
  while (queue.length) {
    const at = queue.shift()!;
    for (const next of NEXT.get(at) ?? []) {
      if (back.has(next)) continue;
      back.set(next, at);
      if (next === to) {
        const out = [to];
        for (let n = to; n !== from; ) out.unshift((n = back.get(n)!));
        return out;
      }
      queue.push(next);
    }
  }
  return null;
}

/**
 * Moves the run to `node`. The steps between that streamed nothing (route, plan) are filled in along the graph's own
 * edges, so the highlighted path is always one the graph can take. A node already passed this turn is ignored: a turn
 * walks the graph forward and never goes back.
 */
export function advance(run: GraphRun, node: string | null): GraphRun {
  if (!node || !GRAPH_NODES.includes(node) || run.path.includes(node)) return run;
  const from = run.path[run.path.length - 1];
  const way = from ? routeBetween(from, node) : null;
  const added = way ? way.slice(1) : [node];
  return { active: node, path: [...run.path, ...added] };
}

/** The node a progress key belongs to, or null when the key is unknown. */
export function nodeOfProgress(step: string | undefined): string | null {
  return (step && PROGRESS_NODE[step]) || null;
}

/** The node a tool event belongs to, given the node the run is on. */
export function nodeOfTool(event: { step: string; status: string }, active: string | null): string | null {
  if (WRITES.has(event.step)) return event.status === "done" ? "verify" : "act";
  if (event.step === "compute_deadline") return active;
  const node = TOOL_NODE[event.step] ?? null;
  if (node === "status" && active && READ_INSIDE.has(active)) return active;
  return node;
}

/** The frames the chat shows (lib/chat-reveal.ts TurnFrame), as far as the graph needs them. */
export type GraphFrame =
  | { kind: "progress"; step?: string; label?: string }
  | { kind: "tool"; event: { step: string; status: string } }
  | { kind: "text" }
  | { kind: "reply" };

/** Folds one shown frame into the run: progress and tools move it; the reply being written is `respond`. */
export function applyFrame(run: GraphRun, frame: GraphFrame): GraphRun {
  if (run.path.length === 0) return run;
  switch (frame.kind) {
    case "progress":
      return advance(run, nodeOfProgress(frame.step));
    case "tool":
      return advance(run, nodeOfTool(frame.event, run.active));
    default:
      return advance(run, "respond");
  }
}

/** The turn has been shown whole: the path ends at END and nothing is current any more. */
export function finishRun(run: GraphRun): GraphRun {
  if (run.path.length === 0) return run;
  const ended = advance(advance(run, "respond"), "END");
  return { active: null, path: ended.path };
}

/** A turn that stopped (an error, "Nuevo caso"): the path stays as it was, nothing is current. */
export function stopRun(run: GraphRun): GraphRun {
  return { active: null, path: run.path };
}

/** The rail's entrance through the chat motion adapter: a 150 ms fade, nothing at all under reduced motion (AC-27). */
export const RAIL_ENTER: EnterKind = "fade";
