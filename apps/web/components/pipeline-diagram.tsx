"use client";

// Shared "how it's built" flow of /data, /evaluation and /analytics (spec 12 AC-07, AC-09). Numbered steps run left
// to right from lg and top to bottom below it, so 390 px never scrolls sideways. Every step takes keyboard focus and
// shows its detail in the same tooltip as the charts; "Detail →" opens the side panel with its method, source and spec.
// On entering the viewport the diagram walks once, step by step, with a flowing edge between steps (motion kit; with
// reduced motion everything is in place at once). The edges sit in the grid gap, so nothing shifts.
import { FOCUS, TipBody, useTip } from "@/app/analytics/charts";
import { DetailButton } from "@/components/detail-button";
import { CountText, FlowConnector, Reveal } from "@/components/motion";
import { lift, walkSchedule } from "@/lib/motion";
import type { CSSProperties } from "react";
import type { PipelineStep } from "@/lib/pipelines";

const TONE = { source: "border-t-muted-foreground/60", layer: "border-t-primary", output: "border-t-brand-teal" } as const;
const LABEL = /\[(data|external|assumption|simulated|projected)\]/;

function Node({ step, n, bind, small = false, at = 0 }: { step: PipelineStep; n?: number; bind: ReturnType<typeof useTip>["bind"]; small?: boolean; at?: number }) {
  return (
    <div
      tabIndex={0}
      role="group"
      aria-label={`${step.title}: ${step.lines.join(" ")} ${step.tip.map(([k, v]) => `${k}: ${v}`).join("; ")}`}
      className={`h-full rounded-md border border-t-2 bg-background/60 ${small ? "p-2.5" : "p-3"} ${TONE[step.tone ?? "layer"]} ${lift} ${FOCUS}`}
      {...bind(<TipBody title={step.title} rows={step.tip} note={step.note} />)}
    >
      <p className="flex items-baseline gap-1.5 text-sm font-medium [overflow-wrap:anywhere]">
        {n ? <span className="font-mono text-xs text-muted-foreground">{n}</span> : null}
        {step.title}
      </p>
      {step.lines.map((line) => (
        <p key={line} className="mt-0.5 text-xs text-muted-foreground [overflow-wrap:anywhere]">
          {/* a figure line (it carries a label) counts up while its step appears */}
          {LABEL.test(line) ? <CountText text={line} delay={at} /> : line}
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
  const walk = walkSchedule(steps.length, outputs.length);
  // From lg the edge points right, except at the end of a row; below lg it points down (also into the outputs).
  const edge = (i: number) => (
    <>
      {i < steps.length - 1 || outputs.length ? (
        <FlowConnector direction="down" length={14} delay={walk.edge(i)} className="absolute -bottom-[17px] left-1/2 -translate-x-1/2 lg:hidden" />
      ) : null}
      {i < steps.length - 1 && (i + 1) % cols ? (
        <FlowConnector direction="right" length={16} delay={walk.edge(i)} className="absolute top-1/2 -right-[18px] hidden -translate-y-1/2 lg:block" />
      ) : null}
    </>
  );
  return (
    <div data-slot="pipeline-diagram">
      <ol aria-label={label} className="grid gap-5 lg:grid-cols-[repeat(var(--cols),minmax(0,1fr))]" style={{ "--cols": cols } as CSSProperties}>
        {steps.map((step, i) => (
          <Reveal as="li" key={step.title} delay={walk.node(i)} className="relative">
            <Node step={step} n={i + 1} bind={bind} at={walk.node(i)} />
            {edge(i)}
          </Reveal>
        ))}
      </ol>
      {outputs.length ? (
        <div className="mt-5">
          <p className="mb-1.5 text-xs text-muted-foreground">
            <span aria-hidden className="hidden lg:inline">↓ </span>
            {outputsTitle}
          </p>
          <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {outputs.map((step, i) => (
              <Reveal as="li" key={step.title} delay={walk.outputsAt + i * walk.outputStep}>
                <Node step={step} bind={bind} small at={walk.outputsAt + i * walk.outputStep} />
              </Reveal>
            ))}
          </ul>
        </div>
      ) : null}
      {node}
    </div>
  );
}
