"use client";

// "How the console works" (spec 08 AC-24): the analyst's flow drawn in /agent's architecture language
// (components/agent/architecture-view.tsx), from lib/console-flow.ts. One plain line; every box takes focus (Tab) and
// opens the shared detail panel (Enter, Space or a click). "Walk through" plays the links in order with a dot travelling
// along each one (components/agent/motion.tsx); it plays once when opened, never with reduced motion.
import { ChevronLeft, ChevronRight, Pause, Play } from "lucide-react";
import { useReducedMotion } from "motion/react";
import { useEffect, useId, useState, type KeyboardEvent } from "react";
import { FlowDot } from "@/components/agent/motion";
import { DetailField, DetailFields, DetailPanel } from "@/components/detail-panel";
import { Button } from "@/components/ui/button";
import { EVIDENCE_BRACKET, EVIDENCE_FRAME, FLOW_LINE, FLOW_VIEW, NEEDS_FRAME, boxOf, type FlowBox, type FlowLink } from "@/lib/console-flow";
import { pathOf } from "@/lib/agent-motion";
import { cn } from "@/lib/utils";

const { width: W, height: H, boxes, links } = FLOW_VIEW;
const DWELL_MS = 1600;
const FADE = "transition-[opacity,stroke-width] duration-200 ease-out motion-reduce:transition-none";
const STROKE: Record<FlowLink["kind"], string> = { step: "stroke-chart-1", needs: "stroke-chart-2" };
const FILL: Record<FlowLink["kind"], string> = { step: "fill-chart-1", needs: "fill-chart-2" };
const key = (l: FlowLink) => `${l.from}->${l.to}`;

export function ConsoleFlow({ className }: { className?: string }) {
  const uid = useId().replace(/:/g, "");
  const reduced = useReducedMotion() ?? false;
  // Plays once when the view is opened (it mounts on demand, in the browser), unless motion is reduced.
  const [playing, setPlaying] = useState(() => typeof window !== "undefined" && !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
  const [step, setStep] = useState<number | null>(() => (playing ? 0 : null));
  const [open, setOpen] = useState<FlowBox | null>(null);
  const link = step === null ? null : links[step];

  useEffect(() => {
    if (!playing || step === null) return;
    const timer = setTimeout(() => {
      if (step < links.length - 1) setStep(step + 1);
      else {
        setPlaying(false);
        setStep(null);
      }
    }, DWELL_MS);
    return () => clearTimeout(timer);
  }, [playing, step]);

  const go = (next: number) => {
    setPlaying(false);
    setStep(next);
  };
  const toggle = () => {
    if (playing) setPlaying(false);
    else {
      setStep((s) => (s === null || s === links.length - 1 ? 0 : s));
      setPlaying(true);
    }
  };
  const onBoxKey = (event: KeyboardEvent, box: FlowBox) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setPlaying(false);
      setOpen(box);
    }
  };
  const on = (id: string) => link !== null && (link.from === id || link.to === id);

  return (
    <div className={cn("space-y-3", className)} data-slot="console-flow">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm">{FLOW_LINE}</p>
        <div className="flex items-center gap-1.5">
          <Button type="button" variant="outline" size="icon-sm" onClick={() => go(step === null ? links.length - 1 : Math.max(0, step - 1))} aria-label="Previous step">
            <ChevronLeft aria-hidden="true" />
          </Button>
          <Button type="button" variant="outline" size="icon-sm" onClick={() => go(step === null ? 0 : Math.min(links.length - 1, step + 1))} aria-label="Next step">
            <ChevronRight aria-hidden="true" />
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={toggle} aria-pressed={playing} className="w-32">
            {playing ? <Pause aria-hidden="true" /> : <Play aria-hidden="true" />}
            {playing ? "Pause" : "Walk through"}
          </Button>
        </div>
      </div>
      <div className="rounded-md border bg-background/40 p-2">
        <svg
          role="group"
          aria-labelledby={`${uid}-title`}
          viewBox={`0 0 ${W} ${H}`}
          className="mx-auto block h-auto w-full"
          style={{ maxWidth: 560 }}
          data-step={step ?? undefined}
        >
          <title id={`${uid}-title`}>
            The analyst&apos;s flow: queue, case card with its evidence, analyst action, verification and close, and what it runs on. Each box opens its detail.
          </title>
          <defs>
            {(["step", "needs"] as const).map((kind) => (
              <marker key={kind} id={`${uid}-${kind}`} viewBox="0 0 8 8" refX="7" refY="4" markerUnits="userSpaceOnUse" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
                <path d="M0 0.5 L8 4 L0 7.5 z" className={FILL[kind]} />
              </marker>
            ))}
          </defs>

          <g aria-hidden="true">
            <rect {...frame(EVIDENCE_FRAME)} rx={8} fill="none" strokeDasharray="3 3" className={cn("stroke-border", FADE)} />
            <path d={pathOf(EVIDENCE_BRACKET)} fill="none" strokeWidth={1.25} className="stroke-muted-foreground/60" />
            <rect {...frame(NEEDS_FRAME)} rx={10} fill="none" strokeDasharray="4 3" className="stroke-border" />
            <text x={NEEDS_FRAME.x + 10} y={NEEDS_FRAME.y + 14} fontSize={11} className="fill-muted-foreground font-medium">
              {NEEDS_FRAME.title}
            </text>
            {links.map((l) => {
              const lit = link === l;
              return (
                <path
                  key={key(l)}
                  d={l.path}
                  fill="none"
                  markerEnd={`url(#${uid}-${l.kind})`}
                  strokeWidth={lit ? 2.25 : 1.25}
                  strokeDasharray={l.kind === "needs" ? "4 3" : undefined}
                  strokeLinejoin="round"
                  data-link={key(l)}
                  data-on={lit || undefined}
                  className={cn(STROKE[l.kind], FADE, link && !lit && "opacity-25")}
                />
              );
            })}
            {link && !reduced ? <FlowDot key={step} points={link.points} play={step ?? 0} className={FILL[link.kind]} /> : null}
          </g>

          {boxes.map((b) => {
            const lit = on(b.id);
            const pill = b.group === "evidence";
            return (
              <g
                key={b.id}
                role="button"
                tabIndex={0}
                aria-haspopup="dialog"
                aria-label={`${b.name}${b.sub ? `, ${b.sub}` : ""}. Open its detail.`}
                data-box={b.id}
                className={cn("group cursor-pointer outline-none", FADE, link && !lit && "opacity-50")}
                onClick={() => {
                  setPlaying(false);
                  setOpen(b);
                }}
                onKeyDown={(e) => onBoxKey(e, b)}
              >
                <rect
                  x={b.x - b.w / 2}
                  y={b.y - b.h / 2}
                  width={b.w}
                  height={b.h}
                  rx={pill ? b.h / 2 : 6}
                  strokeWidth={lit ? 2 : 1}
                  className={cn(
                    "transition-[stroke] duration-200 ease-out motion-reduce:transition-none",
                    b.group === "need" ? "fill-muted" : "fill-card",
                    lit ? "stroke-primary" : "stroke-border",
                    "group-hover:stroke-primary group-focus-visible:stroke-ring group-focus-visible:[stroke-width:2.5]",
                  )}
                />
                <text
                  x={b.x}
                  y={pill ? b.y : b.y - 7}
                  textAnchor="middle"
                  dominantBaseline="central"
                  fontSize={pill ? 11 : 14}
                  className={cn("pointer-events-none select-none fill-foreground font-medium", !pill && "max-sm:translate-y-[7px]")}
                >
                  {b.name}
                </text>
                {b.sub ? (
                  <text x={b.x} y={b.y + 10} textAnchor="middle" dominantBaseline="central" fontSize={10.5} className="pointer-events-none select-none fill-muted-foreground max-sm:hidden">
                    {b.sub}
                  </text>
                ) : null}
              </g>
            );
          })}
        </svg>
      </div>
      <p className="min-h-5 text-xs text-muted-foreground" aria-live={playing ? "off" : "polite"}>
        {link ? (
          <>
            <span className="tabular-nums">
              {(step ?? 0) + 1}/{links.length}
            </span>{" "}
            {boxOf(link.from)?.name} → {boxOf(link.to)?.name} · {link.label}
          </>
        ) : (
          "Select a box to read what it does."
        )}
      </p>
      <DetailPanel open={open !== null} onClose={() => setOpen(null)} title={open?.name ?? ""} description={open?.sub || undefined}>
        {open ? (
          <DetailFields>
            <DetailField label="What it does">{open.detail}</DetailField>
            <DetailField label="Source" mono>
              {open.source}
            </DetailField>
          </DetailFields>
        ) : null}
      </DetailPanel>
    </div>
  );
}

const frame = (f: { x: number; y: number; w: number; h: number }) => ({ x: f.x, y: f.y, width: f.w, height: f.h });
