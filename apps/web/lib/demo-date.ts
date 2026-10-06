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
