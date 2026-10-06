"use client";

// "Detail →" of the insight pages (spec 12): opens the shared side panel with the method, the source, the label of
// the figures and a link to the spec; with `query`, a chart drawn from one query: "What it shows", the query path and
// "Read the query →". Escape, the close button and the backdrop close it (components/detail-panel.tsx).
import { useState } from "react";
import { DetailField, DetailFields, DetailPanel } from "@/components/detail-panel";
import type { Detail } from "@/lib/pipelines";

const LINK = "rounded-sm underline underline-offset-2 outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring";

export function DetailButton({ title, detail, className = "", query = false }: { title: string; detail: Detail; className?: string; query?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" aria-haspopup="dialog" onClick={() => setOpen(true)} className={`whitespace-nowrap ${LINK} ${className}`}>
        Detail →
      </button>
      <DetailPanel
        open={open}
        onClose={() => setOpen(false)}
        title={title}
        footer={
          <a className={LINK} href={detail.spec}>
            {query ? "Read the query →" : "Read the spec →"}
          </a>
        }
      >
        <DetailFields>
          {detail.meaning ? <DetailField label={query ? "What it shows" : "What it means"}>{detail.meaning}</DetailField> : null}
          <DetailField label="How it is computed">{detail.method}</DetailField>
          <DetailField label={query ? "Query" : "Source"} mono>
            {detail.source}
          </DetailField>
          <DetailField label="Figures">
            <span className="font-mono text-xs">{detail.label}</span>
          </DetailField>
        </DetailFields>
      </DetailPanel>
    </>
  );
}
