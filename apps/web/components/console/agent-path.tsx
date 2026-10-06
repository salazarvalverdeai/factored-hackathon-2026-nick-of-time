"use client";

// "Agent path for this case" (spec 08 AC-23): /agent's graph drawing with the nodes this case's run went through
// standing out, reconstructed from the case events and the handoff card (lib/console-path.ts). Collapsed by default so
// the working view stays short; drawn final (no reveal). "How it was read" opens the shared detail panel with the event
// that pins each node.
import { GraphView } from "@/components/agent/graph-view";
import { DetailField, DetailFields, DetailPanel } from "@/components/detail-panel";
import { casePath } from "@/lib/console-path";
import type { ConsoleCase } from "@/lib/types";
import { ChevronRight } from "lucide-react";
import { useState } from "react";

const LINK = "rounded-sm text-xs underline underline-offset-2 outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring";

export function AgentPath({ c }: { c: ConsoleCase }) {
  const [detail, setDetail] = useState(false);
  const { path, evidence, stop } = casePath({ events: c.events, handoff: c.handoffEmitted === false ? null : c.handoff });
  const nodes = path.filter((n) => n !== "START" && n !== "END");
  return (
    <details className="group rounded-xl border bg-card" data-slot="agent-path">
      <summary className="flex cursor-pointer list-none items-center gap-2 rounded-xl p-3 outline-none focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
        <ChevronRight aria-hidden className="size-4 shrink-0 transition-transform group-open:rotate-90 motion-reduce:transition-none" />
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Agent path for this case</span>
        <span className="ml-auto text-xs text-muted-foreground">{nodes.length ? `${nodes.length} nodes` : "not pinned"}</span>
      </summary>
      <div className="space-y-2 border-t p-3">
        <p className="flex flex-wrap items-baseline justify-between gap-2 text-xs text-muted-foreground">
          <span>Reconstructed from the case events.</span>
          <button type="button" aria-haspopup="dialog" onClick={() => setDetail(true)} className={LINK}>
            How it was read →
          </button>
        </p>
        {path.length ? (
          <>
            <GraphView path={path} reveal={false} className="xl:grid-cols-1" />
            {stop ? <p className="text-xs text-muted-foreground">{stop}</p> : null}
          </>
        ) : (
          <p className="text-sm text-muted-foreground">{stop}</p>
        )}
      </div>
      <DetailPanel
        open={detail}
        onClose={() => setDetail(false)}
        title="Agent path for this case"
        description="Reconstructed from the case events and the handoff card; a node they cannot pin is left out."
      >
        <DetailFields>
          {evidence.map((e, i) => (
            <DetailField key={`${e.node}-${e.source}-${i}`} label={<span className="font-mono">{e.node}</span>}>
              {e.source === "graph" ? "Forced by the graph" : e.source === "handoff_card" ? "Handoff card" : <span className="font-mono text-xs">{e.source}</span>}
              <span className="block text-xs text-muted-foreground">{e.why}</span>
            </DetailField>
          ))}
          {stop ? <DetailField label="Where it stops">{stop}</DetailField> : null}
        </DetailFields>
      </DetailPanel>
    </details>
  );
}
