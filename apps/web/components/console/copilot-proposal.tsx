"use client";

// The copilot proposal in plain words, with a button that carries it out through the existing analyst action. The
// copilot only proposes: the analyst presses, then confirms; supervised mode adds its own second confirmation
// (spec 08 AC-05). Provisional credit is always a human decision (constitution #6). Labels follow the UI language
// (spec 16 AC-06); the proposal's own text is shown as the api sent it.
import { Lightbulb } from "lucide-react";
import { Fragment, type ReactNode, useState } from "react";
import { useLocale, useT } from "@/components/i18n-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { AnalystActionName, ConsoleAction } from "@/lib/console-actions";
import type { CopilotProposal as Proposal } from "@/lib/console-api";
import { proposalAction, proposalElsewhere, proposalWords } from "@/lib/console-view";

/** A translated sentence with `{name}` placeholders filled by React nodes (bold action, mono case id). */
function rich(text: string, nodes: Record<string, ReactNode>): ReactNode {
  return text.split(/\{(\w+)\}/g).map((part, i) => (i % 2 ? <Fragment key={i}>{nodes[part] ?? `{${part}}`}</Fragment> : part));
}

export function CopilotProposal({
  caseId,
  proposal,
  offered,
  busy,
  confirming,
  reason,
  onReason,
  onRun,
}: {
  caseId: string;
  proposal: Proposal;
  offered: ConsoleAction[];
  busy: boolean;
  /** The approval waiting for its supervised-mode second click, if any. */
  confirming: AnalystActionName | null;
  reason: string;
  onReason: (reason: string) => void;
  onRun: (action: AnalystActionName, confirmed?: boolean) => void;
}) {
  const t = useT();
  const { locale } = useLocale();
  const words = proposalWords(proposal, locale);
  const action = proposalAction(proposal, offered);
  const [step, setStep] = useState<{ caseId: string; open: boolean }>({ caseId, open: false });
  const open = step.caseId === caseId && step.open;
  const supervisedStep = action && confirming === action.action;
  const actionLabel = action ? t(`console.actions.${action.action}`) : "";

  return (
    <section aria-label={t("console.proposal.aria")} className="space-y-2 rounded-xl border border-brand-violet/40 bg-brand-violet/5 p-3" data-slot="copilot-proposal">
      <h3 className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        <Lightbulb aria-hidden className="size-4 text-brand-violet" />
        {t("console.proposal.title")}
      </h3>
      <p className="text-base font-medium">{words.title}</p>
      {words.text ? <p className="text-sm text-muted-foreground">{words.text}</p> : null}

      {!action ? (
        <p className="text-xs text-muted-foreground">{proposalElsewhere(proposal.action, locale)}</p>
      ) : supervisedStep ? (
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label={t("console.proposal.supervisedAria")}>
          <p className="w-full text-sm">{t("console.proposal.supervisedOnceMore")}</p>
          <Button size="sm" disabled={busy} onClick={() => onRun(action.action, true)}>
            {t("console.detail.confirmApproval")}
          </Button>
        </div>
      ) : open ? (
        <div className="space-y-2 rounded-lg border bg-background p-2" role="group" aria-label={t("console.proposal.confirmAria")}>
          <p className="text-sm">
            {rich(t("console.proposal.aboutTo"), {
              action: <b className="font-medium">{actionLabel.toLowerCase()}</b>,
              id: <span className="font-mono">{caseId}</span>,
            })}
          </p>
          {action.needsReason ? (
            <label className="block text-xs">
              {t("console.detail.reason")}
              <Input value={reason} onChange={(e) => onReason(e.target.value)} placeholder={t("console.detail.reasonPlaceholder")} />
            </label>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              disabled={busy || (action.needsReason && !reason.trim())}
              onClick={() => {
                setStep({ caseId, open: false });
                onRun(action.action);
              }}
            >
              {t("console.proposal.confirm")}
            </Button>
            <Button size="sm" variant="outline" onClick={() => setStep({ caseId, open: false })}>
              {t("console.proposal.cancel")}
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          <Button size="sm" disabled={busy} onClick={() => setStep({ caseId, open: true })}>
            {actionLabel}
          </Button>
          <p className="self-center text-xs text-muted-foreground">{t("console.proposal.orAnother")}</p>
        </div>
      )}
    </section>
  );
}
