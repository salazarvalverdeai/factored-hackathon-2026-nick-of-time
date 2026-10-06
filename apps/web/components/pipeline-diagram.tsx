"use client";

// Shared "how it's built" flow of /data, /evaluation and /analytics (spec 12 AC-07, AC-09). Numbered steps run left
// to right from lg and top to bottom below it, so 390 px never scrolls sideways. Every step takes keyboard focus and
// shows its detail in the same tooltip as the charts; "Detail →" opens the side panel with its method, source and spec.
import { FOCUS, TipBody, useTip } from "@/app/analytics/charts";
import { DetailButton } from "@/components/detail-button";
import type { CSSProperties } from "react";
import type { PipelineStep } from "@/lib/pipelines";

const TONE = { source: "border-t-muted-foreground/60", layer: "border-t-primary", output: "border-t-brand-teal" } as const;
const ARROW = "pointer-events-none absolute select-none text-sm leading-none text-muted-foreground";

function Node({ step, n, bind, small = false }: { step: PipelineStep; n?: number; bind: ReturnType<typeof useTip>["bind"]; small?: boolean }) {
  return (
    <div
      tabIndex={0}
      role="group"
      aria-label={`${step.title}: ${step.lines.join(" ")} ${step.tip.map(([k, v]) => `${k}: ${v}`).join("; ")}`}
      className={`h-full rounded-md border border-t-2 bg-background/60 ${small ? "p-2.5" : "p-3"} ${TONE[step.tone ?? "layer"]} ${FOCUS}`}
      {...bind(<TipBody title={step.title} rows={step.tip} note={step.note} />)}
    >
      <p className="flex items-baseline gap-1.5 text-sm font-medium [overflow-wrap:anywhere]">
        {n ? <span className="font-mono text-xs text-muted-foreground">{n}</span> : null}
        {step.title}
      </p>
      {step.lines.map((line) => (
        <p key={line} className="mt-0.5 text-xs text-muted-foreground [overflow-wrap:anywhere]">
          {line}
        </p>
      ))}
      <DetailButton title={step.title} detail={step.detail} className="mt-1 inline-block text-xs" />
    </div>
  );
}

/** `outputs` fan out of the last step as a row of smaller nodes under the flow (e.g. what reads gold). */
export function PipelineDiagram({ label, steps, outputs = [], outputsTitle = "Read by", columns }: {
  label: string;
  steps: PipelineStep[];
  outputs?: PipelineStep[];
  outputsTitle?: string;
  columns?: number;
}) {
  const { bind, node } = useTip();
  const cols = columns ?? steps.length;
  // From lg the arrow points right, except at the end of a row; below lg it points down (also into the outputs).
  const arrow = (i: number) => (
    <>
      {i < steps.length - 1 || outputs.length ? <span aria-hidden className={`${ARROW} -bottom-3.5 left-1/2 -translate-x-1/2 lg:hidden`}>↓</span> : null}
      {i < steps.length - 1 && (i + 1) % cols ? <span aria-hidden className={`${ARROW} top-1/2 -right-3.5 hidden -translate-y-1/2 lg:block`}>→</span> : null}
    </>
  );
  return (
    <div data-slot="pipeline-diagram">
      <ol aria-label={label} className="grid gap-5 lg:grid-cols-[repeat(var(--cols),minmax(0,1fr))]" style={{ "--cols": cols } as CSSProperties}>
        {steps.map((step, i) => (
          <li key={step.title} className="relative">
            <Node step={step} n={i + 1} bind={bind} />
            {arrow(i)}
          </li>
        ))}
      </ol>
      {outputs.length ? (
        <div className="mt-5">
          <p className="mb-1.5 text-xs text-muted-foreground">
            <span aria-hidden className="hidden lg:inline">↓ </span>
            {outputsTitle}
          </p>
          <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {outputs.map((step) => (
              <li key={step.title}>
                <Node step={step} bind={bind} small />
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {node}
    </div>
  );
}
