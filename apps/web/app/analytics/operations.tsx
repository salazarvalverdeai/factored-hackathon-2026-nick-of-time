"use client";

// The "Operation" section of /analytics (spec 12 T6, AC-02; spec 14 §11): a three-position switch over ops_kpis.json.
// Every bar shows its detail on hover and on keyboard focus, and every chart has a table view with the same values.
import Link from "next/link";
import { useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { EmptyState } from "@/components/states";
import { DETAIL, POSITIONS, days, opsState, pct, tableRows, type Chart, type OpsSeries, type Position } from "@/lib/ops";
import { FOCUS, PALETTE, TableView, TipBody, useTip } from "./charts";

const COLOR: Record<string, string> = { bank_today: "var(--series-1)", replay: "var(--series-2)" };
const fmt = (chart: Chart, v: number | null) => (chart.metric.kind === "rate" ? pct(v) : days(v));
const monthName = (m: string) =>
  new Date(`${m}-15T00:00:00Z`).toLocaleDateString("en-US", { month: "short", year: "numeric", timeZone: "UTC" });

function Switch({ value, onChange }: { value: Position; onChange: (p: Position) => void }) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const move = (e: KeyboardEvent, i: number) => {
    const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const next = (i + step + POSITIONS.length) % POSITIONS.length;
    onChange(POSITIONS[next].key);
    refs.current[next]?.focus();
  };
  return (
    <div role="radiogroup" aria-label="Series" className="inline-flex w-full flex-wrap gap-1 rounded-lg border bg-muted/40 p-1 sm:w-auto">
      {POSITIONS.map((p, i) => {
        const on = p.key === value;
        return (
          <button
            key={p.key}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="button"
            role="radio"
            aria-checked={on}
            tabIndex={on ? 0 : -1}
            onClick={() => onChange(p.key)}
            onKeyDown={(e) => move(e, i)}
            className={`flex-1 rounded-md px-3 py-1.5 text-sm whitespace-nowrap transition sm:flex-none ${FOCUS} ${
              on ? "bg-background font-medium text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {p.label}
          </button>
        );
      })}
    </div>
  );
}

function MetricChart({ chart, color, other }: { chart: Chart; color: string; other: { text: string; label: string } | null }) {
  const { bind, node } = useTip();
  return (
    <figure className="min-w-0 rounded-lg border bg-card p-5 text-card-foreground">
      <h3 className="text-base font-semibold">{chart.metric.title}</h3>
      <p className="mt-2 flex flex-wrap items-baseline gap-x-2">
        <span className="text-3xl font-semibold tracking-tight tabular-nums">{fmt(chart, chart.total.value)}</span>
        <span className="font-mono text-xs text-muted-foreground">{chart.label}</span>
      </p>
      <p className="text-xs text-muted-foreground">
        12 months{other ? ` · other series: ${other.text} ` : ""}
        {other ? <span className="font-mono">{other.label}</span> : null}
      </p>
      <div className="mt-4 flex h-24 items-end gap-[3px] border-b" aria-label={`${chart.metric.title} per month`} role="group">
        {chart.points.map((p) => (
          <div
            key={p.month}
            tabIndex={0}
            role="img"
            aria-label={`${monthName(p.month)}: ${fmt(chart, p.value)}`}
            className={`min-w-0 flex-1 rounded-t-[2px] transition hover:brightness-110 ${FOCUS}`}
            style={{
              height: p.value === null ? "100%" : `${Math.max(1.5, (p.value / chart.scaleMax) * 100)}%`,
              background: p.value === null ? "transparent" : color,
              border: p.value === null ? "1px dashed var(--border)" : undefined,
            }}
            {...bind(<TipBody title={monthName(p.month)} rows={p.detail} />)}
          />
        ))}
      </div>
      <div className="mt-1 flex justify-between text-[11px] text-muted-foreground">
        <span>{monthName(chart.points[0]?.month ?? "")}</span>
        <span>{monthName(chart.points.at(-1)?.month ?? "")}</span>
      </div>
      <p className="mt-3 text-sm">
        {chart.note}{" "}
        <a href={chart.label === "[data]" ? DETAIL.bank_today : DETAIL.replay} className={`whitespace-nowrap text-primary underline-offset-4 hover:underline ${FOCUS}`}>
          Detail →
        </a>
      </p>
      <TableView head={["Month", ...chart.total.detail.map(([k]) => k)]} rows={tableRows(chart)} />
      {node}
    </figure>
  );
}

export function Operations({ file }: { file: { data?: { series?: OpsSeries } } | null }) {
  const [position, setPosition] = useState<Position>("bank_today");
  const state = opsState(file, position);
  const all = file?.data?.series;
  const otherKey = position === "bank_today" ? "replay" : "bank_today";
  return (
    <section aria-labelledby="ops-title" className={`mt-12 ${PALETTE}`}>
      <h2 id="ops-title" className="text-lg font-semibold">
        Operation
      </h2>
      <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
        The bank&apos;s own unrecognized and wrongful charge complaints of the last twelve months, as the bank handled them
        and as <Link href="/agent" className={`text-primary underline-offset-4 hover:underline ${FOCUS}`}>the system</Link>{" "}
        would take them in. The simulation replays the bank&apos;s own complaints with the rules engine; it does not model
        the final resolution time, which a person decides.
      </p>
      <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
        Most of these complaints cannot be tied to one card charge of the customer, so the system asks which charge it is
        and the contact counts as not resolved. Cases opened in 2025 get no legal deadline, because the repository has
        verified holiday calendars for 2026 only.{" "}
        <a href={DETAIL.method} className={`whitespace-nowrap text-primary underline-offset-4 hover:underline ${FOCUS}`}>
          Detail →
        </a>
      </p>
      <div className="mt-4">
        <Switch value={position} onChange={setPosition} />
      </div>
      {state.kind === "pending" ? (
        <EmptyState className="mt-4" title={state.title} hint={state.missing} />
      ) : (
        <>
          <p className="mt-3 font-mono text-xs break-words text-muted-foreground">
            {state.series.source} · {state.series.window.join(" to ")}
          </p>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            {state.charts.map((chart) => {
              const twin = all?.[otherKey];
              const otherTotal = twin && chart.metric.key in twin.total ? opsState(file, otherKey) : null;
              const match = otherTotal?.kind === "ready" ? otherTotal.charts.find((c) => c.metric.key === chart.metric.key) : undefined;
              return (
                <MetricChart
                  key={chart.metric.key}
                  chart={chart}
                  color={COLOR[position]}
                  other={match && twin ? { text: `${twin.name} ${fmt(match, match.total.value)}`, label: twin.label } : null}
                />
              );
            })}
          </div>
        </>
      )}
      {state.kind === "pending" ? (
        <p className="mt-2 text-sm">
          <a href={state.detail} className={`text-primary underline-offset-4 hover:underline ${FOCUS}`}>
            Detail →
          </a>
        </p>
      ) : null}
    </section>
  );
}
