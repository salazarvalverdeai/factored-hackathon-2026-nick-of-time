"use client";

// A button that opens the shared side panel (components/detail-panel.tsx) with whatever /agent puts in it: a zone's
// rule, a tool's contract, a guardrail, an engine, or a section's sources. The trigger can be a link-styled "Detail →"
// or a whole chip; Escape, the close button and the backdrop close the panel and focus comes back here.
import { useState, type ReactNode } from "react";
import { DetailPanel } from "@/components/detail-panel";
import { cn } from "@/lib/utils";

export function DetailTrigger({
  label,
  title,
  description,
  footer,
  children,
  className,
  ariaLabel,
}: {
  label: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
  className?: string;
  ariaLabel?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" aria-haspopup="dialog" aria-label={ariaLabel} onClick={() => setOpen(true)} className={cn("outline-none focus-visible:ring-2 focus-visible:ring-ring", className)}>
        {label}
      </button>
      <DetailPanel open={open} onClose={() => setOpen(false)} title={title} description={description} footer={footer}>
        {children}
      </DetailPanel>
    </>
  );
}
