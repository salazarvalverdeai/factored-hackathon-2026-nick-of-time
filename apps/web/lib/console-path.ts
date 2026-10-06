// The agent's path for one case, drawn on the console's GraphView (spec 08 AC-23). The console holds no agent trace,
// so the path is reconstructed from the case's own events and its handoff card, and the graph's shape
// (lib/agent-reference.ts, read from apps/agent/agent/intake.py) fills in what the topology forces: `open_case` runs only
// in `act`, and `act` has a single way in from START. A node the data cannot pin is left out, never guessed.
import { AGENT_REFERENCE } from "./agent-reference.ts";

const { graph } = AGENT_REFERENCE;

export const START = "START";
export const END = "END";

/** Every edge of the graph, flattened: the topology the reconstruction walks. */
const EDGES = graph.edges.flatMap((e) => e.to.map((to) => ({ from: e.from, to })));
const ins = (id: string) => EDGES.filter((e) => e.to === id).map((e) => e.from);
const outs = (id: string) => EDGES.filter((e) => e.from === id).map((e) => e.to);

/** The nodes every run that reaches `id` went through, from START: followed back while a node has one way in. */
export function forcedBefore(id: string): string[] {
  const path = [id];
  for (let at = id; ins(at).length === 1; ) {
    at = ins(at)[0];
    path.unshift(at);
    if (at === START) break;
  }
  return path;
}

/** The nodes every run that leaves `id` goes through next: followed forward while a node has one way out. */
export function forcedAfter(id: string): string[] {
  const path: string[] = [];
  for (let at = id; outs(at).length === 1; ) {
    at = outs(at)[0];
    path.push(at);
    if (at === END) break;
  }
  return path;
}

/** The node each case event or handoff action pins, and why. Every id here is a node of agent-reference (tested). */
export const PINS = {
  case_opened: { node: "act", why: "open_case runs only in act" },
  card_blocked: { node: "act", why: "block_card runs only in act" },
  block_verified: { node: "verify", why: "verify reads the block back" },
  action_verified: { node: "verify", why: "verify reads each write back" },
  request_call: { node: "connect", why: "request_call runs only in connect" },
  handoff_emitted: { node: "respond", why: "respond builds the handoff card" },
  receipt_issued: { node: "respond", why: "respond builds the receipt" },
} as const satisfies Record<string, { node: string; why: string }>;

export type PinSource = keyof typeof PINS;

export interface PathEvidence {
  node: string;
  /** What in the case pins it: an event type, a handoff action, or the graph's own shape. */
  source: PinSource | "graph" | "handoff_card";
  why: string;
}

export interface CasePath {
  /** The nodes in order, for GraphView's `path`; empty when the case events pin nothing. */
  path: string[];
  evidence: PathEvidence[];
  /** Why the path stops where it does, when it stops before END. */
  stop: string | null;
}

interface PathInput {
  events: readonly { type: string; actor: string }[];
  handoff: { actions: readonly { tool: string }[] } | null;
}

const TOPOLOGY = "the graph has one way here";

/**
 * The opening turn's path: the case was opened by `open_case`, so the run went START → … → act → verify (forced by the
 * graph). After verify the run goes to connect or respond; the handoff card pins which when it carries that turn's
 * actions (open_case or block_card), and a case with no call by the agent and a receipt or card goes straight to
 * respond. Otherwise the path stops at verify.
 */
export function casePath({ events, handoff }: PathInput): CasePath {
  const has = (type: string) => events.some((e) => e.type === type);
  if (!has("case_opened")) return { path: [], evidence: [], stop: "No case_opened event: nothing pins the agent's run." };

  const evidence: PathEvidence[] = [];
  const pin = (source: PinSource) => evidence.push({ node: PINS[source].node, source, why: PINS[source].why });
  const forced = (nodes: string[]) => nodes.forEach((node) => evidence.push({ node, source: "graph", why: TOPOLOGY }));

  const toAct = forcedBefore("act");
  forced(toAct.slice(0, -1));
  pin("case_opened");
  if (has("card_blocked")) pin("card_blocked");
  const afterAct = forcedAfter("act");
  const path = [...toAct, ...afterAct];
  if (has("block_verified")) pin("block_verified");
  else if (has("action_verified")) pin("action_verified");
  else forced(afterAct);

  const tools = new Set((handoff?.actions ?? []).map((a) => a.tool));
  const actTurnCard = tools.has("open_case") || tools.has("block_card");
  const agentCall = events.some((e) => e.type === "call_requested" && e.actor === "agent");
  const reply = has("receipt_issued") ? "receipt_issued" : has("handoff_emitted") ? "handoff_emitted" : null;

  let next: string | null = null;
  if (actTurnCard) next = tools.has("request_call") ? "connect" : "respond";
  else if (!agentCall && reply) next = "respond";
  if (!next) {
    return {
      path,
      evidence,
      stop: agentCall
        ? "A call was requested, but the case events do not say in which turn, so the path stops at verify."
        : "No receipt or handoff card from that turn, so the path stops at verify.",
    };
  }
  if (next === "connect") pin("request_call");
  else if (actTurnCard) evidence.push({ node: "respond", source: "handoff_card", why: "the turn's handoff card shows no call" });
  if (reply) pin(reply);
  const tail = [next, ...forcedAfter(next)];
  forced(tail.filter((node) => !evidence.some((e) => e.node === node)));
  return { path: [...path, ...tail], evidence, stop: null };
}

/** The ids a path may hold: the graph's nodes, START and END. */
export const GRAPH_IDS: ReadonlySet<string> = new Set([START, ...graph.nodes, END]);
