"use client";

// "The data at a glance" on /data (spec 12 AC-03, AC-07, AC-09): five charts of the committed outputs of
// queries/data/d02..d06, shaped by lib/data-profile.ts. Every mark gives its detail on hover and on keyboard focus,
// every chart has a table view, and the motion kit grows the bars, draws the line and counts the headline figures
// once; with reduced motion everything renders in its final state. Plain HTML and SVG, no new dependency.
import type { ReactNode } from "react";
import { CountText, DrawPath, GrowBar, Stagger } from "@/components/motion";
import { DetailButton } from "@/components/detail-button";
import { EmptyState } from "@/components/states";
import { FOCUS, Swatch, TableView, TipBody, useTip } from "@/app/analytics/charts";
import {
  PRODUCT_TYPES,
  compact,
  int,
  monthLong,
  monthName,
  flagText,
  pct,
  pendingHint,
  smallPct,
  type DataProfile,
  type ProfileKey,
} from "@/lib/data-profile";
import { MOTION, fitStep, growTarget } from "@/lib/motion";
import type { Detail } from "@/lib/pipelines";
import { cn } from "@/lib/utils";

// Series colors, checked with the dataviz palette validator on the card surfaces (#ffffff, #111827): teal (#0d9488,
// BRAND.md chart step) and violet pass every adjacent check in both themes; the slate "other" fill is a de-emphasis
// context (legend and table carry it). The score bands are one violet ramp, validated as ordinal in both themes.
const PALETTE =
  "[--dp-1:#0d9488] [--dp-2:#7c3aed] dark:[--dp-2:#8b5cf6] [--dp-other:#cbd5e1] dark:[--dp-other:#475569] " +
  "[--dp-b1:#a78bfa] dark:[--dp-b1:#6d28d9] [--dp-b2:#7c3aed] dark:[--dp-b2:#a78bfa] [--dp-b3:#4c1d95] dark:[--dp-b3:#ddd6fe]";
const FILL: Record<string, string> = {
  credit: "var(--dp-1)",
  debit: "var(--dp-2)",
  other: "var(--dp-other)",
  Fees: "var(--dp-1)",
  Transactions: "var(--dp-2)",
  null: "var(--dp-other)",
  lt30: "var(--dp-b1)",
  "30_49": "var(--dp-b2)",
  ge50: "var(--dp-b3)",
  nullRate: "var(--dp-2)",
  flag: "var(--dp-1)",
};
const INK = "var(--foreground)";
const AXIS = "text-[11px] tabular-nums text-muted-foreground";
const GUTTER = "ml-11";

type Tip = ReturnType<typeof useTip>;

/** A column or flag name that may wrap after an underscore, never inside a word. */
function Snake({ name }: { name: string }) {
  return name.split("_").map((part, i) => (
    <span key={i}>
      {i ? "_" : ""}
      {i ? <wbr /> : null}
      {part}
    </span>
  ));
}

function Label({ children }: { children: string }) {
  return <span className="font-mono text-xs font-normal text-muted-foreground">{children}</span>;
}

/** The card: a title, ONE plain line with "Detail →", the chart, then its table view. */
function Card({ title, line, detail, className, children }: { title: string; line: string; detail: Detail; className?: string; children: ReactNode }) {
  return (
    <figure aria-label={title} className={cn("min-w-0 rounded-lg border bg-card p-5 text-card-foreground", className)}>
      <h3 className="text-base font-semibold">{title}</h3>
      <p className="mt-0.5 text-sm text-muted-foreground">
        {line} <DetailButton title={title} detail={detail} query />
      </p>
      <div className="mt-4">{children}</div>
    </figure>
  );
}

function Pending({ title, k, className }: { title: string; k: ProfileKey; className?: string }) {
  return (
    <figure aria-label={title} className={cn("min-w-0 rounded-lg border bg-card p-5 text-card-foreground", className)}>
      <h3 className="text-base font-semibold">{title}</h3>
      <EmptyState className="mt-4" title="Results pending" hint={pendingHint(k)} />
    </figure>
  );
}

/** The headline figure counts up once; its label sits beside it. */
function Headline({ value, text, label }: { value: string; text: ReactNode; label: string }) {
  return (
    <p className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
      <span className="text-3xl font-semibold tracking-tight">
        <CountText text={value} delay={150} />
      </span>
      <span className="text-sm text-muted-foreground">
        {text} <Label>{label}</Label>
      </span>
    </p>
  );
}

function Legend({ items }: { items: { color: string; text: ReactNode; line?: boolean }[] }) {
  return (
    <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
      {items.map((item, i) => (
        <span key={i} className="inline-flex items-center gap-1.5">
          {item.line ? <span aria-hidden className="inline-block h-0.5 w-4 rounded-full" style={{ background: item.color }} /> : <Swatch color={item.color} />}
          {item.text}
        </span>
      ))}
    </div>
  );
}

/** Horizontal gridlines with their values in the left gutter; the plot sits right of the gutter. */
function Grid({ ticks, max, format }: { ticks: number[]; max: number; format: (n: number) => string }) {
  return (
    <>
      {ticks.map((t) => (
        <div key={t} aria-hidden className="absolute inset-x-0 border-t border-border" style={{ bottom: `${(t / max) * 100}%` }}>
          <span className={cn("absolute right-full mr-2 -translate-y-1/2 whitespace-nowrap", AXIS)}>{format(t)}</span>
        </div>
      ))}
    </>
  );
}

type Column = { key: string; total: number; parts: { key: string; n: number }[]; dim?: boolean; tip: ReactNode; aria: string };

/**
 * Stacked columns over months: a 2 px surface gap between segments, a 4 px rounded top, columns at most 24 px wide.
 * Each month's hit target is its whole slot (plot and the strip under it), so the pointer never has to land on a bar.
 */
function Columns({ columns, ticks, height, strip, labels, tip }: {
  columns: Column[]; ticks: number[]; height: number; strip?: ReactNode; labels: ReactNode; tip: Tip;
}) {
  const max = ticks[ticks.length - 1];
  const n = columns.length;
  const step = fitStep(n, MOTION.step, MOTION.grow, 150);
  return (
    <div className="relative">
      <div className={cn("relative", GUTTER)} style={{ height }}>
        <Grid ticks={ticks} max={max} format={compact} />
        <div aria-hidden className="absolute inset-0 flex items-end gap-px sm:gap-0.5">
          {columns.map((c, i) => (
            <div key={c.key} className="flex h-full min-w-0 flex-1 items-end justify-center">
              <GrowBar
                axis="y"
                delay={150 + i * step}
                className="flex w-full max-w-6 flex-col-reverse gap-[2px] overflow-hidden rounded-t-[4px]"
                style={{ height: `${growTarget(c.total, max)}%`, opacity: c.dim ? 0.5 : 1 }}
              >
                {c.parts
                  .filter((p) => p.n > 0)
                  .map((p) => (
                    <div key={p.key} className="min-h-0" style={{ flexGrow: p.n, flexBasis: 0, background: FILL[p.key] }} />
                  ))}
              </GrowBar>
            </div>
          ))}
        </div>
      </div>
      {strip}
      {/* One focusable slot per month over the plot and the strip: the same detail on hover and on Tab. */}
      <div className={cn("absolute inset-y-0 right-0 flex gap-px sm:gap-0.5", GUTTER)} style={{ left: 0 }}>
        {columns.map((c) => (
          <div key={c.key} tabIndex={0} role="img" aria-label={c.aria} className={cn("min-w-0 flex-1 rounded-sm hover:bg-foreground/5 focus-visible:bg-foreground/5", FOCUS)} {...tip.bind(c.tip)} />
        ))}
      </div>
      {labels}
    </div>
  );
}

/** Month labels centered under their slot; `rows` lets a second line carry the year. */
function XLabels({ n, items }: { n: number; items: { i: number; text: string; className?: string; row?: number }[] }) {
  const rows = Math.max(1, ...items.map((x) => (x.row ?? 0) + 1));
  return (
    <div aria-hidden className={cn("pointer-events-none relative mt-1.5", GUTTER)} style={{ height: rows * 15 }}>
      {items.map((x) => (
        <span
          key={`${x.row ?? 0}-${x.i}`}
          className={cn("absolute -translate-x-1/2 whitespace-nowrap leading-none", AXIS, x.className)}
          style={{ left: `${((x.i + 0.5) / n) * 100}%`, top: (x.row ?? 0) * 15 }}
        >
          {x.text}
        </span>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- d02
function VolumeCard({ c, className }: { c: NonNullable<DataProfile["charts"]["d02"]>; className?: string }) {
  const tip = useTip();
  const columns: Column[] = c.months.map((m) => ({
    key: m.month,
    total: m.total,
    parts: m.parts,
    aria: `${monthLong(m.month)}: ${int(m.total)} transactions; ${m.parts.map((p) => `${p.label} ${int(p.n)}`).join(", ")}`,
    tip: (
      <TipBody
        title={`${monthLong(m.month)} · ${int(m.total)} transactions`}
        rows={[
          ...[...m.parts].reverse().map((p): [ReactNode, string] => [<Key key={p.key} color={FILL[p.key]} text={p.label} />, `${int(p.n)} · ${pct(p.pct)}`]),
          ...m.status.map((s): [ReactNode, string] => [s.label, pct(s.pct)]),
        ]}
        note="[data] status shares of the month's transactions"
      />
    ),
  }));
  return (
    <Card
      className={className}
      title="Transactions per month"
      line="Each column is a month of gold, split by the product the transaction was made with; card transactions are the ones customers dispute."
      detail={c.detail}
    >
      <Headline value={int(c.total)} text={`transactions, ${monthLong(c.window[0])} to ${monthLong(c.window[1])}`} label={c.label} />
      <ul aria-label="Status of the transactions" className="mt-3 flex flex-wrap gap-1.5 text-xs">
        {c.status.map((s) => (
          <li key={s.key} className="rounded-full border px-2 py-0.5 text-muted-foreground">
            {s.label} <span className="font-medium tabular-nums text-foreground">{pct(s.pct)}</span>
          </li>
        ))}
        <li className="self-center pl-0.5">
          <Label>{c.label}</Label>
        </li>
      </ul>
      <Legend items={[...PRODUCT_TYPES].reverse().map((t) => ({ color: FILL[t.key], text: t.label }))} />
      <div className="mt-4">
        <Columns
          columns={columns}
          ticks={c.ticks}
          height={168}
          tip={tip}
          labels={
            <XLabels
              n={c.months.length}
              items={[
                ...c.months.map((m, i) => ({ i, text: monthName(m.month), className: i % 2 ? "hidden sm:inline" : undefined })),
                ...c.months.flatMap((m, i) => (i === 0 || m.month.endsWith("-01") ? [{ i, text: m.month.slice(0, 4), row: 1 }] : [])),
              ]}
            />
          }
        />
      </div>
      <TableView head={c.table.head} rows={c.table.rows} />
      {tip.node}
    </Card>
  );
}

function Key({ color, text, line = false }: { color: string; text: string; line?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      {line ? <span aria-hidden className="inline-block h-0.5 w-3 rounded-full" style={{ background: color }} /> : <Swatch color={color} />}
      {text}
    </span>
  );
}

// ---------------------------------------------------------------- d03
function CountryCard({ c, className }: { c: NonNullable<DataProfile["charts"]["d03"]>; className?: string }) {
  const tip = useTip();
  const panels = [
    { key: "customers", title: "Customers", max: c.maxCustomers, get: (x: (typeof c.countries)[number]) => x.customers },
    { key: "transactions", title: "Transactions", max: c.maxTransactions, get: (x: (typeof c.countries)[number]) => x.transactions },
  ] as const;
  const step = fitStep(c.countries.length * 2, MOTION.step, MOTION.grow, 150);
  return (
    <Card
      className={className}
      title="Customers and transactions per country"
      line="Mexico holds about half of the customers and of their transactions; the segment mix is the same in every country."
      detail={c.detail}
    >
      <Headline value={int(c.customers)} text={`customers · ${int(c.transactions)} transactions`} label={c.label} />
      <div className="mt-4 grid gap-5 sm:grid-cols-2">
        {panels.map((panel, pi) => (
          <div key={panel.key} className="min-w-0">
            <p className="text-xs font-medium text-muted-foreground">{panel.title}</p>
            <div className="mt-1.5 space-y-1.5">
              {c.countries.map((x, i) => (
                <div key={x.country} className="grid grid-cols-[4.75rem_minmax(0,1fr)] items-center gap-2">
                  <span className="truncate text-sm">{x.name}</span>
                  <div className="flex min-w-0 items-center gap-2 border-l border-border">
                    <GrowBar
                      tabIndex={0}
                      role="img"
                      aria-label={`${x.name}, ${panel.title.toLowerCase()}: ${int(panel.get(x))}`}
                      delay={150 + (pi * c.countries.length + i) * step}
                      className={cn("h-[18px] shrink-0 rounded-r-[4px] hover:brightness-110", FOCUS)}
                      style={{ width: `${growTarget(panel.get(x), panel.max, 72)}%`, background: "var(--dp-2)" }}
                      {...tip.bind(
                        <TipBody
                          title={`${x.name} · ${int(x.customers)} customers`}
                          rows={[
                            ["Transactions", int(x.transactions)],
                            ...x.segments.map((s): [ReactNode, string] => [s.segment, `${int(s.customers)} · ${pct(s.pctCustomers)}`]),
                          ]}
                          note="[data] customers per segment, and their share of the country"
                        />,
                      )}
                    />
                    <span className="text-sm tabular-nums">{int(panel.get(x))}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
      <p className="mt-4 text-xs text-muted-foreground">
        Segment mix of the customers:{" "}
        {c.segmentMix.map((s, i) => (
          <span key={s.segment}>
            {i ? " · " : ""}
            {s.segment} <span className="tabular-nums text-foreground">{pct(s.pct)}</span>
          </span>
        ))}{" "}
        <Label>{c.label}</Label>
      </p>
      <TableView head={c.table.head} rows={c.table.rows} />
      {tip.node}
    </Card>
  );
}

// ---------------------------------------------------------------- d04
function ScoreCard({ c, className }: { c: NonNullable<DataProfile["charts"]["d04"]>; className?: string }) {
  const tip = useTip();
  const zoomMax = c.maxPer10k * 1.25;
  const bandTip = (x: (typeof c.countries)[number], b: (typeof x.bands)[number]) =>
    tip.bind(
      <TipBody
        title={`${x.name} · ${b.label}`}
        rows={[
          ["Card transactions", `${int(b.n)} of ${int(x.total)}`],
          ["Share", smallPct(b.pct)],
          ["Per 10,000", b.per10k.toFixed(1)],
        ]}
        note={`[data] ${b.zone}`}
      />,
    );
  const step = fitStep(c.countries.length, MOTION.step, MOTION.grow, 150);
  return (
    <Card
      className={className}
      title="The bank's fraud score on card transactions"
      line="A score the bank gives each card transaction, not a fraud label: almost every one scores below 30 or has no score."
      detail={c.detail}
    >
      <Headline value={smallPct(c.upperPct)} text="of card transactions score 30 or more" label={c.label} />
      <p className="mt-1 text-sm text-muted-foreground">
        <span className="tabular-nums text-foreground">{pct(c.nullPct)}</span> have no score <Label>{c.label}</Label>
      </p>
      <Legend items={c.all.bands.map((b) => ({ color: FILL[b.key], text: `${b.label} · ${smallPct(b.pct)}` }))} />
      <div className="mt-3 space-y-2">
        {c.countries.map((x, i) => (
          <div key={x.country} className="grid grid-cols-[4.75rem_minmax(0,1fr)] items-center gap-2">
            <span className={cn("truncate text-sm", x.country === "all" && "font-medium")}>{x.country === "all" ? "All" : x.name}</span>
            <GrowBar delay={150 + i * step} className="flex h-5 min-w-0 gap-[2px]">
              {x.bands
                .filter((b) => b.key === "null" || b.key === "lt30")
                .map((b, j) => (
                  <div
                    key={b.key}
                    tabIndex={0}
                    role="img"
                    aria-label={`${x.name}, ${b.label}: ${int(b.n)} card transactions, ${smallPct(b.pct)}`}
                    className={cn("min-w-0 hover:brightness-110", j > 0 && "rounded-r-[4px]", FOCUS)}
                    style={{ flexGrow: b.n, flexBasis: 0, background: FILL[b.key] }}
                    {...bandTip(x, b)}
                  />
                ))}
            </GrowBar>
          </div>
        ))}
      </div>
      {/* The two upper bands are under 0.1%: drawn at their true width above they are invisible, so they get a zoom. */}
      <div className="mt-5 rounded-md border border-dashed p-3">
        <p className="text-xs text-muted-foreground">
          Zoom on the bands the policy acts on: card transactions <span className="text-foreground">per 10,000</span>
        </p>
        <div className="mt-2 space-y-2">
          {c.countries.map((x, i) => (
            <div key={x.country} className="grid grid-cols-[4.75rem_minmax(0,1fr)] items-center gap-2">
              <span className={cn("truncate text-sm", x.country === "all" && "font-medium")}>{x.country === "all" ? "All" : x.name}</span>
              <div className="min-w-0 space-y-[2px] border-l border-border">
                {x.bands
                  .filter((b) => b.key === "30_49" || b.key === "ge50")
                  .map((b) => (
                    <div key={b.key} className="flex items-center gap-1.5">
                      <GrowBar
                        tabIndex={0}
                        role="img"
                        aria-label={`${x.name}, score ${b.label}: ${int(b.n)} card transactions, ${b.per10k.toFixed(1)} per 10,000`}
                        delay={400 + i * step}
                        className={cn("h-2.5 shrink-0 rounded-r-[4px] hover:brightness-110", FOCUS)}
                        style={{ width: `${growTarget(b.per10k, zoomMax, 80)}%`, background: FILL[b.key] }}
                        {...bandTip(x, b)}
                      />
                      <span className="text-[11px] leading-none tabular-nums text-muted-foreground">{b.per10k.toFixed(1)}</span>
                    </div>
                  ))}
              </div>
            </div>
          ))}
        </div>
      </div>
      <TableView head={c.table.head} rows={c.table.rows} />
      {tip.node}
    </Card>
  );
}

// ---------------------------------------------------------------- d05
function ComplaintCard({ c, className }: { c: NonNullable<DataProfile["charts"]["d05"]>; className?: string }) {
  const tip = useTip();
  const n = c.months.length;
  const top = c.shareTicks[c.shareTicks.length - 1];
  const x = (i: number) => (i + 0.5) * 10;
  const y = (v: number) => 100 - (v / top) * 100;
  const last = c.months[n - 1];
  const stripHeight = 72;
  const columns: Column[] = c.months.map((m) => ({
    key: m.month,
    total: m.total,
    parts: m.groups,
    dim: m.partial,
    aria: `${monthLong(m.month)}${m.partial ? ", partial month" : ""}: ${int(m.total)} complaints, W3 ${int(m.w3)}, ${pct(m.w3Pct)}`,
    tip: (
      <TipBody
        title={`${monthLong(m.month)} · ${int(m.total)} complaints`}
        rows={[
          [<Key key="w3" color={INK} text="W3 share" line />, `${pct(m.w3Pct)} · ${int(m.w3)}`],
          ...m.categories.map((k): [ReactNode, string] => [k.category, int(k.n)]),
        ]}
        note={`[data]${m.partial ? " Partial month: the window starts or ends inside it." : " W3: unrecognized or wrongful charges."}`}
      />
    ),
  }));
  const strip = (
    <div className={cn("relative mt-5", GUTTER)} style={{ height: stripHeight }}>
      <p className="absolute -top-4 left-0 text-[11px] leading-none text-muted-foreground">W3 share of the month</p>
      <Grid ticks={c.shareTicks} max={top} format={(v) => `${v}%`} />
      <svg aria-hidden className="absolute inset-0 h-full w-full overflow-visible" viewBox={`0 0 ${n * 10} 100`} preserveAspectRatio="none">
        <DrawPath
          points={c.months.map((m, i) => `${x(i)},${y(m.w3Pct)}`).join(" ")}
          delay={500}
          fill="none"
          stroke={INK}
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
      <span
        aria-hidden
        className="absolute size-2.5 -translate-x-1/2 translate-y-1/2 rounded-full ring-2 ring-card"
        style={{ left: `${(x(n - 1) / (n * 10)) * 100}%`, bottom: `${(last.w3Pct / top) * 100}%`, background: INK }}
      />
    </div>
  );
  return (
    <Card
      className={className}
      title="Complaints per month"
      line="Every complaint by category; the line under the columns is the share that are unrecognized or wrongful charges (W3), steady month after month."
      detail={c.detail}
    >
      <Headline value={pct(c.w3Pct)} text={`of ${int(c.total)} complaints are W3, ${monthLong(c.window[0])} to ${monthLong(c.window[1])}`} label={c.label} />
      <Legend
        items={[
          { color: FILL.Transactions, text: "Transactions" },
          { color: FILL.Fees, text: "Fees" },
          { color: FILL.other, text: "Branch, Service, Technical" },
          { color: INK, text: "W3 share", line: true },
        ]}
      />
      <p className="mt-1 text-xs text-muted-foreground">Paler columns: the first and last months are partial.</p>
      <div className="mt-4">
        <Columns
          columns={columns}
          ticks={c.ticks}
          height={152}
          tip={tip}
          strip={strip}
          labels={
            <XLabels
              n={n}
              items={c.months.flatMap((m, i) => (i === 0 || m.month.endsWith("-01") ? [{ i, text: i === 0 ? monthLong(m.month) : m.month.slice(0, 4) }] : []))}
            />
          }
        />
      </div>
      <TableView head={c.table.head} rows={c.table.rows} />
      {tip.node}
    </Card>
  );
}

// ---------------------------------------------------------------- d06
function QualityCard({ c, className }: { c: NonNullable<DataProfile["charts"]["d06"]>; className?: string }) {
  const tip = useTip();
  return (
    <Card
      className={className}
      title="Data quality per gold table"
      line="Empty key columns and rows flagged by a quality check, per table; flagged rows are kept, never deleted."
      detail={c.detail}
    >
      <Headline value={int(c.rows)} text={`rows in ${c.tables.length} gold tables · ${c.clean} of ${c.checked} checks find nothing`} label={c.label} />
      <Legend
        items={[
          { color: FILL.nullRate, text: "Key column empty (null)" },
          { color: FILL.flag, text: "Rows flagged (qc_*)" },
        ]}
      />
      <div className="mt-4 grid gap-x-8 gap-y-5 sm:grid-cols-2">
        {c.tables.map((t) => (
          <div key={t.table} className="min-w-0">
            <p className="flex items-baseline justify-between gap-2 border-b pb-1">
              <span className="font-mono text-sm font-medium">{t.table}</span>
              <span className="text-xs tabular-nums text-muted-foreground">{int(t.rows)} rows</span>
            </p>
            <ul className="mt-2 space-y-2">
              {t.found.map((item, i) => (
                <li
                  key={`${item.kind}-${item.name}`}
                  tabIndex={0}
                  aria-label={`${t.table}, ${item.kind === "null" ? `${item.name} empty` : `${item.name} flagged`}: ${int(item.n)} of ${int(item.of)} rows, ${pct(item.pct)}`}
                  className={cn("rounded-sm hover:bg-foreground/5", FOCUS)}
                  {...tip.bind(
                    <TipBody
                      title={`${t.table} · ${item.name}`}
                      rows={[
                        [item.kind === "null" ? "Rows with it empty" : "Rows flagged", `${int(item.n)} of ${int(item.of)}`],
                        ["Share", pct(item.pct)],
                      ]}
                      note={item.kind === "flag" ? `[data] ${flagText(item.name)}; the row is kept.` : "[data] a key column with no value."}
                    />,
                  )}
                >
                  <div className="flex items-baseline justify-between gap-2 text-xs">
                    <span className="min-w-0 break-words font-mono">
                      <Snake name={item.name} />
                    </span>
                    <span className="shrink-0 tabular-nums">{pct(item.pct)}</span>
                  </div>
                  <div className="mt-1 h-2 rounded-r-[4px] bg-muted">
                    <GrowBar
                      delay={150 + i * MOTION.step}
                      className="h-full rounded-r-[4px]"
                      style={{ width: `${growTarget(item.pct, 100)}%`, background: item.kind === "null" ? FILL.nullRate : FILL.flag }}
                    />
                  </div>
                </li>
              ))}
            </ul>
            {t.cleanNull.length || t.cleanFlag.length ? (
              <p className="mt-2 text-xs text-muted-foreground">
                At 0%:{" "}
                <span className="break-words font-mono">{[...t.cleanNull, ...t.cleanFlag].join(", ")}</span>
              </p>
            ) : null}
          </div>
        ))}
      </div>
      <TableView head={c.table.head} rows={c.table.rows} />
      {tip.node}
    </Card>
  );
}

/** spec 12 AC-03: the group, placed under the medallion; "Results pending" (AC-04) when the profile is absent. */
export function DataAtAGlance({ data }: { data: DataProfile }) {
  const { charts } = data;
  const wide = "lg:col-span-2";
  return (
    <section aria-labelledby="glance-title" className={PALETTE}>
      <h2 id="glance-title" className="text-lg font-semibold">
        The data at a glance
      </h2>
      <p className="mt-0.5 text-sm text-muted-foreground">
        The shape of gold, drawn from the committed outputs of queries/data. Hover a mark, or reach it with the Tab key, for its numbers.
      </p>
      {data.pending ? (
        <EmptyState className="mt-4" title="Results pending" hint="data_quality.json has no profile yet: run queries/data/run.py and `python -m data.pipeline report --json`." />
      ) : (
        <Stagger count={5} className="mt-4 grid items-start gap-4 lg:grid-cols-2">
          {charts.d02 ? <VolumeCard c={charts.d02} /> : <Pending k="d02" title="Transactions per month" />}
          {charts.d03 ? <CountryCard c={charts.d03} /> : <Pending k="d03" title="Customers and transactions per country" />}
          {charts.d05 ? <ComplaintCard c={charts.d05} className={wide} /> : <Pending k="d05" title="Complaints per month" className={wide} />}
          {charts.d04 ? <ScoreCard c={charts.d04} /> : <Pending k="d04" title="The bank's fraud score on card transactions" />}
          {charts.d06 ? <QualityCard c={charts.d06} /> : <Pending k="d06" title="Data quality per gold table" />}
        </Stagger>
      )}
    </section>
  );
}

