// Content of the home page (`/`). Every figure is copied from docs/problem_in_numbers.md with its label and its source;
// `lib/landing.test.ts` fails if a number here does not appear in that document. No figure is computed or rounded here.
// The words around the figures are dictionary keys (messages/landing.ts, spec 16 AC-06); the figures and sources are not.
import { type MessageKey, type Translate, translator } from "./i18n.ts";

export type FigureLabel = "data" | "external" | "assumption" | "simulated" | "projected";

export interface Source {
  label: string;
  href: string;
}

const REPO = "https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/blob/main";
const query = (file: string, label: string): Source => ({ label, href: `${REPO}/queries/pitch/${file}` });

export const PROBLEM_DOC: Source = { label: "docs/problem_in_numbers.md", href: `${REPO}/docs/problem_in_numbers.md` };
export const POLICIES: Source = { label: "contracts/policies.yaml", href: `${REPO}/contracts/policies.yaml` };

/** One side of a comparison, e.g. complaint contacts against the whole bank. */
export interface Side {
  name: MessageKey;
  value: string;
  /** The value's words, e.g. "{n} days", filled with `value`. */
  valueKey?: MessageKey;
  note?: string;
  /** Animated once with the number ticker; the text above is what renders without JavaScript. */
  ticker?: { value: number; decimals: number; suffix: string };
}

export interface Stat {
  id: string;
  title: MessageKey;
  sides: Side[];
  detail: MessageKey;
  label: FigureLabel;
  sources: Source[];
  /** A second, labeled caveat on the same figure (constitution #8). */
  caveat?: { text: MessageKey; label: FigureLabel };
}

/** The headline: first-contact resolution, the main goal of the system (ADR 0014). Doc §2. */
export const FCR: Stat = {
  id: "fcr",
  title: "landing.stats.fcrTitle",
  sides: [
    {
      name: "landing.stats.complaintContacts",
      value: "43.6%",
      note: "CI95 43.3–43.9, n = 117,021",
      ticker: { value: 43.6, decimals: 1, suffix: "%" },
    },
    { name: "landing.stats.wholeBank", value: "76.6%", note: "n = 686,296", ticker: { value: 76.6, decimals: 1, suffix: "%" } },
  ],
  detail: "landing.stats.fcrDetail",
  label: "data",
  sources: [query("p02_fcr_complaint_vs_bank.sql", "query p02")],
};

/** Doc §1 to §4. */
export const STATS: Stat[] = [
  {
    id: "share",
    title: "landing.stats.shareTitle",
    sides: [{ name: "landing.stats.w3Charges", value: "36.4%" }],
    detail: "landing.stats.shareDetail",
    label: "data",
    sources: [query("p01_w3_share_complaints.sql", "query p01")],
  },
  {
    id: "follow-up",
    title: "landing.stats.followTitle",
    sides: [
      { name: "landing.stats.complaintContacts", value: "63.0%" },
      { name: "landing.stats.wholeBank", value: "34.8%" },
    ],
    detail: "landing.stats.followDetail",
    label: "data",
    sources: [query("p03_complaint_follow_up.sql", "query p03")],
  },
  {
    id: "duration",
    title: "landing.stats.durationTitle",
    sides: [
      { name: "landing.stats.complaintContacts", value: "7.18 min" },
      { name: "landing.stats.wholeBank", value: "4.85 min" },
    ],
    detail: "landing.stats.durationDetail",
    label: "data",
    sources: [query("p04_complaint_duration_vs_bank.sql", "query p04")],
  },
  {
    id: "precision",
    title: "landing.stats.precisionTitle",
    sides: [
      { name: "landing.stats.precisionHigh", value: "100%" },
      { name: "landing.stats.precisionBand", value: "53.6%" },
    ],
    detail: "landing.stats.precisionDetail",
    label: "data",
    sources: [query("p08_fraud_score_thresholds.sql", "query p08")],
    caveat: { text: "landing.stats.precisionCaveat", label: "assumption" },
  },
  {
    id: "human-zone",
    title: "landing.stats.humanTitle",
    sides: [{ name: "landing.stats.humanSide", value: "45.0%" }],
    detail: "landing.stats.humanDetail",
    label: "data",
    sources: [query("p08_fraud_score_thresholds.sql", "query p08"), query("p07_fraud_per_month.sql", "query p07")],
  },
];

/** Doc §2 limits: the median resolution time, which matters only against the legal deadlines. */
export const RESOLUTION: Stat = {
  id: "resolution",
  title: "landing.stats.resolutionTitle",
  sides: [{ name: "landing.stats.w3Charges", value: "16", valueKey: "landing.stats.days" }],
  detail: "landing.stats.resolutionDetail",
  label: "data",
  sources: [query("p06_w3_resolution_days.sql", "query p06")],
};

export interface Deadline {
  /** The country code; `countryKey` adds the product where it matters. */
  country: string;
  countryKey?: MessageKey;
  obligation: MessageKey;
  source: Source;
}

// Doc §5, `[external]`, linked to the official text recorded in contracts/policies.yaml (source_url, ADR 0019).
// The obligations keep the doc's figures; AR says "resolve" only, because policies.yaml promises no credit date there.
export const DEADLINES: Deadline[] = [
  {
    country: "MX",
    countryKey: "landing.deadlines.mxDebit",
    obligation: "landing.deadlines.mxDebitText",
    source: {
      label: "Banxico Circular 3/2012, art. 19 Bis 3",
      href: "https://www.banxico.org.mx/marco-normativo/normativa-emitida-por-el-banco-de-mexico/circular-3-2012/%7B4E0281A4-7AD8-1462-BC79-7F2925F3171D%7D.pdf",
    },
  },
  {
    country: "MX",
    countryKey: "landing.deadlines.mxCredit",
    obligation: "landing.deadlines.mxCreditText",
    source: { label: "LTOSF art. 23", href: "https://www.ordenjuridico.gob.mx/Documentos/Federal/pdf/wo46.pdf" },
  },
  {
    country: "AR",
    obligation: "landing.deadlines.arText",
    source: { label: "BCRA", href: "https://www.bcra.gob.ar/archivos/Pdfs/texord/t-pusf.pdf" },
  },
  {
    country: "CO",
    obligation: "landing.deadlines.coText",
    source: {
      label: "SFC",
      href: "https://www.superfinanciera.gov.co/preguntas-frecuentes/3/3-derechos-de-peticion-ante-entidades-vigiladas/",
    },
  },
  {
    country: "BR",
    obligation: "landing.deadlines.brText",
    source: {
      label: "Resolução CMN 4.860 (2020)",
      href: "https://www.bcb.gov.br/estabilidadefinanceira/exibenormativo?tipo=Resolu%C3%A7%C3%A3o%20CMN&numero=4860",
    },
  },
];

/** Every number written in a piece of landing text, as it is spelled (e.g. "117,021", "4.860", "19"). */
export function numbersIn(text: string): string[] {
  return text.match(/\d[\d,]*(?:\.\d+)?/g)?.map((n) => n.replace(/,$/, "")) ?? [];
}

/** A side's value as shown: the figure, with its words when it has them ("16 days"). */
export function sideValue(side: Side, t: Translate): string {
  return side.valueKey ? t(side.valueKey, { n: side.value }) : side.value;
}

/** A deadline row's country as shown ("MX, debit card" or "AR"). */
export function deadlineCountry(d: Deadline, t: Translate): string {
  return d.countryKey ? t(d.countryKey) : d.country;
}

/** All the texts of the page that carry figures in one language, for the test against the doc. */
export function figureTexts(t: Translate = translator("en")): string[] {
  const stats = [FCR, ...STATS, RESOLUTION];
  return [
    ...stats.flatMap((s) => [
      t(s.title),
      t(s.detail),
      s.caveat ? t(s.caveat.text) : "",
      ...s.sides.flatMap((d) => [t(d.name), sideValue(d, t), d.note ?? ""]),
    ]),
    ...DEADLINES.flatMap((d) => [deadlineCountry(d, t), t(d.obligation), d.source.label]),
  ];
}
