// What the assisted case view shows, as pure functions (spec 08 assisted console, spec 18 T5/T5b): the status stepper,
// the deadline countdown, the proposal's console action and a human label for every enum the console routes send.
// The components in components/console/ only draw these. No raw identifier, no bracket tag reaches the screen.
import type { ConsoleAction } from "./console-actions.ts";
import type { AuditCheck, CopilotProposal, SummaryDeadline, Verdict } from "./console-api.ts";
import { COPILOT_ACTION_LABELS } from "./handoff-labels.ts";
import type { CaseStatus } from "./types.ts";

const titleCase = (v: string) => v.replace(/[_-]+/g, " ").trim().replace(/^./, (c) => c.toUpperCase());
/** An unknown identifier (`some_value`) reads as words; free text from the api (it has spaces, dates…) stays as it is. */
const fallback = (v: string) => (/^[a-z][a-z0-9_]*$/i.test(v) ? titleCase(v) : v);
const labelOf = (table: Record<string, string>) => (v: string | null | undefined) =>
  v ? (table[v] ?? fallback(v)) : "—";

/** Removes the figure labels (`[simulated]`, `[data]`…) from texts the operational screens show (spec 08, 13). */
export const plain = (text: string): string =>
  text.replace(/\s*\[(simulated|assumption|data|external|projected)\]/g, "").trim();

// --- enum labels ----------------------------------------------------------------------------------------------------

export const VERDICT_LABELS: Record<Verdict, string> = {
  agree: "Agrees with the proposal",
  disagree: "Disagrees with the proposal",
  uncertain: "Not sure about the proposal",
};
export const verdictLabel = labelOf(VERDICT_LABELS);

/** The auditor's checks (spec 18 §4.1, P0 is A1–A7), worded as what passing means. */
export const AUDIT_CHECK_LABELS: Record<string, string> = {
  A1: "Decision: the rules give the same decision",
  A2: "Deadline: the legal clock gives the same dates",
  A3: "Actions: every verified action was read back",
  A4: "Grounding: every figure shown comes from a tool",
  A5: "Coherence: what the customer was told matches the record",
  A6: "Privacy: nothing sensitive reached the customer",
  A7: "Lifecycle: valid steps only, a person resolves and closes",
};
export const auditCheckLabel = (c: Pick<AuditCheck, "id" | "name">) => AUDIT_CHECK_LABELS[c.id] ?? titleCase(c.name || c.id);

export const AUDIT_STATE_LABELS = { passed: "Passed", finding: "Finding", na: "Not applicable" } as const;
/** The short word shown next to a check; screen readers get AUDIT_STATE_LABELS. */
export const AUDIT_STATE_SHORT = { passed: "Passed", finding: "Finding", na: "n/a" } as const;
/** The api's `status` wins; `not_applicable` (A4, A5 in the console: they need the agent trace) is never a failure. */
export const auditState = (c: Pick<AuditCheck, "passed" | "status">): keyof typeof AUDIT_STATE_LABELS => {
  if (c.status === "not_applicable") return "na";
  if (c.status === "finding") return "finding";
  if (c.status === "passed") return "passed";
  return c.passed === true ? "passed" : c.passed === false ? "finding" : "na";
};

/** Why there is no second opinion (`X-No-Opinion-Reason`), as one calm line (spec 18 AC-11). */
export const NO_OPINION_REASON_LABELS: Record<string, string> = {
  no_handoff: "Not available: the agent has not written the handoff card yet",
  budget: "Not available: daily budget reached",
  timeout: "Not available: the judge did not answer in time",
  error: "Not available: the judge's answer could not be used",
  unavailable: "Not available: the judge model is not configured",
};
export const noOpinionReasonLabel = (v: string | null | undefined) =>
  (v && NO_OPINION_REASON_LABELS[v]) || NO_OPINION_REASON_LABELS.error;

export const OUTCOME_LABELS: Record<string, string> = {
  block_and_verify: "Block the card and verify",
  confirm_with_customer: "Confirm with the customer first",
  human_review: "A person reviews the case",
  credit_approved: "Provisional credit approved",
  approve_credit: "Provisional credit approved",
  approve_block: "Card block approved",
  resolved: "Resolved by a person",
  closed_without_action: "Closed without action",
  close_without_action: "Closed without action",
  rejected: "Dispute rejected",
};
export const outcomeLabel = labelOf(OUTCOME_LABELS);

export const CHANNEL_LABELS: Record<string, string> = {
  in_app: "In the app",
  log: "In the app",
  telegram: "Telegram",
  email: "E-mail",
};
export const channelLabel = labelOf(CHANNEL_LABELS);

export const DELIVERY_LABELS: Record<string, string> = {
  sent: "Sent",
  delivered: "Delivered",
  queued: "Queued",
  pending: "Pending",
  failed: "Not delivered",
  denied: "Not sent (demo)",
};
export const deliveryLabel = labelOf(DELIVERY_LABELS);

export const NOTIFICATION_EVENT_LABELS: Record<string, string> = {
  case_opened: "Case opened",
  status_new: "Case opened",
  status_verification: "Verifying the case",
  status_review: "A person is reviewing",
  status_resolved: "Case resolved",
  status_closed: "Case closed",
  status_changed: "Status changed",
  card_blocked: "Card blocked",
  call_requested: "Call requested",
  credit_approved: "Credit approved",
};
export const notificationEventLabel = labelOf(NOTIFICATION_EVENT_LABELS);

export const CARD_STATUS_LABELS: Record<string, string> = {
  active: "Active",
  blocked: "Blocked",
  block_requested: "Block requested",
  cancelled: "Cancelled",
  expired: "Expired",
};
export const cardStatusLabel = labelOf(CARD_STATUS_LABELS);

export const PRODUCT_LABELS: Record<string, string> = { debit: "Debit card", credit: "Credit card" };
export const productLabel = labelOf(PRODUCT_LABELS);

export const CALL_STATUS_LABELS: Record<string, string> = {
  requested: "Requested",
  scheduled: "Scheduled",
  completed: "Done",
  done: "Done",
  missed: "Missed",
  cancelled: "Cancelled",
};
export const callStatusLabel = labelOf(CALL_STATUS_LABELS);

export const CASE_STATUS_LABELS: Record<CaseStatus, string> = {
  new: "New",
  verification: "Verification",
  review: "Review",
  resolved: "Resolved",
  closed: "Closed",
};
export const caseStatusLabel = labelOf(CASE_STATUS_LABELS);

export const DEADLINE_KIND_LABELS: Record<string, string> = {
  credit: "Provisional credit due",
  ruling: "Ruling due",
  resolution: "Resolution due",
};
export const deadlineKindLabel = labelOf(DEADLINE_KIND_LABELS);

export const WRITER_LABELS: Record<string, string> = {
  llm: "Written by the agent's model from the case record",
  template: "Built from the case record with a fixed template",
};
export const writerLabel = labelOf(WRITER_LABELS);

// --- dates and amounts (es-MX, 24 h) ------------------------------------------------------------------------------

/** "5 jun 2026" from YYYY-MM-DD or an ISO timestamp (the date part, never shifted by the browser's zone). */
export function formatDay(iso: string): string {
  const day = iso.slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) return iso;
  return new Date(`${day}T12:00:00Z`).toLocaleDateString("es-MX", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

/** "4,200.00 MXN": the currency code stays visible, so no symbol is ambiguous across countries. */
/** A transaction's merchant, or a plain word when the bank's record has none. */
export const merchantLabel = (m: string | null | undefined) => (m && m.trim() ? m : "Unknown merchant");
/** "•••• 4417", or "—" when the card is not known. */
export const cardLabel = (last4: string | null | undefined) => (last4 ? `•••• ${last4}` : "—");

export function formatAmount(amount: number, currency: string): string {
  return `${amount.toLocaleString("es-MX", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`;
}

// --- status stepper ---------------------------------------------------------------------------------------------------

export type StepState = "done" | "current" | "upcoming";
export interface Step {
  key: "new" | "work" | "resolved" | "closed";
  label: string;
  state: StepState;
}

/**
 * The case queue as four steps: new → verification or review → resolved → closed (CLAUDE.md, contracts/policies.yaml).
 * The second step names the path the case took (`verification` or `review`), or both while it has not reached it.
 */
export function stepperSteps(status: CaseStatus, path: { verification?: boolean; review?: boolean } = {}): Step[] {
  const order = { new: 0, verification: 1, review: 1, resolved: 2, closed: 3 } as const;
  const at = order[status];
  const work =
    status === "verification" || (status !== "review" && path.verification && !path.review)
      ? "Verification"
      : status === "review" || path.review
        ? "Review"
        : "Verification or review";
  const keys: Step["key"][] = ["new", "work", "resolved", "closed"];
  const labels = ["New", work, "Resolved", "Closed"];
  return keys.map((key, i) => ({
    key,
    label: labels[i],
    // A closed case has finished every step, the last one included.
    state: i < at || (status === "closed" && i === at) ? "done" : i === at ? "current" : "upcoming",
  }));
}

// --- deadline countdown ---------------------------------------------------------------------------------------------

export type CountdownLevel = "green" | "amber" | "red" | "unknown";

/** "2 days left" for the summary's deadline, with the same thresholds as the inbox's SLA light (spec 08 AC-08). */
export function countdown(d: Pick<SummaryDeadline, "days_left">): { level: CountdownLevel; text: string } {
  const n = d.days_left;
  const days = (k: number) => `${k} day${k === 1 ? "" : "s"}`;
  if (n === null || n === undefined) return { level: "unknown", text: "Countdown not available" };
  if (n < 0) return { level: "red", text: `Past due by ${days(-n)}` };
  if (n === 0) return { level: "red", text: "Due today" };
  if (n <= 2) return { level: "amber", text: `${days(n)} left` };
  return { level: "green", text: `${days(n)} left` };
}

// --- copilot proposal -----------------------------------------------------------------------------------------------

/** Which console action carries out the proposal, if the case's status offers it (the analyst still decides). */
const PROPOSAL_TO_ACTION: Record<string, string[]> = {
  approve_credit: ["approve_credit"],
  close_without_action: ["resolve", "close_case"],
};

export function proposalAction(p: Pick<CopilotProposal, "action">, offered: ConsoleAction[]): ConsoleAction | null {
  for (const name of PROPOSAL_TO_ACTION[p.action] ?? []) {
    const hit = offered.find((a) => a.action === name);
    if (hit) return hit;
  }
  return null;
}

/** Why a proposal has no button here, in plain words. */
export const PROPOSAL_ELSEWHERE: Record<string, string> = {
  request_customer_info: "Ask the customer through the case or the call; the console has no button for it.",
  approve_block: "The card block is decided with the customer on the call, not from the console.",
  approve_credit: "Approving the credit is not offered in this status.",
  close_without_action: "Closing is not offered in this status.",
};

/** The proposal in plain words: the api's `explanation`, or its rationale without labels. */
export function proposalWords(p: CopilotProposal): { title: string; text: string } {
  const title = COPILOT_ACTION_LABELS[p.action] ?? titleCase(p.action);
  const text = plain(p.explanation?.trim() || p.rationale || "");
  return { title, text };
}
