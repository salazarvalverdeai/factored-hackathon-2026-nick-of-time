// Domain types shared by the mock API, the API client and the pages.
// Shapes follow contracts/handoff.schema.json and the case queue in contracts/policies.yaml.
// Spec 01 (integration contract) is not merged yet: when it lands, regenerate these from its stubs [assumption].

export type Zone = "high" | "medium" | "human";
export type Language = "es" | "pt";
export type CaseStatus = "new" | "verification" | "review" | "resolved" | "closed";
export type Priority = "high" | "normal" | "low";

export interface Customer {
  id: string;
  name: string;
  country: "MX" | "AR" | "BR";
  product: "debit" | "credit";
  language: Language;
  /** Simulated bank fraud_score [simulated]; null means the bank sent none. */
  fraudScore: number | null;
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

export interface Receipt {
  caseId: string;
  time: string; // HH:MM
  deadline: Deadline;
  aiDid: string[];
  personWillDo: string[];
}

export interface AgentReply {
  text: string;
  trace: TraceStep[];
  guardrails: string[];
  receipt?: Receipt;
  deny?: boolean;
  awaitingConfirmation?: boolean;
}
