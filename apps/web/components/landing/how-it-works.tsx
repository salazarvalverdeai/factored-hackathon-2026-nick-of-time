import { BadgeCheck, MessageSquareText, Scale, UserCheck, Wrench } from "lucide-react";
import { getT } from "@/lib/i18n-server";

// The constitution's first rule as five steps (CLAUDE.md, constraint 1). Each line states what exists on main.
const STEPS = [
  { title: "landing.how.s1", text: "landing.how.s1Text", Icon: MessageSquareText },
  { title: "landing.how.s2", text: "landing.how.s2Text", Icon: Scale },
  { title: "landing.how.s3", text: "landing.how.s3Text", Icon: Wrench },
  { title: "landing.how.s4", text: "landing.how.s4Text", Icon: BadgeCheck },
  { title: "landing.how.s5", text: "landing.how.s5Text", Icon: UserCheck },
] as const;

export async function HowItWorks() {
  const { t } = await getT();
  return (
    <section aria-labelledby="how-title" className="space-y-6">
      <div className="max-w-2xl space-y-2">
        <h2 id="how-title" className="text-2xl font-semibold tracking-tight">
          {t("landing.how.title")}
        </h2>
        <p className="text-muted-foreground">{t("landing.how.lead")}</p>
      </div>
      <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {STEPS.map(({ title, text, Icon }, i) => (
          <li key={title} className="flex flex-col gap-2 rounded-xl border bg-card p-4">
            <div className="flex items-center gap-2">
              <span className="flex size-7 shrink-0 items-center justify-center rounded-full border border-brand-violet/60 font-mono text-xs">
                {i + 1}
              </span>
              <Icon aria-hidden="true" className={`size-4 ${i === 3 ? "text-brand-teal dark:text-teal-300" : "text-muted-foreground"}`} />
            </div>
            <h3 className="font-medium">{t(title)}</h3>
            <p className="text-sm text-muted-foreground">{t(text)}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
