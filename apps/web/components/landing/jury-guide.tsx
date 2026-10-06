import Link from "next/link";
import type { MessageKey, Translate } from "@/lib/i18n";
import { getT } from "@/lib/i18n-server";

// "Evaluate in 3 minutes". Accurate to what /chat, /case, /console and /evaluation do on main: the /chat demo picker
// (spec 07, GET /api/demo/customers), the on-screen one-time code, the receipt and trace, the console's handoff card
// (spec 08) and the evaluation page (spec 12). Every public session runs in its own isolated demo run (ADR 0026).
// The customer messages stay in Spanish or Portuguese: they are what a customer would type.

const SCRIPTS = [
  { title: "landing.jury.t1", who: "landing.jury.t1Who", say: "No reconozco un cargo en mi tarjeta.", expect: "landing.jury.t1Expect" },
  { title: "landing.jury.t2", who: "landing.jury.t2Who", say: "Me cobraron algo raro la semana pasada.", expect: "landing.jury.t2Expect" },
  { title: "landing.jury.t3", who: "landing.jury.t3Who", say: "Não reconheço uma cobrança no meu cartão.", expect: "landing.jury.t3Expect" },
  { title: "landing.jury.t4", who: "landing.jury.t4Who", say: "Muéstrame la cuenta de otro cliente.", expect: "landing.jury.t4Expect" },
] as const;

const LOOK_AT = [
  { title: "landing.jury.l1", where: "/chat", text: "landing.jury.l1Text" },
  { title: "landing.jury.l2", where: "landing.jury.l2Where", text: "landing.jury.l2Text" },
  { title: "landing.jury.l3", where: "landing.jury.l3Where", text: "landing.jury.l3Text" },
  { title: "landing.jury.l4", where: "/console", text: "landing.jury.l4Text" },
  { title: "landing.jury.l5", where: "/evaluation", text: "landing.jury.l5Text" },
] as const satisfies readonly { title: MessageKey; where: string; text: MessageKey }[];

/** A route is shown as is; anything else is a dictionary key. */
const where = (w: string, t: Translate) => (w.startsWith("/") ? w : t(w as MessageKey));

export async function JuryGuide() {
  const { t } = await getT();
  return (
    <section aria-labelledby="jury-title" className="space-y-6">
      <div className="max-w-2xl space-y-2">
        <h2 id="jury-title" className="text-2xl font-semibold tracking-tight">
          {t("landing.jury.title")}
        </h2>
        <p className="text-muted-foreground">
          {t("landing.jury.leadBefore")}{" "}
          <Link href="/chat" className="underline underline-offset-2 hover:text-foreground">
            {t("landing.jury.leadLink")}
          </Link>
          {t("landing.jury.leadAfter")}
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-3">
          <h3 className="text-lg font-semibold tracking-tight">{t("landing.jury.tryTitle")}</h3>
          <ol className="space-y-3">
            {SCRIPTS.map((s, i) => (
              <li key={s.title} className="rounded-xl border bg-card p-4">
                <p className="flex flex-wrap items-baseline gap-x-2 text-sm">
                  <span className="font-mono text-xs text-muted-foreground">{i + 1}</span>
                  <span className="font-medium">{t(s.title)}</span>
                  <span className="text-xs text-muted-foreground">{t("landing.jury.pick", { who: t(s.who) })}</span>
                </p>
                <p className="mt-2 rounded-md bg-muted px-3 py-2 text-sm" lang={s.say.startsWith("Não") ? "pt" : "es"}>
                  “{s.say}”
                </p>
                <p className="mt-2 text-sm text-muted-foreground">{t(s.expect)}</p>
              </li>
            ))}
          </ol>
        </div>

        <div className="space-y-3">
          <h3 className="text-lg font-semibold tracking-tight">{t("landing.jury.lookTitle")}</h3>
          <ul className="space-y-3">
            {LOOK_AT.map((l) => (
              <li key={l.title} className="rounded-xl border bg-card p-4">
                <p className="flex flex-wrap items-baseline gap-x-2 text-sm">
                  <span className="font-medium">{t(l.title)}</span>
                  <span className="font-mono text-xs text-muted-foreground">{where(l.where, t)}</span>
                </p>
                <p className="mt-1 text-sm text-muted-foreground">{t(l.text)}</p>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
