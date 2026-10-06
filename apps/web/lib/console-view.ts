// What the assisted case view shows, as pure functions (spec 08 assisted console, spec 18 T5/T5b): the status stepper,
// the deadline countdown, the proposal's console action and a human label for every enum the console routes send, in
// the UI language (spec 16 AC-06; the words live in messages/console.ts and messages/ui.ts).
// The components in components/console/ only draw these. No raw identifier, no bracket tag reaches the screen.
import { consoleUi } from "../messages/console.ts";
import { ui } from "../messages/ui.ts";
import type { ConsoleAction } from "./console-actions.ts";
import type { AuditCheck, CopilotProposal, SummaryDeadline } from "./console-api.ts";
import { daysLeftText, pastDueText } from "./console-metrics.ts";
import { copilotActionLabel } from "./handoff-labels.ts";
import { formatDay as formatIntlDay, formatNumber, type Locale, translator } from "./i18n.ts";
import type { CaseStatus } from "./types.ts";

const titleCase = (v: string) => v.replace(/[_-]+/g, " ").trim().replace(/^./, (c) => c.toUpperCase());
/** An unknown identifier (`some_value`) reads as words; free text from the api (it has spaces, dates…) stays as it is. */
const fallback = (v: string) => (/^[a-z][a-z0-9_]*$/i.test(v) ? titleCase(v) : v);

/** Removes the figure labels (`[simulated]`, `[data]`…) from texts the operational screens show (spec 08, 13). */
export const plain = (text: string): string =>
  text.replace(/\s*\[(simulated|assumption|data|external|projected)\]/g, "").trim();

// --- enum labels (messages/console.ts `labels`, per UI language) -----------------------------------------------------

type LabelTable = keyof (typeof consoleUi)["en"]["labels"];
/** Every enum table of the console in one locale (the tests check each has a word for every value). */
export const labelTables = (locale: Locale): Record<LabelTable, Record<string, string>> => consoleUi[locale].labels;
const labelOf =
  (table: LabelTable) =>
  (v: string | null | undefined, locale: Locale): string =>
    v ? (labelTables(locale)[table][v] ?? fallback(v)) : "—";

export const verdictLabel = labelOf("verdict");

/** The auditor's checks (spec 18 §4.1, P0 is A1–A7), worded as what passing means. */
export const auditCheckLabel = (c: Pick<AuditCheck, "id" | "name">, locale: Locale): string =>
  labelTables(locale).auditCheck[c.id] ?? titleCase(c.name || c.id);

export type AuditState = "passed" | "finding" | "na";
/** The api's `status` wins; `not_applicable` (A4, A5 in the console: they need the agent trace) is never a failure. */
export const auditState = (c: Pick<AuditCheck, "passed" | "status">): AuditState => {
  if (c.status === "not_applicable") return "na";
  if (c.status === "finding") return "finding";
  if (c.status === "passed") return "passed";
  return c.passed === true ? "passed" : c.passed === false ? "finding" : "na";
};
export const auditStateLabel = (s: AuditState, locale: Locale): string => labelTables(locale).auditState[s];
/** The short word shown next to a check; screen readers get auditStateLabel. */
export const auditStateShort = (s: AuditState, locale: Locale): string => labelTables(locale).auditStateShort[s];

/** Why there is no second opinion (`X-No-Opinion-Reason`), as one calm line (spec 18 AC-11). */
export const noOpinionReasonLabel = (v: string | null | undefined, locale: Locale): string => {
  const table: Record<string, string> = labelTables(locale).noOpinionReason;
  return (v && table[v]) || table.error;
};

export const outcomeLabel = labelOf("outcome");
export const channelLabel = labelOf("channel");
export const deliveryLabel = labelOf("delivery");
export const notificationEventLabel = labelOf("notificationEvent");
export const cardStatusLabel = labelOf("cardStatus");
export const productLabel = labelOf("product");
export const callStatusLabel = labelOf("callStatus");
export const deadlineKindLabel = labelOf("deadlineKind");
export const writerLabel = labelOf("writer");

/** A case status in words, as the status badge says it (messages/ui.ts `status`). */
export const caseStatusLabel = (v: string | null | undefined, locale: Locale): string =>
  v ? ((ui[locale].status as Record<string, string>)[v] ?? titleCase(v)) : "—";

// --- dates and amounts (per UI language, 24 h) ----------------------------------------------------------------------

/** "5 jun 2026" from YYYY-MM-DD or an ISO timestamp (the date part, never shifted by the browser's zone). */
export function formatDay(locale: Locale, iso: string): string {
  const day = iso.slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) return iso;
  return formatIntlDay(locale, day);
}

/** A transaction's merchant, or a plain word when the bank's record has none. */
export const merchantLabel = (m: string | null | undefined, locale: Locale): string =>
  m && m.trim() ? m : translator(locale)("console.history.unknownMerchant");
/** "•••• 4417", or "—" when the card is not known. */
export const cardLabel = (last4: string | null | undefined): string => (last4 ? `•••• ${last4}` : "—");

/** "4,200.00 MXN" (es, en) or "4.200,00 MXN" (pt): the currency code stays visible, so no symbol is ambiguous. */
export function formatAmount(locale: Locale, amount: number, currency: string): string {
  return `${formatNumber(locale, amount, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`;
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
export function stepperSteps(status: CaseStatus, locale: Locale, path: { verification?: boolean; review?: boolean } = {}): Step[] {
  const order = { new: 0, verification: 1, review: 1, resolved: 2, closed: 3 } as const;
  const at = order[status];
  const words = ui[locale].status;
  const work =
    status === "verification" || (status !== "review" && path.verification && !path.review)
      ? words.verification
      : status === "review" || path.review
        ? words.review
        : consoleUi[locale].header.either;
  const keys: Step["key"][] = ["new", "work", "resolved", "closed"];
  const labels = [words.new, work, words.resolved, words.closed];
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
export function countdown(d: Pick<SummaryDeadline, "days_left">, locale: Locale): { level: CountdownLevel; text: string } {
  const n = d.days_left;
  const t = translator(locale);
  if (n === null || n === undefined) return { level: "unknown", text: t("ui.time.countdownUnavailable") };
  if (n < 0) return { level: "red", text: pastDueText(locale, -n) };
  if (n === 0) return { level: "red", text: t("ui.time.dueToday") };
  if (n <= 2) return { level: "amber", text: daysLeftText(locale, n) };
  return { level: "green", text: daysLeftText(locale, n) };
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
export function proposalElsewhere(action: string, locale: Locale): string {
  const why: Record<string, string> = consoleUi[locale].proposal.elsewhere;
  return why[action] ?? consoleUi[locale].proposal.noAction;
}

/** The proposal in plain words: the api's `explanation`, or its rationale without labels (the text stays as sent). */
export function proposalWords(p: CopilotProposal, locale: Locale): { title: string; text: string } {
  const title = copilotActionLabel(p.action, locale);
  const text = plain(p.explanation?.trim() || p.rationale || "");
  return { title, text };
}
