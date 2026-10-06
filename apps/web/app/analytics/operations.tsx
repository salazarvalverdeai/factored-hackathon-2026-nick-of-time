"use client";

// The "Operation" section of /analytics (spec 12 T6, AC-02; spec 14 §11): a three-position switch over ops_kpis.json.
// Every bar shows its detail on hover and on keyboard focus, and every chart has a table view with the same values.
import Link from "next/link";
import { useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { DetailField, DetailFields, DetailPanel } from "@/components/detail-panel";
import { EmptyState } from "@/components/states";
import {
  OPS_INTRO, POSITIONS, SAME_CONTACT, SAME_CONTACT_NOTE, chartDetail, daysText, introDetail, opsState, pct, pendingDetail, tableRows,
  type Chart, type Detail, type OpsSeries, type Position,
} from "@/lib/ops";
import { FOCUS, PALETTE, TableView, TipBody, useTip } from "./charts";

const COLOR: Record<string, string> = { bank_today: "var(--series-1)", replay: "var(--series-2)" };
const fmt = (chart: Chart, v: number | null) => (chart.metric.kind === "rate" ? pct(v) : daysText(chart.metric.id, v));
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

const LINK = `whitespace-nowrap text-primary underline-offset-4 hover:underline ${FOCUS}`;

function MetricChart({ chart, color, other, tag, onDetail }: {
  chart: Chart; color: string; other: { text: string; label: string } | null; tag: string; onDetail: () => void;
}) {
  const { bind, node } = useTip();
  const months = `${chart.points.length} months`;
  const context = chart.metric.role === "context";
  return (
    <figure className={`min-w-0 rounded-lg border p-5 text-card-foreground ${context ? "border-dashed bg-card/60" : "bg-card"}`}>
      <p className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">{tag}</p>
      <h3 className="mt-1 text-base font-semibold">{chart.title}</h3>
      <p className="mt-2 flex flex-wrap items-baseline gap-x-2">
        <span className="text-3xl font-semibold tracking-tight tabular-nums">{fmt(chart, chart.total.value)}</span>
        <span className="font-mono text-xs text-muted-foreground">{chart.label}</span>
      </p>
      {chart.metric.id === "days_to_receipt" && fmt(chart, chart.total.value) === SAME_CONTACT ? (
        <p className="text-sm">{SAME_CONTACT_NOTE}</p>
      ) : null}
      <p className="text-xs text-muted-foreground">
        {months}
        {other ? ` · other series: ${other.text} ` : ""}
        {other ? <span className="font-mono">{other.label}</span> : null}
      </p>
      <div className="mt-4 flex h-24 items-end gap-1 border-b" aria-label={`${chart.title} per month`} role="group">
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
        <button type="button" onClick={onDetail} className={`${LINK} rounded-sm`}>
          Detail →
        </button>
      </p>
      {chart.secondary.map((extra) => (
        <div key={extra.title} className="mt-3 rounded-md border border-dashed px-3 py-2 text-xs text-muted-foreground">
          <p>
            <span className="text-foreground">{extra.title}: </span>
            <span className="font-semibold text-foreground tabular-nums">{extra.value}</span>{" "}
            <span className="font-mono">{chart.label}</span>
          </p>
          <p className="mt-1">{extra.note}</p>
        </div>
      ))}
      <TableView head={["Month", ...chart.total.detail.map(([k]) => k)]} rows={tableRows(chart)} />
      {node}
    </figure>
  );
}

export function Operations({ file }: { file: { data?: { series?: OpsSeries } } | null }) {
  const [position, setPosition] = useState<Position>("bank_today");
  const state = opsState(file, position);
  const otherKey = position === "bank_today" ? "replay" : "bank_today";
  const twin = opsState(file, otherKey);
  const all = file?.data?.series;
  const [detail, setDetail] = useState<Detail | null>(null);
  return (
    <section aria-labelledby="ops-title" className={`mt-12 ${PALETTE}`}>
      <h2 id="ops-title" className="text-lg font-semibold">
        Operation
      </h2>
      <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
        {OPS_INTRO.split("the system")[0]}
        <Link href="/agent" className={LINK}>
          the system
        </Link>
        {OPS_INTRO.split("the system")[1]}{" "}
        <button type="button" onClick={() => setDetail(introDetail(all))} className={`${LINK} rounded-sm`}>
          Detail →
        </button>
      </p>
      <div className="mt-4">
        <Switch value={position} onChange={setPosition} />
      </div>
      {state.kind === "pending" ? (
        <>
          <EmptyState className="mt-4" title={state.title} hint={state.missing} />
          <p className="mt-2 text-sm">
            <button type="button" onClick={() => setDetail(pendingDetail(state, all))} className={`${LINK} rounded-sm`}>
              Detail →
            </button>
          </p>
        </>
      ) : (
        <>
          <p className="mt-3 font-mono text-xs break-words text-muted-foreground">
            {state.series.source} · {state.series.window.join(" to ")}
          </p>
          <h3 className="mt-5 text-sm font-semibold">Compared with the other series</h3>
          <p className="mt-0.5 max-w-3xl text-sm text-muted-foreground">
            Only these two figures are set side by side, each with its own definition.
          </p>
          <div className="mt-3 grid gap-4 md:grid-cols-2">
            {state.charts.filter((c) => c.metric.role === "comparison").map((chart) => {
              const match = twin.kind === "ready" ? twin.charts.find((c) => c.metric.id === chart.metric.id) : undefined;
              const other = match && twin.kind === "ready"
                ? { text: `${twin.series.name}, ${match.title.toLowerCase()} ${fmt(match, match.total.value)}`, label: match.label }
                : null;
              const tag = twin.kind === "ready" ? `Compared with: ${twin.series.name}` : "Comparison";
              return (
                <MetricChart key={chart.metric.id} chart={chart} color={COLOR[position]} other={other} tag={tag}
                             onDetail={() => setDetail(chartDetail(chart, state.series))} />
              );
            })}
          </div>
          <h3 className="mt-8 text-sm font-semibold">Context for {state.series.name} only</h3>
          <p className="mt-0.5 max-w-3xl text-sm text-muted-foreground">
            These figures are defined differently in each series, so they are never compared: read each one with its own
            definition.
          </p>
          <div className="mt-3 grid gap-4 md:grid-cols-2">
            {state.charts.filter((c) => c.metric.role === "context").map((chart) => (
              <MetricChart key={chart.metric.id} chart={chart} color={COLOR[position]} other={null}
                           tag={`Context · ${state.series.name} only`}
                           onDetail={() => setDetail(chartDetail(chart, state.series))} />
            ))}
          </div>
        </>
      )}
      <DetailPanel
        open={detail !== null}
        onClose={() => setDetail(null)}
        title={detail?.title ?? ""}
        description={detail?.description}
        footer={detail ? (
          <span className="flex flex-col gap-1">
            <a href={detail.href} className={LINK}>
              Read spec 14 §11 →
            </a>
            {detail.extra ? (
              <a href={detail.extra.href} className={LINK}>
                {detail.extra.label}
              </a>
            ) : null}
          </span>
        ) : null}
      >
        {detail ? (
          <DetailFields>
            <DetailField label="Method">
              {detail.method.map((line) => (
                <p key={line} className="mt-1 first:mt-0">{line}</p>
              ))}
            </DetailField>
            <DetailField label="Source query" mono>{detail.source}</DetailField>
            <DetailField label="Window">{detail.window}</DetailField>
            <DetailField label="Label of the figures" mono>{detail.label}</DetailField>
          </DetailFields>
        ) : null}
      </DetailPanel>
    </section>
  );
}
