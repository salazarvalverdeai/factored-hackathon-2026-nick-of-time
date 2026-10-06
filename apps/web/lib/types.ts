// Domain types shared by the mock API, the API client and the pages.
// Shapes follow spec 01 §6.2 and packages/nick_of_time/contracts.py (customer projections: no score, zone, priority or
// policy ids), contracts/handoff.schema.json (analyst only) and the case queue in contracts/policies.yaml.
// Customer-facing types use the contract's snake_case names; the mock's internal records keep camelCase.
import type { ToolEvent } from "./chat-stream.ts";

export type Zone = "high" | "medium" | "human";
export type Language = "es" | "pt";
export type CaseStatus = "new" | "verification" | "review" | "resolved" | "closed";
export type Priority = "normal" | "high";
export type Country = "MX" | "AR" | "BR" | "CO";

/** The mock's bank-side record of a customer. INTERNAL: it carries the fraud score, so no customer page may import it. */
export interface MockCustomer {
  id: string;
  name: string;
  country: Country;
  product: "debit" | "credit";
  language: Language;
  last4: string;
  /** Simulated bank fraud_score [simulated]; null means the bank sent none. */
  fraudScore: number | null;
}

/** What `GET /api/demo/customers` returns (spec 01 §6.2, spec 09): enough to pick a demo customer, never the score. */
export interface DemoCustomer {
  customer_id: string;
  display_name: string;
  country: Country;
  segment: "mass" | "premium";
  scenario: string;
  language: Language;
}

export interface Deadline {
  country: string;
  product: string;
  /** ISO date (YYYY-MM-DD) or null while the policy engine (spec 02) does not provide it. */
  creditDeadline: string | null;
  /** Live: the ruling date (YYYY-MM-DD), when the country's clock has one. The countdown counts to the nearer date. */
  rulingDeadline?: string | null;
  deadlineSource: string;
  /** Live: days left as the api counted them (null = no countdown). Absent in the mock, which counts from the frozen demo date. */
  daysLeft?: number | null;
}

export type CaseEventType =
  | "case_opened"
  | "card_blocked"
  | "verification_started"
  | "sent_to_review"
  | "credit_approved"
  | "case_closed"
  | "call_requested"
  | "customer_info_added"
  | "telegram_linked"
  | "email_confirmed";

export interface CaseEvent {
  id: string;
  at: string; // ISO timestamp
  type: CaseEventType;
  actor: string; // "agent", "customer" or an analyst user name
  status: CaseStatus; // status after this event: a case's status is its last event
  reason?: string;
}

export interface HandoffCard {
  case_id: string;
  language: Language;
  zone: Zone;
  handoff_reason?: string;
  request: string;
  verified_facts: { fact: string; source_id: string }[];
  actions: { tool: string; action_id: string; result: string; verified: boolean; verification_id: string }[];
  evidence: string[];
  open_questions: string[];
  copilot_proposal?: { action: string; rationale: string; requires_human: boolean };
  deadline: { country: string; product: string; credit_deadline: string | null; deadline_source: string };
  trace_id: string;
  score: number | null;
  queue_status: CaseStatus;
  guardrails_triggered: string[];
}

/** An event as the customer sees it: no actor name, no internal reason. */
export interface CustomerTimelineItem {
  event_id: string;
  /** The mock uses `CaseEventType`; the live api sends the store's event type (a string). */
  type: string;
  created_at: string; // ISO timestamp
  /** Customer-facing status after this event (messages.yaml status.label), localized. */
  status_label: string;
}

/** What `GET /api/cases/{id}` returns to a customer (D-013): no zone, priority, score, handoff, policy ids or customer id. */
export interface CustomerCaseView {
  case_id: string;
  language: Language;
  /** messages.yaml status.label for the case's last event, in the customer's language. */
  status_label: string;
  created_at: string;
  /** Raw YYYY-MM-DD dates (D-018); null when the country has no verified clock entry. */
  credit_deadline: string | null;
  ruling_deadline: string | null;
  deadline_source: string | null;
  deadline_countdown_days: number | null;
  timeline: CustomerTimelineItem[];
  channels: { telegram: boolean; email: boolean };
  /** Live only: `replay` runs on the frozen demo date, `live` on the real one. Absent in the mock (frozen date). */
  mode?: "replay" | "live";
}

/** What `POST /api/cases/{id}/call-request` returns (D-008). */
export interface CallRequestResult {
  event_id: string;
  /** YYYY-MM-DD computed by the tool from the policy window, or null when none is promised. */
  expected_contact_by: string | null;
}

/** The analyst's case (console only). */
export interface CaseRecord {
  id: string;
  customerId: string;
  customerName: string;
  language: Language;
  zone: Zone;
  priority: Priority;
  openedAt: string;
  deadline: Deadline;
  events: CaseEvent[];
  handoff: HandoffCard;
}

/** A case as the inbox lists it: enough to pick one, no handoff. `CaseRecord` (mock) satisfies it. */
export interface CaseListItem {
  id: string;
  customerName: string;
  zone: Zone;
  priority: Priority;
  deadline: Deadline;
  /** The queue status: the last event (spec 05 AC-02). */
  status: CaseStatus;
}

/** One event in the analyst's timeline. Live events do not carry the status they led to, so it is optional. */
export interface ConsoleEvent {
  id: string;
  at: string;
  type: string;
  actor: string;
  status?: CaseStatus;
  reason?: string;
}

/** The analyst's case with its handoff card (`GET /api/console/cases/{id}`). */
export interface ConsoleCase extends CaseListItem {
  customerId: string;
  language: Language;
  openedAt: string;
  events: ConsoleEvent[];
  handoff: HandoffCard;
  /** Live only: the handoff card is empty until the graph emits it (spec 05 console_case). */
  handoffEmitted?: boolean;
  /** Live only: the case's time mode (ADR 0020). The mock runs on the frozen demo date, like replay. */
  mode?: "replay" | "live";
}

export interface NotificationEntry {
  id: string;
  caseId: string;
  at: string;
  status: CaseStatus;
  title: string;
  body: string;
  channels: { channel: "in_app" | "telegram" | "email"; delivered: boolean }[];
}

export interface AuditEntry {
  id: string;
  at: string;
  actor: string;
  action: string;
  target: string;
  reason?: string;
}

export interface CustomerSession {
  /** The mock's picked customer. A live demo session has none here: the api chose the customer server-side (D-068). */
  customerId: string;
  expiresAt: number; // epoch ms
  /** Live demo: what the start screen knew (the typed name or the scenario's customer name), the session language and mode. */
  displayName?: string;
  language?: Language;
  mode?: "live" | "replay";
}

/** One scenario card of `GET /api/demo/scenarios` (spec 05 AC-15): no customer id, score or zone. */
export interface Scenario {
  scenario_id: string;
  title: string;
  country: string;
  language: Language;
  segment: string;
  customer_name: string | null;
  cases: string[];
  tags: string[];
}

export interface DemoStart {
  /** Optional, at most 40 characters; the api refuses a name that is not a plain name (422). */
  displayName?: string;
  language: Language;
  country?: "MX" | "CO" | "AR";
  /** A `scenario_id`, or "auto" to be assigned one. */
  scenario: string;
  /** "live" only for demo type C (the visitor registers a test charge, dated today); omitted, the api's default (replay). */
  mode?: "live";
  /** The picked scenario's `customer_name` (gold's first name): the web greets with it when no name is typed. Never sent. */
  customerName?: string;
}

/** `GET /api/sessions/{id}/recent-transactions` (spec 05 AC-17): the customer's latest card charges, no score or label. */
export interface RecentTransaction {
  transaction_id: string;
  date: string; // YYYY-MM-DD
  amount: number;
  currency: string;
  merchant: string | null;
  last4: string | null;
  /** A live demo run's test charge [simulated] (spec 05 AC-19). */
  synthetic: boolean;
  /** Only on the answer of a test charge: always "[simulated]". */
  label?: "[simulated]";
}

export type PersonaCharacter = "aggressive" | "passive" | "terse" | "verbose" | "confused" | "code_switching";

/** `POST /api/demo/persona` (spec 05 AC-20): a suggested first message. A draft for the composer, never sent on its own. */
export interface PersonaDraft {
  message: string;
  source: "llm" | "template";
  language: Language;
  character: PersonaCharacter;
  transaction_id: string;
  synthetic: boolean;
}

export interface AnalystSession {
  username: string;
  displayName: string;
}

/** What the pages read about who is signed in and the console's own settings: the same in mock and live mode. */
export interface SessionSnapshot {
  customerSession: CustomerSession | null;
  analystSession: AnalystSession | null;
  supervised: boolean;
  /** The actions taken in this console session (live: this browser; the case timeline holds the server's record). */
  audit: AuditEntry[];
}

export interface TraceStep {
  step: string;
  result: string;
  kind: "ok" | "in_progress" | "accepted" | "verified" | "not_confirmed" | "guardrail" | "deny";
}

/** One step label of a running agent turn (spec 04 AC-17): in progress only, never a result. */
export interface ProgressLabel {
  step: string;
  label: string;
}

/** What a chat turn may carry besides text: a chip press (`TurnAction`, spec 01 §6.4) skips the classifier. */
export interface TurnAction {
  type: "confirm" | "choose_option" | "verify_now" | "request_call" | "request_reevaluation" | "send_summary";
  value?: string;
}

/** The verified receipt (spec 01 §6.7, shape of CustomerReceipt): texts come from contracts/messages.yaml in the customer's language. */
export interface Receipt {
  case_id: string;
  language: Language;
  /** UTC ISO-8601. */
  issued_at: string;
  title: string;
  card_blocked: string | null;
  deadline: Deadline;
  /** "Credit deadline … Source …" line, or the deadline_unknown text. */
  deadline_text: string;
  what_ai_did: string;
  what_a_person_does: string;
  case_url: string;
  /** Live: the verified facts and actions of the contract's receipt, shown as they are. */
  facts?: string[];
  actions?: { label: string; state: string; verification_id?: string }[];
  /** The legal source of the deadlines, shown as a named link (never a raw URL); `url` only when the tool returned one. */
  source?: { label: string; url: string | null; verified_on: string | null };
  /** Live: the ruling date `YYYY-MM-DD`, when the country's clock has one. */
  ruling_deadline?: string | null;
}

export interface Suggestion {
  label: string;
  /** What is sent when the chip is chosen. */
  text: string;
  /** Live: an action chip sends this instead of text (skips the classifier). */
  action?: TurnAction;
  /** Live: a link chip opens this path on our own host. */
  href?: string;
}

export interface AgentReply {
  text: string;
  trace: TraceStep[];
  guardrails: string[];
  receipt?: Receipt;
  suggestions?: Suggestion[];
  deny?: boolean;
  awaitingConfirmation?: boolean;
  /** The plan the agent stated (`CustomerTurn.plan`), one line per step. */
  plan?: string[];
  /** The tool calls the turn streamed (spec 01 §6.4.1), settled: a call with no result is shown as failed. */
  tools?: ToolEvent[];
  /** The charges the turn offers (`CustomerTurn.options`, spec 01 §6.4): one card to confirm (spec 04 D-067
   *  `clarify.confirm_one`) or up to `max_candidate_transactions` to pick from. */
  options?: TurnOption[];
}

/** One charge a turn offers: the transaction id and the server's label ("USD 1,250.00 · 2026-05-31 · TIENDA X"). */
export interface TurnOption {
  id: string;
  label: string;
}
