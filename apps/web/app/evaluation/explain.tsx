// Small shared parts of /evaluation (spec 12 AC-11): a plain explanation with its "Detail →" button (opens the shared side panel), the limitations block,
// and one interval row that every chart of the page reuses. Plain SVG-free markup, no dependency.
import type { ReactNode } from "react";
import { DetailButton } from "@/components/detail-button";
import { DETAILS, DEVELOPMENT_CHIP, detailUrl } from "@/lib/evaluation";

/** One or two plain lines on what a chart means, and a link to the markdown that defines it. */
export function Explain({ children, detail, className = "" }: { children: ReactNode; detail: keyof typeof DETAILS; className?: string }) {
  const d = DETAILS[detail];
  return (
    <p data-slot="explain" className={`text-sm text-muted-foreground ${className}`}>
      {children}{" "}
      <DetailButton title={d.title} detail={{ meaning: d.meaning, method: d.method, source: d.source, label: d.label, spec: detailUrl(detail) }} />
    </p>
  );
}

/** spec 12 AC-05: the small chip beside the title of a section whose file is a development run (the page notice says why). */
export function DevChip({ show }: { show: boolean }) {
  return show ? (
    <span data-slot="development-chip" className="ml-2 whitespace-nowrap rounded-full border border-brand-amber px-2 py-0.5 align-middle text-xs font-normal text-foreground">
      {DEVELOPMENT_CHIP}
    </span>
  ) : null;
}

/** spec 12 AC-11: plain sentences for the files that exist, no tags. Nothing renders when there is no limitation. */
export function Limitations({ items }: { items: string[] }) {
  if (items.length === 0) return null;
  return (
    <section aria-label="Limitations" data-slot="limitations" className="rounded-lg border bg-card p-5 text-card-foreground">
      <h2 className="text-base font-semibold">Limitations</h2>
      <p className="mt-0.5 text-sm text-muted-foreground">What to keep in mind before reading any figure above.</p>
      <ul className="mt-3 list-disc space-y-1.5 pl-5 text-sm">
        {items.map((text) => (
          <li key={text}>{text}</li>
        ))}
      </ul>
    </section>
  );
}

/**
 * A bar from 0 to the value, the 95% interval over it and a dot at the value, on a 0 to 1 scale. The caller wraps it
 * in the focusable element that carries the tooltip, so hover and keyboard focus show the same detail (AC-06, AC-07).
 */
export function IntervalBar({ value, low, high, color }: { value: number | null; low: number | null; high: number | null; color: string }) {
  const has = value !== null;
  return (
    <div className="relative h-4 flex-1">
      <div className="absolute inset-x-0 top-1/2 h-px bg-border" />
      {has ? <div className="absolute inset-y-0.5 left-0 rounded-r-sm opacity-20" style={{ width: `${value * 100}%`, background: color }} /> : null}
      {has && low !== null && high !== null ? (
        <div
          className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full opacity-45"
          style={{ left: `${low * 100}%`, width: `${Math.max((high - low) * 100, 0.5)}%`, background: color }}
        />
      ) : null}
      {has ? <div className="absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-card" style={{ left: `${value * 100}%`, background: color }} /> : null}
    </div>
  );
}
