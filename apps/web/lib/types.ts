// Domain types shared by the mock API, the API client and the pages.
// Shapes follow spec 01 §6.2 and packages/nick_of_time/contracts.py (customer projections: no score, zone, priority or
// policy ids), contracts/handoff.schema.json (analyst only) and the case queue in contracts/policies.yaml.
// Customer-facing types use the contract's snake_case names; the mock's internal records keep camelCase.

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
  deadlineSource: string;
}

export interface CaseEvent {
  id: string;
  at: string; // ISO timestamp
  type:
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
  type: CaseEvent["type"];
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
  customerId: string;
  expiresAt: number; // epoch ms
}

export interface AnalystSession {
  username: string;
  displayName: string;
}

export interface TraceStep {
  step: string;
  result: string;
  kind: "ok" | "accepted" | "verified" | "guardrail" | "deny";
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
}

export interface Suggestion {
  label: string;
  /** What is sent when the chip is chosen. */
  text: string;
}

export interface AgentReply {
  text: string;
  trace: TraceStep[];
  guardrails: string[];
  receipt?: Receipt;
  suggestions?: Suggestion[];
  deny?: boolean;
  awaitingConfirmation?: boolean;
}
