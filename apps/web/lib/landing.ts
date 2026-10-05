// Content of the home page (`/`). Every figure is copied from docs/problem_in_numbers.md with its label and its source;
// `lib/landing.test.ts` fails if a number here does not appear in that document. No figure is computed or rounded here.

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
  name: string;
  value: string;
  note?: string;
  /** Animated once with the number ticker; the text above is what renders without JavaScript. */
  ticker?: { value: number; decimals: number; suffix: string };
}

export interface Stat {
  id: string;
  title: string;
  sides: Side[];
  detail: string;
  label: FigureLabel;
  sources: Source[];
  /** A second, labeled caveat on the same figure (constitution #8). */
  caveat?: { text: string; label: FigureLabel };
}

/** The headline: first-contact resolution, the main goal of the system (ADR 0014). Doc §2. */
export const FCR: Stat = {
  id: "fcr",
  title: "Resolved at first contact (FCR)",
  sides: [
    {
      name: "Complaint contacts",
      value: "43.6%",
      note: "CI95 43.3–43.9, n = 117,021",
      ticker: { value: 43.6, decimals: 1, suffix: "%" },
    },
    { name: "Whole bank", value: "76.6%", note: "n = 686,296", ticker: { value: 76.6, decimals: 1, suffix: "%" } },
  ],
  detail: "More than half of these contacts are not resolved the first time.",
  label: "data",
  sources: [query("p02_fcr_complaint_vs_bank.sql", "query p02")],
};

/** Doc §1 to §4. */
export const STATS: Stat[] = [
  {
    id: "share",
    title: "Share of the bank's complaints",
    sides: [{ name: "Unrecognized or wrongful charges", value: "36.4%" }],
    detail: "24,431 of 67,095 complaints, about 679 per month over 35 full months.",
    label: "data",
    sources: [query("p01_w3_share_complaints.sql", "query p01")],
  },
  {
    id: "follow-up",
    title: "Requires follow-up",
    sides: [
      { name: "Complaint contacts", value: "63.0%" },
      { name: "Whole bank", value: "34.8%" },
    ],
    detail: "Almost two in three of these contacts leave work pending.",
    label: "data",
    sources: [query("p03_complaint_follow_up.sql", "query p03")],
  },
  {
    id: "duration",
    title: "Median contact duration",
    sides: [
      { name: "Complaint contacts", value: "7.18 min" },
      { name: "Whole bank", value: "4.85 min" },
    ],
    detail: "These contacts take longer than the rest of the bank's.",
    label: "data",
    sources: [query("p04_complaint_duration_vs_bank.sql", "query p04")],
  },
  {
    id: "precision",
    title: "Precision of the bank's fraud score",
    sides: [
      { name: "Score ≥ 50", value: "100%" },
      { name: "Band 30–49", value: "53.6%" },
    ],
    detail:
      "All 1,670 transactions flagged at 50 or more were fraud, so the system acts at once there. In the 30–49 band (derived from the two thresholds) almost half are legitimate, so the customer confirms first and a person approves the block.",
    label: "data",
    sources: [query("p08_fraud_score_thresholds.sql", "query p08")],
    caveat: { text: "A precision of exactly 100% is a property of the synthetic generator.", label: "assumption" },
  },
  {
    id: "human-zone",
    title: "Frauds the score cannot decide",
    sides: [{ name: "Score below 30 or no score", value: "45.0%" }],
    detail:
      "Of the 4,316 transactions labeled as fraud, 1,052 have a score below 30 and 891 have no score at all. The handoff to a person is a main path, not an exception.",
    label: "data",
    sources: [query("p08_fraud_score_thresholds.sql", "query p08"), query("p07_fraud_per_month.sql", "query p07")],
  },
];

/** Doc §2 limits: the median resolution time, which matters only against the legal deadlines. */
export const RESOLUTION: Stat = {
  id: "resolution",
  title: "Median resolution",
  sides: [{ name: "Unrecognized or wrongful charges", value: "16 days" }],
  detail: "The same as the whole bank. Against a legal clock, the first contact has to start it and state the deadline.",
  label: "data",
  sources: [query("p06_w3_resolution_days.sql", "query p06")],
};

export interface Deadline {
  country: string;
  obligation: string;
  source: Source;
}

// Doc §5, `[external]`, linked to the official text recorded in contracts/policies.yaml (source_url, ADR 0019).
// The obligations keep the doc's figures; AR says "resolve" only, because policies.yaml promises no credit date there.
export const DEADLINES: Deadline[] = [
  {
    country: "MX, debit card",
    obligation: "Provisional credit by business day 2",
    source: {
      label: "Banxico Circular 3/2012, art. 19 Bis 3",
      href: "https://www.banxico.org.mx/marco-normativo/normativa-emitida-por-el-banco-de-mexico/circular-3-2012/%7B4E0281A4-7AD8-1462-BC79-7F2925F3171D%7D.pdf",
    },
  },
  {
    country: "MX, credit card",
    obligation: "Ruling within 45 days (180 if the charge was abroad)",
    source: { label: "LTOSF art. 23", href: "https://www.ordenjuridico.gob.mx/Documentos/Federal/pdf/wo46.pdf" },
  },
  {
    country: "AR",
    obligation: "Resolve within 10 business days",
    source: { label: "BCRA", href: "https://www.bcra.gob.ar/archivos/Pdfs/texord/t-pusf.pdf" },
  },
  {
    country: "CO",
    obligation: "Answer within 15 days",
    source: {
      label: "SFC",
      href: "https://www.superfinanciera.gov.co/preguntas-frecuentes/3/3-derechos-de-peticion-ante-entidades-vigiladas/",
    },
  },
  {
    country: "BR",
    obligation: "Ombudsman answer within 10 business days",
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

/** All the texts of the page that carry figures, for the test against the doc. */
export function figureTexts(): string[] {
  const stats = [FCR, ...STATS, RESOLUTION];
  return [
    ...stats.flatMap((s) => [s.title, s.detail, s.caveat?.text ?? "", ...s.sides.flatMap((d) => [d.name, d.value, d.note ?? ""])]),
    ...DEADLINES.flatMap((d) => [d.country, d.obligation, d.source.label]),
  ];
}
