const MONTHS: Record<string, string[]> = {
  es: ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"],
  pt: ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"],
};

/** "Fecha de la demo: 1 de junio de 2026" (es) / "Data da demo: 1 de junho de 2026" (pt), from a raw YYYY-MM-DD. */
export function demoDateLabel(iso: string, lang: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return iso;
  const l = lang === "pt" ? "pt" : "es";
  return `${l === "pt" ? "Data da demo" : "Fecha de la demo"}: ${Number(m[3])} de ${MONTHS[l][Number(m[2]) - 1]} de ${m[1]}`;
}

/** A real-clock instant in a tool text: "2026-10-06 01:00 UTC", "2026-10-06T01:00:00Z". Meaningless next to replay dates. */
const WALL_CLOCK = /[,;]?\s*\(?\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?\s?(?:Z|UTC)?\)?/g;

/** In replay the issued and verified wall-clock times are the real clock, not the demo date: drop them from a fact. */
export function withoutWallClock(text: string): string {
  return text.replace(WALL_CLOCK, "").replace(/\s{2,}/g, " ").trim();
}
