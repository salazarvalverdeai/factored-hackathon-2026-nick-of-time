// What the analyst console computes from the cases it reads (spec 08 AC-07 to AC-09): the KPI strip, the SLA light of
// each open case and the Closed tab. Pure functions over `listCases` + `getConsoleCase`; nothing here reads the system
// clock. Days left come from the api's business clock (`deadline_countdown_days`, ADR 0020) or, in mock mode, from the
// frozen demo date, exactly as `formatDeadline` counts them.
import type { ApiClient } from "./client.ts";
import { DEMO_TODAY, daysBetween } from "./mock/store.ts";
import type { CaseListItem, CaseStatus, ConsoleEvent, Deadline } from "./types.ts";

/** A case is at risk when its legal deadline is this many calendar days away or less, or already past. */
export const AT_RISK_DAYS = 2;
export const OPEN_STATUSES: readonly CaseStatus[] = ["new", "verification", "review"];
export const DONE_STATUSES: readonly CaseStatus[] = ["resolved", "closed"];

/** Events that mark a verified action: the store's post-condition reads, and the mock's move to verification. */
const VERIFIED_EVENTS = new Set(["block_verified", "action_verified", "verification_started"]);

/** The time zone of each country's business clock (contracts/policies.yaml `countries`); UTC otherwise, as the api does. */
const TIME_ZONES: Record<string, string> = {
  MX: "America/Mexico_City",
  AR: "America/Argentina/Buenos_Aires",
  BR: "America/Sao_Paulo",
  CO: "America/Bogota",
  PE: "America/Lima",
  CL: "America/Santiago",
};

/** The inbox summary plus, when it could be read, the case's events, opening time and time mode. */
export type BoardCase = CaseListItem & { events?: ConsoleEvent[]; openedAt?: string; mode?: "replay" | "live" };

export const DEFINITIONS = {
  open: "Cases in status new, verification or review: a person has not resolved them yet.",
  atRisk:
    `Open cases whose legal deadline is ${AT_RISK_DAYS} calendar days away or less (today, tomorrow or the day after), ` +
    "or already past, counted on the api's business clock. Cases with no legal deadline are not counted: a person decides.",
  toVerification:
    "Median time from the case opening to its first verified action (the block's post-condition read). " +
    "Cases with no verified action, such as the ones sent straight to a person, are left out.",
  label: "[simulated] Computed from the demo cases in this console (simulated customers), not from the dataset.",
} as const;

// --- deadlines -----------------------------------------------------------------------------------------------------

/** The nearest legal date of the case (credit or ruling), the one the api's countdown counts to; null = no clock. */
export function legalDeadline(d: Pick<Deadline, "creditDeadline" | "rulingDeadline">): string | null {
  const dates = [d.creditDeadline, d.rulingDeadline].filter((x): x is string => Boolean(x)).sort();
  return dates[0] ?? null;
}

/**
 * Days left to the legal deadline as the api counts them: live sends its count (`daysLeft`, null = none read yet);
 * the mock counts from the frozen demo date (ADR 0012). Null when there is no deadline or no count.
 */
export function daysLeftOf(d: Pick<Deadline, "creditDeadline" | "rulingDeadline" | "daysLeft">): number | null {
  const due = legalDeadline(d);
  if (!due) return null;
  if (d.daysLeft === undefined) return daysBetween(DEMO_TODAY, due);
  return d.daysLeft;
}

export type SlaLevel = "green" | "amber" | "red" | "none" | "unknown";

export interface Sla {
  level: SlaLevel;
  daysLeft: number | null;
  /** Short text shown next to the icon: the light never relies on color alone. */
  label: string;
}

const days = (n: number) => `${n} day${n === 1 ? "" : "s"}`;

/** The traffic light of a case from the days left to its legal deadline (spec 08 AC-08). */
export function slaOf(c: Pick<CaseListItem, "deadline">): Sla {
  if (!legalDeadline(c.deadline)) return { level: "none", daysLeft: null, label: "No legal deadline · a person decides" };
  const left = daysLeftOf(c.deadline);
  if (left === null) return { level: "unknown", daysLeft: null, label: "Countdown not available" };
  if (left < 0) return { level: "red", daysLeft: left, label: `Past due by ${days(-left)}` };
  if (left === 0) return { level: "red", daysLeft: 0, label: "Due today" };
  if (left <= AT_RISK_DAYS) return { level: "amber", daysLeft: left, label: `Due soon · ${days(left)} left` };
  return { level: "green", daysLeft: left, label: `On track · ${days(left)} left` };
}

export const isOpen = (c: Pick<CaseListItem, "status">) => OPEN_STATUSES.includes(c.status);
export const isAtRisk = (c: Pick<CaseListItem, "deadline">) => ["amber", "red"].includes(slaOf(c).level);

// --- KPI strip -----------------------------------------------------------------------------------------------------

export interface Kpis {
  open: number;
  atRisk: number;
  /** Open cases with no legal deadline: a person decides (never counted as at risk). */
  openWithoutDeadline: number;
  medianToVerificationMs: number | null;
  /** How many cases the median is computed from. */
  verifiedCases: number;
}

function openedAtOf(c: BoardCase): string | null {
  return c.openedAt ?? c.events?.find((e) => e.type === "case_opened")?.at ?? null;
}

/** Milliseconds from the case opening to its first verified action, or null when it has none. */
export function timeToVerificationMs(c: BoardCase): number | null {
  const opened = openedAtOf(c);
  const verified = c.events?.find((e) => VERIFIED_EVENTS.has(e.type))?.at;
  if (!opened || !verified) return null;
  const ms = Date.parse(verified) - Date.parse(opened);
  return Number.isFinite(ms) && ms >= 0 ? ms : null;
}

export function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const s = [...values].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

/** The three figures of the KPI strip (spec 08 AC-07). */
export function kpis(cases: BoardCase[]): Kpis {
  const open = cases.filter(isOpen);
  const times = cases.map(timeToVerificationMs).filter((x): x is number => x !== null);
  return {
    open: open.length,
    atRisk: open.filter(isAtRisk).length,
    openWithoutDeadline: open.filter((c) => slaOf(c).level === "none").length,
    medianToVerificationMs: median(times),
    verifiedCases: times.length,
  };
}

/** "under 1 min", "12 min", "3 h 5 min", "2 d 4 h". */
export function formatDuration(ms: number | null): string {
  if (ms === null) return "—";
  const minutes = Math.floor(ms / 60_000);
  if (minutes < 1) return "under 1 min";
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return minutes % 60 ? `${hours} h ${minutes % 60} min` : `${hours} h`;
  const d = Math.floor(hours / 24);
  return hours % 24 ? `${d} d ${hours % 24} h` : `${d} d`;
}

// --- Closed tab ----------------------------------------------------------------------------------------------------

export type DeadlineOutcome = "met" | "missed" | "none" | "unknown";

export interface ClosedRow {
  id: string;
  customerName: string;
  status: CaseStatus;
  outcome: string;
  /** Who moved the case to resolved, as the event records it. */
  decidedBy: string | null;
  resolvedAt: string | null;
  closedAt: string | null;
  /** Opening to closing; null while the case is resolved and waits for a person to close it. */
  timeToCloseMs: number | null;
  deadline: DeadlineOutcome;
  /** The legal date the outcome is measured against. */
  legalDeadline: string | null;
}

/**
 * When the case was last resolved and when it was closed. A case's status is its last event: the mock's events carry
 * the status they led to; the api's carry none, so its `status_changed` events are read in order — a case is closed
 * only from resolved, so a closed case's last change is the close and the one before it the resolution.
 */
export function statusMoments(c: BoardCase): { resolvedAt: string | null; closedAt: string | null; resolvedBy: string | null } {
  const events = c.events ?? [];
  if (events.some((e) => e.status !== undefined)) {
    let resolving: ConsoleEvent | null = null;
    let closing: ConsoleEvent | null = null;
    for (let i = 0; i < events.length; i++) {
      const e = events[i];
      const before = i > 0 ? events[i - 1].status : undefined;
      if (e.status === "resolved" && before !== "resolved") resolving = e;
      if (e.status === "closed" && before !== "closed") closing = e;
    }
    return moments(resolving, closing);
  }
  const changes = events.filter((e) => e.type === "status_changed");
  const last = changes[changes.length - 1] ?? null;
  if (c.status === "closed") return moments(changes[changes.length - 2] ?? null, last);
  if (c.status === "resolved") return moments(last, null);
  return moments(null, null);
}

function moments(resolving: ConsoleEvent | null, closing: ConsoleEvent | null) {
  return {
    resolvedAt: resolving?.at ?? null,
    closedAt: closing?.at ?? null,
    resolvedBy: resolving ? resolving.actor.replace(/^analyst:/, "") : null,
  };
}

/** The calendar date of an instant in a country's time zone (YYYY-MM-DD). */
export function localDate(iso: string, country: string): string | null {
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return null;
  return new Intl.DateTimeFormat("en-CA", { timeZone: TIME_ZONES[country] ?? "UTC", year: "numeric", month: "2-digit", day: "2-digit" }).format(t);
}

function shiftDays(iso: string, n: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

/**
 * The business date the case was resolved on. Live-mode cases run on the real date in the country's time zone, so it
 * is the resolution's local date. Replay cases and the mock run on a frozen date (ADR 0020, ADR 0012): it is the api's
 * own today for the case, read back from its countdown (deadline − days left).
 */
export function resolutionDay(c: BoardCase, resolvedAt: string): string | null {
  if (c.mode === "live") return localDate(resolvedAt, c.deadline.country);
  const due = legalDeadline(c.deadline);
  const left = daysLeftOf(c.deadline);
  return due && left !== null ? shiftDays(due, -left) : null;
}

/** Met when the case was resolved on or before its nearest legal date; "none" when it has no legal deadline. */
export function deadlineOutcome(c: BoardCase, resolvedAt: string | null): DeadlineOutcome {
  if (!legalDeadline(c.deadline)) return "none";
  if (!resolvedAt) return "unknown";
  const day = resolutionDay(c, resolvedAt);
  if (!day) return "unknown";
  return day <= (legalDeadline(c.deadline) as string) ? "met" : "missed";
}

/** The Closed tab's rows: resolved and closed cases, the most recently finished first (spec 08 AC-09). */
export function closedRows(cases: BoardCase[]): ClosedRow[] {
  return cases
    .filter((c) => DONE_STATUSES.includes(c.status))
    .map((c) => {
      const { resolvedAt, closedAt, resolvedBy } = statusMoments(c);
      const opened = openedAtOf(c);
      const credit = c.events?.some((e) => e.type === "credit_approved");
      const ms = opened && closedAt ? Date.parse(closedAt) - Date.parse(opened) : NaN;
      return {
        id: c.id,
        customerName: c.customerName,
        status: c.status,
        outcome: credit ? "Credit approved" : "Resolved by a person",
        decidedBy: resolvedBy,
        resolvedAt,
        closedAt,
        timeToCloseMs: Number.isFinite(ms) && ms >= 0 ? ms : null,
        deadline: deadlineOutcome(c, resolvedAt),
        legalDeadline: legalDeadline(c.deadline),
      };
    })
    .sort((a, b) => (b.closedAt ?? b.resolvedAt ?? "").localeCompare(a.closedAt ?? a.resolvedAt ?? ""));
}

// --- loading -------------------------------------------------------------------------------------------------------

async function mapLimit<T, R>(items: T[], limit: number, fn: (item: T) => Promise<R>): Promise<R[]> {
  const out: R[] = new Array(items.length);
  let next = 0;
  const worker = async () => {
    while (next < items.length) {
      const i = next++;
      out[i] = await fn(items[i]);
    }
  };
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
  return out;
}

/**
 * The inbox with what the KPI strip, the SLA lights and the Closed tab need. The api's list carries no events and no
 * countdown, so each case is read once more (`GET /api/console/cases/{id}`, a few at a time); the mock's list already
 * has them. A case whose detail cannot be read keeps its summary, and its light says the countdown is not available.
 */
export async function loadBoard(client: Pick<ApiClient, "listCases" | "getConsoleCase">, limit = 6): Promise<BoardCase[]> {
  const list: BoardCase[] = await client.listCases();
  return mapLimit(list, limit, async (item) => {
    if (Array.isArray(item.events)) return item;
    try {
      const d = await client.getConsoleCase(item.id);
      return { ...item, deadline: d.deadline, events: d.events, openedAt: d.openedAt, mode: d.mode };
    } catch {
      return item;
    }
  });
}
