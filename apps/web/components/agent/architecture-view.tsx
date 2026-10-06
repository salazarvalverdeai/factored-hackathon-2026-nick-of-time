"use client";

import { ChevronLeft, ChevronRight, Pause, Play } from "lucide-react";
import { useReducedMotion } from "motion/react";
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";
import { ARCH_VIEW, flowsOf, nameOf, type ArchFlow, type FlowKind } from "@/lib/agent-architecture";
import { pointAt } from "@/lib/agent-motion";
import { useT } from "@/components/i18n-provider";
import type { MessageKey } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { FlowDot } from "./motion";

// The services architecture of /agent (spec 04 AC-08), drawn from lib/agent-architecture.ts (facts from
// docs/infrastructure.md and the CLAUDE.md stack). "Walk through" plays the request paths in order, a dot travelling
// along each one; every service takes focus (Tab) and shows its role in the side panel. It plays once by itself when it
// scrolls into view; with reduced motion nothing moves and the steps only change when asked. The static drawing stays
// one link away (app/agent/page.tsx).

const STROKE: Record<FlowKind, string> = {
  request: "stroke-muted-foreground",
  agent: "stroke-chart-1",
  llm: "stroke-chart-1",
  data: "stroke-chart-2",
  deploy: "stroke-muted-foreground/60",
};
const FILL: Record<FlowKind, string> = {
  request: "fill-muted-foreground",
  agent: "fill-chart-1",
  llm: "fill-chart-1",
  data: "fill-chart-2",
  deploy: "fill-muted-foreground/60",
};
const DASH: Partial<Record<FlowKind, string>> = { llm: "4 3", deploy: "2 3" };
const KINDS = Object.keys(STROKE) as FlowKind[];
const FADE = "transition-[opacity,stroke-width] duration-200 ease-out motion-reduce:transition-none";
const DWELL_MS = 1800;
const { width: W, height: H, services, flows, ec2 } = ARCH_VIEW;
const flowKey = (f: ArchFlow) => `${f.from}->${f.to}`;

export function ArchitectureView({ className }: { className?: string }) {
  const t = useT();
  const uid = useId().replace(/:/g, "");
  const frame = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion() ?? false;
  const [hovered, setHovered] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [step, setStep] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const focus = hovered ?? selected;
  const flow = step === null ? null : flows[step];

  // Plays once by itself when the drawing scrolls into view, unless motion is reduced.
  useEffect(() => {
    const el = frame.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        observer.disconnect();
        if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
        setStep(0);
        setPlaying(true);
      },
      { threshold: 0.4 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!playing || step === null) return;
    const timer = setTimeout(() => {
      if (step < flows.length - 1) setStep(step + 1);
      else {
        setPlaying(false);
        setStep(null);
      }
    }, DWELL_MS);
    return () => clearTimeout(timer);
  }, [playing, step]);

  const go = (next: number | null) => {
    setPlaying(false);
    setHovered(null);
    setSelected(null);
    setStep(next);
  };
  const toggle = () => {
    setHovered(null);
    setSelected(null);
    if (playing) setPlaying(false);
    else {
      setStep((s) => (s === null || s === flows.length - 1 ? 0 : s));
      setPlaying(true);
    }
  };
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === "Escape") {
      setHovered(null);
      setSelected(null);
      setPlaying(false);
      setStep(null);
    }
  };

  const flowOn = (f: ArchFlow) => (focus ? f.from === focus || f.to === focus : flow ? f === flow : false);
  const flowDim = (f: ArchFlow) => (focus || flow ? !flowOn(f) : false);
  const near = new Set(focus ? [focus, ...flows.filter(flowOn).flatMap((f) => [f.from, f.to])] : flow ? [flow.from, flow.to] : []);
  const boxDim = (id: string) => (focus || flow) && !near.has(id);

  return (
    <div onKeyDown={onKeyDown} className={cn("grid gap-4 xl:grid-cols-[minmax(0,1fr)_18rem]", className)}>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Legend />
          <div className="flex items-center gap-1.5">
            <Button type="button" variant="outline" size="icon-sm" onClick={() => go(step === null ? flows.length - 1 : Math.max(0, step - 1))} aria-label={t("agent.ui.arch.previous")}>
              <ChevronLeft aria-hidden="true" />
            </Button>
            <span className="w-24 text-center text-xs tabular-nums text-muted-foreground" aria-live={playing ? "off" : "polite"}>
              {step === null ? t("agent.ui.arch.overview") : t("agent.ui.arch.step", { n: step + 1, total: flows.length })}
            </span>
            <Button type="button" variant="outline" size="icon-sm" onClick={() => go(step === null ? 0 : Math.min(flows.length - 1, step + 1))} aria-label={t("agent.ui.arch.next")}>
              <ChevronRight aria-hidden="true" />
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={toggle} aria-pressed={playing} className="w-32">
              {playing ? <Pause aria-hidden="true" /> : <Play aria-hidden="true" />}
              {playing ? t("agent.ui.arch.pause") : t("agent.ui.arch.play")}
            </Button>
          </div>
        </div>
        <div ref={frame} className="mt-2 overflow-x-auto rounded-md border bg-background/40 p-2">
          <svg
            role="group"
            aria-labelledby={`${uid}-title`}
            viewBox={`0 0 ${W} ${H}`}
            width={W}
            height={H}
            className="mx-auto block h-auto w-full"
            style={{ maxWidth: 680 }}
            data-step={step ?? undefined}
          >
            <title id={`${uid}-title`}>{t("agent.ui.arch.title", { services: services.length, flows: flows.length })}</title>
            <defs>
              {KINDS.map((kind) => (
                <marker key={kind} id={`${uid}-${kind}`} viewBox="0 0 8 8" refX="7" refY="4" markerUnits="userSpaceOnUse" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
                  <path d="M0 0.5 L8 4 L0 7.5 z" className={FILL[kind]} />
                </marker>
              ))}
            </defs>

            <g aria-hidden="true" className={cn(FADE, (focus || flow) && flow?.to !== "ec2" && "opacity-60")}>
              <rect
                x={ec2.x}
                y={ec2.y}
                width={ec2.w}
                height={ec2.h}
                rx={10}
                fill="none"
                strokeDasharray="4 3"
                strokeWidth={flow?.to === "ec2" ? 2 : 1}
                className={cn(FADE, flow?.to === "ec2" ? "stroke-primary" : "stroke-border")}
              />
              <text x={ec2.x + 10} y={ec2.y + 16} fontSize={11} className="fill-foreground font-medium">
                {ec2.title}
              </text>
              <text x={ec2.x + 10} y={ec2.y + 30} fontSize={10} className="fill-muted-foreground max-sm:hidden">
                {ec2.sub}
              </text>
            </g>

            <g aria-hidden="true">
              {flows.map((f) => {
                const on = flowOn(f);
                return (
                  <path
                    key={flowKey(f)}
                    d={f.path}
                    fill="none"
                    markerEnd={`url(#${uid}-${f.kind})`}
                    strokeWidth={on ? 2.25 : 1.25}
                    strokeDasharray={DASH[f.kind]}
                    strokeLinejoin="round"
                    data-flow={flowKey(f)}
                    data-on={on || undefined}
                    className={cn(STROKE[f.kind], FADE, flowDim(f) && "opacity-20")}
                  />
                );
              })}
              {flows.map((f, i) => {
                const mid = pointAt(f.points, 0.5);
                return (
                  <g key={`${flowKey(f)}-n`} className={cn(FADE, flowDim(f) && "opacity-30")}>
                    <circle cx={mid.x} cy={mid.y} r={7.5} strokeWidth={1} className={cn("fill-card", STROKE[f.kind])} />
                    <text x={mid.x} y={mid.y} textAnchor="middle" dominantBaseline="central" fontSize={9} className="fill-foreground font-mono tabular-nums">
                      {i + 1}
                    </text>
                  </g>
                );
              })}
              {flow && !reduced ? <FlowDot key={step} points={flow.points} play={step ?? 0} className={FILL[flow.kind]} /> : null}
            </g>

            {services.map((s) => {
              const on = s.id === focus || (flow !== null && (flow.from === s.id || flow.to === s.id));
              return (
                <g
                  key={s.id}
                  role="button"
                  tabIndex={0}
                  aria-label={`${s.name}, ${s.sub}: ${s.role}`}
                  aria-pressed={s.id === selected}
                  data-service={s.id}
                  className={cn("group cursor-pointer outline-none", FADE, boxDim(s.id) && "opacity-40")}
                  onMouseEnter={() => setHovered(s.id)}
                  onMouseLeave={() => setHovered(null)}
                  onFocus={() => {
                    setPlaying(false);
                    setSelected(s.id);
                  }}
                  onClick={() => {
                    setPlaying(false);
                    setSelected(s.id);
                  }}
                >
                  <rect
                    x={s.x - s.w / 2}
                    y={s.y - s.h / 2}
                    width={s.w}
                    height={s.h}
                    rx={6}
                    strokeWidth={on ? 2 : 1}
                    className={cn(
                      "transition-[stroke] duration-200 ease-out motion-reduce:transition-none",
                      s.zone === "managed" ? "fill-muted" : "fill-card",
                      on ? "stroke-primary" : "stroke-border",
                      "group-hover:stroke-primary group-focus-visible:stroke-ring group-focus-visible:[stroke-width:2.5]",
                    )}
                  />
                  <text
                    x={s.x}
                    y={s.y - 8}
                    textAnchor="middle"
                    dominantBaseline="central"
                    fontSize={14}
                    className="pointer-events-none select-none fill-foreground font-medium max-sm:translate-y-2"
                  >
                    {s.name}
                  </text>
                  <text x={s.x} y={s.y + 10} textAnchor="middle" dominantBaseline="central" fontSize={10.5} className="pointer-events-none select-none fill-muted-foreground max-sm:hidden">
                    {s.sub}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
        <Steps current={step} onPick={go} />
      </div>
      <Panel focus={focus} step={step} quiet={playing} />
    </div>
  );
}

function Legend() {
  const t = useT();
  const kinds = KINDS.filter((k) => k !== "llm");
  return (
    <ul aria-label={t("agent.ui.arch.legendLabel")} className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
      {[...kinds.slice(0, 2), "llm" as const, ...kinds.slice(2)].map((kind) => (
        <li key={kind} className="flex items-center gap-1.5">
          <svg aria-hidden="true" width="16" height="4" className="overflow-visible">
            <line x1="0" y1="2" x2="16" y2="2" strokeWidth={2} strokeDasharray={DASH[kind]} className={STROKE[kind]} />
          </svg>
          {t(`agent.ui.arch.kinds.${kind}` as MessageKey)}
        </li>
      ))}
    </ul>
  );
}

function Steps({ current, onPick }: { current: number | null; onPick: (i: number) => void }) {
  const t = useT();
  return (
    <details className="group mt-3 text-xs">
      <summary className="cursor-pointer text-muted-foreground hover:text-foreground">{t("agent.ui.arch.stepsTitle")}</summary>
      <ol className="mt-2 grid gap-1 sm:grid-cols-2">
        {flows.map((f, i) => (
          <li key={flowKey(f)}>
            <button
              type="button"
              onClick={() => onPick(i)}
              aria-current={i === current ? "step" : undefined}
              className={cn(
                "w-full rounded-md px-2 py-1 text-left hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring",
                i === current && "bg-accent text-foreground",
              )}
            >
              <span className="font-mono tabular-nums text-muted-foreground">{i + 1}.</span> {nameOf(f.from)} → {nameOf(f.to)}{" "}
              <span className="text-muted-foreground">· {f.label}</span>
            </button>
          </li>
        ))}
      </ol>
    </details>
  );
}

function Panel({ focus, step, quiet }: { focus: string | null; step: number | null; quiet: boolean }) {
  const t = useT();
  const service = focus ? services.find((s) => s.id === focus) : null;
  const flow = step === null ? null : flows[step];
  const links = service ? flowsOf(service.id) : null;
  return (
    <aside
      aria-live={quiet ? "off" : "polite"}
      aria-label={t("agent.ui.arch.panelLabel")}
      className="min-h-[9.5rem] self-start rounded-md border bg-card/95 p-3 text-sm xl:sticky xl:top-20"
    >
      {service && links ? (
        <>
          <p className="font-semibold">{service.name}</p>
          <p className="text-xs text-muted-foreground">{service.sub}</p>
          <p className="mt-2 text-muted-foreground">{service.role}</p>
          {links.out.length ? (
            <p className="mt-3 text-xs text-muted-foreground">
              {t("agent.ui.arch.sends")}{" "}
              <span className="text-foreground">{links.out.map((f) => `${f.label} → ${nameOf(f.to)}`).join(" · ")}</span>
            </p>
          ) : null}
          {links.in.length ? (
            <p className="mt-1 text-xs text-muted-foreground">
              {t("agent.ui.arch.receives")}{" "}
              <span className="text-foreground">{links.in.map((f) => `${f.label} ← ${nameOf(f.from)}`).join(" · ")}</span>
            </p>
          ) : null}
        </>
      ) : flow && step !== null ? (
        <>
          <p className="text-xs tabular-nums text-muted-foreground">{t("agent.ui.arch.step", { n: step + 1, total: flows.length })}</p>
          <p className="mt-1 font-semibold">
            {nameOf(flow.from)} → {nameOf(flow.to)}
          </p>
          <p className="font-mono text-xs text-muted-foreground">{flow.label}</p>
          <p className="mt-2 text-muted-foreground">{flow.text}</p>
        </>
      ) : (
        <p className="text-xs text-muted-foreground">{t("agent.ui.arch.panelHint")}</p>
      )}
    </aside>
  );
}
