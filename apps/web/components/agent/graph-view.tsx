"use client";

import { RotateCcw } from "lucide-react";
import { useId, useRef, useState, type KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";
import { GRAPH_REVEAL, GRAPH_VIEW, KIND_TEXT, ariaLabelOf, graphHighlight, linksOf, type BranchKind, type GraphEdge } from "@/lib/agent-graph";
import { TIMING, linkKey } from "@/lib/agent-motion";
import { AGENT_UI, fill } from "@/lib/agent-strings";
import { cn } from "@/lib/utils";
import { DrawPath, Reveal, useReveal } from "./motion";

// The dispute_intake graph drawn from lib/agent-reference.ts (spec 04 AC-08): coordinates precomputed by
// scripts/sync-agent.mjs, colors from the theme tokens so both themes follow BRAND.md. Hover or focus a node (Tab) to
// read what it does and what decides each way out; Escape clears. The table below the drawing is the same data.
// When it scrolls into view the graph draws itself in topological order (lib/agent-motion.ts); with reduced motion, or
// on the server, it is drawn final. `activeNode` and `path` let /chat (the live node) and the console (a case's run)
// reuse the same drawing.

type Kind = BranchKind | "plain";

export interface GraphViewProps {
  /** The node a run is on now (e.g. the live node in /chat): marked as current and shown in the side panel. */
  activeNode?: string;
  /** The nodes a run went through, in order (e.g. a case's run in the console): its nodes and edges stand out. */
  path?: string[];
  /** Draw the graph in order when it scrolls into view, with a Replay button (default true). */
  reveal?: boolean;
  /** Fit the drawing to a narrow container (the /chat rail or sheet): one column, scaled down, no sideways scroll. */
  fit?: boolean;
  className?: string;
}

const STROKE: Record<Kind, string> = {
  policy: "stroke-chart-1",
  tool: "stroke-chart-2",
  input: "stroke-muted-foreground",
  plain: "stroke-muted-foreground/60",
};
const FILL: Record<Kind, string> = {
  policy: "fill-chart-1",
  tool: "fill-chart-2",
  input: "fill-muted-foreground",
  plain: "fill-muted-foreground/60",
};
const SWATCH: Record<BranchKind, string> = { policy: "bg-chart-1", tool: "bg-chart-2", input: "bg-muted-foreground" };
const KINDS = Object.keys(KIND_TEXT) as BranchKind[];
const FADE = "transition-[opacity,stroke-width] duration-200 ease-out motion-reduce:transition-none";
const T = AGENT_UI.graph;

const kindOf = (e: GraphEdge): Kind => e.kind ?? "plain";
const touches = (e: GraphEdge, id: string | null) => id !== null && (e.from === id || e.to === id);

export function GraphView({ activeNode, path, reveal = true, fit = false, className }: GraphViewProps = {}) {
  const uid = useId().replace(/:/g, "");
  const frame = useRef<HTMLDivElement>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const { phase, run, replay } = useReveal(frame, { enabled: reveal, total: GRAPH_REVEAL.total });
  const focus = hovered ?? selected;
  const run$ = graphHighlight(activeNode, path);
  const near = new Set(focus ? [focus, ...GRAPH_VIEW.edges.filter((e) => touches(e, focus)).flatMap((e) => [e.from, e.to])] : []);

  const edgeOn = (e: GraphEdge) => (focus ? touches(e, focus) : run$.edges.has(linkKey(e)));
  const edgeDim = (e: GraphEdge) => (focus ? !touches(e, focus) : run$.dims && !run$.edges.has(linkKey(e)));
  const nodeDim = (id: string) => (focus ? !near.has(id) : run$.dims && !run$.nodes.has(id));

  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === "Escape") {
      setHovered(null);
      setSelected(null);
    }
  };

  return (
    <div onKeyDown={onKeyDown} className={cn("grid gap-4", !fit && "xl:grid-cols-[minmax(0,1fr)_18rem]", className)}>
      <div className="min-w-0">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <Legend />
          {reveal ? (
            <Button type="button" variant="outline" size="sm" onClick={replay} aria-label={T.replayLabel} className="motion-reduce:hidden">
              <RotateCcw aria-hidden="true" />
              {T.replay}
            </Button>
          ) : null}
        </div>
        {fit ? null : <p className="mt-2 text-xs text-muted-foreground sm:hidden">{T.scrollHint}</p>}
        <div ref={frame} className={cn("mt-2 rounded-md border bg-background/40 p-2", fit ? "overflow-hidden" : "overflow-x-auto")}>
          <svg
            role="group"
            aria-labelledby={`${uid}-title`}
            viewBox={`0 0 ${GRAPH_VIEW.width} ${GRAPH_VIEW.height}`}
            width={GRAPH_VIEW.width}
            height={GRAPH_VIEW.height}
            className={cn("mx-auto block h-auto w-full", !fit && "min-w-[560px]")}
            style={{ maxWidth: GRAPH_VIEW.width }}
            data-phase={phase}
          >
            <title id={`${uid}-title`}>
              {fill(T.title, { name: GRAPH_VIEW.name, nodes: GRAPH_VIEW.nodes.length, edges: GRAPH_VIEW.edges.length })}
            </title>
            <defs>
              {(["policy", "tool", "input", "plain"] as const).map((kind) => (
                <marker key={kind} id={`${uid}-${kind}`} viewBox="0 0 8 8" refX="7" refY="4" markerUnits="userSpaceOnUse" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
                  <path d="M0 0.5 L8 4 L0 7.5 z" className={FILL[kind]} />
                </marker>
              ))}
            </defs>

            <g key={run}>
              <g aria-hidden="true">
                {GRAPH_VIEW.edges.map((e, i) => {
                  const on = edgeOn(e);
                  return (
                    <DrawPath
                      key={linkKey(e)}
                      phase={phase}
                      delay={GRAPH_REVEAL.edge[linkKey(e)]}
                      maskId={`${uid}-draw-${i}`}
                      bounds={GRAPH_VIEW}
                      d={e.path}
                      fill="none"
                      markerEnd={`url(#${uid}-${kindOf(e)})`}
                      strokeWidth={on ? 2 : 1.25}
                      strokeDasharray={e.kind === "tool" ? "5 3" : e.kind === "input" ? "2 3" : undefined}
                      data-edge={linkKey(e)}
                      data-on={on || undefined}
                      className={cn(STROKE[kindOf(e)], FADE, edgeDim(e) && "opacity-20")}
                    />
                  );
                })}
                {GRAPH_VIEW.edges.map((e) =>
                  e.labelBox && e.label ? (
                    <Reveal key={`${linkKey(e)}-label`} phase={phase} delay={GRAPH_REVEAL.label[linkKey(e)]} duration={TIMING.label}>
                      <g className={cn(FADE, edgeDim(e) && "opacity-25")}>
                        <rect x={e.labelBox.x} y={e.labelBox.y} width={e.labelBox.w} height={e.labelBox.h} rx={4} className={cn("fill-card", STROKE[kindOf(e)])} strokeWidth={1} />
                        <text
                          x={e.labelBox.x + e.labelBox.w / 2}
                          y={e.labelBox.y + e.labelBox.h / 2}
                          textAnchor="middle"
                          dominantBaseline="central"
                          fontSize={10}
                          className="fill-foreground font-mono"
                        >
                          {e.label}
                        </text>
                      </g>
                    </Reveal>
                  ) : null,
                )}
              </g>

              {GRAPH_VIEW.nodes.map((n) => {
                const on = n.id === focus;
                const current = n.id === run$.current;
                const visited = run$.nodes.has(n.id);
                return (
                  <Reveal key={n.id} phase={phase} delay={GRAPH_REVEAL.node[n.id]} rise={4}>
                    <g
                      role="button"
                      tabIndex={0}
                      aria-label={`${ariaLabelOf(n.id)}${current ? ` ${T.current}.` : visited ? ` ${T.onPath}.` : ""}`}
                      aria-pressed={n.id === selected}
                      aria-current={current ? "step" : undefined}
                      data-node={n.id}
                      data-current={current || undefined}
                      data-visited={visited || undefined}
                      className={cn("group cursor-pointer outline-none", FADE, nodeDim(n.id) && "opacity-40")}
                      onMouseEnter={() => setHovered(n.id)}
                      onMouseLeave={() => setHovered(null)}
                      onFocus={() => setSelected(n.id)}
                      onClick={() => setSelected(n.id)}
                    >
                      <rect
                        x={n.x - n.w / 2}
                        y={n.y - n.h / 2}
                        width={n.w}
                        height={n.h}
                        rx={n.terminal ? n.h / 2 : 6}
                        strokeWidth={current ? 2.5 : on ? 2 : visited ? 1.5 : 1}
                        className={cn(
                          "transition-[fill,stroke] duration-200 ease-out motion-reduce:transition-none",
                          current ? "fill-primary/15" : n.terminal ? "fill-muted" : "fill-card",
                          on || current ? "stroke-primary" : visited ? "stroke-primary/70" : "stroke-border",
                          "group-hover:stroke-primary group-focus-visible:stroke-ring group-focus-visible:[stroke-width:2.5]",
                        )}
                      />
                      <text
                        x={n.x}
                        y={n.y}
                        textAnchor="middle"
                        dominantBaseline="central"
                        fontSize={12}
                        className={cn(
                          "pointer-events-none select-none font-mono",
                          current && "font-semibold",
                          n.terminal ? "fill-muted-foreground" : "fill-foreground",
                        )}
                      >
                        {n.id}
                      </text>
                    </g>
                  </Reveal>
                );
              })}
            </g>
          </svg>
        </div>
      </div>
      <Panel active={focus ?? run$.current} current={run$.current} fit={fit} />
    </div>
  );
}

function Legend() {
  return (
    <ul aria-label={T.legendLabel} className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
      {KINDS.map((kind) => (
        <li key={kind} className="flex items-center gap-1.5">
          <span aria-hidden="true" className={cn("inline-block h-0.5 w-4 rounded-full", SWATCH[kind])} />
          {fill(T.branchOn, { kind: KIND_TEXT[kind] })}
        </li>
      ))}
      <li className="flex items-center gap-1.5">
        <span aria-hidden="true" className="inline-block h-0.5 w-4 rounded-full bg-muted-foreground/60" />
        {T.alwaysNext}
      </li>
    </ul>
  );
}

function Panel({ active, current, fit }: { active: string | null; current: string | null; fit?: boolean }) {
  const links = active ? linksOf(active) : null;
  return (
    <aside
      aria-live="polite"
      aria-label={T.panelLabel}
      className={cn(
        "z-10 self-start overflow-y-auto rounded-md border bg-card/95 p-3 text-sm backdrop-blur",
        !fit && "xl:sticky xl:top-20 xl:bottom-auto xl:max-h-none",
        !fit && active && "sticky bottom-3 max-h-[38vh]",
      )}
    >
      {active && links ? (
        <>
          <p className="font-mono font-semibold">
            {active}
            {active === current ? <span className="ml-2 font-sans text-xs font-normal text-primary-text">{T.current}</span> : null}
          </p>
          <p className="mt-1 text-muted-foreground">{GRAPH_VIEW.nodes.find((n) => n.id === active)?.info}</p>
          {links.out.length ? (
            <div className="mt-3">
              <p className="text-xs font-medium text-muted-foreground">{T.goesTo}</p>
              <ul className="mt-1 grid gap-1.5">
                {links.out.map((e) => (
                  <li key={e.to} className="text-xs">
                    <span className="font-mono">{e.to}</span>
                    {e.when ? (
                      <>
                        {" "}
                        <span className="text-muted-foreground">{T.when}</span> <span className="font-mono">{e.when}</span>{" "}
                        <span className="text-muted-foreground">({e.kind ? KIND_TEXT[e.kind] : ""})</span>
                      </>
                    ) : (
                      <span className="text-muted-foreground"> {T.always}</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {links.in.length ? (
            <p className="mt-3 text-xs text-muted-foreground">
              {T.comesFrom} <span className="font-mono text-foreground">{links.in.map((e) => e.from).join(" · ")}</span>
            </p>
          ) : null}
        </>
      ) : (
        <p className="text-xs text-muted-foreground">{T.panelHint}</p>
      )}
    </aside>
  );
}
