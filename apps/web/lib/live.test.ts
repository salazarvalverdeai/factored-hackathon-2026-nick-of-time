// Offline checks for the live client (spec 16 AC-03, Task 5). A fake `fetch` plays the spec 05 api and Cognito, so no
// network is used. Each test cites the criterion it covers; the api's own rules are tested in tests/test_spec05_*.py.
import assert from "node:assert/strict";
import test from "node:test";
import { consoleActions } from "./console-actions.ts";
import { createLiveApi, readSse, replyFromTurn } from "./live.ts";
import { ApiError } from "./mock/store.ts";

interface Call {
  method: string;
  url: string;
  headers: Record<string, string>;
  body: unknown;
}

type Handler = (call: Call) => Response | Promise<Response>;

const NOW = Date.parse("2026-10-05T15:00:00Z");

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function sse(...events: [string, unknown][]): Response {
  const text = events.map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join("");
  return new Response(text, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

/** An api whose routes are `"METHOD /path"` keys; every call is recorded. Unknown routes answer 404. */
function setup(routes: Record<string, Handler>, options: { cognito?: boolean; clock?: { t: number } } = {}) {
  const calls: Call[] = [];
  const clock = options.clock ?? { t: NOW };
  const fetchImpl = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const call: Call = {
      method: init?.method ?? "GET",
      url,
      headers: (init?.headers ?? {}) as Record<string, string>,
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
    };
    calls.push(call);
    const path = url.replace("http://api.test", "");
    const handler = routes[`${call.method} ${path}`];
    if (!handler) return jsonResponse({ code: "NOT_FOUND", message: `no route ${call.method} ${path}` }, 404);
    return handler(call);
  }) as typeof fetch;
  const data = new Map<string, string>();
  const api = createLiveApi({
    fetch: fetchImpl,
    baseUrl: "http://api.test",
    storage: { getItem: (k) => data.get(k) ?? null, setItem: (k, v) => void data.set(k, v), removeItem: (k) => void data.delete(k) },
    now: () => clock.t,
    cognito: options.cognito === false ? null : { region: "us-east-2", clientId: "client-1" },
    newId: (() => {
      let n = 0;
      return () => `id-${++n}`;
    })(),
  });
  return { api, calls, clock };
}

const CUSTOMERS = [
  { customer_id: "C-1", display_name: "Ana Pérez", country: "MX", segment: "mass", scenario: "unrecognized", language: "es" },
  { customer_id: "C-2", display_name: "João Silva", country: "BR", segment: "premium", scenario: "wrongful", language: "pt" },
];

const SESSION_ROUTES: Record<string, Handler> = {
  "GET /api/demo/customers": () => jsonResponse(CUSTOMERS),
  "POST /api/sessions": () => jsonResponse({ session_id: "S-1", mode: "live", today: "2026-10-05", otp_demo: "123456", expires_at: "2026-10-05T15:15:00Z" }, 201),
  "POST /api/sessions/S-1/verify": (c) =>
    (c.body as { otp: string }).otp === "123456"
      ? jsonResponse({ verified: true, expires_at: "2026-10-05T15:15:00Z" })
      : jsonResponse({ code: "UNAUTHENTICATED", message: "Wrong code" }, 401),
};

async function customerLogin(api: ReturnType<typeof setup>["api"]) {
  const otp = await api.requestOtp("C-1");
  return api.verifyOtp(otp);
}

const TURN = {
  reply: "Caso NOT-0001 abierto y verificado.",
  language: "es",
  decision: "block_and_open_case",
  progress: [
    { step: "open_case", label: "Abriendo tu caso", state: "verified" },
    { step: "block_card", label: "Bloqueando la tarjeta", state: "requested" },
  ],
  actions: [{ tool: "open_case", state: "verified", verification_id: "V-0123456789AB" }],
  suggestions: [
    { id: "view", label: "Ver mi caso", kind: "link", href: "/case/NOT-0001" },
    { id: "call", label: "Que me llame una persona", kind: "action", action: { type: "request_call" } },
  ],
  receipt: {
    case_id: "NOT-0001",
    language: "es",
    issued_at: "2026-10-05T15:01:00Z",
    verified_facts: [{ fact: "Cargo de 4,200 MXN en TIENDA X", source_id: "T-1" }],
    actions: [{ label: "Caso abierto", state: "verified", verification_id: "V-0123456789AB" }],
    deadline: { country: "MX", product: "debit", credit_deadline: "2026-10-07", ruling_deadline: null, deadline_source: "Banxico 3/2012", source_url: "https://example.org/b", verified_on: "2026-09-30" },
    what_ai_did: "Lo que hizo el asistente: abrió tu caso.",
    what_a_person_does: "Lo que sigue: una persona revisa tu caso.",
    case_url: "https://evil.example/phish",
  },
  guardrails_triggered: [],
  denials: [],
};

// --- spec 16 AC-03: live mode answers from the api and never invents data ----------------------------------------

test("spec 16 AC-03: live mode answers the api's error instead of faking data", async () => {
  const { api } = setup({ "GET /api/demo/customers": () => jsonResponse({ code: "UNAVAILABLE", message: "down" }, 503) });
  assert.equal(api.mode, "live");
  await assert.rejects(api.listDemoCustomers(), (e: unknown) => e instanceof ApiError && e.code === "UNAVAILABLE" && e.status === 503);
});

test("spec 16 AC-03: a network failure is an UNAVAILABLE error, not an empty list", async () => {
  const api = createLiveApi({ baseUrl: "http://api.test", storage: null, fetch: (async () => { throw new TypeError("fetch failed"); }) as typeof fetch });
  await assert.rejects(api.listDemoCustomers(), (e: unknown) => e instanceof ApiError && e.code === "UNAVAILABLE");
});

test("spec 16 AC-03: the demo picker comes from the api and carries no score", async () => {
  const { api } = setup(SESSION_ROUTES);
  const list = await api.listDemoCustomers();
  assert.equal(list.length, 2);
  assert.ok(list.every((c) => !("fraudScore" in c) && !("score" in c)));
});

// --- customer session (spec 05 AC-01, AC-09) -----------------------------------------------------------------------

test("spec 05 AC-01: the session opens with the code and lasts until the api's expiry", async () => {
  const { api, calls } = setup(SESSION_ROUTES);
  const session = await customerLogin(api);
  assert.equal(session.customerId, "C-1");
  assert.equal(session.expiresAt, Date.parse("2026-10-05T15:15:00Z"));
  assert.deepEqual(api.session.getSnapshot().customerSession, session);
  assert.deepEqual(calls.find((c) => c.url.endsWith("/api/sessions"))?.body, { customer_id: "C-1" });
});

test("spec 05 AC-01: a wrong code does not open a session", async () => {
  const { api } = setup(SESSION_ROUTES);
  await api.requestOtp("C-1");
  await assert.rejects(api.verifyOtp("000000"), (e: unknown) => e instanceof ApiError && e.status === 401);
  assert.equal(api.session.getSnapshot().customerSession, null);
});

test("spec 05 AC-01: verifying without asking for a code first is refused before any request", async () => {
  const { api, calls } = setup(SESSION_ROUTES);
  await assert.rejects(api.verifyOtp("123456"), (e: unknown) => e instanceof ApiError && e.code === "UNAUTHORIZED");
  assert.equal(calls.length, 0);
});

test("spec 05 AC-01: SESSION_EXPIRED from the api marks the session expired", async () => {
  const { api } = setup({
    ...SESSION_ROUTES,
    "GET /api/cases/NOT-0001": () => jsonResponse({ code: "SESSION_EXPIRED", message: "Session expired: verify again" }, 401),
  });
  await customerLogin(api);
  await assert.rejects(api.getCase("NOT-0001"), (e: unknown) => e instanceof ApiError && e.code === "SESSION_EXPIRED");
  assert.ok(api.session.getSnapshot().customerSession!.expiresAt <= NOW, "the page sees an expired session");
});

test("spec 05 AC-01: chat after the session ran out does not call the agent", async () => {
  const clock = { t: NOW };
  const { api, calls } = setup(SESSION_ROUTES, { clock });
  await customerLogin(api);
  clock.t = Date.parse("2026-10-05T15:16:00Z");
  const before = calls.length;
  await assert.rejects(api.chat("hola"), (e: unknown) => e instanceof ApiError && e.code === "SESSION_EXPIRED");
  assert.equal(calls.length, before);
});

test("spec 05 AC-09: another customer's case answers DENY and the page gets the api's words", async () => {
  const { api } = setup({
    ...SESSION_ROUTES,
    "GET /api/cases/NOT-9999": () => jsonResponse({ code: "DENY", message: "The case does not belong to this customer" }, 403),
  });
  await customerLogin(api);
  await assert.rejects(api.getCase("NOT-9999"), (e: unknown) => e instanceof ApiError && e.code === "DENY" && e.status === 403);
});

// --- the agent (spec 05 AC-05, spec 01 §6.4, spec 04 AC-17) ----------------------------------------------------------

test("spec 05 AC-05: a turn sends only the customer's text; the customer, language and mode come from the session", async () => {
  const { api, calls } = setup({
    ...SESSION_ROUTES,
    "POST /api/agent/threads": () => jsonResponse({ thread_id: "th-1" }),
    "POST /api/agent/threads/th-1/runs/stream": () => sse(["turn", TURN]),
  });
  await customerLogin(api);
  await api.chat("No reconozco un cargo de 4,200 pesos");
  const run = calls.find((c) => c.url.endsWith("/runs/stream"))!;
  assert.deepEqual(run.body, { input: { messages: [{ role: "user", content: "No reconozco un cargo de 4,200 pesos" }] } });
  assert.ok(!JSON.stringify(run.body).match(/customer|language|mode|arm|session/i));
  assert.ok(!JSON.stringify(calls).match(/LANGSMITH|x-api-key/i), "the Platform key never reaches the browser");
});

test("spec 05 AC-05: the thread is created once per session", async () => {
  const { api, calls } = setup({
    ...SESSION_ROUTES,
    "POST /api/agent/threads": () => jsonResponse({ thread_id: "th-1" }),
    "POST /api/agent/threads/th-1/runs/stream": () => sse(["turn", TURN]),
  });
  await customerLogin(api);
  await api.chat("hola");
  await api.chat("otra vez");
  assert.equal(calls.filter((c) => c.url.endsWith("/api/agent/threads")).length, 1);
});

test("spec 01 §6.4: a chip press sends its action and no text", async () => {
  const { api, calls } = setup({
    ...SESSION_ROUTES,
    "POST /api/agent/threads": () => jsonResponse({ thread_id: "th-1" }),
    "POST /api/agent/threads/th-1/runs/stream": () => sse(["turn", TURN]),
  });
  await customerLogin(api);
  await api.chat("Que me llame una persona", { action: { type: "request_call" } });
  const run = calls.find((c) => c.url.endsWith("/runs/stream"))!;
  assert.deepEqual(run.body, { input: { messages: [], action: { type: "request_call" } } });
});

test("spec 04 AC-17: progress labels reach the page as the run goes, then the turn", async () => {
  const labels: string[] = [];
  const { api } = setup({
    ...SESSION_ROUTES,
    "POST /api/agent/threads": () => jsonResponse({ thread_id: "th-1" }),
    "POST /api/agent/threads/th-1/runs/stream": () =>
      sse(["progress", { step: "open_case", label: "Abriendo tu caso", state: "in_progress" }], ["turn", TURN]),
  });
  await customerLogin(api);
  const reply = await api.chat("hola", { onProgress: (p) => labels.push(p.label) });
  assert.deepEqual(labels, ["Abriendo tu caso"]);
  assert.equal(reply.text, TURN.reply);
});

test("spec 07 AC-08: a live turn with no actions fills the trace from the streamed labels and the decision", async () => {
  const { api } = setup({
    ...SESSION_ROUTES,
    "POST /api/agent/threads": () => jsonResponse({ thread_id: "th-1" }),
    "POST /api/agent/threads/th-1/runs/stream": () =>
      sse(
        ["progress", { step: "reading_message", label: "Leyendo tu mensaje…", state: "in_progress" }],
        ["progress", { step: "searching", label: "Buscando el cargo…", state: "in_progress" }],
        ["turn", { ...TURN, decision: "ask", progress: [], actions: [], receipt: null, guardrails_triggered: ["G-IN-03"] }],
      ),
  });
  await customerLogin(api);
  const reply = await api.chat("No reconozco un cargo");
  assert.deepEqual(reply.trace.map((t) => t.step), ["reading_message", "searching", "decide"]);
  assert.deepEqual(reply.guardrails, ["G-IN-03"]);
});

test("spec 04 AC-17: a stream that ends without a turn is an error, not a made-up answer", async () => {
  const { api } = setup({
    ...SESSION_ROUTES,
    "POST /api/agent/threads": () => jsonResponse({ thread_id: "th-1" }),
    "POST /api/agent/threads/th-1/runs/stream": () => sse(["progress", { step: "x", label: "…", state: "in_progress" }]),
  });
  await customerLogin(api);
  await assert.rejects(api.chat("hola"), (e: unknown) => e instanceof ApiError && e.code === "UNAVAILABLE");
});

test("spec 05 AC-18: the abuse guard's 429 reaches the page with its calm message", async () => {
  const { api } = setup({
    ...SESSION_ROUTES,
    "POST /api/agent/threads": () => jsonResponse({ code: "RATE_LIMITED", message: "Hiciste muchas consultas; vuelve a intentarlo más tarde." }, 429),
  });
  await customerLogin(api);
  await assert.rejects(api.chat("hola"), (e: unknown) => e instanceof ApiError && e.code === "RATE_LIMITED" && /vuelve/.test(e.message));
});

test("constitution #4: only a verified step is shown as verified; a requested one is only accepted", () => {
  const reply = replyFromTurn(TURN as never);
  assert.deepEqual(reply.trace.slice(0, 2).map((t) => [t.step, t.kind]), [["open_case", "verified"], ["block_card", "accepted"]]);
  assert.deepEqual(reply.trace.filter((t) => t.step === "verify").map((t) => t.kind), ["verified"], "1 of 1 action verified");
  const none = replyFromTurn({ ...TURN, progress: [{ step: "block_card", label: "x", state: "not_confirmed" }], receipt: null } as never);
  assert.equal(none.trace[0].kind, "not_confirmed");
});

test("spec 04 AC-29: chips keep their action or link; the receipt links to our own case page and shows tool facts only", () => {
  const reply = replyFromTurn(TURN as never);
  assert.deepEqual(reply.suggestions?.map((s) => [s.label, s.href, s.action?.type]), [
    ["Ver mi caso", "/case/NOT-0001", undefined],
    ["Que me llame una persona", undefined, "request_call"],
  ]);
  assert.equal(reply.receipt?.case_url, "/case/NOT-0001", "a host sent by the api is never linked");
  assert.deepEqual(reply.receipt?.facts, ["Cargo de 4,200 MXN en TIENDA X"]);
  assert.match(reply.receipt!.deadline_text, /2026-10-07/);
  assert.match(reply.receipt!.deadline_text, /Banxico 3\/2012/);
});

test("spec 01 §6.7: a receipt with no verified deadline says so instead of inventing one", () => {
  const reply = replyFromTurn({ ...TURN, receipt: { ...TURN.receipt, deadline: null } } as never);
  assert.match(reply.receipt!.deadline_text, /plazo legal verificado/);
  assert.equal(reply.receipt!.deadline.creditDeadline, null);
});

test("spec 04 AC-03: a denial shows as DENY with the guardrail, and the reply stays the api's text", () => {
  const reply = replyFromTurn({ ...TURN, receipt: null, decision: "deny", denials: [{ guardrail_id: "G-IN-01", detail: "injection" }] } as never);
  assert.equal(reply.deny, true);
  assert.equal(reply.trace.at(-1)?.kind, "deny");
});

test("the SSE reader splits events across chunks and drops a malformed one", async () => {
  const chunks = ["event: progress\ndata: {\"a\":", "1}\n\nevent: turn\nda", "ta: {\"b\":2}\n\nevent: x\ndata: not json\n\n"];
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const c of chunks) controller.enqueue(new TextEncoder().encode(c));
      controller.close();
    },
  });
  const out: unknown[] = [];
  for await (const e of readSse(body)) out.push(e);
  assert.deepEqual(out, [{ event: "progress", data: { a: 1 } }, { event: "turn", data: { b: 2 } }]);
});

// --- demo-mode start screen (spec 07 §8, D-068; spec 05 AC-14 to AC-20) ----------------------------------------------

const DEMO_ROUTES: Record<string, Handler> = {
  "GET /api/demo/scenarios?language=es&country=MX": () => jsonResponse([{ scenario_id: "SCN-MX-1", title: "Cargo no reconocido", country: "MX", language: "es", segment: "mass", customer_name: "Ana", cases: [], tags: [] }]),
  "GET /api/demo/scenarios?language=pt": () => jsonResponse([]),
  "POST /api/sessions": () => jsonResponse({ session_id: "S-9", mode: "live", today: "2026-10-05", otp_demo: "654321", expires_at: "2026-10-05T15:15:00Z" }, 201),
  "POST /api/sessions/S-9/verify": () => jsonResponse({ verified: true, expires_at: "2026-10-05T15:15:00Z" }),
};

async function demoLogin(api: ReturnType<typeof setup>["api"], name?: string) {
  const otp = await api.startDemoSession({ displayName: name, language: "es", country: "MX", scenario: "SCN-MX-1" });
  return api.verifyOtp(otp);
}

test("spec 07 AC-01: the scenario cards come from the api for a language and a country, with no customer id", async () => {
  const { api, calls } = setup(DEMO_ROUTES);
  const list = await api.listScenarios({ language: "es", country: "MX" });
  assert.deepEqual(list.map((s) => [s.scenario_id, s.customer_name]), [["SCN-MX-1", "Ana"]]);
  assert.ok(!JSON.stringify(list).match(/customer_id|score|zone/));
  assert.equal(calls[0].url, "http://api.test/api/demo/scenarios?language=es&country=MX");
  assert.deepEqual(await api.listScenarios({ language: "pt" }), []);
});

test("spec 07 §8.5: a demo session is opened by scenario and the body never carries a customer id", async () => {
  const { api, calls } = setup(DEMO_ROUTES);
  const otp = await api.startDemoSession({ displayName: "  Ana  ", language: "es", country: "MX", scenario: "SCN-MX-1" });
  assert.equal(otp, "654321");
  assert.deepEqual(calls[0].body, { display_name: "Ana", language: "es", country: "MX", scenario: "SCN-MX-1" });
  assert.ok(!JSON.stringify(calls[0].body).includes("customer_id"));
});

test("spec 07 §8.1: with no name the request carries none, and 'assign me one' sends auto", async () => {
  const { api, calls } = setup(DEMO_ROUTES);
  await api.startDemoSession({ displayName: "   ", language: "pt", scenario: "auto" });
  assert.deepEqual(calls[0].body, { language: "pt", scenario: "auto" });
});

test("spec 07 §8.1: the api's 422 message for a name is what the page shows", async () => {
  const { api } = setup({ ...DEMO_ROUTES, "POST /api/sessions": () => jsonResponse({ code: "INVALID", message: "Use a plain first name" }, 422) });
  await assert.rejects(api.startDemoSession({ displayName: "x@y.co", language: "es", scenario: "auto" }), (e: unknown) => e instanceof ApiError && e.status === 422 && /plain first name/.test(e.message));
});

test("spec 07 §8.5: after the code the demo session knows its name, language and mode, and no customer", async () => {
  const { api } = setup(DEMO_ROUTES);
  const session = await demoLogin(api, "Ana");
  assert.deepEqual(session, { customerId: "", expiresAt: Date.parse("2026-10-05T15:15:00Z"), language: "es", displayName: "Ana", mode: "live" });
});

test("spec 07 §8.6: the recent charges are read for the verified session, and not before the code", async () => {
  const txs = [{ transaction_id: "T-1", date: "2026-10-05", amount: 99.5, currency: "MXN", merchant: "TIENDA X", last4: "4417", synthetic: true }];
  const { api, calls } = setup({ ...DEMO_ROUTES, "GET /api/sessions/S-9/recent-transactions?limit=10": () => jsonResponse(txs) });
  await assert.rejects(api.listRecentTransactions(), (e: unknown) => e instanceof ApiError && e.code === "SESSION_EXPIRED");
  await api.startDemoSession({ language: "es", scenario: "auto" });
  await assert.rejects(api.listRecentTransactions(), (e: unknown) => e instanceof ApiError, "a session that is not verified has no charges");
  await api.verifyOtp("654321");
  assert.deepEqual(await api.listRecentTransactions(), txs);
  assert.ok(calls.some((c) => c.url.endsWith("/api/sessions/S-9/recent-transactions?limit=10")));
});

test("spec 07 §8.7: a test charge carries only an amount and a store, and the chip list reads again", async () => {
  const { api, calls } = setup({
    ...DEMO_ROUTES,
    "POST /api/sessions/S-9/synthetic-charge": () => jsonResponse({ transaction_id: "T-9", date: "2026-10-05", amount: 1250.5, currency: "MXN", merchant: "TIENDA Y", last4: "4417", synthetic: true, label: "[simulated]" }, 201),
  });
  await demoLogin(api);
  let changes = 0;
  api.subscribe(() => changes++);
  const charge = await api.registerTestCharge(1250.5, "TIENDA Y");
  assert.equal(charge.label, "[simulated]");
  assert.deepEqual(calls.find((c) => c.url.endsWith("/synthetic-charge"))!.body, { amount: 1250.5, merchant: "TIENDA Y" });
  assert.equal(changes, 1, "pages read the list again");
});

test("spec 07 §8.7: a 429 and a 403 reach the page as they are", async () => {
  const { api } = setup({
    ...DEMO_ROUTES,
    "POST /api/sessions/S-9/synthetic-charge": () => jsonResponse({ code: "DENY", message: "One synthetic charge per minute, three per session" }, 429),
  });
  await demoLogin(api);
  await assert.rejects(api.registerTestCharge(10, "TIENDA"), (e: unknown) => e instanceof ApiError && e.status === 429);
  const replay = setup({ ...DEMO_ROUTES, "POST /api/sessions/S-9/synthetic-charge": () => jsonResponse({ code: "DENY", message: "Synthetic charges exist only in a live demo session" }, 403) });
  await demoLogin(replay.api);
  await assert.rejects(replay.api.registerTestCharge(10, "TIENDA"), (e: unknown) => e instanceof ApiError && e.status === 403);
});

test("spec 07 §8.8: a persona answer is a suggested draft, and the chosen charge goes with it only when there is one", async () => {
  const draft = { message: "Mira, no reconozco ese cargo.", source: "template", language: "es", character: "aggressive", transaction_id: "T-1", synthetic: false, suggested: true };
  const { api, calls } = setup({ ...DEMO_ROUTES, "POST /api/demo/persona": () => jsonResponse(draft) });
  await demoLogin(api);
  const out = await api.suggestPersona("aggressive");
  assert.equal(out.source, "template");
  await api.suggestPersona("terse", "T-1");
  const bodies = calls.filter((c) => c.url.endsWith("/api/demo/persona")).map((c) => c.body);
  assert.deepEqual(bodies, [{ character: "aggressive" }, { character: "terse", transaction_id: "T-1" }]);
});

// --- case pages ---------------------------------------------------------------------------------------------------

test("spec 05 AC-09: the case page maps the customer's projection and never asks for internals", async () => {
  const { api } = setup({
    ...SESSION_ROUTES,
    "GET /api/cases/NOT-0001": () =>
      jsonResponse({
        case_id: "NOT-0001", queue_status: "review", credit_deadline: "2026-10-07", ruling_deadline: null, created_at: "2026-10-05T15:01:00Z",
        status_label: "Under review by a person", mode: "live", deadline_countdown_days: 2, deadline_source: "Banxico 3/2012",
        timeline: [{ event_id: "E-1", type: "case_opened", label: "Case opened", created_at: "2026-10-05T15:01:00Z" }],
        channels: { telegram: false, email: true },
      }),
  });
  await customerLogin(api);
  const view = await api.getCase("NOT-0001");
  assert.equal(view.language, "es");
  assert.equal(view.deadline_countdown_days, 2);
  assert.equal(view.mode, "live");
  assert.deepEqual(view.timeline, [{ event_id: "E-1", type: "case_opened", created_at: "2026-10-05T15:01:00Z", status_label: "Case opened" }]);
  assert.deepEqual(view.channels, { telegram: false, email: true });
});

test("spec 13 AC-07: the customer's notifications are one entry per status change, channels together, newest first", async () => {
  const row = (id: string, event: string, channel: string, at: string, status = "sent") => ({
    notification_id: id, case_id: "NOT-0001", event, channel, text: `texto ${event}`, delivery_status: status, created_at: at,
  });
  const { api } = setup({
    ...SESSION_ROUTES,
    "GET /api/notifications": () =>
      jsonResponse([
        row("N-1", "case_opened", "log", "2026-10-05T15:01:00.000Z"),
        row("N-2", "case_opened", "telegram", "2026-10-05T15:01:00.800Z", "failed"),
        row("N-3", "in_review", "log", "2026-10-05T15:30:00Z"),
        { ...row("N-4", "in_review", "log", "2026-10-05T15:31:00Z"), case_id: "NOT-0002" },
      ]),
  });
  await customerLogin(api);
  const list = await api.getNotifications("NOT-0001");
  assert.deepEqual(list.map((n) => [n.status, n.channels.map((c) => `${c.channel}:${c.delivered}`)]), [
    ["review", ["in_app:true"]],
    ["new", ["in_app:true", "telegram:false"]],
  ]);
});

test("spec 13 AC-02: the Telegram link is the api's deep link, and the mock-only simulation is refused", async () => {
  const { api } = setup({
    ...SESSION_ROUTES,
    "POST /api/cases/NOT-0001/channels/telegram": () => jsonResponse({ deep_link: "https://t.me/bot?start=abc", expires_at: "2026-10-05T15:16:00Z" }, 201),
  });
  await customerLogin(api);
  assert.deepEqual(await api.createTelegramLink("NOT-0001"), { token: "", deepLink: "https://t.me/bot?start=abc" });
  await assert.rejects(api.simulateTelegramStart("NOT-0001", ""), (e: unknown) => e instanceof ApiError);
});

test("spec 13 AC-04: an e-mail whose confirmation could not be sent is an error", async () => {
  const { api } = setup({
    ...SESSION_ROUTES,
    "POST /api/cases/NOT-0001/channels/email": () => jsonResponse({ confirmation_sent: false }, 202),
  });
  await customerLogin(api);
  await assert.rejects(api.confirmEmail("NOT-0001", "a@b.co"), (e: unknown) => e instanceof ApiError && e.code === "UNAVAILABLE");
});

test("spec 05 AC-11: in a demo run the channels answer DENY and the page shows why", async () => {
  const { api } = setup({
    ...SESSION_ROUTES,
    "POST /api/cases/NOT-0001/channels/telegram": () => jsonResponse({ code: "DENY", message: "Telegram and e-mail are off in the demo; this page shows every update" }, 403),
  });
  await customerLogin(api);
  await assert.rejects(api.createTelegramLink("NOT-0001"), (e: unknown) => e instanceof ApiError && e.code === "DENY" && /demo/.test(e.message));
});

// --- analyst (spec 05 AC-06, AC-07, AC-10; ADR 0017) ------------------------------------------------------------------

function jwt(claims: Record<string, unknown>): string {
  const part = (o: unknown) => Buffer.from(JSON.stringify(o)).toString("base64url");
  return `${part({ alg: "RS256" })}.${part(claims)}.sig`;
}

const COGNITO = "POST https://cognito-idp.us-east-2.amazonaws.com/";
const ANALYST_ROUTES: Record<string, Handler> = {
  [COGNITO]: (c) => {
    const params = (c.body as { AuthParameters: { USERNAME: string; PASSWORD: string } }).AuthParameters;
    return params.PASSWORD === "good"
      ? jsonResponse({ AuthenticationResult: { IdToken: jwt({ "cognito:username": params.USERNAME, sub: "sub-1" }), ExpiresIn: 3600 } })
      : jsonResponse({ __type: "NotAuthorizedException", message: "Incorrect username or password." }, 400);
  },
  "GET /api/console/settings": () => jsonResponse({ supervised_mode: false, score_provider: "dataset", policies_version: 3 }),
};

async function analystLogin(api: ReturnType<typeof setup>["api"], password = "good") {
  return api.analystLogin("freddy", password);
}

const SUMMARY = {
  case_id: "NOT-0001", country: "MX", queue_status: "review", credit_deadline: "2026-10-07", ruling_deadline: null,
  created_at: "2026-10-05T15:01:00Z", customer_id: "C-1", zone: "high", priority: "high", sla_due_at: null, tags: [],
};

test("spec 05 AC-07: the analyst signs in with Cognito and every console call carries the token", async () => {
  const { api, calls } = setup({ ...ANALYST_ROUTES, "GET /api/console/cases": () => jsonResponse([SUMMARY]), "GET /api/demo/customers": () => jsonResponse(CUSTOMERS) });
  const session = await analystLogin(api);
  assert.deepEqual(session, { username: "freddy", displayName: "freddy" });
  const cognito = calls[0];
  assert.equal((cognito.body as { AuthFlow: string }).AuthFlow, "USER_PASSWORD_AUTH");
  assert.equal(cognito.headers["X-Amz-Target"], "AWSCognitoIdentityProviderService.InitiateAuth");
  const cases = await api.listCases();
  assert.deepEqual(cases.map((c) => [c.id, c.customerName, c.status, c.zone]), [["NOT-0001", "Ana Pérez", "review", "high"]]);
  const consoleCall = calls.find((c) => c.url.endsWith("/api/console/cases"))!;
  assert.match(consoleCall.headers.Authorization, /^Bearer .+\..+\..+$/);
});

test("spec 05 AC-07: a wrong password says so and opens nothing", async () => {
  const { api, calls } = setup(ANALYST_ROUTES);
  await assert.rejects(analystLogin(api, "bad"), (e: unknown) => e instanceof ApiError && e.code === "UNAUTHORIZED" && /Wrong user or password/.test(e.message));
  assert.equal(api.session.getSnapshot().analystSession, null);
  assert.equal(calls.length, 1, "no console call without a token");
});

test("spec 05 AC-07: console calls without a sign-in never reach the api", async () => {
  const { api, calls } = setup(ANALYST_ROUTES);
  await assert.rejects(api.listCases(), (e: unknown) => e instanceof ApiError && e.code === "UNAUTHORIZED");
  assert.equal(calls.length, 0);
});

test("spec 05 AC-07: sign-in is off, with a clear message, when the Cognito client is not configured", async () => {
  const { api } = setup(ANALYST_ROUTES, { cognito: false });
  await assert.rejects(analystLogin(api), (e: unknown) => e instanceof ApiError && e.code === "UNAVAILABLE" && /NEXT_PUBLIC_COGNITO_CLIENT_ID/.test(e.message));
});

test("spec 05 AC-07: a token the api refuses ends the sign-in instead of showing an empty console", async () => {
  const { api } = setup({ ...ANALYST_ROUTES, "GET /api/console/settings": () => jsonResponse({ code: "UNAUTHENTICATED", message: "Invalid analyst token" }, 401) });
  await assert.rejects(analystLogin(api), (e: unknown) => e instanceof ApiError && /same/.test(e.message));
  assert.equal(api.session.getSnapshot().analystSession, null);
});

test("spec 05 AC-07: a 401 on a console call signs the analyst out", async () => {
  const { api } = setup({ ...ANALYST_ROUTES, "GET /api/console/cases": () => jsonResponse({ code: "UNAUTHENTICATED", message: "Invalid analyst token" }, 401) });
  await analystLogin(api);
  await assert.rejects(api.listCases(), (e: unknown) => e instanceof ApiError && e.code === "UNAUTHORIZED");
  assert.equal(api.session.getSnapshot().analystSession, null);
});

test("spec 08 AC-04: the console case keeps the handoff card as the agent wrote it, and says when there is none yet", async () => {
  const detail = (handoff: unknown) => () =>
    jsonResponse({
      case: { ...SUMMARY, deadline_countdown_days: 2, deadline_source: "Banxico 3/2012" },
      handoff,
      events: [{ event_id: "E-1", type: "case_opened", actor: "agent", created_at: "2026-10-05T15:01:00Z" }],
    });
  const full = { case_id: "NOT-0001", language: "es", zone: "high", request: "Cargo no reconocido", verified_facts: [{ fact: "f", source_id: "T-1" }], actions: [], evidence: ["e"], open_questions: [], deadline: { country: "MX", deadline_source: "Banxico 3/2012" }, trace_id: "tr-1", score: 72 };
  const { api } = setup({ ...ANALYST_ROUTES, "GET /api/demo/customers": () => jsonResponse(CUSTOMERS), "GET /api/console/cases/NOT-0001": detail(full), "GET /api/console/cases/NOT-0002": detail({}) });
  await analystLogin(api);
  const a = await api.getConsoleCase("NOT-0001");
  assert.equal(a.handoffEmitted, true);
  assert.equal(a.handoff.request, "Cargo no reconocido");
  assert.equal(a.handoff.score, 72);
  assert.equal(a.deadline.daysLeft, 2, "the countdown is the api's, not the mock's frozen date");
  const b = await api.getConsoleCase("NOT-0002");
  assert.equal(b.handoffEmitted, false);
  assert.equal(b.handoff.request, "");
  assert.deepEqual(b.handoff.verified_facts, []);
});

test("spec 05 AC-10: an analyst action carries its reason and a fresh idempotency key; the actor is the token's", async () => {
  const { api, calls } = setup({
    ...ANALYST_ROUTES,
    "POST /api/cases/NOT-0001/action": () => jsonResponse({ event_id: "E-9", previous_status: "review", new_status: "resolved", notification_id: "N-9" }),
  });
  await analystLogin(api);
  await api.analystAction("NOT-0001", "resolve", { reason: "  confirmed fraud  " });
  const call = calls.find((c) => c.url.endsWith("/action"))!;
  assert.deepEqual(call.body, { case_id: "NOT-0001", actor_id: "console", action: "resolve", reason: "confirmed fraud", idempotency_key: "id-1" });
  await api.analystAction("NOT-0001", "take");
  const keys = calls.filter((c) => c.url.endsWith("/action")).map((c) => (c.body as { idempotency_key: string }).idempotency_key);
  assert.equal(new Set(keys).size, 2, "each action is its own request");
  assert.deepEqual(api.session.getSnapshot().audit.map((a) => [a.actor, a.action, a.target, a.reason]), [
    ["freddy", "take", "NOT-0001", undefined],
    ["freddy", "resolve", "NOT-0001", "confirmed fraud"],
  ]);
});

test("spec 05 AC-04: a transition the queue does not allow is the api's 409 DENY and nothing is logged as done", async () => {
  const { api } = setup({
    ...ANALYST_ROUTES,
    "POST /api/cases/NOT-0001/action": () => jsonResponse({ code: "DENY", policy_id: "POL-QUEUE-TRANSITION", message: "resolve is not allowed from the current status" }, 409),
  });
  await analystLogin(api);
  await assert.rejects(api.analystAction("NOT-0001", "resolve", { reason: "x" }), (e: unknown) => e instanceof ApiError && e.code === "DENY" && e.status === 409);
  assert.deepEqual(api.session.getSnapshot().audit, []);
});

test("spec 05 AC-06: supervised mode is the api's setting; approving then needs a second click and sends nothing before it", async () => {
  const { api, calls } = setup({
    ...ANALYST_ROUTES,
    "PUT /api/console/settings": (c) => jsonResponse({ supervised_mode: (c.body as { supervised_mode: boolean }).supervised_mode, score_provider: "dataset", policies_version: 3 }),
    "POST /api/cases/NOT-0001/action": () => jsonResponse({ event_id: "E-9", previous_status: "review", new_status: "review", notification_id: null }),
  });
  await analystLogin(api);
  await api.setSupervised(true);
  assert.equal(api.session.getSnapshot().supervised, true);
  const before = calls.length;
  await assert.rejects(api.analystAction("NOT-0001", "approve_credit"), (e: unknown) => e instanceof ApiError && e.code === "APPROVAL_REQUIRED");
  assert.equal(calls.length, before);
  await api.analystAction("NOT-0001", "approve_credit", { confirmed: true });
  assert.equal(calls.length, before + 1);
});

test("spec 05 AC-07: signing out forgets the token", async () => {
  const { api } = setup({ ...ANALYST_ROUTES, "GET /api/console/cases": () => jsonResponse([]) });
  await analystLogin(api);
  await api.analystLogout();
  assert.equal(api.session.getSnapshot().analystSession, null);
  await assert.rejects(api.listCases(), (e: unknown) => e instanceof ApiError && e.code === "UNAUTHORIZED");
});

test("the session survives a reload of the tab, the analyst's token included, until it expires", async () => {
  const data = new Map<string, string>();
  const storage = { getItem: (k: string) => data.get(k) ?? null, setItem: (k: string, v: string) => void data.set(k, v), removeItem: (k: string) => void data.delete(k) };
  const clock = { t: NOW };
  const fetchImpl = (async (input: RequestInfo | URL) => {
    const url = String(input);
    return url.includes("cognito") ? jsonResponse({ AuthenticationResult: { IdToken: jwt({ name: "x" }), ExpiresIn: 60 } }) : jsonResponse({ supervised_mode: false });
  }) as typeof fetch;
  const make = () => createLiveApi({ fetch: fetchImpl, storage, now: () => clock.t, cognito: { region: "us-east-2", clientId: "c" } });
  await make().analystLogin("diego", "pw");
  assert.equal(make().session.getSnapshot().analystSession?.username, "diego");
  clock.t += 61_000;
  assert.equal(make().session.getSnapshot().analystSession, null, "an expired token is dropped on load");
});

// --- which buttons the console offers ----------------------------------------------------------------------------------

test("spec 05 AC-04: the console offers only moves the queue allows (D-034)", () => {
  const names = (status: Parameters<typeof consoleActions>[0]) => consoleActions(status, "live").map((a) => a.action);
  assert.deepEqual(names("new"), ["take"]);
  assert.deepEqual(names("verification"), ["take", "approve_credit", "resolve"]);
  assert.deepEqual(names("review"), ["take", "approve_credit", "resolve"]);
  assert.deepEqual(names("resolved"), ["close_case", "reopen_case"]);
  assert.deepEqual(names("closed"), []);
});

test("spec 05 AC-10: the reason is asked for exactly where the api requires it", () => {
  const needing = (["new", "verification", "review", "resolved"] as const).flatMap((s) => consoleActions(s, "live").filter((a) => a.needsReason).map((a) => a.action));
  assert.deepEqual([...new Set(needing)].sort(), ["close_case", "reopen_case", "resolve"]);
  assert.ok(consoleActions("review", "mock").every((a) => !a.needsReason), "the mock queue never asks for one");
});
