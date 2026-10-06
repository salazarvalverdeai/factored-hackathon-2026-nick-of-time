// Offline checks for the console's KPI strip, SLA light and Closed tab (spec 08 AC-07 to AC-09). Run with `npm test`.
import assert from "node:assert/strict";
import test from "node:test";
import { createApi } from "./api.ts";
import {
  type BoardCase,
  closedRows,
  daysLeftOf,
  deadlineOutcome,
  formatDuration,
  kpis,
  legalDeadline,
  loadBoard,
  localDate,
  median,
  slaOf,
  timeToVerificationMs,
} from "./console-metrics.ts";
import { DEMO_TODAY, MockStore } from "./mock/store.ts";
import type { ConsoleCase, ConsoleEvent, Deadline } from "./types.ts";

const MIN = 60_000;
const dl = (over: Partial<Deadline> = {}): Deadline => ({
  country: "MX",
  product: "debit",
  creditDeadline: "2026-10-07",
  rulingDeadline: null,
  deadlineSource: "Banxico 3/2012",
  daysLeft: 5,
  ...over,
});
const ev = (type: string, at: string, actor = "agent", status?: ConsoleEvent["status"]): ConsoleEvent => ({
  id: `${type}-${at}`,
  at,
  type,
  actor,
  ...(status ? { status } : {}),
});
const bc = (over: Partial<BoardCase> = {}): BoardCase => ({
  id: "NOT-0001",
  customerName: "Ana",
  zone: "high",
  priority: "normal",
  status: "verification",
  deadline: dl(),
  ...over,
});

// --- AC-08: SLA light ------------------------------------------------------------------------------------------------

test("spec 08 AC-08: the light is green from 3 days left, amber at 1-2 days, red on the day and after", () => {
  assert.deepEqual(slaOf(bc({ deadline: dl({ daysLeft: 3 }) }), "en"), { level: "green", daysLeft: 3, label: "On track · 3 days left" });
  assert.equal(slaOf(bc({ deadline: dl({ daysLeft: 2 }) }), "en").level, "amber");
  assert.equal(slaOf(bc({ deadline: dl({ daysLeft: 1 }) }), "en").label, "Due soon · 1 day left");
  assert.deepEqual(slaOf(bc({ deadline: dl({ daysLeft: 0 }) }), "en"), { level: "red", daysLeft: 0, label: "Due today" });
  assert.equal(slaOf(bc({ deadline: dl({ daysLeft: -2 }) }), "en").label, "Past due by 2 days");
});

test("spec 08 AC-08, spec 16 AC-06: the light's text follows the UI language; the level does not", () => {
  const three = bc({ deadline: dl({ daysLeft: 3 }) });
  assert.deepEqual(slaOf(three, "es"), { level: "green", daysLeft: 3, label: "En plazo · quedan 3 días" });
  assert.deepEqual(slaOf(three, "pt"), { level: "green", daysLeft: 3, label: "No prazo · faltam 3 dias" });
  assert.equal(slaOf(bc({ deadline: dl({ daysLeft: 1 }) }), "es").label, "Vence pronto · queda 1 día");
  assert.equal(slaOf(bc({ deadline: dl({ daysLeft: 0 }) }), "pt").label, "Vence hoje");
  const none = bc({ deadline: dl({ creditDeadline: null, rulingDeadline: null, daysLeft: null }) });
  assert.match(slaOf(none, "es").label, /una persona decide/);
  assert.match(slaOf(none, "pt").label, /uma pessoa decide/);
});

test("spec 08 AC-08: no legal deadline (POL-CLOCK-UNKNOWN) is a neutral 'a person decides' state, never a date", () => {
  const sla = slaOf(bc({ deadline: dl({ creditDeadline: null, rulingDeadline: null, daysLeft: null }) }), "en");
  assert.equal(sla.level, "none");
  assert.equal(sla.daysLeft, null);
  assert.match(sla.label, /a person decides/);
  assert.doesNotMatch(sla.label, /\d/, "no invented date or count");
});

test("spec 08 AC-08: the count is the api's (nearest of credit and ruling); the mock counts from the frozen demo date", () => {
  assert.equal(legalDeadline({ creditDeadline: "2026-07-20", rulingDeadline: "2026-06-10" }), "2026-06-10");
  assert.equal(slaOf(bc({ deadline: dl({ creditDeadline: null, rulingDeadline: "2026-10-20", daysLeft: 11 }) }), "en").level, "green");
  // mock: no daysLeft at all → counted from DEMO_TODAY, never from the system clock
  assert.equal(daysLeftOf({ creditDeadline: "2026-06-05", rulingDeadline: undefined, daysLeft: undefined }), 4);
  assert.equal(DEMO_TODAY, "2026-06-01");
  // live row whose detail could not be read: a deadline exists but no count → not a guess
  assert.equal(slaOf(bc({ deadline: dl({ daysLeft: null }) }), "en").level, "unknown");
});

// --- AC-07: KPI strip ------------------------------------------------------------------------------------------------

test("spec 08 AC-07: open cases and deadlines at risk count only open cases; no-deadline cases are never at risk", () => {
  const board = [
    bc({ id: "A", status: "new", deadline: dl({ daysLeft: 1 }) }), // amber → at risk
    bc({ id: "B", status: "review", deadline: dl({ daysLeft: -1 }) }), // red → at risk
    bc({ id: "C", status: "verification", deadline: dl({ daysLeft: 9 }) }), // green
    bc({ id: "D", status: "review", deadline: dl({ creditDeadline: null, daysLeft: null }) }), // person decides
    bc({ id: "E", status: "resolved", deadline: dl({ daysLeft: 0 }) }), // done: not counted
    bc({ id: "F", status: "closed", deadline: dl({ daysLeft: -3 }) }),
  ];
  const k = kpis(board);
  assert.equal(k.open, 4);
  assert.equal(k.atRisk, 2);
  assert.equal(k.openWithoutDeadline, 1);
});

test("spec 08 AC-07: time to verification is opening → first verified action; the median skips cases without one", () => {
  const t0 = "2026-10-05T15:00:00.000Z";
  const at = (m: number) => new Date(Date.parse(t0) + m * MIN).toISOString();
  const live = (id: string, m: number) =>
    bc({ id, openedAt: t0, events: [ev("case_opened", t0), ev("card_blocked", at(m / 2)), ev("block_verified", at(m))] });
  const human = bc({ id: "H", openedAt: t0, events: [ev("case_opened", t0), ev("status_changed", at(1))] });
  assert.equal(timeToVerificationMs(live("X", 4)), 4 * MIN);
  assert.equal(timeToVerificationMs(human), null);
  const k = kpis([live("A", 2), live("B", 10), live("C", 4), human]);
  assert.equal(k.medianToVerificationMs, 4 * MIN);
  assert.equal(k.verifiedCases, 3);
  assert.equal(median([1, 3, 5, 7]), 4);
  assert.equal(kpis([human]).medianToVerificationMs, null);
});

test("spec 08 AC-07: durations read calmly", () => {
  assert.equal(formatDuration(null, "en"), "—");
  assert.equal(formatDuration(20_000, "en"), "under 1 min");
  assert.equal(formatDuration(12 * MIN, "en"), "12 min");
  assert.equal(formatDuration(185 * MIN, "en"), "3 h 5 min");
  assert.equal(formatDuration(52 * 60 * MIN, "en"), "2 d 4 h");
  assert.equal(formatDuration(20_000, "es"), "menos de 1 min");
  assert.equal(formatDuration(185 * MIN, "pt"), "3 h 5 min");
});

// --- AC-09: Closed tab -----------------------------------------------------------------------------------------------

test("spec 08 AC-09: a closed live case reads its resolve and close from the last status changes", () => {
  const events = [
    ev("case_opened", "2026-10-05T15:00:00Z"),
    ev("status_changed", "2026-10-05T15:01:00Z"), // new → verification
    ev("analyst_action", "2026-10-06T14:00:00Z", "analyst:gianmarco"),
    ev("status_changed", "2026-10-06T14:00:00Z", "analyst:gianmarco"), // → resolved
    ev("analyst_action", "2026-10-06T16:30:00Z", "analyst:diego"),
    ev("status_changed", "2026-10-06T16:30:00Z", "analyst:diego"), // → closed
  ];
  const [row] = closedRows([bc({ status: "closed", mode: "live", openedAt: "2026-10-05T15:00:00Z", events, deadline: dl({ creditDeadline: "2026-10-07", daysLeft: -1 }) })]);
  assert.equal(row.resolvedAt, "2026-10-06T14:00:00Z");
  assert.equal(row.closedAt, "2026-10-06T16:30:00Z");
  assert.equal(row.decidedBy, "gianmarco");
  assert.equal(row.timeToCloseMs, (25 * 60 + 30) * MIN);
  assert.equal(row.deadline, "met", "resolved on 2026-10-06, before the 2026-10-07 deadline");
  assert.equal(row.outcome, "resolved");
});

test("spec 08 AC-09: met or missed compares the resolution's business date with the nearest legal date", () => {
  // live mode: the local date in the country's time zone (03:00 UTC on the 6th is still the 5th in Mexico City)
  assert.equal(localDate("2026-06-06T03:00:00Z", "MX"), "2026-06-05");
  const live = bc({ mode: "live", deadline: dl({ creditDeadline: "2026-06-05" }) });
  assert.equal(deadlineOutcome(live, "2026-06-06T03:00:00Z"), "met");
  assert.equal(deadlineOutcome(live, "2026-06-06T07:00:00Z"), "missed");
  // replay: the frozen clock's today, read back from the api's countdown (deadline − days left)
  assert.equal(deadlineOutcome(bc({ mode: "replay", deadline: dl({ creditDeadline: "2026-06-03", daysLeft: -1 }) }), "2026-10-05T10:00:00Z"), "missed");
  assert.equal(deadlineOutcome(bc({ mode: "replay", deadline: dl({ creditDeadline: "2026-06-03", daysLeft: 2 }) }), "2026-10-05T10:00:00Z"), "met");
  // no legal deadline: "no deadline", never met or missed
  assert.equal(deadlineOutcome(bc({ deadline: dl({ creditDeadline: null, daysLeft: null }) }), "2026-10-05T10:00:00Z"), "none");
  assert.equal(deadlineOutcome(live, null), "unknown");
});

test("spec 08 AC-09: on the mock, approving and closing lists the case with its outcome, time to close and deadline", async () => {
  const clock = { t: Date.parse("2026-06-03T10:00:00Z") };
  const store = new MockStore(null, () => clock.t);
  const api = createApi(store, { mode: "mock", delayMs: 0 });
  await api.analystLogin("diego", "x");
  const before = await loadBoard(api);
  const k = kpis(before);
  assert.equal(k.open, 2, "the seeded MX and BR cases");
  assert.equal(k.atRisk, 1, "MX debit is 2 days from its deadline; BR has none and a person decides");
  assert.deepEqual(closedRows(before).map((r) => [r.id, r.status, r.timeToCloseMs]), [["NOT-0003", "resolved", null]]);

  clock.t += 30 * MIN;
  await api.analystAction("NOT-0001", "approve_credit");
  clock.t += 90 * MIN;
  await api.analystAction("NOT-0001", "close_case");
  const rows = closedRows(await loadBoard(api));
  const row = rows.find((r) => r.id === "NOT-0001")!;
  assert.equal(rows[0].id, "NOT-0001", "the most recently finished first");
  assert.equal(row.status, "closed", "the status is the last event");
  assert.equal(row.outcome, "credit_approved");
  assert.equal(row.decidedBy, "diego");
  // the seed opened at 09:00Z; the close is at 12:00Z
  assert.equal(row.timeToCloseMs, 180 * MIN);
  assert.equal(row.deadline, "met");
  assert.equal(rows.find((r) => r.id === "NOT-0002"), undefined, "an open case is not in the Closed tab");
});

// --- loading ---------------------------------------------------------------------------------------------------------

test("spec 08 AC-07: live rows are read once more for events and the api's countdown; a failed read keeps the summary", async () => {
  const summary = (id: string): BoardCase => bc({ id, deadline: dl({ daysLeft: null }) });
  const reads: string[] = [];
  const client = {
    listCases: async () => [summary("NOT-0001"), summary("NOT-0002")],
    getConsoleCase: async (id: string) => {
      reads.push(id);
      if (id === "NOT-0002") throw new Error("UNAVAILABLE");
      return { ...summary(id), deadline: dl({ daysLeft: 1 }), events: [ev("case_opened", "2026-10-05T15:00:00Z")], openedAt: "2026-10-05T15:00:00Z", mode: "live" } as unknown as ConsoleCase;
    },
  };
  const board = await loadBoard(client);
  assert.deepEqual(reads.sort(), ["NOT-0001", "NOT-0002"]);
  assert.equal(slaOf(board[0], "en").level, "amber");
  assert.equal(board[0].mode, "live");
  assert.equal(slaOf(board[1], "en").level, "unknown", "no countdown read: the light does not guess");
});
