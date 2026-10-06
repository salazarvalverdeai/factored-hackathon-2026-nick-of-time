"use client";

// "How I decided", inline in each assistant message (spec 07 AC-16): the turn's tool calls on AI Elements
// `chain-of-thought`, each with its status and a one-line result. Open while the turn runs, so every step shows as it
// happens; collapsed to one line once the reply is done ("Revisó tus cargos, aplicó la regla y abrió el caso · 4
// pasos"), and a click opens it again. A step opens the shared right panel (AC-15). Requested is never shown as verified.
import { CheckIcon, ListChecksIcon, LoaderCircleIcon, type LucideIcon, XIcon } from "lucide-react";
import { forwardRef, useState } from "react";
import { ChainOfThought, ChainOfThoughtHeader, ChainOfThoughtStep } from "@/components/ai-elements/chain-of-thought";
import { Shimmer } from "@/components/ai-elements/shimmer";
import { Collapse, DrawCheck } from "@/components/chat/motion";
import { StateBadge } from "@/components/chat/tool-cards";
import { type ActionCard, TOOL_STATUS_WORDS, type ToolEvent, type VerdictCard, customerText } from "@/lib/chat-stream";
import { stepsSummary } from "@/lib/chat-reveal";
import { CHAT_STRINGS as S } from "@/lib/chat-strings";
import type { Language } from "@/lib/types";
import { cn } from "@/lib/utils";

const Spinner = forwardRef<SVGSVGElement, React.ComponentProps<typeof LoaderCircleIcon>>(({ className, ...props }, ref) => (
  <LoaderCircleIcon ref={ref} className={cn(className, "text-primary motion-safe:animate-spin")} {...props} />
));
Spinner.displayName = "Spinner";
// The finished step's check is drawn with its stroke (spec 07 AC-26).
const Done = (({ className }: { className?: string }) => <DrawCheck className={cn(className, "text-brand-teal dark:text-teal-300")} />) as unknown as LucideIcon;
const Failed = forwardRef<SVGSVGElement, React.ComponentProps<typeof XIcon>>(({ className, ...props }, ref) => (
  <XIcon ref={ref} className={cn(className, "text-destructive")} {...props} />
));
Failed.displayName = "Failed";

const ICON: Record<ToolEvent["status"], LucideIcon> = { running: Spinner as LucideIcon, done: Done, failed: Failed as LucideIcon };

const link = "text-primary underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-ring rounded-sm";

export function TurnSteps({
  tools,
  progress = [],
  running,
  lang,
  onOpenTool,
  onOpenRule,
}: {
  tools: readonly ToolEvent[];
  /** Live progress labels, the steps of a turn whose api sends no tool events. */
  progress?: readonly string[];
  running: boolean;
  lang: Language;
  onOpenTool?: (tool: ToolEvent) => void;
  onOpenRule?: (card: VerdictCard, tool: ToolEvent) => void;
}) {
  // Open while the turn runs; once it ends the block collapses (a height animation) and the customer may open it again.
  const [userOpen, setUserOpen] = useState<boolean | null>(null);
  if (tools.length === 0 && progress.length === 0) return null;
  const open = running || (userOpen ?? false);
  const count = tools.length || progress.length;
  const header = running ? (
    <Shimmer as="span" duration={1.6}>{`${S.working[lang]} · ${S.steps[lang](count)}`}</Shimmer>
  ) : tools.length ? (
    stepsSummary(tools, lang)
  ) : (
    `${S.howDecided[lang]} · ${S.steps[lang](count)}`
  );
  return (
    <ChainOfThought open={open} onOpenChange={(o) => !running && setUserOpen(o)} className="max-w-none space-y-0 rounded-xl border bg-card px-3 py-2.5" data-slot="turn-steps">
      <ChainOfThoughtHeader icon={running ? ListChecksIcon : CheckIcon} className="text-left">
        {header}
      </ChainOfThoughtHeader>
      <Collapse open={open}>
        <div className="space-y-3 pt-3">
        {tools.length
          ? tools.map((t) => {
              const actions = t.cards.filter((c): c is ActionCard => c.type === "action");
              const verdict = t.cards.find((c): c is VerdictCard => c.type === "verdict");
              return (
                <ChainOfThoughtStep
                  key={t.id}
                  icon={ICON[t.status]}
                  status={t.status === "running" ? "active" : "complete"}
                  label={
                    <button type="button" onClick={() => onOpenTool?.(t)} disabled={!onOpenTool} className="rounded-sm text-left text-foreground focus-visible:outline-2 focus-visible:outline-ring disabled:cursor-default">
                      {customerText(t.title)}
                      <span className="sr-only">: {TOOL_STATUS_WORDS[t.status][lang]}</span>
                    </button>
                  }
                  description={
                    t.summary || actions.length || verdict ? (
                      <span className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
                        {t.summary ? <span>{customerText(t.summary)}</span> : null}
                        {actions.map((a, i) => (
                          <StateBadge key={`${a.tool}-${i}`} card={a} lang={lang} />
                        ))}
                        {verdict && onOpenRule ? (
                          <button type="button" className={link} onClick={() => onOpenRule(verdict, t)}>
                            · {S.rule[lang]}
                          </button>
                        ) : t.status !== "running" && onOpenTool && !verdict ? (
                          <button type="button" className={link} onClick={() => onOpenTool(t)}>
                            · {S.detail[lang]}
                          </button>
                        ) : null}
                      </span>
                    ) : null
                  }
                />
              );
            })
          : progress.map((label, i) => (
              <ChainOfThoughtStep
                key={`${i}-${label}`}
                icon={running && i === progress.length - 1 ? ICON.running : ICON.done}
                status={running && i === progress.length - 1 ? "active" : "complete"}
                label={<span className="text-foreground">{customerText(label)}</span>}
              />
            ))}
        </div>
      </Collapse>
    </ChainOfThought>
  );
}
