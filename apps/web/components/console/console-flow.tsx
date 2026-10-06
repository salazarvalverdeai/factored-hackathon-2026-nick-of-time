"use client";

// "How the console works" (spec 08 AC-24): the analyst's flow from lib/console-flow.ts, drawn on a CSS grid in /agent's
// diagram language (cards, chart-colored edges, a dashed frame for what it runs on). One plain line; every box is a
// button (Tab, Enter) that opens the shared detail panel. The edges are the motion kit's FlowConnector: they play once,
// in the flow's order, when the view enters the viewport, and with reduced motion nothing moves (components/motion).
import { useState } from "react";
import { DetailField, DetailFields, DetailPanel } from "@/components/detail-panel";
import { FlowConnector } from "@/components/motion";
import { FLOW_BOXES, FLOW_LINE, FLOW_LINKS, NEEDS_TITLE, boxOf, type FlowBox, type FlowLink } from "@/lib/console-flow";
import { MOTION, fitStep, lift } from "@/lib/motion";
import { cn } from "@/lib/utils";

const STEP = fitStep(FLOW_LINKS.length, 150, MOTION.flow + MOTION.after);
const EDGE: Record<FlowLink["kind"], string> = { step: "text-chart-1", needs: "text-chart-2" };
const evidence = FLOW_BOXES.filter((b) => b.group === "evidence");
const placed = FLOW_BOXES.filter((b) => b.row !== null);

export function ConsoleFlow({ className }: { className?: string }) {
  const [open, setOpen] = useState<FlowBox | null>(null);
  return (
    <div className={cn("space-y-3", className)} data-slot="console-flow">
      <p className="text-sm">{FLOW_LINE}</p>
      <div
        role="group"
        aria-label="The analyst's flow and what it runs on. Each box opens its detail."
        className="grid grid-cols-[minmax(0,1fr)_2.25rem_minmax(0,1fr)] gap-y-1 sm:grid-cols-[minmax(0,1fr)_3.5rem_minmax(0,1fr)]"
      >
        {/* The dashed frame around what the flow runs on, behind its boxes. */}
        <div aria-hidden className="-m-1.5 rounded-lg border border-dashed" style={{ gridColumn: 3, gridRow: `${NEEDS_TITLE.row} / 10` }} />
        <p
          className="col-start-3 self-end px-1 text-xs font-medium text-muted-foreground"
          style={{ gridRow: NEEDS_TITLE.row }}
        >
          {NEEDS_TITLE.text}
        </p>
        {placed.map((b) => (
          <div key={b.id} className={cn("min-w-0", b.id === "case" && "space-y-1.5")} style={{ gridColumn: b.col ?? undefined, gridRow: b.row ?? undefined }}>
            <Box box={b} onOpen={setOpen} />
            {b.id === "case" ? (
              <div className="grid grid-cols-2 gap-1 rounded-lg border border-dashed p-1" role="group" aria-label="The case card's evidence">
                {evidence.map((e) => (
                  <Box key={e.id} box={e} onOpen={setOpen} />
                ))}
              </div>
            ) : null}
          </div>
        ))}
        {FLOW_LINKS.map((l, i) => (
          <Edge key={`${l.from}->${l.to}`} link={l} delay={Math.round(i * STEP)} />
        ))}
      </div>
      <ol className="sr-only">
        {FLOW_LINKS.map((l) => (
          <li key={`${l.from}->${l.to}`}>
            {boxOf(l.from)?.name} to {boxOf(l.to)?.name}: {l.label}
          </li>
        ))}
      </ol>
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

function Box({ box, onOpen }: { box: FlowBox; onOpen: (b: FlowBox) => void }) {
  const pill = box.group === "evidence";
  return (
    <button
      type="button"
      aria-haspopup="dialog"
      aria-label={`${box.name}${box.sub ? `, ${box.sub}` : ""}. Open its detail.`}
      data-box={box.id}
      onClick={() => onOpen(box)}
      className={cn(
        "relative w-full min-w-0 border text-center outline-none hover:border-primary focus-visible:ring-2 focus-visible:ring-ring",
        lift,
        pill ? "rounded-full bg-card px-2 py-0.5 text-xs" : "rounded-md px-2 py-2",
        box.group === "need" ? "bg-muted" : "bg-card",
      )}
    >
      <span className={cn("block break-words", !pill && "text-sm font-medium")}>{box.name}</span>
      {box.sub ? <span className="block text-xs text-muted-foreground max-sm:hidden">{box.sub}</span> : null}
    </button>
  );
}

function Edge({ link, delay }: { link: FlowLink; delay: number }) {
  const across = link.direction !== "down";
  return (
    <div
      className={cn("flex min-w-0 items-center justify-center gap-1.5", link.rows > 1 && "flex-col", EDGE[link.kind])}
      style={{ gridColumn: link.col, gridRow: `${link.row} / span ${link.rows}` }}
      data-link={`${link.from}->${link.to}`}
    >
      {/* A long edge: a plain line down to the connector, so the arrow reaches its box. */}
      {link.rows > 1 ? <span aria-hidden className="w-px flex-1 border-l border-dashed border-current" /> : null}
      <FlowConnector direction={link.direction} length={across ? 28 : 18} delay={delay} className="text-current" />
      {!across && link.rows === 1 ? <span aria-hidden className="text-[11px] text-muted-foreground max-sm:hidden">{link.label}</span> : null}
    </div>
  );
}
