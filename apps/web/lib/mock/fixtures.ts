// Simulated data [simulated]: nothing here comes from the dataset. It exists so the pages work without the backend.
import type { Customer } from "../types.ts";

export const CUSTOMERS: Customer[] = [
  { id: "demo-ana", name: "Ana (MX · debit)", country: "MX", product: "debit", language: "es", fraudScore: 62 },
  { id: "demo-carlos", name: "Carlos (AR · credit)", country: "AR", product: "credit", language: "es", fraudScore: 38 },
  { id: "demo-beatriz", name: "Beatriz (BR · credit)", country: "BR", product: "credit", language: "pt", fraudScore: null },
];

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
