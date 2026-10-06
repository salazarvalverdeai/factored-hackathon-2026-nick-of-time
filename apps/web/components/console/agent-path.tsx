"use client";

// "Agent path for this case" (spec 08 AC-23): /agent's graph drawing with the nodes this case's run went through
// standing out, reconstructed from the case events and the handoff card (lib/console-path.ts). Collapsed by default so
// the working view stays short; drawn final (no reveal) and fitted to the case column. "How it was read" opens the
// shared detail panel with what pins each node.
import { ChevronRight } from "lucide-react";
import { useState } from "react";
import { GraphView } from "@/components/agent/graph-view";
import { DetailField, DetailFields, DetailPanel } from "@/components/detail-panel";
import { useT } from "@/components/i18n-provider";
import { casePath } from "@/lib/console-path";
import type { MessageKey } from "@/lib/i18n";
import type { ConsoleCase } from "@/lib/types";

const LINK = "rounded-sm text-xs underline underline-offset-2 outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring";

export function AgentPath({ c }: { c: ConsoleCase }) {
  const t = useT();
  const [detail, setDetail] = useState(false);
  const { path, evidence, stop } = casePath({ events: c.events, handoff: c.handoffEmitted === false ? null : c.handoff });
  const nodes = path.filter((n) => n !== "START" && n !== "END");
  const stopText = stop ? t(`console.path.stop.${stop}` as MessageKey) : null;
  return (
    <details className="group rounded-xl border bg-card" data-slot="agent-path">
      <summary className="flex cursor-pointer list-none items-center gap-2 rounded-xl p-3 outline-none focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
        <ChevronRight aria-hidden className="size-4 shrink-0 transition-transform group-open:rotate-90 motion-reduce:transition-none" />
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("console.path.title")}</span>
        <span className="ml-auto text-xs text-muted-foreground">{nodes.length ? t("console.path.nodes", { n: nodes.length }) : t("console.path.notPinned")}</span>
      </summary>
      <div className="space-y-2 border-t p-3">
        <p className="flex flex-wrap items-baseline justify-between gap-2 text-xs text-muted-foreground">
          <span>{t("console.path.reconstructed")}</span>
          <button type="button" aria-haspopup="dialog" onClick={() => setDetail(true)} className={LINK}>
            {t("console.path.howRead")}
          </button>
        </p>
        {path.length ? (
          <>
            <GraphView path={path} reveal={false} fit />
            {stopText ? <p className="text-xs text-muted-foreground">{stopText}</p> : null}
          </>
        ) : (
          <p className="text-sm text-muted-foreground">{stopText}</p>
        )}
      </div>
      <DetailPanel open={detail} onClose={() => setDetail(false)} title={t("console.path.title")} description={t("console.path.panelDescription")}>
        <DetailFields>
          {evidence.map((e, i) => (
            <DetailField key={`${e.node}-${e.source}-${i}`} label={<span className="font-mono">{e.node}</span>}>
              {e.source === "graph" || e.source === "handoff_card" ? (
                t(`console.path.source.${e.source}` as MessageKey)
              ) : (
                <span className="font-mono text-xs">{e.source}</span>
              )}
              <span className="block text-xs text-muted-foreground">{t(`console.path.why.${e.source}` as MessageKey)}</span>
            </DetailField>
          ))}
          {stopText ? <DetailField label={t("console.path.stopLabel")}>{stopText}</DetailField> : null}
        </DetailFields>
      </DetailPanel>
    </details>
  );
}
