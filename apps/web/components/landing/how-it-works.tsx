import { BadgeCheck, MessageSquareText, Scale, UserCheck, Wrench } from "lucide-react";

// The constitution's first rule as five steps (CLAUDE.md, constraint 1). Each line states what exists on main.
const STEPS = [
  {
    title: "The LLM understands",
    text: "It reads the customer's message in Spanish or Portuguese and works out what happened. It decides nothing.",
    Icon: MessageSquareText,
  },
  {
    title: "The rules decide",
    text: "A policy file the model never reads picks the action and the legal deadline. Anything it does not allow is denied.",
    Icon: Scale,
  },
  {
    title: "The tools act",
    text: "Tools block the card and open the case, only for the customer of the verified session, never one named in the text.",
    Icon: Wrench,
  },
  {
    title: "Verification confirms",
    text: "Each action is read back before the customer hears about it. Accepted is not verified.",
    Icon: BadgeCheck,
  },
  {
    title: "A person closes",
    text: "An analyst gets a handoff card with the evidence and closes every case. Provisional credit is always a human decision.",
    Icon: UserCheck,
  },
] as const;

export function HowItWorks() {
  return (
    <section aria-labelledby="how-title" className="space-y-6">
      <div className="max-w-2xl space-y-2">
        <h2 id="how-title" className="text-2xl font-semibold tracking-tight">
          How it works
        </h2>
        <p className="text-muted-foreground">Five steps, each with one job. The model understands; it never decides or acts.</p>
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
            <h3 className="font-medium">{title}</h3>
            <p className="text-sm text-muted-foreground">{text}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
