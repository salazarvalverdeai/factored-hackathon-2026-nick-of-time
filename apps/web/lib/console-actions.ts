// Which analyst actions the console offers for a case, per mode (spec 08, spec 05 AC-03/AC-04).
// The queue rules live in contracts/policies.yaml and the api enforces them (409 DENY); this only decides which buttons
// to show so a person is not offered a move the api would refuse.
import type { ApiMode } from "./client.ts";
import type { CaseStatus } from "./types.ts";

export type AnalystActionName = "take" | "approve_credit" | "resolve" | "close_case" | "reopen_case";

export interface ConsoleAction {
  action: AnalystActionName;
  label: string;
  /** The api requires a reason for every action except `take` and `approve_*` (spec 05 AC-10). */
  needsReason: boolean;
  /** An approval: in supervised mode it asks for a second click. */
  approval?: boolean;
}

const TAKE: ConsoleAction = { action: "take", label: "Take the case", needsReason: false };
const APPROVE: ConsoleAction = { action: "approve_credit", label: "Approve credit", needsReason: false, approval: true };
const RESOLVE: ConsoleAction = { action: "resolve", label: "Resolve", needsReason: true };
const CLOSE: ConsoleAction = { action: "close_case", label: "Close case", needsReason: true };
const REOPEN: ConsoleAction = { action: "reopen_case", label: "Reopen for review", needsReason: true };

/**
 * Mock: the two-button flow of the first console (approving a credit resolves the case, then a person closes it).
 * Live: the real queue (D-034): `take` from an open status, `approve_credit` records the decision and keeps the status,
 * `resolve` moves it, `close_case` and `reopen_case` start from `resolved`.
 */
export function consoleActions(status: CaseStatus, mode: ApiMode): ConsoleAction[] {
  if (mode === "mock") {
    const open = status === "verification" || status === "review";
    return [...(open ? [APPROVE] : []), ...(status === "resolved" ? [{ ...CLOSE, needsReason: false }] : [])];
  }
  switch (status) {
    case "new":
      return [TAKE];
    case "verification":
    case "review":
      return [TAKE, APPROVE, RESOLVE];
    case "resolved":
      return [CLOSE, REOPEN];
    default:
      return [];
  }
}
