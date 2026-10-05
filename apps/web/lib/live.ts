// The live client (spec 16 Task 5): the same surface as the mock (lib/client.ts) over the spec 05 api.
//  - Customers: `POST /api/sessions` + `/verify` set an httpOnly cookie; every customer call rides on it (same origin,
//    Caddy routes `/api/*` to the api, `next.config.ts` does it in dev). The browser never holds a customer id it can
//    change: the api reads it from the session row (constitution #3).
//  - Analysts: Amazon Cognito (USER_PASSWORD_AUTH, ADR 0017); the id token goes as `Authorization: Bearer` and the api
//    verifies it (spec 05 AC-07). The token lives in sessionStorage for this tab only.
//  - The agent: `POST /api/agent/threads` and the SSE `runs/stream`; the LangSmith key never reaches the browser (AC-05).
// Nothing here invents data: a call that fails answers an ApiError the page shows (UNAVAILABLE, DENY, RATE_LIMITED…).
import type { ApiClient, ChatContext } from "./client.ts";
import { MESSAGES, fill } from "./mock/messages.ts";
import { ApiError } from "./mock/store.ts";
import type {
  AgentReply,
  AnalystSession,
  AuditEntry,
  CaseListItem,
  CaseStatus,
  ConsoleCase,
  CustomerCaseView,
  CustomerSession,
  DemoCustomer,
  DemoStart,
  HandoffCard,
  Language,
  NotificationEntry,
  PersonaCharacter,
  PersonaDraft,
  Receipt,
  RecentTransaction,
  Scenario,
  SessionSnapshot,
  Suggestion,
  TraceStep,
  TurnAction,
} from "./types.ts";

const STORAGE_KEY = "nickoftime.live.v1";

export interface LiveOptions {
  fetch?: typeof fetch;
  /** "" = same origin (production and `next dev` with the rewrite); tests pass a host. */
  baseUrl?: string;
  storage?: Pick<Storage, "getItem" | "setItem" | "removeItem"> | null;
  now?: () => number;
  /** Cognito app client of the analysts' pool (public values). null = analyst sign-in is not configured. */
  cognito?: { region: string; clientId: string } | null;
  newId?: () => string;
}

// --- wire shapes: only the fields read here (packages/nick_of_time/contracts.py, apps/api/app/main.py) -------------

interface WireProgress { step: string; label: string; state: string }
interface WireTurn {
  reply: string;
  language: Language;
  decision?: string | null;
  progress?: WireProgress[];
  actions?: { tool: string; state: string; verification_id?: string | null }[];
  suggestions: { id: string; label: string; kind: "text" | "action" | "link"; action?: TurnAction | null; href?: string | null }[];
  receipt?: WireReceipt | null;
  guardrails_triggered?: string[];
  denials?: { guardrail_id?: string | null; detail: string }[];
}
interface WireReceipt {
  case_id: string;
  language: Language;
  issued_at: string;
  verified_facts: { fact: string }[];
  actions: { label: string; state: string; verification_id?: string | null }[];
  deadline: { country: string; product: string; credit_deadline?: string | null; ruling_deadline?: string | null; deadline_source: string; source_url: string; verified_on: string } | null;
  what_ai_did: string;
  what_a_person_does: string;
}
interface WireCaseSummary {
  case_id: string;
  country: string;
  queue_status: CaseStatus;
  credit_deadline: string | null;
  ruling_deadline: string | null;
  created_at: string;
  customer_id: string;
  zone: "high" | "medium" | "human";
  priority: "normal" | "high";
}
interface WireCaseView extends WireCaseSummary {
  deadline_countdown_days: number | null;
  deadline_source: string | null;
}
interface WireCustomerCase {
  case_id: string;
  queue_status: CaseStatus;
  credit_deadline: string | null;
  ruling_deadline: string | null;
  created_at: string;
  status_label: string;
  mode: "replay" | "live";
  deadline_countdown_days: number | null;
  deadline_source: string | null;
  timeline: { event_id: string; type: string; label: string; created_at: string }[];
  channels: { telegram: boolean; email: boolean };
}
interface WireNotification {
  notification_id: string;
  case_id: string;
  event: string;
  channel: "log" | "telegram" | "email";
  text: string;
  delivery_status: string;
  created_at: string;
}

const NOTIFICATION_STATUS: Record<string, CaseStatus> = {
  case_opened: "new",
  card_blocked: "verification",
  in_review: "review",
  resolved: "resolved",
};

/** Parses a text/event-stream body into `{event, data}` records (the api sends `event:` and one `data:` JSON line). */
export async function* readSse(body: ReadableStream<Uint8Array>): AsyncGenerator<{ event: string; data: unknown }> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const parse = (block: string) => {
    let event = "message";
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (data.length === 0) return null;
    try {
      return { event, data: JSON.parse(data.join("\n")) as unknown };
    } catch {
      return null; // a malformed chunk is dropped, never fails the turn
    }
  };
  for (;;) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, "\n");
    for (let cut = buffer.indexOf("\n\n"); cut !== -1; cut = buffer.indexOf("\n\n")) {
      const record = parse(buffer.slice(0, cut));
      buffer = buffer.slice(cut + 2);
      if (record) yield record;
    }
    if (done) break;
  }
  const rest = parse(buffer);
  if (rest) yield rest;
}

/** The api's turn as the page shows it. Constitution #4: a step is `verified` only when the api says so. */
export function replyFromTurn(turn: WireTurn): AgentReply {
  const kind = (state: string): TraceStep["kind"] =>
    state === "verified" ? "verified" : state === "requested" ? "accepted" : state === "not_confirmed" ? "not_confirmed" : "ok";
  const progress = turn.progress ?? [];
  const trace: TraceStep[] = progress.length
    ? progress.map((p) => ({ step: p.step, result: p.label, kind: kind(p.state) }))
    : (turn.actions ?? []).map((a) => ({
        step: a.tool,
        result: a.verification_id ? `${a.state} (${a.verification_id})` : a.state,
        kind: kind(a.state),
      }));
  const denied = (turn.denials ?? []).length > 0 || turn.decision === "deny";
  for (const d of turn.denials ?? []) trace.push({ step: d.guardrail_id ?? "guardrail", result: d.detail, kind: "deny" });
  const suggestions: Suggestion[] = turn.suggestions.map((s) => ({
    label: s.label,
    text: s.label,
    ...(s.kind === "action" && s.action ? { action: s.action } : {}),
    ...(s.kind === "link" && s.href ? { href: s.href } : {}),
  }));
  return {
    text: turn.reply,
    trace,
    guardrails: turn.guardrails_triggered ?? [],
    suggestions,
    deny: denied || undefined,
    awaitingConfirmation: turn.decision === "confirm",
    receipt: turn.receipt ? receiptFrom(turn.receipt) : undefined,
  };
}

function receiptFrom(r: WireReceipt): Receipt {
  const lang = r.language;
  const d = r.deadline;
  const lines: string[] = [];
  const facts = d ? { deadline_source: d.deadline_source, source_url: d.source_url, verified_on: d.verified_on } : null;
  if (d && facts && d.credit_deadline) lines.push(fill(MESSAGES.receipt.credit_deadline, lang, { ...facts, credit_deadline: d.credit_deadline }));
  if (d && facts && d.ruling_deadline) lines.push(fill(MESSAGES.receipt.ruling_deadline, lang, { ...facts, ruling_deadline: d.ruling_deadline }));
  if (lines.length === 0) lines.push(MESSAGES.receipt.deadline_unknown[lang]);
  return {
    case_id: r.case_id,
    language: lang,
    issued_at: r.issued_at,
    title: fill(MESSAGES.receipt.title, lang, { case_id: r.case_id }),
    card_blocked: null,
    deadline: {
      country: d?.country ?? "",
      product: d?.product ?? "",
      creditDeadline: d?.credit_deadline ?? null,
      deadlineSource: d?.deadline_source ?? "",
      daysLeft: null,
    },
    deadline_text: lines.join(" "),
    what_ai_did: r.what_ai_did,
    what_a_person_does: r.what_a_person_does,
    case_url: `/case/${encodeURIComponent(r.case_id)}`, // our own path, never a host the api sent
    facts: r.verified_facts.map((f) => f.fact),
    actions: r.actions.map((a) => ({ label: a.label, state: a.state, ...(a.verification_id ? { verification_id: a.verification_id } : {}) })),
  };
}

/** The claims of a JWT payload, for the display name only: the api verifies the signature, the browser never trusts it. */
function claimsOf(token: string): Record<string, unknown> {
  try {
    const payload = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const bytes = Uint8Array.from(atob(payload.padEnd(Math.ceil(payload.length / 4) * 4, "=")), (c) => c.charCodeAt(0));
    return JSON.parse(new TextDecoder().decode(bytes)) as Record<string, unknown>;
  } catch {
    return {};
  }
}

function sessionOf(c: NonNullable<Stored["customer"]>): CustomerSession {
  return {
    customerId: c.customerId,
    expiresAt: c.expiresAt,
    language: c.language,
    ...(c.displayName ? { displayName: c.displayName } : {}),
    ...(c.mode ? { mode: c.mode } : {}),
  };
}

function browserSession(): Pick<Storage, "getItem" | "setItem" | "removeItem"> | null {
  try {
    return window.sessionStorage;
  } catch {
    return null; // blocked storage: the session lasts until reload
  }
}

interface Stored {
  /** `sessionId` is what the session routes of the api take in the path (recent transactions, test charge); the same id the cookie holds. */
  customer: {
    customerId: string;
    expiresAt: number;
    language: Language;
    sessionId?: string;
    displayName?: string;
    mode?: "live" | "replay";
  } | null;
  analyst: { username: string; displayName: string; token: string; expiresAt: number } | null;
}

export function createLiveApi(options: LiveOptions = {}): ApiClient {
  const base = options.baseUrl ?? "";
  const doFetch: typeof fetch = options.fetch ?? ((...args) => fetch(...args));
  const now = options.now ?? Date.now;
  const newId = options.newId ?? (() => crypto.randomUUID());
  const storage = options.storage === undefined ? (typeof window === "undefined" ? null : browserSession()) : options.storage;
  const cognito =
    options.cognito === undefined
      ? {
          region: process.env.NEXT_PUBLIC_COGNITO_REGION || "us-east-2",
          clientId: process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID || "",
        }
      : options.cognito;

  // --- state: the snapshot pages read, plus what only this file needs -------------------------------------------
  const listeners = new Set<() => void>();
  const stored: Stored = load();
  const SERVER: SessionSnapshot = { customerSession: null, analystSession: null, supervised: false, audit: [] };
  let snapshot: SessionSnapshot = {
    customerSession: stored.customer ? sessionOf(stored.customer) : null,
    analystSession: stored.analyst ? { username: stored.analyst.username, displayName: stored.analyst.displayName } : null,
    supervised: false,
    audit: [],
  };
  let pending: { sessionId: string; customerId: string; language: Language; displayName?: string; mode?: "live" | "replay" } | null = null;
  let threadId: string | null = null;
  let customers: Promise<DemoCustomer[]> | null = null;

  function load(): Stored {
    try {
      const raw = storage?.getItem(STORAGE_KEY);
      const parsed = raw ? (JSON.parse(raw) as Stored) : null;
      const out: Stored = { customer: parsed?.customer ?? null, analyst: parsed?.analyst ?? null };
      if (out.analyst && out.analyst.expiresAt <= now()) out.analyst = null;
      return out;
    } catch {
      return { customer: null, analyst: null };
    }
  }

  function commit(next: Partial<SessionSnapshot>): void {
    snapshot = { ...snapshot, ...next };
    try {
      storage?.setItem(STORAGE_KEY, JSON.stringify(stored));
    } catch {
      /* storage can be blocked: the in-memory state still works */
    }
    listeners.forEach((l) => l());
  }

  function verifiedSessionId(): string {
    if (!stored.customer?.sessionId || stored.customer.expiresAt <= now()) {
      throw new ApiError("SESSION_EXPIRED", 401, "Session expired: verify again.");
    }
    return stored.customer.sessionId;
  }

  const customerLanguage = (): Language => stored.customer?.language ?? "es";

  // --- http ----------------------------------------------------------------------------------------------------
  function fail(status: number, body: unknown, analyst: boolean): never {
    const b = (body && typeof body === "object" ? body : {}) as { code?: string; message?: string };
    const code = b.code ?? (status === 401 ? "UNAUTHENTICATED" : "UNAVAILABLE");
    if (status === 401 && analyst) {
      stored.analyst = null;
      commit({ analystSession: null });
      throw new ApiError("UNAUTHORIZED", 401, "Your sign-in expired or was not accepted: sign in again.");
    }
    if (status === 401 && code === "SESSION_EXPIRED") expireLocally();
    else if (status === 401 && !analyst && stored.customer) {
      stored.customer = null; // the cookie is gone or unknown to the api: the page asks to verify again
      threadId = null;
      commit({ customerSession: null });
    }
    throw new ApiError(code, status, b.message ?? `The api answered ${status}`);
  }

  function expireLocally(): void {
    if (stored.customer) stored.customer = { ...stored.customer, expiresAt: now() };
    threadId = null;
    commit({ customerSession: stored.customer ? sessionOf(stored.customer) : null });
  }

  async function send(path: string, opts: { method?: string; body?: unknown; analyst?: boolean; raw?: { blob: Blob; contentType: string } } = {}): Promise<Response> {
    const headers: Record<string, string> = { Accept: "application/json" };
    if (opts.raw) headers["Content-Type"] = opts.raw.contentType;
    else if (opts.body !== undefined) headers["Content-Type"] = "application/json";
    if (opts.analyst) {
      if (!stored.analyst) throw new ApiError("UNAUTHORIZED", 401, "Sign in first.");
      headers.Authorization = `Bearer ${stored.analyst.token}`;
    }
    let res: Response;
    try {
      res = await doFetch(`${base}${path}`, {
        method: opts.method ?? "GET",
        headers,
        credentials: "same-origin",
        ...(opts.raw ? { body: opts.raw.blob } : opts.body !== undefined ? { body: JSON.stringify(opts.body) } : {}),
      });
    } catch {
      throw new ApiError("UNAVAILABLE", 0, "Cannot reach the server. Check your connection and try again.");
    }
    if (!res.ok) fail(res.status, await res.json().catch(() => ({})), Boolean(opts.analyst));
    return res;
  }

  async function json<T>(path: string, opts: { method?: string; body?: unknown; analyst?: boolean } = {}): Promise<T> {
    return (await (await send(path, opts)).json()) as T;
  }

  function demoCustomers(): Promise<DemoCustomer[]> {
    customers ??= json<DemoCustomer[]>("/api/demo/customers").catch((e) => {
      customers = null; // try again next time; a failed list is not cached
      throw e;
    });
    return customers;
  }

  const nameOf = async (customerId: string) =>
    (await demoCustomers().catch(() => [])).find((c) => c.customer_id === customerId)?.display_name ?? customerId;

  // --- analyst actions -----------------------------------------------------------------------------------------
  async function analystAction(caseId: string, action: string, opts: { reason?: string; confirmed?: boolean } = {}): Promise<unknown> {
    if (action === "approve_credit" && snapshot.supervised && !opts.confirmed) {
      throw new ApiError("APPROVAL_REQUIRED", 409, "Supervised mode is on: confirm the approval.");
    }
    const out = await json<{ new_status: CaseStatus }>(`/api/cases/${encodeURIComponent(caseId)}/action`, {
      method: "POST",
      analyst: true,
      body: { case_id: caseId, actor_id: "console", action, reason: opts.reason?.trim() || null, idempotency_key: newId() },
    });
    const entry: AuditEntry = {
      id: newId(),
      at: new Date(now()).toISOString(),
      actor: snapshot.analystSession?.displayName ?? "analyst",
      action,
      target: caseId,
      ...(opts.reason?.trim() ? { reason: opts.reason.trim() } : {}),
    };
    commit({ audit: [entry, ...snapshot.audit] });
    return out;
  }

  return {
    mode: "live",
    subscribe: (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    session: { getSnapshot: () => snapshot, getServerSnapshot: () => SERVER },

    // customer
    listDemoCustomers: demoCustomers,

    async requestOtp(customerId) {
      const picked = (await demoCustomers()).find((c) => c.customer_id === customerId);
      const out = await json<{ session_id: string; otp_demo: string }>("/api/sessions", {
        method: "POST",
        body: { customer_id: customerId },
      });
      pending = { sessionId: out.session_id, customerId, language: picked?.language ?? "es" };
      return out.otp_demo;
    },

    // Demo session (D-068, ADR 0026): the body never carries a customer id; the api chooses the customer from the scenario.
    async startDemoSession(start: DemoStart) {
      const name = start.displayName?.trim();
      const out = await json<{ session_id: string; mode: "live" | "replay"; otp_demo: string }>("/api/sessions", {
        method: "POST",
        body: {
          ...(name ? { display_name: name } : {}),
          language: start.language,
          ...(start.country ? { country: start.country } : {}),
          scenario: start.scenario,
        },
      });
      pending = { sessionId: out.session_id, customerId: "", language: start.language, displayName: name || undefined, mode: out.mode };
      return out.otp_demo;
    },

    async listScenarios(filter) {
      const q = new URLSearchParams({ language: filter.language, ...(filter.country ? { country: filter.country } : {}) });
      return json<Scenario[]>(`/api/demo/scenarios?${q}`);
    },

    async listRecentTransactions(limit = 10): Promise<RecentTransaction[]> {
      const id = verifiedSessionId();
      return json<RecentTransaction[]>(`/api/sessions/${encodeURIComponent(id)}/recent-transactions?limit=${limit}`);
    },

    async registerTestCharge(amount, merchant): Promise<RecentTransaction> {
      const id = verifiedSessionId();
      const out = await json<RecentTransaction>(`/api/sessions/${encodeURIComponent(id)}/synthetic-charge`, {
        method: "POST",
        body: { amount, merchant },
      });
      commit({}); // the chip list reads again and shows the new charge first
      return out;
    },

    async transcribe(clip: Blob, contentType: string): Promise<{ text: string; language: string }> {
      verifiedSessionId(); // the route needs the session cookie; an expired session says so
      return (await send("/api/voice/transcribe", { method: "POST", raw: { blob: clip, contentType } })).json();
    },

    async suggestPersona(character: PersonaCharacter, transactionId?: string): Promise<PersonaDraft> {
      return json<PersonaDraft>("/api/demo/persona", {
        method: "POST",
        body: { character, ...(transactionId ? { transaction_id: transactionId } : {}) },
      });
    },

    async verifyOtp(otp) {
      if (!pending) throw new ApiError("UNAUTHORIZED", 401, "Ask for a code first.");
      const out = await json<{ expires_at: string }>(`/api/sessions/${encodeURIComponent(pending.sessionId)}/verify`, {
        method: "POST",
        body: { otp },
      });
      stored.customer = {
        customerId: pending.customerId,
        expiresAt: Date.parse(out.expires_at),
        language: pending.language,
        sessionId: pending.sessionId,
        displayName: pending.displayName,
        mode: pending.mode,
      };
      const session = sessionOf(stored.customer);
      pending = null;
      threadId = null; // a new session never reuses another's thread
      commit({ customerSession: session });
      return session;
    },

    // The api has no logout route (spec 05): the session is forgotten here and expires on its own after 15 minutes.
    async logoutCustomer() {
      stored.customer = null;
      threadId = null;
      pending = null;
      commit({ customerSession: null });
    },

    async expireCustomerSession() {
      expireLocally();
    },

    async chat(text: string, ctx: ChatContext = {}): Promise<AgentReply> {
      if (!stored.customer || stored.customer.expiresAt <= now()) throw new ApiError("SESSION_EXPIRED", 401, "Session expired: verify again.");
      threadId ??= (await json<{ thread_id: string }>("/api/agent/threads", { method: "POST" })).thread_id;
      // Only the customer's text and a chip press go up: language, customer and mode come from the session (spec 01 AC-06).
      const input = ctx.action ? { messages: [], action: ctx.action } : { messages: [{ role: "user", content: text }] };
      const res = await send(`/api/agent/threads/${encodeURIComponent(threadId)}/runs/stream`, {
        method: "POST",
        body: { input },
      });
      if (!res.body) throw new ApiError("UNAVAILABLE", 502, "The agent sent no answer.");
      let turn: WireTurn | null = null;
      for await (const { event, data } of readSse(res.body)) {
        if (event === "progress") {
          const p = data as WireProgress;
          if (p && typeof p.label === "string") ctx.onProgress?.({ step: p.step, label: p.label });
        } else if (event === "turn") {
          turn = data as WireTurn;
        }
      }
      if (!turn) throw new ApiError("UNAVAILABLE", 502, "The agent did not finish the turn.");
      return replyFromTurn(turn);
    },

    // cases
    async getCase(id): Promise<CustomerCaseView> {
      const c = await json<WireCustomerCase>(`/api/cases/${encodeURIComponent(id)}`);
      return {
        case_id: c.case_id,
        language: customerLanguage(),
        status_label: c.status_label,
        created_at: c.created_at,
        credit_deadline: c.credit_deadline,
        ruling_deadline: c.ruling_deadline,
        deadline_source: c.deadline_source,
        deadline_countdown_days: c.deadline_countdown_days,
        timeline: c.timeline.map((e) => ({ event_id: e.event_id, type: e.type, created_at: e.created_at, status_label: e.label })),
        channels: c.channels,
        mode: c.mode,
      };
    },

    async listCases(): Promise<CaseListItem[]> {
      const rows = await json<WireCaseSummary[]>("/api/console/cases", { analyst: true });
      return Promise.all(
        rows.map(async (r) => ({
          id: r.case_id,
          customerName: await nameOf(r.customer_id),
          zone: r.zone,
          priority: r.priority,
          status: r.queue_status,
          deadline: { country: r.country, product: "", creditDeadline: r.credit_deadline, deadlineSource: "", daysLeft: null },
        })),
      );
    },

    async getConsoleCase(id): Promise<ConsoleCase> {
      const out = await json<{
        case: WireCaseView;
        handoff: Partial<HandoffCard> & { deadline?: Partial<HandoffCard["deadline"]> };
        events: { event_id: string; type: string; actor: string; created_at: string }[];
      }>(`/api/console/cases/${encodeURIComponent(id)}`, { analyst: true });
      const c = out.case;
      const h = out.handoff ?? {};
      const emitted = Object.keys(h).length > 0;
      const language: Language = h.language ?? (await demoCustomers().catch(() => [])).find((x) => x.customer_id === c.customer_id)?.language ?? "es";
      const deadline = {
        country: c.country,
        product: h.deadline?.product ?? "",
        creditDeadline: c.credit_deadline,
        deadlineSource: c.deadline_source ?? h.deadline?.deadline_source ?? "",
        daysLeft: c.deadline_countdown_days,
      };
      return {
        id: c.case_id,
        customerId: c.customer_id,
        customerName: await nameOf(c.customer_id),
        language,
        zone: c.zone,
        priority: c.priority,
        status: c.queue_status,
        openedAt: c.created_at,
        deadline,
        events: out.events.map((e) => ({ id: e.event_id, at: e.created_at, type: e.type, actor: e.actor })),
        handoffEmitted: emitted,
        handoff: {
          case_id: c.case_id,
          language,
          zone: c.zone,
          handoff_reason: h.handoff_reason,
          request: h.request ?? "",
          verified_facts: h.verified_facts ?? [],
          actions: h.actions ?? [],
          evidence: h.evidence ?? [],
          open_questions: h.open_questions ?? [],
          copilot_proposal: h.copilot_proposal,
          deadline: {
            country: c.country,
            product: h.deadline?.product ?? "",
            credit_deadline: c.credit_deadline,
            deadline_source: deadline.deadlineSource,
          },
          trace_id: h.trace_id ?? "",
          score: h.score ?? null,
          queue_status: c.queue_status,
          guardrails_triggered: h.guardrails_triggered ?? [],
        },
      };
    },

    async getNotifications(caseId): Promise<NotificationEntry[]> {
      const rows = (await json<WireNotification[]>("/api/notifications")).filter((n) => n.case_id === caseId);
      // One entry per status change: the api writes one row per channel, close together in time.
      const entries: NotificationEntry[] = [];
      for (const n of [...rows].sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at))) {
        const channel = n.channel === "log" ? "in_app" : n.channel;
        const delivered = n.delivery_status === "sent" || n.delivery_status === "delivered";
        const last = entries[entries.length - 1];
        const at = Date.parse(n.created_at);
        if (last && last.status === (NOTIFICATION_STATUS[n.event] ?? "new") && at - Date.parse(last.at) < 5000 && last.body === n.text) {
          last.channels.push({ channel, delivered });
        } else {
          entries.push({
            id: n.notification_id,
            caseId,
            at: n.created_at,
            status: NOTIFICATION_STATUS[n.event] ?? "new",
            title: n.text,
            body: n.text,
            channels: [{ channel, delivered }],
          });
        }
      }
      return entries.reverse(); // newest first, as the mock lists them
    },

    async requestCall(caseId) {
      const out = await json<{ event_id: string; expected_contact_by: string | null }>(`/api/cases/${encodeURIComponent(caseId)}/call-request`, {
        method: "POST",
        body: {},
      });
      commit({});
      return out;
    },

    async addCustomerInfo(caseId, text) {
      await json(`/api/cases/${encodeURIComponent(caseId)}/info`, { method: "POST", body: { text } });
      commit({});
    },

    async createTelegramLink(caseId) {
      const out = await json<{ deep_link: string }>(`/api/cases/${encodeURIComponent(caseId)}/channels/telegram`, { method: "POST" });
      return { token: "", deepLink: out.deep_link };
    },

    async simulateTelegramStart() {
      throw new ApiError("UNAVAILABLE", 501, "Telegram calls the webhook itself in live mode.");
    },

    async confirmEmail(caseId, address) {
      const out = await json<{ confirmation_sent: boolean }>(`/api/cases/${encodeURIComponent(caseId)}/channels/email`, {
        method: "POST",
        body: { email: address },
      });
      if (!out.confirmation_sent) throw new ApiError("UNAVAILABLE", 502, "We could not send the confirmation e-mail. Try again in a moment.");
      commit({});
    },

    // analyst
    async analystLogin(username, password): Promise<AnalystSession> {
      if (!cognito?.clientId) {
        throw new ApiError("UNAVAILABLE", 503, "Analyst sign-in is not configured here (NEXT_PUBLIC_COGNITO_CLIENT_ID).");
      }
      let res: Response;
      try {
        res = await doFetch(`https://cognito-idp.${cognito.region}.amazonaws.com/`, {
          method: "POST",
          headers: {
            "Content-Type": "application/x-amz-json-1.1",
            "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
          },
          body: JSON.stringify({
            AuthFlow: "USER_PASSWORD_AUTH",
            ClientId: cognito.clientId,
            AuthParameters: { USERNAME: username, PASSWORD: password },
          }),
        });
      } catch {
        throw new ApiError("UNAVAILABLE", 0, "Cannot reach the sign-in service. Check your connection.");
      }
      const data = (await res.json().catch(() => ({}))) as {
        __type?: string;
        ChallengeName?: string;
        AuthenticationResult?: { IdToken?: string; ExpiresIn?: number };
      };
      if (!res.ok) {
        const type = String(data.__type ?? "").split("#").pop();
        throw new ApiError(
          "UNAUTHORIZED",
          401,
          type === "NotAuthorizedException" || type === "UserNotFoundException" ? "Wrong user or password." : "Sign-in failed. Try again, or ask the lead.",
        );
      }
      const token = data.AuthenticationResult?.IdToken;
      if (!token) {
        throw new ApiError("UNAUTHORIZED", 401, `Sign-in needs a step this page does not do (${data.ChallengeName ?? "no token"}): ask the lead to set your password.`);
      }
      const claims = claimsOf(token);
      const displayName = [claims["cognito:username"], claims.preferred_username, claims.name, username].find((v): v is string => typeof v === "string" && v.length > 0) ?? username;
      stored.analyst = { username, displayName, token, expiresAt: now() + (data.AuthenticationResult?.ExpiresIn ?? 3600) * 1000 };
      commit({ analystSession: { username, displayName }, audit: [] });
      try {
        // The first call with the token: it proves the api accepts this pool, and gives the current supervised mode.
        const s = await json<{ supervised_mode: boolean }>("/api/console/settings", { analyst: true });
        commit({ supervised: s.supervised_mode });
      } catch (e) {
        stored.analyst = null;
        commit({ analystSession: null });
        throw e instanceof ApiError && e.code === "UNAUTHORIZED"
          ? new ApiError("UNAUTHORIZED", 401, "The api did not accept this sign-in. The Cognito pool of the api and of this page must be the same.")
          : e;
      }
      return { username, displayName };
    },

    async analystLogout() {
      stored.analyst = null;
      commit({ analystSession: null, audit: [], supervised: false });
    },

    analystAction,

    async setSupervised(on) {
      const out = await json<{ supervised_mode: boolean }>("/api/console/settings", { method: "PUT", analyst: true, body: { supervised_mode: on } });
      const entry: AuditEntry = {
        id: newId(),
        at: new Date(now()).toISOString(),
        actor: snapshot.analystSession?.displayName ?? "analyst",
        action: "supervised_mode",
        target: out.supervised_mode ? "on" : "off",
      };
      commit({ supervised: out.supervised_mode, audit: [entry, ...snapshot.audit] });
    },
  };
}

