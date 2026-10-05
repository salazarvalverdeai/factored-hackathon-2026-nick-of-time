// Simulated data [simulated]: nothing here comes from the dataset. It exists so the pages work without the backend.
import type { DemoCustomer, MockCustomer } from "../types.ts";

/** INTERNAL bank-side records, with the score. Only the store and the scripted agent read this list. */
export const CUSTOMERS: MockCustomer[] = [
  { id: "demo-ana", name: "Ana (MX · debit)", country: "MX", product: "debit", language: "es", last4: "4417", fraudScore: 62 },
  { id: "demo-carlos", name: "Carlos (AR · credit)", country: "AR", product: "credit", language: "es", last4: "5521", fraudScore: 38 },
  { id: "demo-beatriz", name: "Beatriz (BR · credit)", country: "BR", product: "credit", language: "pt", last4: "9034", fraudScore: null },
];

const DEMO_META: Record<string, Pick<DemoCustomer, "segment" | "scenario">> = {
  "demo-ana": { segment: "mass", scenario: "unrecognized charge" },
  "demo-carlos": { segment: "premium", scenario: "wrongful charge" },
  "demo-beatriz": { segment: "mass", scenario: "unrecognized charge · Portuguese" },
};

/** What GET /api/demo/customers returns (spec 01 §6.2): no score, no zone. The scenario text is neutral on purpose. */
export const DEMO_CUSTOMERS: DemoCustomer[] = CUSTOMERS.map((c) => ({
  customer_id: c.id,
  display_name: c.name,
  country: c.country,
  language: c.language,
  ...DEMO_META[c.id],
}));

/** Mock analyst accounts. Real login is Amazon Cognito in spec 05 (ADR 0017). */
export const ANALYSTS = [
  { username: "freddy", displayName: "Freddy" },
  { username: "gianmarco", displayName: "GianMarco" },
  { username: "diego", displayName: "Diego" },
  { username: "judge", displayName: "Judge" },
];

/** Legal deadline rules known today (CLAUDE.md business rules). Anything else stays null until spec 02. */
export const DEADLINE_RULES: Record<string, { businessDays: number | null; source: string }> = {
  "MX:debit": { businessDays: 2, source: "Banxico 3/2012 — provisional credit by business day 2" },
  "AR:credit": { businessDays: 10, source: "BCRA — 10 business days" },
  "BR:credit": { businessDays: null, source: "CMN 4.860 — days pending the policy engine (spec 02)" },
};
