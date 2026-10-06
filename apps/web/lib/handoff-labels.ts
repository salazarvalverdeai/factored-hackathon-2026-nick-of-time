// Human labels for the handoff card enums (contracts/handoff.schema.json). Customers never see these; analysts do.
export const HANDOFF_REASON_LABELS: Record<string, string> = {
  zone_human: "No bank score: a person decides",
  zone_medium: "Medium risk: confirm with the customer",
  supervised_mode: "Supervised mode: a person approves",
  amount_over_case_gate: "Amount over the approval gate",
  identity_unverified: "Identity not verified",
  clarification_exhausted: "Could not clarify the charge",
  tool_failure: "A tool failed or was not confirmed",
  language_low_confidence: "Language not understood with confidence",
  person_requested: "The customer asked for a person",
};

export const COPILOT_ACTION_LABELS: Record<string, string> = {
  approve_credit: "Approve provisional credit",
  approve_block: "Approve the card block",
  request_customer_info: "Ask the customer for more information",
  close_without_action: "Close without action",
};

const titleCase = (v: string) => v.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

/** The label for an enum value; an unknown value reads as spaced words, never as a raw identifier. */
export const handoffReasonLabel = (v: string) => HANDOFF_REASON_LABELS[v] ?? titleCase(v);
export const copilotActionLabel = (v: string) => COPILOT_ACTION_LABELS[v] ?? titleCase(v);

/** "5/10/2026, 19:04:23": es-MX, 24 h clock, the same everywhere (console and /case). */
export const formatDateTime = (iso: string | number | Date): string =>
  new Date(iso).toLocaleString("es-MX", { hour12: false, hourCycle: "h23" });
export const formatTime = (iso: string | number | Date): string =>
  new Date(iso).toLocaleTimeString("es-MX", { hour12: false, hourCycle: "h23" });
