"use client";

// "How the console works" (spec 08 AC-24): the analyst's flow from lib/console-flow.ts, drawn on a CSS grid in /agent's
// diagram language (cards, chart-colored edges, a dashed frame for what it runs on). One plain line; every box is a
// button (Tab, Enter) that opens the shared detail panel. The edges are the motion kit's FlowConnector: they play once,
// in the flow's order, when the view enters the viewport, and with reduced motion nothing moves (components/motion).
import { useState } from "react";
import { DetailField, DetailFields, DetailPanel } from "@/components/detail-panel";
import { useT } from "@/components/i18n-provider";
import { FlowConnector } from "@/components/motion";
import { FLOW_BOXES, FLOW_LINKS, NEEDS_TITLE, type FlowBox, type FlowId, type FlowLink } from "@/lib/console-flow";
import type { MessageKey } from "@/lib/i18n";
import { MOTION, fitStep, lift } from "@/lib/motion";
import { cn } from "@/lib/utils";

const STEP = fitStep(FLOW_LINKS.length, 150, MOTION.flow + MOTION.after);
const EDGE: Record<FlowLink["kind"], string> = { step: "text-chart-1", needs: "text-chart-2" };
const evidence = FLOW_BOXES.filter((b) => b.group === "evidence");
const placed = FLOW_BOXES.filter((b) => b.row !== null);
const lastNeedRow = Math.max(...FLOW_BOXES.filter((b) => b.group === "need").map((b) => b.row ?? 0));
const boxKey = (id: FlowId, field: "name" | "sub" | "detail") => `console.flow.box.${id}.${field}` as MessageKey;

export function ConsoleFlow({ className }: { className?: string }) {
  const t = useT();
  const [open, setOpen] = useState<FlowBox | null>(null);
  const name = (id: FlowId) => t(boxKey(id, "name"));
  return (
    <div className={cn("space-y-3", className)} data-slot="console-flow">
      <p className="text-sm">{t("console.flow.line")}</p>
      <div
        role="group"
        aria-label={t("console.flow.groupAria")}
        className="grid grid-cols-[minmax(0,1fr)_2.25rem_minmax(0,1fr)] gap-y-1 sm:grid-cols-[minmax(0,1fr)_3.5rem_minmax(0,1fr)]"
      >
        {/* The dashed frame around what the flow runs on, behind its boxes. */}
        <div
          aria-hidden
          className="-m-1.5 rounded-lg border border-dashed"
          style={{ gridColumn: NEEDS_TITLE.col, gridRow: `${NEEDS_TITLE.row} / ${lastNeedRow + 1}` }}
        />
        <p className="self-end px-1 text-xs font-medium text-muted-foreground" style={{ gridColumn: NEEDS_TITLE.col, gridRow: NEEDS_TITLE.row }}>
          {t("console.flow.needsTitle")}
        </p>
        {placed.map((b) => (
          <div key={b.id} className={cn("min-w-0", b.id === "case" && "space-y-1.5")} style={{ gridColumn: b.col ?? undefined, gridRow: b.row ?? undefined }}>
            <Box box={b} onOpen={setOpen} />
            {b.id === "case" ? (
              <div className="grid grid-cols-2 gap-1 rounded-lg border border-dashed p-1" role="group" aria-label={t("console.flow.evidenceAria")}>
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
            {t("console.flow.edge", { from: name(l.from), to: name(l.to), label: t(`console.flow.link.${l.label}` as MessageKey) })}
          </li>
        ))}
      </ol>
      <DetailPanel
        open={open !== null}
        onClose={() => setOpen(null)}
        title={open ? name(open.id) : ""}
        description={open && open.group !== "evidence" ? t(boxKey(open.id, "sub")) : undefined}
      >
        {open ? (
          <DetailFields>
            <DetailField label={t("console.flow.whatItDoes")}>{t(boxKey(open.id, "detail"))}</DetailField>
            <DetailField label={t("console.flow.source")} mono>
              {open.source}
            </DetailField>
          </DetailFields>
        ) : null}
      </DetailPanel>
    </div>
  );
}

function Box({ box, onOpen }: { box: FlowBox; onOpen: (b: FlowBox) => void }) {
  const t = useT();
  const pill = box.group === "evidence";
  const name = t(boxKey(box.id, "name"));
  // Evidence pills carry a name only; every other box has a second line.
  const sub = pill ? "" : t(boxKey(box.id, "sub"));
  return (
    <button
      type="button"
      aria-haspopup="dialog"
      aria-label={t("console.flow.openDetail", { name: sub ? `${name}, ${sub}` : name })}
      data-box={box.id}
      onClick={() => onOpen(box)}
      className={cn(
        "relative w-full min-w-0 border text-center outline-none focus-visible:ring-2 focus-visible:ring-ring",
        lift,
        pill ? "rounded-full px-2 py-0.5 text-xs" : "rounded-md px-2 py-2",
        box.group === "need" ? "bg-muted" : "bg-card",
      )}
    >
      <span className={cn("block break-words", !pill && "text-sm font-medium")}>{name}</span>
      {sub ? <span className="block text-xs text-muted-foreground max-sm:hidden">{sub}</span> : null}
    </button>
  );
}

function Edge({ link, delay }: { link: FlowLink; delay: number }) {
  const t = useT();
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
      {!across && link.rows === 1 ? (
        <span aria-hidden className="text-[11px] text-muted-foreground max-sm:hidden">
          {t(`console.flow.link.${link.label}` as MessageKey)}
        </span>
      ) : null}
    </div>
  );
}
