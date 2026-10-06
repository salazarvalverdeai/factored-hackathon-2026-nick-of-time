"use client";

// The copilot proposal in plain words, with a button that carries it out through the existing analyst action. The
// copilot only proposes: the analyst presses, then confirms; supervised mode adds its own second confirmation
// (spec 08 AC-05). Provisional credit is always a human decision (constitution #6).
import { Lightbulb } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { AnalystActionName, ConsoleAction } from "@/lib/console-actions";
import type { CopilotProposal as Proposal } from "@/lib/console-api";
import { PROPOSAL_ELSEWHERE, proposalAction, proposalWords } from "@/lib/console-view";

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
  const words = proposalWords(proposal);
  const action = proposalAction(proposal, offered);
  const [step, setStep] = useState<{ caseId: string; open: boolean }>({ caseId, open: false });
  const open = step.caseId === caseId && step.open;
  const supervisedStep = action && confirming === action.action;

  return (
    <section aria-label="Copilot proposal" className="space-y-2 rounded-xl border border-brand-violet/40 bg-brand-violet/5 p-3" data-slot="copilot-proposal">
      <h3 className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        <Lightbulb aria-hidden className="size-4 text-brand-violet" />
        Copilot proposal · you decide
      </h3>
      <p className="text-base font-medium">{words.title}</p>
      {words.text ? <p className="text-sm text-muted-foreground">{words.text}</p> : null}

      {!action ? (
        <p className="text-xs text-muted-foreground">{PROPOSAL_ELSEWHERE[proposal.action] ?? "No console action carries out this proposal."}</p>
      ) : supervisedStep ? (
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Supervised confirmation">
          <p className="w-full text-sm">Supervised mode is on: confirm once more.</p>
          <Button size="sm" disabled={busy} onClick={() => onRun(action.action, true)}>
            Confirm approval (supervised mode)
          </Button>
        </div>
      ) : open ? (
        <div className="space-y-2 rounded-lg border bg-background p-2" role="group" aria-label="Confirm the decision">
          <p className="text-sm">
            You are about to <b className="font-medium">{action.label.toLowerCase()}</b> on <span className="font-mono">{caseId}</span>. It is
            recorded with your user.
          </p>
          {action.needsReason ? (
            <label className="block text-xs">
              Reason (recorded with your user)
              <Input value={reason} onChange={(e) => onReason(e.target.value)} placeholder="Why this decision" />
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
              Confirm
            </Button>
            <Button size="sm" variant="outline" onClick={() => setStep({ caseId, open: false })}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          <Button size="sm" disabled={busy} onClick={() => setStep({ caseId, open: true })}>
            {action.label}
          </Button>
          <p className="self-center text-xs text-muted-foreground">or choose another action below</p>
        </div>
      )}
    </section>
  );
}
