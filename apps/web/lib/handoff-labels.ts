// Human labels for the handoff card enums (contracts/handoff.schema.json), in the UI language (spec 16 AC-06). Customers
// never see these; analysts do. The labels live in messages/console.ts; only the field labels are translated, never the
// card's facts (constitution #5).
import { consoleUi } from "../messages/console.ts";
import { formatDateTime as formatIntl, type Locale } from "./i18n.ts";

/** Per locale: handoff_reason → label. */
export const HANDOFF_REASON_LABELS: Record<Locale, Record<string, string>> = {
  en: consoleUi.en.handoffReason,
  es: consoleUi.es.handoffReason,
  pt: consoleUi.pt.handoffReason,
};

/** Per locale: copilot_proposal.action → label. */
export const COPILOT_ACTION_LABELS: Record<Locale, Record<string, string>> = {
  en: consoleUi.en.copilotAction,
  es: consoleUi.es.copilotAction,
  pt: consoleUi.pt.copilotAction,
};

const titleCase = (v: string) => v.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

/** The label for an enum value; an unknown value reads as spaced words, never as a raw identifier. */
export const handoffReasonLabel = (v: string, locale: Locale) => HANDOFF_REASON_LABELS[locale][v] ?? titleCase(v);
export const copilotActionLabel = (v: string, locale: Locale) => COPILOT_ACTION_LABELS[locale][v] ?? titleCase(v);

/** "5/10/2026, 19:04:23" (es-MX), "05/10/2026, 19:04:23" (pt-BR), "10/5/2026, 19:04:23" (en-US): always 24 h. */
export const formatDateTime = (locale: Locale, iso: string | number | Date): string =>
  formatIntl(locale, new Date(iso), {
    year: "numeric",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
/** "19:04:23", 24 h in every locale. */
export const formatTime = (locale: Locale, iso: string | number | Date): string =>
  formatIntl(locale, new Date(iso), { hour: "2-digit", minute: "2-digit", second: "2-digit" });
