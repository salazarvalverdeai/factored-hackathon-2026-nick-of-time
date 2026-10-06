"use client";

import { useId, useState, type KeyboardEvent } from "react";
import { GRAPH_VIEW, KIND_TEXT, ariaLabelOf, linksOf, type BranchKind, type GraphEdge } from "@/lib/agent-graph";
import { cn } from "@/lib/utils";

// The dispute_intake graph drawn from lib/agent-reference.ts (spec 04 AC-08): coordinates precomputed by
// scripts/sync-agent.mjs, colors from the theme tokens so both themes follow BRAND.md. Hover or focus a node (Tab) to
// read what it does and what decides each way out; Escape clears. The table below the drawing is the same data.

type Kind = BranchKind | "plain";

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
const FADE = "transition-opacity duration-150 motion-reduce:transition-none";

const kindOf = (e: GraphEdge): Kind => e.kind ?? "plain";
const touches = (e: GraphEdge, id: string | null) => id !== null && (e.from === id || e.to === id);

export function GraphView() {
  const uid = useId().replace(/:/g, "");
  const [hovered, setHovered] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const active = hovered ?? selected;
  const near = new Set(active ? [active, ...GRAPH_VIEW.edges.filter((e) => touches(e, active)).flatMap((e) => [e.from, e.to])] : []);

  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === "Escape") {
      setHovered(null);
      setSelected(null);
    }
  };

  return (
    <div onKeyDown={onKeyDown} className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_18rem]">
      <div className="min-w-0">
        <Legend />
        <p className="mt-2 text-xs text-muted-foreground sm:hidden">Scroll sideways to see the whole graph; the table below lists the same nodes.</p>
        <div className="mt-2 overflow-x-auto rounded-md border bg-background/40 p-2">
          <svg
            role="group"
            aria-labelledby={`${uid}-title`}
            viewBox={`0 0 ${GRAPH_VIEW.width} ${GRAPH_VIEW.height}`}
            width={GRAPH_VIEW.width}
            height={GRAPH_VIEW.height}
            className="mx-auto block h-auto w-full min-w-[560px]"
            style={{ maxWidth: GRAPH_VIEW.width }}
          >
            <title id={`${uid}-title`}>
              {`Graph ${GRAPH_VIEW.name}: ${GRAPH_VIEW.nodes.length} nodes and ${GRAPH_VIEW.edges.length} edges from START to END. Each node can be focused to read what it does.`}
            </title>
            <defs>
              {(["policy", "tool", "input", "plain"] as const).map((kind) => (
                <marker key={kind} id={`${uid}-${kind}`} viewBox="0 0 8 8" refX="7" refY="4" markerUnits="userSpaceOnUse" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
                  <path d="M0 0.5 L8 4 L0 7.5 z" className={FILL[kind]} />
                </marker>
              ))}
            </defs>

            <g aria-hidden="true">
              {GRAPH_VIEW.edges.map((e) => {
                const on = touches(e, active);
                return (
                  <path
                    key={`${e.from}-${e.to}`}
                    d={e.path}
                    fill="none"
                    markerEnd={`url(#${uid}-${kindOf(e)})`}
                    strokeWidth={on ? 2 : 1.25}
                    strokeDasharray={e.kind === "tool" ? "5 3" : e.kind === "input" ? "2 3" : undefined}
                    className={cn(STROKE[kindOf(e)], FADE, active && !on && "opacity-20")}
                  />
                );
              })}
              {GRAPH_VIEW.edges.map((e) =>
                e.labelBox && e.label ? (
                  <g key={`${e.from}-${e.to}-label`} className={cn(FADE, active && !touches(e, active) && "opacity-25")}>
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
                ) : null,
              )}
            </g>

            {GRAPH_VIEW.nodes.map((n) => {
              const on = n.id === active;
              return (
                <g
                  key={n.id}
                  role="button"
                  tabIndex={0}
                  aria-label={ariaLabelOf(n.id)}
                  aria-pressed={n.id === selected}
                  data-node={n.id}
                  className={cn("group cursor-pointer outline-none", FADE, active && !near.has(n.id) && "opacity-40")}
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
                    strokeWidth={on ? 2 : 1}
                    className={cn(
                      n.terminal ? "fill-muted" : "fill-card",
                      on ? "stroke-primary" : "stroke-border",
                      "group-hover:stroke-primary group-focus-visible:stroke-ring group-focus-visible:[stroke-width:2.5]",
                    )}
                  />
                  <text
                    x={n.x}
                    y={n.y}
                    textAnchor="middle"
                    dominantBaseline="central"
                    fontSize={12}
                    className={cn("pointer-events-none select-none font-mono", n.terminal ? "fill-muted-foreground" : "fill-foreground")}
                  >
                    {n.id}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
      </div>
      <Panel active={active} />
    </div>
  );
}

function Legend() {
  return (
    <ul aria-label="Edge colors" className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
      {KINDS.map((kind) => (
        <li key={kind} className="flex items-center gap-1.5">
          <span aria-hidden="true" className={cn("inline-block h-0.5 w-4 rounded-full", SWATCH[kind])} />
          Branch on a {KIND_TEXT[kind]}
        </li>
      ))}
      <li className="flex items-center gap-1.5">
        <span aria-hidden="true" className="inline-block h-0.5 w-4 rounded-full bg-muted-foreground/60" />
        Always next
      </li>
    </ul>
  );
}

function Panel({ active }: { active: string | null }) {
  const links = active ? linksOf(active) : null;
  return (
    <aside
      aria-live="polite"
      aria-label="Selected node"
      className={cn(
        "z-10 self-start overflow-y-auto rounded-md border bg-card/95 p-3 text-sm backdrop-blur xl:sticky xl:top-20 xl:bottom-auto xl:max-h-none",
        active && "sticky bottom-3 max-h-[38vh]",
      )}
    >
      {active && links ? (
        <>
          <p className="font-mono font-semibold">{active}</p>
          <p className="mt-1 text-muted-foreground">{GRAPH_VIEW.nodes.find((n) => n.id === active)?.info}</p>
          {links.out.length ? (
            <div className="mt-3">
              <p className="text-xs font-medium text-muted-foreground">Goes to</p>
              <ul className="mt-1 grid gap-1.5">
                {links.out.map((e) => (
                  <li key={e.to} className="text-xs">
                    <span className="font-mono">{e.to}</span>
                    {e.when ? (
                      <>
                        {" "}
                        <span className="text-muted-foreground">when</span> <span className="font-mono">{e.when}</span>{" "}
                        <span className="text-muted-foreground">({e.kind ? KIND_TEXT[e.kind] : ""})</span>
                      </>
                    ) : (
                      <span className="text-muted-foreground"> always</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {links.in.length ? (
            <p className="mt-3 text-xs text-muted-foreground">
              Comes from <span className="font-mono text-foreground">{links.in.map((e) => e.from).join(" · ")}</span>
            </p>
          ) : null}
        </>
      ) : (
        <p className="text-xs text-muted-foreground">Hover a node, or Tab to one, to see what it does and what decides each way out. Esc clears.</p>
      )}
    </aside>
  );
}
