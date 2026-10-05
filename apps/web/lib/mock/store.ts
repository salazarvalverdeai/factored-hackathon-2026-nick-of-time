// In-memory (and localStorage-backed) stand-in for the backend until spec 05 ships [simulated].
// It enforces the rules the real API must enforce, so the pages are built against the right behavior:
//  - a case's status is its last event; events are only appended (spec 05 AC-02)
//  - transitions follow the case queue: new → verification | review → resolved → closed (AC-04)
//  - customer sessions last 15 minutes and then answer SESSION_EXPIRED (AC-01)
//  - analyst actions need an analyst session and record who did them (AC-07)
//  - notifications never carry the score, policy ids or the transcript (spec 13 AC-08)
import type {
  AnalystSession,
  AuditEntry,
  CaseEvent,
  CaseRecord,
  CallRequestResult,
  CaseStatus,
  CustomerCaseView,
  CustomerSession,
  Deadline,
  HandoffCard,
  Language,
  MockCustomer,
  NotificationEntry,
  Zone,
} from "../types.ts";
import { ANALYSTS, CUSTOMERS, DEADLINE_RULES } from "./fixtures.ts";
import { MESSAGES } from "./messages.ts";

export const DEMO_TODAY = "2026-06-03"; // ADR 0012: the demo date is frozen
export const SESSION_TTL_MS = 15 * 60 * 1000;
export const TELEGRAM_TOKEN_TTL_MS = 15 * 60 * 1000;
const STORAGE_KEY = "nickoftime.mock.v1";

export type ApiErrorCode =
  | "SESSION_EXPIRED"
  | "UNAUTHORIZED"
  | "INVALID_OTP"
  | "INVALID_TRANSITION"
  | "APPROVAL_REQUIRED"
  | "NOT_FOUND"
  | "BAD_REQUEST"
  | "LIVE_API_NOT_READY"
  // the live api's own codes (spec 05 / spec 01 §6.2)
  | "UNAUTHENTICATED"
  | "DENY"
  | "INVALID"
  | "UNAVAILABLE"
  | "RATE_LIMITED"
  | (string & {});

export class ApiError extends Error {
  code: ApiErrorCode;
  status: number;
  constructor(code: ApiErrorCode, status: number, message?: string) {
    super(message ?? code);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

/** Case queue from contracts/policies.yaml. */
export const TRANSITIONS: Record<CaseStatus, CaseStatus[]> = {
  new: ["verification", "review"],
  verification: ["resolved"],
  review: ["resolved"],
  resolved: ["closed"],
  closed: [],
};

export function caseStatus(c: CaseRecord): CaseStatus {
  return c.events[c.events.length - 1].status;
}

/** messages.yaml status.label: the customer-facing label of a queue status, in the customer's language. */
export function statusLabel(status: CaseStatus, lang: Language): string {
  const labels = MESSAGES.status.label;
  const key = status === "new" ? "received" : status === "resolved" ? "resolved" : status === "closed" ? "closed" : "in_review";
  return labels[key][lang];
}

// --- dates (weekends only; bank holidays arrive with the policy engine, spec 02) -------------------------------

export function addBusinessDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  let left = days;
  while (left > 0) {
    d.setUTCDate(d.getUTCDate() + 1);
    const weekday = d.getUTCDay();
    if (weekday !== 0 && weekday !== 6) left--;
  }
  return d.toISOString().slice(0, 10);
}

export function daysBetween(fromIso: string, toIso: string): number {
  return Math.round((Date.parse(`${toIso}T00:00:00Z`) - Date.parse(`${fromIso}T00:00:00Z`)) / 86_400_000);
}

export function deadlineFor(customer: Pick<MockCustomer, "country" | "product">): Deadline {
  const rule = DEADLINE_RULES[`${customer.country}:${customer.product}`];
  return {
    country: customer.country,
    product: customer.product,
    creditDeadline: rule?.businessDays ? addBusinessDays(DEMO_TODAY, rule.businessDays) : null,
    deadlineSource: rule?.source ?? "pending the policy engine (spec 02)",
  };
}

// --- state ------------------------------------------------------------------------------------------------------

export interface MockState {
  cases: CaseRecord[];
  notifications: NotificationEntry[];
  audit: AuditEntry[];
  supervised: boolean;
  customerSession: CustomerSession | null;
  analystSession: AnalystSession | null;
  pendingOtp: { customerId: string; otp: string } | null;
  telegram: Record<string, { token: string; expiresAt: number; linked: boolean }>;
  emails: Record<string, { address: string; confirmed: boolean }>;
  seq: number;
}

interface CaseSeed {
  id: string;
  customerId: string;
  customerName: string;
  customer: Pick<MockCustomer, "country" | "product" | "language" | "fraudScore">;
  zone: Zone;
  request: string;
  openedAt: string;
  guardrails?: string[];
}

function ev(id: string, at: string, type: CaseEvent["type"], actor: string, status: CaseStatus, reason?: string): CaseEvent {
  return { id, at, type, actor, status, ...(reason ? { reason } : {}) };
}

/** Builds a case the way the agent would leave it: block + verification for zones high/medium, review for human. */
export function buildCase(seed: CaseSeed, finalStatus?: CaseStatus): CaseRecord {
  const blocks = seed.zone !== "human";
  const e = (n: number) => `${seed.id}-E${n}`;
  const events: CaseEvent[] = [ev(e(1), seed.openedAt, "case_opened", "agent", "new")];
  if (blocks) {
    events.push(ev(e(2), seed.openedAt, "card_blocked", "agent", "new", "post-condition verified"));
    events.push(ev(e(3), seed.openedAt, "verification_started", "agent", "verification"));
  } else {
    events.push(ev(e(2), seed.openedAt, "sent_to_review", "agent", "review", "zone_human"));
  }
  if (finalStatus === "resolved") {
    events.push(ev(e(events.length + 1), seed.openedAt, "credit_approved", "diego", "resolved", "seed"));
  }
  const deadline = deadlineFor(seed.customer);
  const status = events[events.length - 1].status;
  const handoff: HandoffCard = {
    case_id: seed.id,
    language: seed.customer.language,
    zone: seed.zone,
    ...(blocks ? {} : { handoff_reason: "zone_human" }),
    request: seed.request,
    verified_facts: [
      { fact: `Customer reports an unrecognized charge on a ${seed.customer.product} card`, source_id: "tool:search_transaction" },
    ],
    actions: blocks
      ? [{ tool: "block_card", action_id: `blk-${seed.id}`, result: "accepted", verified: true, verification_id: `ver-${seed.id}` }]
      : [],
    evidence: ["transaction match [simulated]", "OTP verified [simulated]"],
    open_questions: blocks ? ["Approve provisional credit?"] : ["No fraud score from the bank: a person decides the zone"],
    copilot_proposal: {
      action: blocks ? "approve_credit" : "request_customer_info",
      rationale: "Proposal only [simulated]; a person decides.",
      requires_human: true,
    },
    deadline: {
      country: deadline.country,
      product: deadline.product,
      credit_deadline: deadline.creditDeadline,
      deadline_source: deadline.deadlineSource,
    },
    trace_id: `trace-${seed.id}`,
    score: seed.customer.fraudScore,
    queue_status: status,
    guardrails_triggered: seed.guardrails ?? [],
  };
  return {
    id: seed.id,
    customerId: seed.customerId,
    customerName: seed.customerName,
    language: seed.customer.language,
    zone: seed.zone,
    priority: seed.zone === "high" ? "high" : "normal",
    openedAt: seed.openedAt,
    deadline,
    events,
    handoff,
  };
}

function seedState(): MockState {
  const at = "2026-06-03T09:00:00.000Z";
  return {
    cases: [
      buildCase({
        id: "NOT-0001", customerId: "seed-1", customerName: "M. Rojas (MX · debit)", zone: "high", openedAt: at,
        customer: { country: "MX", product: "debit", language: "es", fraudScore: 71 },
        request: "Cargo no reconocido de 4,200 MXN",
      }),
      buildCase({
        id: "NOT-0002", customerId: "seed-2", customerName: "J. Souza (BR · credit)", zone: "human", openedAt: at,
        customer: { country: "BR", product: "credit", language: "pt", fraudScore: null },
        request: "Cobrança não reconhecida de 380 BRL",
      }),
      buildCase(
        {
          id: "NOT-0003", customerId: "seed-3", customerName: "L. Pérez (AR · credit)", zone: "high", openedAt: at,
          customer: { country: "AR", product: "credit", language: "es", fraudScore: 55 },
          request: "Consumo desconocido de 18,900 ARS",
        },
        "resolved",
      ),
    ],
    notifications: [],
    audit: [],
    supervised: false,
    customerSession: null,
    analystSession: null,
    pendingOtp: null,
    telegram: {},
    emails: {},
    seq: 3,
  };
}

// --- notification copy: fixed templates, so nothing sensitive can leak into them (spec 13 AC-08) --------------------

const COPY: Record<Language, Record<CaseStatus, string>> = {
  es: {
    new: "Registramos tu caso",
    verification: "Bloqueamos tu tarjeta y estamos verificando tu caso",
    review: "Un analista está revisando tu caso",
    resolved: "Tu caso fue resuelto; un analista lo cerrará",
    closed: "Tu caso está cerrado",
  },
  pt: {
    new: "Registramos o seu caso",
    verification: "Bloqueamos o seu cartão e estamos verificando o caso",
    review: "Um analista está revisando o seu caso",
    resolved: "Seu caso foi resolvido; um analista irá encerrá-lo",
    closed: "Seu caso está encerrado",
  },
};

// --- the store --------------------------------------------------------------------------------------------------

interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export class MockStore {
  private state: MockState;
  private listeners = new Set<() => void>();
  private storage: StorageLike | null;
  /** Injectable clock, so tests can move time. */
  clock: () => number;
  /** Channels that fail on purpose (spec 13 AC-07). */
  failingChannels: Set<"telegram" | "email"> = new Set();

  constructor(storage: StorageLike | null = null, clock: () => number = () => Date.now()) {
    this.storage = storage;
    this.clock = clock;
    this.state = seedState();
    if (storage) {
      try {
        const raw = storage.getItem(STORAGE_KEY);
        if (raw) this.state = JSON.parse(raw) as MockState;
      } catch {
        /* a broken saved state is ignored: the seed stays */
      }
    }
  }

  getState = (): MockState => this.state;
  getServerState = (): MockState => SERVER_STATE;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  reset(): void {
    this.state = seedState();
    this.save();
    this.emit();
  }

  private emit(): void {
    this.listeners.forEach((l) => l());
  }

  private save(): void {
    try {
      this.storage?.setItem(STORAGE_KEY, JSON.stringify(this.state));
    } catch {
      /* storage can be blocked (private window): the in-memory state still works */
    }
  }

  private mutate<T>(fn: (draft: MockState) => T): T {
    const draft = structuredClone(this.state);
    const result = fn(draft);
    this.state = draft;
    this.save();
    this.emit();
    return result;
  }

  private nowIso(): string {
    return new Date(this.clock()).toISOString();
  }

  // customer identity (ADR 0017) -----------------------------------------------------------------------------------

  requestOtp(customerId: string): string {
    if (!CUSTOMERS.some((c) => c.id === customerId)) throw new ApiError("NOT_FOUND", 404, "unknown demo customer");
    const otp = String(Math.floor(100000 + Math.random() * 900000));
    this.mutate((s) => {
      s.pendingOtp = { customerId, otp };
    });
    return otp;
  }

  verifyOtp(otp: string): CustomerSession {
    const pending = this.state.pendingOtp;
    if (!pending || pending.otp !== otp) throw new ApiError("INVALID_OTP", 401, "the code does not match");
    const session = { customerId: pending.customerId, expiresAt: this.clock() + SESSION_TTL_MS };
    this.mutate((s) => {
      s.customerSession = session;
      s.pendingOtp = null;
    });
    return session;
  }

  /** Every protected customer route goes through here: no session → 401, expired → SESSION_EXPIRED. */
  requireCustomerSession(): CustomerSession {
    const session = this.state.customerSession;
    if (!session) throw new ApiError("UNAUTHORIZED", 401, "verify your identity first");
    if (this.clock() > session.expiresAt) throw new ApiError("SESSION_EXPIRED", 401, "your session expired");
    return session;
  }

  expireCustomerSession(): void {
    this.mutate((s) => {
      if (s.customerSession) s.customerSession.expiresAt = this.clock() - 1;
    });
  }

  logoutCustomer(): void {
    this.mutate((s) => {
      s.customerSession = null;
    });
  }

  customerOf(session: CustomerSession): MockCustomer {
    const customer = CUSTOMERS.find((c) => c.id === session.customerId);
    if (!customer) throw new ApiError("NOT_FOUND", 404, "unknown demo customer");
    return customer;
  }

  // analyst identity (mock Cognito) --------------------------------------------------------------------------------

  analystLogin(username: string, password: string): AnalystSession {
    const user = ANALYSTS.find((a) => a.username === username.trim().toLowerCase());
    if (!user || password.length === 0) throw new ApiError("UNAUTHORIZED", 401, "wrong user or password");
    const session = { username: user.username, displayName: user.displayName };
    this.mutate((s) => {
      s.analystSession = session;
    });
    return session;
  }

  analystLogout(): void {
    this.mutate((s) => {
      s.analystSession = null;
    });
  }

  /** Every analyst route goes through here; the actor of each action comes from this session, never from input. */
  requireAnalyst(): AnalystSession {
    if (!this.state.analystSession) throw new ApiError("UNAUTHORIZED", 401, "analyst login required");
    return this.state.analystSession;
  }

  // cases ----------------------------------------------------------------------------------------------------------

  private findCase(s: MockState, id: string): CaseRecord {
    const found = s.cases.find((c) => c.id === id);
    if (!found) throw new ApiError("NOT_FOUND", 404, `case ${id} not found`);
    return found;
  }

  /** A customer reads only their own cases; an analyst reads any. */
  authorizeCase(id: string): { role: "customer" | "analyst"; actor: string } {
    if (this.state.analystSession) return { role: "analyst", actor: this.state.analystSession.username };
    const session = this.requireCustomerSession();
    const found = this.findCase(this.state, id);
    if (found.customerId !== session.customerId) throw new ApiError("NOT_FOUND", 404, `case ${id} not found`);
    return { role: "customer", actor: "customer" };
  }

  /** The analyst's case, with the handoff card (GET /api/console/cases/{id}). A customer session cannot read it. */
  getCase(id: string): CaseRecord {
    this.requireAnalyst();
    return this.findCase(this.state, id);
  }

  /** The customer's projection of their own case (GET /api/cases/{id}): no score, zone, priority, actor names or reasons. */
  getCustomerCase(id: string): CustomerCaseView {
    const session = this.requireCustomerSession();
    const c = this.findCase(this.state, id);
    if (c.customerId !== session.customerId) throw new ApiError("NOT_FOUND", 404, `case ${id} not found`);
    const left = c.deadline.creditDeadline ? daysBetween(DEMO_TODAY, c.deadline.creditDeadline) : null;
    return {
      case_id: c.id,
      language: c.language,
      status_label: statusLabel(caseStatus(c), c.language),
      created_at: c.openedAt,
      credit_deadline: c.deadline.creditDeadline,
      ruling_deadline: null,
      deadline_source: c.deadline.creditDeadline ? c.deadline.deadlineSource : null,
      deadline_countdown_days: left,
      timeline: c.events.map((e) => ({
        event_id: e.id,
        type: e.type,
        created_at: e.at,
        status_label: statusLabel(e.status, c.language),
      })),
      channels: {
        telegram: this.state.telegram[id]?.linked ?? false,
        email: this.state.emails[id]?.confirmed ?? false,
      },
    };
  }

  listCases(): CaseRecord[] {
    this.requireAnalyst();
    return this.state.cases;
  }

  /** Called by the mock agent after it blocks the card (or decides a person must review). */
  openCase(customer: MockCustomer, zone: Zone, request: string, guardrails: string[] = []): CaseRecord {
    const session = this.requireCustomerSession();
    if (session.customerId !== customer.id) throw new ApiError("UNAUTHORIZED", 401, "customer_id comes from the session only");
    return this.mutate((s) => {
      s.seq += 1;
      const id = `NOT-${String(s.seq).padStart(4, "0")}`;
      const built = buildCase({
        id, customerId: customer.id, customerName: customer.name, customer, zone, request, guardrails,
        openedAt: this.nowIso(),
      });
      s.cases.push(built);
      this.notify(s, built, caseStatus(built));
      return built;
    });
  }

  private append(s: MockState, c: CaseRecord, type: CaseEvent["type"], actor: string, status: CaseStatus, reason?: string): void {
    const current = caseStatus(c);
    // Actions that move the case (approve, close) must follow the queue even when the target equals the current
    // status; informational events (call, info, links) keep the status as it is.
    const movesCase = status !== current || type === "credit_approved" || type === "case_closed";
    if (movesCase && !TRANSITIONS[current].includes(status)) {
      throw new ApiError("INVALID_TRANSITION", 409, `${current} → ${status} is not in the case queue`);
    }
    s.seq += 1;
    c.events.push(ev(`${c.id}-E${s.seq}`, this.nowIso(), type, actor, status, reason));
    c.handoff.queue_status = status;
    if (status !== current) this.notify(s, c, status);
  }

  private audit(s: MockState, actor: string, action: string, target: string, reason?: string): void {
    s.seq += 1;
    s.audit.unshift({ id: `A-${s.seq}`, at: this.nowIso(), actor, action, target, ...(reason ? { reason } : {}) });
  }

  private notify(s: MockState, c: CaseRecord, status: CaseStatus): void {
    const channels: NotificationEntry["channels"] = [{ channel: "in_app", delivered: true }];
    if (s.telegram[c.id]?.linked) channels.push({ channel: "telegram", delivered: !this.failingChannels.has("telegram") });
    if (s.emails[c.id]?.confirmed) channels.push({ channel: "email", delivered: !this.failingChannels.has("email") });
    s.seq += 1;
    s.notifications.unshift({
      id: `N-${s.seq}`, caseId: c.id, at: this.nowIso(), status,
      title: COPY[c.language][status],
      body: `${c.id} · /case/${c.id}`, // fixed template: never the score, policy ids or the transcript
      channels,
    });
  }

  // analyst actions (spec 05 AC-03, AC-04, AC-06) ------------------------------------------------------------------

  approveCredit(caseId: string, opts: { confirmed?: boolean; reason?: string } = {}): CaseRecord {
    const analyst = this.requireAnalyst();
    if (this.state.supervised && !opts.confirmed) {
      throw new ApiError("APPROVAL_REQUIRED", 428, "supervised mode: a human must confirm this action");
    }
    return this.mutate((s) => {
      const c = this.findCase(s, caseId);
      this.append(s, c, "credit_approved", analyst.username, "resolved", opts.reason ?? "approved by analyst");
      this.audit(s, analyst.username, "approve_credit", caseId, opts.reason);
      return c;
    });
  }

  closeCase(caseId: string): CaseRecord {
    const analyst = this.requireAnalyst();
    return this.mutate((s) => {
      const c = this.findCase(s, caseId);
      this.append(s, c, "case_closed", analyst.username, "closed", "closed by analyst");
      this.audit(s, analyst.username, "close_case", caseId);
      return c;
    });
  }

  setSupervised(on: boolean): void {
    const analyst = this.requireAnalyst();
    this.mutate((s) => {
      s.supervised = on;
      this.audit(s, analyst.username, "set_supervised_mode", "system", on ? "on" : "off");
    });
  }

  // customer actions on /case/{id} (spec 13) -----------------------------------------------------------------------

  /** POST /api/cases/{id}/call-request (D-008): the date is computed here from the policy window, never by the model. */
  requestCall(caseId: string): CallRequestResult {
    const who = this.authorizeCase(caseId);
    return this.mutate((s) => {
      const c = this.findCase(s, caseId);
      this.append(s, c, "call_requested", who.actor, caseStatus(c));
      // contracts/policies.yaml contact.callback_within_business_days: 1 [assumption]
      return { event_id: c.events[c.events.length - 1].id, expected_contact_by: addBusinessDays(DEMO_TODAY, 1) };
    });
  }

  addCustomerInfo(caseId: string, text: string): void {
    const who = this.authorizeCase(caseId);
    if (!text.trim()) throw new ApiError("BAD_REQUEST", 400, "write something to add");
    this.mutate((s) => {
      const c = this.findCase(s, caseId);
      this.append(s, c, "customer_info_added", who.actor, caseStatus(c), text.trim());
    });
  }

  notificationsFor(caseId: string): NotificationEntry[] {
    this.authorizeCase(caseId);
    return this.state.notifications.filter((n) => n.caseId === caseId);
  }

  // Telegram link and e-mail (spec 13) -----------------------------------------------------------------------------

  createTelegramLink(caseId: string): { token: string; deepLink: string; expiresAt: number } {
    this.authorizeCase(caseId);
    const token = Math.random().toString(36).slice(2, 12);
    const expiresAt = this.clock() + TELEGRAM_TOKEN_TTL_MS;
    this.mutate((s) => {
      s.telegram[caseId] = { token, expiresAt, linked: false };
    });
    return { token, deepLink: `https://t.me/BOT_USERNAME?start=${token}`, expiresAt }; // bot name arrives with spec 13
  }

  /** What the Telegram webhook does on `/start <token>`. A wrong secret or an expired token processes nothing. */
  telegramStart(caseId: string, token: string, secretHeaderOk: boolean): void {
    const link = this.state.telegram[caseId];
    if (!secretHeaderOk || !link || link.token !== token || this.clock() > link.expiresAt) {
      throw new ApiError("UNAUTHORIZED", 401, "webhook rejected");
    }
    this.mutate((s) => {
      s.telegram[caseId].linked = true;
      const c = this.findCase(s, caseId);
      this.append(s, c, "telegram_linked", "customer", caseStatus(c));
    });
  }

  /** E-mail goes only to an address the user typed and confirmed, never to a dataset address. */
  confirmEmail(caseId: string, address: string): void {
    const who = this.authorizeCase(caseId);
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(address)) throw new ApiError("BAD_REQUEST", 400, "enter a valid e-mail address");
    this.mutate((s) => {
      s.emails[caseId] = { address, confirmed: true };
      const c = this.findCase(s, caseId);
      this.append(s, c, "email_confirmed", who.actor, caseStatus(c));
    });
  }
}

const SERVER_STATE = seedState();

/** One store for the browser tab. On the server it has no storage, so it always renders the seed. */
export const mockStore = new MockStore(typeof localStorage === "undefined" ? null : localStorage);
