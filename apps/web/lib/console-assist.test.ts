// The assisted case view of the console (spec 08 assisted console; spec 18 T5 AC-09, AC-11 and T5b AC-06): the mock
// answers the api lane's shapes, the live client calls the analyst routes, and every enum reads as words.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { createApi } from "./api.ts";
import { consoleActions } from "./console-actions.ts";
import { type CaseContext, createLiveConsoleApi, createMockConsoleApi, storedAnalystToken } from "./console-api.ts";
import {
  auditStateShort,
  cardLabel,
  merchantLabel,
  noOpinionReasonLabel,
  auditCheckLabel,
  auditState,
  auditStateLabel,
  callStatusLabel,
  cardStatusLabel,
  caseStatusLabel,
  channelLabel,
  countdown,
  formatAmount,
  formatDay,
  labelTables,
  notificationEventLabel,
  outcomeLabel,
  plain,
  proposalAction,
  proposalElsewhere,
  proposalWords,
  stepperSteps,
  verdictLabel,
} from "./console-view.ts";
import { LOCALES, translator } from "./i18n.ts";
import { MockStore } from "./mock/store.ts";

const src = (p: string) => readFileSync(new URL(p, import.meta.url), "utf-8");
const TAG = /\[(simulated|assumption|data|external|projected)\]/;

function mockConsole() {
  const store = new MockStore(null);
  store.analystLogin("diego", "x");
  const api = createApi(store, { delayMs: 0 });
  return { api, console: createMockConsoleApi({ getCase: (id) => api.getConsoleCase(id) }) };
}

test("spec 08 AC-11: the mock context has the api lane's shape and one highlighted disputed charge within ±30 days", async () => {
  const { console: c } = mockConsole();
  const ctx: CaseContext = await c.getContext("NOT-0001");
  assert.deepEqual(Object.keys(ctx).sort(), ["calls", "cards", "notifications", "previous_cases", "transactions"]);
  assert.equal(ctx.transactions.filter((t) => t.disputed).length, 1);
  const disputed = ctx.transactions.find((t) => t.disputed)!;
  assert.equal(disputed.amount, 4200);
  assert.equal(disputed.currency, "MXN");
  for (const t of ctx.transactions) {
    const days = Math.abs(Date.parse(t.date) - Date.parse(disputed.date)) / 86_400_000;
    assert.ok(days <= 30, t.date);
    for (const k of ["transaction_id", "date", "amount", "currency", "merchant", "last4", "disputed"]) assert.ok(k in t, k);
  }
  assert.equal(ctx.cards[0].status, "blocked"); // NOT-0001's block was verified
  for (const n of ctx.notifications) for (const k of ["at", "channel", "event", "status"]) assert.ok(k in n, k);
});

test("spec 08 AC-10: the summary carries lines and the deadline with its countdown and a named source link", async () => {
  const { console: c } = mockConsole();
  const s = await c.getSummary("NOT-0001");
  assert.ok(s.lines.length >= 2);
  assert.equal(s.writer, "template");
  assert.ok(s.deadline);
  assert.equal(s.deadline.kind, "credit");
  assert.match(s.deadline.date, /^\d{4}-\d{2}-\d{2}$/);
  assert.equal(typeof s.deadline.days_left, "number");
  assert.match(s.deadline.source_url ?? "", /^https:\/\/www\.banxico\.org\.mx\//);
  assert.ok(s.deadline.source_label && !s.deadline.source_label.startsWith("http"));
  // BR has no business-day count in the mock: no date is invented (POL-CLOCK-UNKNOWN behaviour).
  assert.equal((await c.getSummary("NOT-0002")).deadline, null);
});

test("spec 08 AC-12, spec 18 AC-09 / AC-11: the second opinion is asked, never pre-filled, ties reasons to evidence ids and is labeled advisory", async () => {
  const { console: c } = mockConsole();
  assert.equal(await c.getSecondOpinion("NOT-0001"), null);
  const asked = await c.requestSecondOpinion("NOT-0001");
  const o = asked.opinion;
  assert.ok(o);
  assert.equal(asked.reason, null);
  assert.equal(o.label, "AI second opinion — advisory");
  assert.ok(["agree", "disagree", "uncertain"].includes(o.verdict));
  assert.ok(o.reasons.length > 0 && o.reasons.length <= 5);
  for (const r of o.reasons) assert.ok(r.evidence_ids.length > 0);
  assert.deepEqual(await c.getSecondOpinion("NOT-0001"), o);

  // The panel's title and empty state are UI words in every language (spec 16 AC-06); the api's label is compared.
  const panel = src("../components/console/oversight.tsx");
  assert.ok(panel.includes('ADVISORY_LABEL = "AI second opinion — advisory"'));
  assert.ok(panel.includes('t("console.oversight.advisory")') && panel.includes('t("console.oversight.noOpinion")'));
  assert.equal(translator("en")("console.oversight.advisory"), "AI second opinion — advisory");
  assert.equal(translator("en")("console.oversight.noOpinion"), "No second opinion");
  assert.match(translator("es")("console.oversight.advisory"), /consultiva/);
  assert.match(translator("pt")("console.oversight.advisory"), /consultiva/);
  // Shown after the auditor's facts (AC-09).
  const page = src("../app/console/page.tsx");
  assert.ok(page.indexOf("<AuditChecklist") > 0 && page.indexOf("<AuditChecklist") < page.indexOf("<SecondOpinionPanel"));
});

test("spec 08 AC-12, spec 18 AC-06: the auditor gives A1–A7 with passed, finding or not applicable, each as a word", async () => {
  const { console: c } = mockConsole();
  const a = await c.getAudit("NOT-0002");
  assert.deepEqual(a.checks.map((x) => x.id), ["A1", "A2", "A3", "A4", "A5", "A6", "A7"]);
  assert.equal(typeof a.matches, "boolean");
  assert.equal(auditState({ passed: true }), "passed");
  assert.equal(auditState({ passed: false }), "finding");
  assert.equal(auditState({ passed: null }), "na");
  assert.ok(src("../components/console/oversight.tsx").includes('t("console.oversight.auditorTitle")'));
  assert.equal(translator("en")("console.oversight.auditorTitle"), "The outcome re-derives from the rules");
  for (const loc of LOCALES) {
    for (const id of ["A1", "A2", "A3", "A4", "A5", "A6", "A7"]) assert.ok(labelTables(loc).auditCheck[id], `${loc} ${id}`);
    for (const s of ["passed", "finding", "na"] as const) assert.ok(auditStateLabel(s, loc));
  }
  assert.equal(auditCheckLabel({ id: "A9", name: "notifications_sent" }, "en"), "Notifications sent");
  assert.equal(auditStateLabel("na", "es"), "No aplica");
  // The api's status wins: A4 and A5 come as not_applicable with passed null, shown "n/a", never as a failure.
  assert.equal(auditState({ status: "not_applicable", passed: null }), "na");
  assert.equal(auditState({ status: "finding", passed: false }), "finding");
  assert.equal(auditStateShort("na", "en"), "n/a");
  for (const id of ["A4", "A5"]) assert.equal(auditState(a.checks.find((x) => x.id === id)!), "na");
  assert.equal(a.matches, true);
});

test("spec 08 AC-14: the status stepper marks done, current and upcoming for every status", () => {
  const states = (s: Parameters<typeof stepperSteps>[0]) => stepperSteps(s, "en").map((x) => x.state).join(",");
  assert.equal(states("new"), "current,upcoming,upcoming,upcoming");
  assert.equal(states("verification"), "done,current,upcoming,upcoming");
  assert.equal(states("review"), "done,current,upcoming,upcoming");
  assert.equal(states("resolved"), "done,done,current,upcoming");
  assert.equal(states("closed"), "done,done,done,done");
  assert.equal(stepperSteps("verification", "en")[1].label, "Verification");
  assert.equal(stepperSteps("review", "en")[1].label, "Review");
  assert.equal(stepperSteps("new", "en")[1].label, "Verification or review");
  assert.equal(stepperSteps("resolved", "en", { review: true })[1].label, "Review");
  // spec 16 AC-06: the same steps in the UI language
  assert.deepEqual(stepperSteps("new", "es").map((x) => x.label), ["Nuevo", "Verificación o revisión", "Resuelto", "Cerrado"]);
  assert.deepEqual(stepperSteps("review", "pt").map((x) => x.label), ["Novo", "Revisão", "Resolvido", "Encerrado"]);
});

test("spec 08 AC-10: the deadline countdown uses the inbox thresholds and never color alone", () => {
  assert.deepEqual(countdown({ days_left: 5 }, "en"), { level: "green", text: "5 days left" });
  assert.deepEqual(countdown({ days_left: 1 }, "en"), { level: "amber", text: "1 day left" });
  assert.deepEqual(countdown({ days_left: 0 }, "en"), { level: "red", text: "Due today" });
  assert.deepEqual(countdown({ days_left: -2 }, "en"), { level: "red", text: "Past due by 2 days" });
  assert.equal(countdown({ days_left: null }, "en").level, "unknown");
  // spec 16 AC-06: same levels, words in the UI language
  assert.deepEqual(countdown({ days_left: 5 }, "es"), { level: "green", text: "Quedan 5 días" });
  assert.deepEqual(countdown({ days_left: 1 }, "pt"), { level: "amber", text: "Falta 1 dia" });
  assert.equal(countdown({ days_left: -1 }, "es").text, "Vencido hace 1 día");
});

test("spec 08 AC-13: the copilot proposal maps to an offered analyst action, or says why not", () => {
  const live = consoleActions("review", "live");
  assert.equal(proposalAction({ action: "approve_credit" }, live)?.action, "approve_credit");
  assert.equal(proposalAction({ action: "close_without_action" }, live)?.action, "resolve");
  assert.equal(proposalAction({ action: "request_customer_info" }, live), null);
  assert.equal(proposalAction({ action: "approve_credit" }, consoleActions("closed", "live")), null);
  const w = proposalWords({ action: "approve_credit", rationale: "Proposal only [simulated]; a person decides.", requires_human: true }, "en");
  assert.equal(w.title, "Approve provisional credit");
  assert.ok(!TAG.test(w.text));
  assert.equal(proposalWords({ action: "approve_credit", rationale: "r", requires_human: true, explanation: "Plain words." }, "en").text, "Plain words.");
  assert.equal(proposalWords({ action: "approve_credit", rationale: "r", requires_human: true }, "es").title, "Aprobar el crédito provisional");
  assert.match(proposalElsewhere("approve_block", "pt"), /ligação/);
  assert.equal(proposalElsewhere("something_new", "en"), "No console action carries out this proposal.");
  // The proposal only proposes: its button opens a confirm step before the action runs.
  const s = src("../components/console/copilot-proposal.tsx");
  assert.ok(s.includes('t("console.proposal.confirmAria")') && s.includes('t("console.proposal.title")'));
  assert.equal(translator("en")("console.proposal.confirmAria"), "Confirm the decision");
  assert.match(translator("en")("console.proposal.title"), /you decide/);
});

test("spec 08 AC-14: no bracket tags on the console screens or in what the mock shows", async () => {
  for (const f of ["agent-summary", "case-header", "copilot-proposal", "customer-history", "oversight"]) {
    assert.ok(!TAG.test(src(`../components/console/${f}.tsx`)), f);
  }
  assert.ok(!TAG.test(src("../app/console/page.tsx")));
  assert.equal(plain("transaction match [simulated]"), "transaction match");
  const { console: c } = mockConsole();
  const all = JSON.stringify([await c.getSummary("NOT-0001"), await c.getAudit("NOT-0001"), (await c.requestSecondOpinion("NOT-0001")).opinion]);
  assert.ok(!TAG.test(all));
});

test("spec 08 AC-14, spec 16 AC-06: every enum of the console routes has a human label in every language, and unknown values read as words", () => {
  const tables = ["verdict", "auditCheck", "auditState", "outcome", "channel", "delivery", "notificationEvent", "cardStatus", "product", "callStatus", "deadlineKind", "writer"] as const;
  for (const loc of LOCALES) {
    const all = labelTables(loc);
    for (const name of tables) {
      assert.deepEqual(Object.keys(all[name]).sort(), Object.keys(labelTables("en")[name]).sort(), `${loc}.${name}`);
      for (const [k, v] of Object.entries(all[name])) assert.ok(v && !v.includes("_"), `${loc}.${name}.${k}`);
    }
    for (const v of ["agree", "disagree", "uncertain"] as const) assert.ok(all.verdict[v]);
    for (const s of ["new", "verification", "review", "resolved", "closed"] as const) assert.ok(!caseStatusLabel(s, loc).includes("_"));
    for (const fn of [verdictLabel, outcomeLabel, channelLabel, notificationEventLabel, cardStatusLabel, callStatusLabel]) {
      assert.ok(!fn("some_new_value", loc).includes("_"));
    }
  }
  assert.equal(channelLabel("in_app", "en"), "In the app");
  assert.equal(channelLabel("in_app", "es"), "En la app");
  assert.equal(channelLabel("in_app", "pt"), "No app");
  assert.equal(outcomeLabel(null, "en"), "—");
});

test("spec 08 AC-14, spec 16 AC-06: dates and amounts per language (es-MX, pt-BR, en-US) with the currency code", () => {
  assert.match(formatDay("es", "2026-06-05"), /^5 jun\.? 2026$/);
  assert.equal(formatDay("es", "2026-06-05T23:30:00Z"), formatDay("es", "2026-06-05"));
  assert.match(formatDay("pt", "2026-06-05"), /^5 de jun\.? de 2026$/);
  assert.match(formatDay("en", "2026-06-05"), /^Jun 5, 2026$/);
  assert.equal(formatAmount("es", 4200, "MXN"), "4,200.00 MXN");
  assert.equal(formatAmount("pt", 4200, "BRL"), "4.200,00 BRL");
  assert.equal(formatAmount("en", 4200, "MXN"), "4,200.00 MXN");
});

test("spec 08 AC-10 to AC-12: the live client calls the analyst routes with the id token and reads 404 or 204 as no opinion", async () => {
  const calls: { url: string; method: string; auth: string }[] = [];
  const replies: Record<string, Response> = {
    "GET /api/console/cases/K-1/second-opinion": new Response("{}", { status: 404 }),
    "POST /api/console/cases/K-1/second-opinion": new Response(null, { status: 204, headers: { "X-No-Opinion-Reason": "budget" } }),
    "GET /api/console/cases/K-1/audit": Response.json({ checks: [], rederived_outcome: "human_review", matches: true }),
    "GET /api/console/cases/K-1/summary": new Response(JSON.stringify({ code: "DENY", message: "no" }), { status: 403 }),
  };
  const live = createLiveConsoleApi({
    token: () => "tok",
    fetch: (async (url: string, init: RequestInit) => {
      const method = init.method ?? "GET";
      calls.push({ url, method, auth: (init.headers as Record<string, string>).Authorization });
      return replies[`${method} ${url}`];
    }) as typeof fetch,
  });
  assert.equal(await live.getSecondOpinion("K-1"), null);
  assert.deepEqual(await live.requestSecondOpinion("K-1"), { opinion: null, reason: "budget" });
  assert.equal((await live.getAudit("K-1")).matches, true);
  await assert.rejects(live.getSummary("K-1"), (e: Error & { code?: string }) => e.code === "DENY");
  assert.ok(calls.every((c) => c.auth === "Bearer tok"));

  const noToken = createLiveConsoleApi({ token: () => null, fetch: (async () => Response.json({})) as unknown as typeof fetch });
  await assert.rejects(noToken.getContext("K-1"), (e: Error & { code?: string }) => e.code === "UNAUTHORIZED");
});

test("spec 08 AC-15: the conversation tab is a read-only transcript next to the handoff card, which stays first", async () => {
  const { console: c } = mockConsole();
  const conv = await c.getConversation("NOT-0002");
  assert.equal(conv.threads.length, 1);
  const t = conv.threads[0];
  for (const k of ["thread_id", "session_started_at", "messages"]) assert.ok(k in t, k);
  assert.ok(t.messages.some((m) => m.role === "customer") && t.messages.some((m) => m.role === "agent"));
  for (const m of t.messages) assert.ok(["customer", "agent"].includes(m.role) && m.text && m.at);
  assert.match(t.messages.find((m) => m.role === "agent")!.text, /Olá/); // NOT-0002 is a Portuguese case

  const view = src("../components/console/conversation-transcript.tsx");
  assert.ok(view.includes('from "@/components/chat/markdown"')); // the chat's safe markdown, reused
  assert.ok(view.includes('from "@/components/ai-elements/conversation"'));
  assert.ok(!/onSend|<Input|<textarea|Suggestion/.test(view)); // nothing can be sent from here
  const page = src("../app/console/page.tsx");
  assert.ok(page.indexOf('value="handoff"') < page.indexOf('value="conversation"'));
  assert.ok(page.includes('useState<{ caseId: string; view: string }>({ caseId: c.id, view: "handoff" })'));

  const live = createLiveConsoleApi({
    token: () => "tok",
    fetch: (async (url: string) =>
      url === "/api/console/cases/K-1/conversation" ? Response.json({ threads: [] }) : new Response(null, { status: 500 })) as unknown as typeof fetch,
  });
  assert.deepEqual(await live.getConversation("K-1"), { threads: [] });
  // 503: Platform cannot search the threads; the tab says so calmly instead of an error.
  const down = createLiveConsoleApi({
    token: () => "tok",
    fetch: (async () => Response.json({ code: "UNAVAILABLE" }, { status: 503 })) as unknown as typeof fetch,
  });
  assert.deepEqual(await down.getConversation("K-1"), { threads: [], unavailable: true });
  assert.ok(src("../components/console/conversation-transcript.tsx").includes("console.transcript.unavailableTitle"));
  assert.equal(translator("en")("console.transcript.unavailableTitle"), "Conversation not available right now");
});

test("spec 08 AC-12, spec 18 AC-11: every no-opinion reason of the api reads as one calm line", () => {
  assert.equal(noOpinionReasonLabel("budget", "en"), "Not available: daily budget reached");
  for (const r of ["no_handoff", "budget", "timeout", "error", "unavailable"]) {
    assert.match(noOpinionReasonLabel(r, "en"), /^Not available: /);
    for (const loc of LOCALES) assert.ok(noOpinionReasonLabel(r, loc));
  }
  assert.equal(noOpinionReasonLabel("something_new", "en"), labelTables("en").noOpinionReason.error);
  assert.equal(noOpinionReasonLabel(null, "en"), labelTables("en").noOpinionReason.error);
  assert.equal(verdictLabel("uncertain", "en"), "Not sure about the proposal");
});

test("spec 08 AC-11: a transaction with no merchant or no card renders words, never null", () => {
  assert.equal(merchantLabel(null, "en"), "Unknown merchant");
  assert.equal(merchantLabel(null, "es"), "Comercio desconocido");
  assert.equal(merchantLabel("", "en"), "Unknown merchant");
  assert.equal(merchantLabel("Farmacia Plaza", "en"), "Farmacia Plaza");
  assert.equal(cardLabel(null), "—");
  assert.equal(cardLabel("4417"), "•••• 4417");
  const view = src("../components/console/customer-history.tsx");
  assert.ok(view.includes("merchantLabel(t.merchant, locale)") && view.includes("cardLabel(t.last4)"));
  // Free text from the api (the re-derived outcome) is shown as written: dates and ids keep their hyphens.
  assert.equal(outcomeLabel("zone high · credit by 2026-06-05", "en"), "zone high · credit by 2026-06-05");
  assert.equal(outcomeLabel("approve_block", "en"), "Card block approved");
});

test("spec 08 AC-10 to AC-12: the analyst token is read from lib/live.ts's session entry, never past its expiry", () => {
  const store = (v: unknown) => ({ getItem: () => JSON.stringify(v) });
  assert.equal(storedAnalystToken(store({ analyst: { token: "t", expiresAt: Date.now() + 60_000 } })), "t");
  assert.equal(storedAnalystToken(store({ analyst: { token: "t", expiresAt: Date.now() - 1 } })), null);
  assert.equal(storedAnalystToken(store({ analyst: null })), null);
  assert.ok(src("./live.ts").includes('const STORAGE_KEY = "nickoftime.live.v1"'));
});
