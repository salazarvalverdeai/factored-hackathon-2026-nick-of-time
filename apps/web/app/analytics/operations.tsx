"use client";

// The "Operation" section of /analytics (spec 12 T6, AC-02; spec 14 §11): a three-position switch over ops_kpis.json.
// Every bar shows its detail on hover and on keyboard focus, and every chart has a table view with the same values.
// Motion kit: the cards rise in sequence, the monthly columns grow once, and the switch crossfades the charts while the
// columns move to the other series' heights (nothing remounts, so an open table or the keyboard focus stays).
import Link from "next/link";
import { useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { DetailField, DetailFields, DetailPanel } from "@/components/detail-panel";
import { EmptyState } from "@/components/states";
import {
  OPS_INTRO, POSITIONS, SAME_CONTACT, SAME_CONTACT_NOTE, chartDetail, dayName, daysText, introDetail, liveDetail, opsState, pct,
  pendingDetail, tableRows, type Chart, type Detail, type LiveView, type ModeKey, type OpsSeries, type Position,
} from "@/lib/ops";
import { FOCUS, PALETTE, Swatch, TableView, TipBody, useTip } from "./charts";
import { CountText, Crossfade, GrowBar, Stagger } from "@/components/motion";
import { fitStep } from "@/lib/motion";

const COLOR: Record<string, string> = { bank_today: "var(--series-1)", replay: "var(--series-2)" };
const MODE_COLOR: Record<ModeKey, string> = { live: "var(--series-1)", replay: "var(--series-2)" };
const fmt = (chart: Chart, v: number | null) => (chart.metric.kind === "rate" ? pct(v) : daysText(chart.metric.id, v));
/** The one line under a chart: the first sentence of its note; the whole note is in the detail panel's method. */
const firstSentence = (text: string) => text.split(/(?<=\.)\s+/)[0];
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
    <figure className={`min-w-0 rounded-lg border p-6 text-card-foreground ${context ? "border-dashed bg-card/60" : "bg-card"}`}>
      <p className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">{tag}</p>
      <h3 className="mt-1 text-base font-semibold">{chart.title}</h3>
      <p className="mt-2 flex flex-wrap items-baseline gap-x-2">
        <CountText className="text-3xl font-semibold tracking-tight tabular-nums" text={fmt(chart, chart.total.value)} />
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
        {chart.points.map((p, i) => (
          <GrowBar
            key={p.month}
            axis="y"
            delay={i * fitStep(chart.points.length, 50, 500)}
            tabIndex={0}
            role="img"
            aria-label={`${monthName(p.month)}: ${fmt(chart, p.value)}`}
            className={`min-w-0 flex-1 rounded-t-[2px] transition-[height,background-color,filter] duration-500 ease-out hover:brightness-110 motion-reduce:transition-none ${FOCUS}`}
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
      <p className="mt-4 text-sm">
        {firstSentence(chart.note)}{" "}
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

/** The Live position when its file is ready: public demo traffic in both modes, four headline cards, the cases per day
 * (each column split by mode), the mode breakdown, one plain line with "Detail →" and the table, collapsed. */
function LiveSection({ view, onDetail }: { view: LiveView; onDetail: () => void }) {
  const { bind, node } = useTip();
  const { live } = view;
  const short = (d: string) => dayName(d).replace(/, \d{4}$/, "");
  return (
    <div className="mt-6">
      <h3 className="text-base font-semibold">{live.message}</h3>
      <Stagger className="mt-3 grid grid-cols-2 gap-4 lg:grid-cols-4" step={90}>
        {view.cards.map((card) => (
          <div key={card.id} className="min-w-0 rounded-lg border bg-card p-4 text-card-foreground">
            <p className="text-sm text-muted-foreground">{card.title}</p>
            <p className="mt-1 flex flex-wrap items-baseline gap-x-2">
              <CountText className="text-3xl font-semibold tracking-tight tabular-nums" text={card.value} />
              <span className="font-mono text-xs text-muted-foreground">{live.label}</span>
            </p>
            <p className="mt-1 text-xs text-muted-foreground">{card.sub}</p>
          </div>
        ))}
      </Stagger>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <figure className="min-w-0 rounded-lg border bg-card p-6 text-card-foreground">
          <h4 className="text-sm font-semibold">Cases per day</h4>
          <p className="text-xs text-muted-foreground">By the UTC day the case was written, split by mode</p>
          <div role="group" aria-label="Cases per day" className="mt-4 flex h-28 items-end gap-2 border-b">
            {view.bars.map((bar, i) => (
              <GrowBar
                key={bar.day}
                axis="y"
                delay={i * fitStep(view.bars.length, 50, 500)}
                tabIndex={0}
                role="img"
                aria-label={`${dayName(bar.day)}: ${bar.detail.map(([k, v]) => `${k} ${v}`).join(", ")}`}
                className={`flex max-w-14 min-w-0 flex-1 flex-col-reverse overflow-hidden rounded-t-[2px] hover:brightness-110 ${FOCUS}`}
                style={{ height: `${Math.max(1.5, (bar.cases / view.scaleMax) * 100)}%` }}
                {...bind(<TipBody title={dayName(bar.day)} rows={bar.detail} />)}
              >
                <span style={{ flexGrow: bar.byMode.replay, background: MODE_COLOR.replay }} />
                <span style={{ flexGrow: bar.byMode.live, background: MODE_COLOR.live }} />
              </GrowBar>
            ))}
          </div>
          <div className="mt-1 flex gap-2 text-[11px] text-muted-foreground" aria-hidden>
            {view.bars.map((bar) => (
              <span key={bar.day} className="max-w-14 min-w-0 flex-1 truncate text-center">{short(bar.day)}</span>
            ))}
          </div>
        </figure>
        <figure className="min-w-0 rounded-lg border bg-card p-6 text-card-foreground">
          <h4 className="text-sm font-semibold">By mode</h4>
          <p className="text-xs text-muted-foreground">Share of the {view.live.total.cases} cases</p>
          <div className="mt-4 flex h-3 overflow-hidden rounded-full bg-muted" aria-hidden>
            {view.modes.map((m, i) => (
              <GrowBar key={m.mode} axis="x" delay={i * 120} className="h-full" style={{ width: `${m.share * 100}%`, background: MODE_COLOR[m.mode] }} />
            ))}
          </div>
          <ul className="mt-4 space-y-2 text-sm">
            {view.modes.map((m) => (
              <li key={m.mode} className="flex flex-wrap items-center gap-x-2">
                <Swatch color={MODE_COLOR[m.mode]} />
                <span className="font-medium">{m.title}</span>
                <CountText className="tabular-nums" text={`${m.text} (${pct(m.share)})`} />
                <span className="text-xs text-muted-foreground">{m.note}</span>
              </li>
            ))}
          </ul>
        </figure>
      </div>
      <p className="mt-4 text-sm">
        {view.line}{" "}
        <button type="button" onClick={onDetail} className={`${LINK} rounded-sm`}>
          Detail →
        </button>
      </p>
      <TableView head={view.head} rows={view.rows} />
      <p className="mt-6 font-mono text-xs break-words text-muted-foreground">{view.footer}</p>
      {node}
    </div>
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
      ) : state.kind === "live" ? (
        <LiveSection view={state.view} onDetail={() => setDetail(liveDetail(state.view.live))} />
      ) : (
        <>
          <Crossfade id={position}>
          <h3 className="mt-6 text-sm font-semibold">Compared with the other series</h3>
          <Stagger className="mt-3 grid gap-4 md:grid-cols-2" step={90}>
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
          </Stagger>
          <h3 className="mt-8 text-sm font-semibold">Context for {state.series.name} only</h3>
          <p className="mt-0.5 max-w-3xl text-sm text-muted-foreground">Defined differently in each series, so never compared.</p>
          <Stagger className="mt-3 grid gap-4 md:grid-cols-2" step={90}>
            {state.charts.filter((c) => c.metric.role === "context").map((chart) => (
              <MetricChart key={chart.metric.id} chart={chart} color={COLOR[position]} other={null}
                           tag={`Context · ${state.series.name} only`}
                           onDetail={() => setDetail(chartDetail(chart, state.series))} />
            ))}
          </Stagger>
          <p className="mt-6 font-mono text-xs break-words text-muted-foreground">
            {state.series.source} · {state.series.window.join(" to ")}
          </p>
          </Crossfade>
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
