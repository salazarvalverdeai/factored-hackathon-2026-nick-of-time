"use client";

// Interactive charts of /analytics. Every mark shows its detail on hover and on keyboard focus; the same values are
// always reachable without hovering, through the direct labels and the "View as table" block under each chart.
// Labels follow the UI language and numbers its locale (spec 16 AC-06); sources and bracket labels stay as written.
import { useState } from "react";
import type { CSSProperties, FocusEvent, PointerEvent, ReactNode } from "react";
import { useLocale, useT } from "@/components/i18n-provider";
import { formatNumber, type Translate } from "@/lib/i18n";

export type PitchNumbers = {
  share: {
    n_complaints: number;
    n_w3: number;
    pct_w3: number;
    n_w3_full_months: number;
    n_full_months: number;
    w3_per_month: number;
  };
  contacts: {
    key: string;
    label: string;
    unit: string;
    scale_max: number;
    query: string;
    groups: { name: string; value: number; numerator?: number; denominator: number; ci_low?: number; ci_high?: number }[];
  }[];
  thresholds: {
    threshold: number;
    n_flagged: number;
    n_frauds_flagged: number;
    precision_pct: number;
    recall_with_score_pct: number;
    recall_all_frauds_pct: number;
  }[];
  frauds: {
    total: number;
    with_score: number;
    without_score: number;
    zones: { key: string; zone: string; range: string; action: string; n: number; pct: number }[];
  };
};

// Series colors checked with the palette validator on the light and dark card surfaces (violet and teal follow
// docs/brand/BRAND.md). Zone colors are the brand's zone hues, one step darker so they clear 3:1 on both surfaces.
const PALETTE =
  "[--series-1:#7c3aed] dark:[--series-1:#8b5cf6] [--series-2:#0d9488] " +
  "[--zone-high:#059669] [--zone-medium:#d97706] [--zone-human:#e11d48]";
const CONTEXT = "color-mix(in oklab, var(--muted-foreground) 45%, transparent)";
const ZONE_FILL: Record<string, string> = {
  high: "var(--zone-high)",
  medium: "var(--zone-medium)",
  human: "var(--zone-human)",
  human_no_score: CONTEXT,
};
export const FOCUS = "outline-none focus-visible:ring-2 focus-visible:ring-ring";

/** Integers, fixed decimals and percentages in the UI locale ("1,234" en-US, "1.234" pt-BR). */
export function useNumbers() {
  const { locale } = useLocale();
  const dec = (n: number, digits: number) => formatNumber(locale, n, { minimumFractionDigits: digits, maximumFractionDigits: digits });
  return {
    int: (n: number) => formatNumber(locale, n),
    dec,
    pct: (n: number, digits = 1) => `${dec(n, digits)}%`,
  };
}

const MEASURES = ["fcr", "follow_up", "duration"] as const;
const GROUPS: Record<string, "complaints" | "bank"> = { "Complaint contacts": "complaints", "Whole bank": "bank" };
const ZONES = ["high", "medium", "human", "human_no_score"] as const;
type ZoneKey = (typeof ZONES)[number];
const isZone = (key: string): key is ZoneKey => (ZONES as readonly string[]).includes(key);

/** A contact measure's label in the UI language; a key this page does not know keeps the exporter's label. */
function measureLabel(t: Translate, key: string, fallback: string) {
  return (MEASURES as readonly string[]).includes(key) ? t(`analytics.measures.${key as (typeof MEASURES)[number]}` as const) : fallback;
}
const groupLabel = (t: Translate, name: string) => (GROUPS[name] ? t(`analytics.groups.${GROUPS[name]}` as const) : name);

type Tip = { x: number; y: number; content: ReactNode } | null;

export function useTip() {
  const [tip, setTip] = useState<Tip>(null);
  const bind = (content: ReactNode) => ({
    onPointerMove: (e: PointerEvent<Element>) => setTip({ x: e.clientX, y: e.clientY, content }),
    onPointerLeave: () => setTip(null),
    onFocus: (e: FocusEvent<Element>) => {
      const r = e.currentTarget.getBoundingClientRect();
      setTip({ x: r.left + r.width / 2, y: r.bottom, content });
    },
    onBlur: () => setTip(null),
  });
  const node = tip ? (
    <div
      role="tooltip"
      className="pointer-events-none fixed z-50 w-64 rounded-md border bg-popover p-3 text-xs text-popover-foreground shadow-md"
      style={{
        left: Math.max(8, Math.min(tip.x + 14, window.innerWidth - 264)),
        top: Math.min(tip.y + 14, window.innerHeight - 150),
      }}
    >
      {tip.content}
    </div>
  ) : null;
  return { bind, node };
}

export function TipBody({ title, rows, note }: { title: string; rows: [ReactNode, string][]; note?: string }) {
  return (
    <>
      <p className="font-medium">{title}</p>
      <dl className="mt-1.5 space-y-1">
        {rows.map(([label, value], i) => (
          <div key={i} className="flex items-baseline justify-between gap-3">
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="text-sm font-semibold tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>
      {note ? <p className="mt-1.5 text-muted-foreground">{note}</p> : null}
    </>
  );
}

function LineKey({ color, children }: { color: string; children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span aria-hidden className="inline-block h-0.5 w-4 rounded-full" style={{ background: color }} />
      {children}
    </span>
  );
}

export function Swatch({ color }: { color: string }) {
  return <span aria-hidden className="inline-block size-2.5 shrink-0 rounded-[2px]" style={{ background: color }} />;
}

function ChartCard({
  title,
  subtitle,
  takeaway,
  source,
  children,
}: {
  title: string;
  subtitle: string;
  takeaway: string;
  source: string;
  children: ReactNode;
}) {
  return (
    <figure className={`rounded-lg border bg-card p-5 text-card-foreground ${PALETTE}`}>
      <h2 className="text-base font-semibold">{title}</h2>
      <p className="mt-0.5 text-sm text-muted-foreground">{subtitle}</p>
      <div className="mt-5">{children}</div>
      <p className="mt-4 text-sm">{takeaway}</p>
      <figcaption className="mt-2 font-mono text-xs text-muted-foreground">{source}</figcaption>
    </figure>
  );
}

export function TableView({ head, rows }: { head: string[]; rows: string[][] }) {
  const t = useT();
  return (
    <details className="mt-4">
      <summary className={`cursor-pointer rounded-sm text-xs text-muted-foreground ${FOCUS}`}>{t("analytics.viewAsTable")}</summary>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full text-left text-xs tabular-nums">
          <thead className="text-muted-foreground">
            <tr>
              {head.map((h) => (
                <th key={h} className="border-b py-1.5 pr-4 font-normal">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                {r.map((c, j) => (
                  <td key={j} className="border-b py-1.5 pr-4">
                    {c}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

function ShareChart({ share }: { share: PitchNumbers["share"] }) {
  const { bind, node } = useTip();
  const t = useT();
  const { int, pct } = useNumbers();
  const other = share.n_complaints - share.n_w3;
  const perMonth = t("analytics.share.perMonth", { n: int(Math.round(share.w3_per_month)) });
  return (
    <ChartCard
      title={t("analytics.share.title")}
      subtitle={t("analytics.share.subtitle")}
      takeaway={t("analytics.share.takeaway")}
      source="[data] queries/pitch/p01_w3_share_complaints.sql"
    >
      <div className="flex flex-wrap items-end gap-x-5 gap-y-1">
        <p className="text-5xl font-semibold tracking-tight">{pct(share.pct_w3)}</p>
        <p className="pb-1 text-sm text-muted-foreground">
          <span className="text-foreground">{t("analytics.share.ofComplaints", { n: int(share.n_w3), total: int(share.n_complaints) })}</span>
          <br />
          {t("analytics.share.about", { perMonth, months: share.n_full_months })}
        </p>
      </div>
      <div className="mt-4 flex h-5 gap-0.5">
        <div
          tabIndex={0}
          role="img"
          aria-label={t("analytics.share.w3Aria", { n: int(share.n_w3), pct: pct(share.pct_w3) })}
          className={`rounded-l-sm transition hover:brightness-110 ${FOCUS}`}
          style={{ width: `${share.pct_w3}%`, background: "var(--series-1)" }}
          {...bind(
            <TipBody
              title={t("analytics.share.w3")}
              rows={[
                [t("analytics.share.complaints"), int(share.n_w3)],
                [t("analytics.share.shareOfAll"), pct(share.pct_w3)],
                [t("analytics.share.inMonths", { months: share.n_full_months }), int(share.n_w3_full_months)],
                [t("analytics.share.average"), perMonth],
              ]}
            />,
          )}
        />
        <div
          tabIndex={0}
          role="img"
          aria-label={t("analytics.share.otherAria", { n: int(other), pct: pct(100 - share.pct_w3) })}
          className={`flex-1 rounded-r-sm transition hover:brightness-110 ${FOCUS}`}
          style={{ background: "color-mix(in oklab, var(--series-1) 22%, transparent)" }}
          {...bind(
            <TipBody
              title={t("analytics.share.other")}
              rows={[
                [t("analytics.share.complaints"), int(other)],
                [t("analytics.share.shareOfAll"), pct(100 - share.pct_w3)],
              ]}
            />,
          )}
        />
      </div>
      <div className="mt-2 flex justify-between gap-4 text-xs text-muted-foreground">
        <span>{t("analytics.share.w3")}</span>
        <span className="text-right">
          {t("analytics.share.other")} · {pct(100 - share.pct_w3)}
        </span>
      </div>
      {node}
    </ChartCard>
  );
}

function ContactsChart({ contacts }: { contacts: PitchNumbers["contacts"] }) {
  const { bind, node } = useTip();
  const t = useT();
  const { int, pct, dec } = useNumbers();
  const fills = ["var(--series-1)", CONTEXT];
  const fmt = (unit: string, v: number) => (unit === "%" ? pct(v) : `${dec(v, 2)} ${unit}`);
  const [complaints, bank] = contacts[0].groups;
  return (
    <ChartCard
      title={t("analytics.contacts.title")}
      subtitle={t("analytics.contacts.subtitle", { complaints: int(complaints.denominator), bank: int(bank.denominator) })}
      takeaway={t("analytics.contacts.takeaway")}
      source="[data] queries/pitch/p02 · p03 · p04 — contacts with reason “Queja”, a low-confidence match to W3"
    >
      <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <Swatch color={fills[0]} />
          {t("analytics.groups.complaints")}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <Swatch color={fills[1]} />
          {t("analytics.groups.bank")}
        </span>
      </div>
      <div className="mt-4 space-y-5">
        {contacts.map((m) => (
          <div key={m.key}>
            <p className="text-sm font-medium">
              {measureLabel(t, m.key, m.label)}{" "}
              <span className="font-normal text-muted-foreground">
                {m.unit === "%" ? t("analytics.contacts.pctOfContacts") : t("analytics.contacts.scale", { unit: m.unit, max: m.scale_max })}
              </span>
            </p>
            <div className="mt-1.5 space-y-0.5 border-l pl-px">
              {m.groups.map((g, i) => (
                <div key={g.name} className="flex items-center gap-2">
                  <div
                    tabIndex={0}
                    role="img"
                    aria-label={`${measureLabel(t, m.key, m.label)}, ${groupLabel(t, g.name)}: ${fmt(m.unit, g.value)}`}
                    className={`h-[18px] rounded-r-sm transition hover:brightness-110 ${FOCUS}`}
                    style={{ width: `${(g.value / m.scale_max) * 78}%`, background: fills[i] }}
                    {...bind(
                      <TipBody
                        title={`${groupLabel(t, g.name)} · ${measureLabel(t, m.key, m.label)}`}
                        rows={
                          g.numerator === undefined
                            ? [
                                [t("analytics.contacts.median"), fmt(m.unit, g.value)],
                                [t("analytics.contacts.withDuration"), int(g.denominator)],
                              ]
                            : [
                                [t("analytics.contacts.rate"), fmt(m.unit, g.value)],
                                [t("analytics.contacts.contacts"), t("analytics.ofN", { n: int(g.numerator), total: int(g.denominator) })],
                                [t("analytics.interval95"), `${pct(g.ci_low ?? 0)} – ${pct(g.ci_high ?? 0)}`],
                              ]
                        }
                      />,
                    )}
                  />
                  <span className="text-sm tabular-nums">{fmt(m.unit, g.value)}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
      <TableView
        head={[t("analytics.contacts.measure"), t("analytics.groups.complaints"), t("analytics.groups.bank")]}
        rows={contacts.map((m) => [measureLabel(t, m.key, m.label), ...m.groups.map((g) => fmt(m.unit, g.value))])}
      />
      {node}
    </ChartCard>
  );
}

function ThresholdChart({ thresholds, frauds }: Pick<PitchNumbers, "thresholds" | "frauds">) {
  const { bind, node } = useTip();
  const t = useT();
  const { int, pct } = useNumbers();
  const [active, setActive] = useState<number | null>(null);
  const W = 600;
  const H = 300;
  const left = 44;
  const right = 506;
  const top = 26;
  const bottom = 238;
  const sx = (v: number) => left + ((v - 20) / 75) * (right - left);
  const sy = (v: number) => bottom - (v / 100) * (bottom - top);
  const series = [
    { name: t("analytics.thresholds.precision"), color: "var(--series-1)", get: (row: PitchNumbers["thresholds"][number]) => row.precision_pct },
    { name: t("analytics.thresholds.recall"), color: "var(--series-2)", get: (row: PitchNumbers["thresholds"][number]) => row.recall_with_score_pct },
  ];
  // Hover and focus columns: each one runs from the midpoint with the previous threshold to the midpoint with the next.
  const edges = thresholds.map((row, i) => (i === 0 ? 20 : (thresholds[i - 1].threshold + row.threshold) / 2));
  const label: CSSProperties = { fontSize: 12 };
  const tick: CSSProperties = { fontSize: 11 };
  const [t30, t50] = thresholds;
  return (
    <ChartCard
      title={t("analytics.thresholds.title")}
      subtitle={t("analytics.thresholds.subtitle")}
      takeaway={t("analytics.thresholds.takeaway")}
      source="[data] queries/pitch/p08_fraud_score_thresholds.sql — synthetic dataset, whole window, not a held-out set"
    >
      <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
        <LineKey color={series[0].color}>{t("analytics.thresholds.precisionKey")}</LineKey>
        <LineKey color={series[1].color}>{t("analytics.thresholds.recallKey")}</LineKey>
      </div>
      <div className="mt-2 overflow-x-auto">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full min-w-[520px]" role="group" aria-label={t("analytics.thresholds.aria")}>
          {[0, 25, 50, 75, 100].map((v) => (
            <g key={v}>
              <line x1={left} x2={right} y1={sy(v)} y2={sy(v)} className="stroke-border" />
              <text x={left - 8} y={sy(v) + 4} textAnchor="end" className="fill-muted-foreground" style={tick}>
                {v}%
              </text>
            </g>
          ))}
          {[30, 50].map((v) => (
            <line key={v} x1={sx(v)} x2={sx(v)} y1={top} y2={bottom} className="stroke-muted-foreground/50" />
          ))}
          {(
            [
              [25, t("analytics.thresholds.zoneHuman")],
              [40, t("analytics.thresholds.zoneMedium")],
              [72.5, t("analytics.thresholds.zoneHigh")],
            ] as const
          ).map(([v, name]) => (
            <text key={name} x={sx(v)} y={bottom - 8} textAnchor="middle" className="fill-muted-foreground" style={tick}>
              {name}
            </text>
          ))}
          <line x1={left} x2={right} y1={bottom} y2={bottom} className="stroke-muted-foreground/50" />
          {thresholds.map((row) => (
            <text key={row.threshold} x={sx(row.threshold)} y={bottom + 17} textAnchor="middle" className="fill-muted-foreground" style={tick}>
              {row.threshold}
            </text>
          ))}
          <text x={(left + right) / 2} y={bottom + 38} textAnchor="middle" className="fill-muted-foreground" style={tick}>
            {t("analytics.thresholds.axis")}
          </text>
          {active !== null ? (
            <line x1={sx(thresholds[active].threshold)} x2={sx(thresholds[active].threshold)} y1={top} y2={bottom} className="stroke-foreground/60" />
          ) : null}
          {series.map((s) => (
            <g key={s.name}>
              <polyline
                points={thresholds.map((row) => `${sx(row.threshold)},${sy(s.get(row))}`).join(" ")}
                fill="none"
                stroke={s.color}
                strokeWidth={2}
                strokeLinejoin="round"
                strokeLinecap="round"
              />
              {thresholds.map((row, i) => (
                <circle key={row.threshold} cx={sx(row.threshold)} cy={sy(s.get(row))} r={active === i ? 6 : 4} fill={s.color} strokeWidth={2} className="stroke-card" />
              ))}
              <text x={right + 10} y={sy(s.get(thresholds[thresholds.length - 1])) + 4} className="fill-foreground" style={label}>
                {s.name}
              </text>
            </g>
          ))}
          <g className="fill-foreground" style={label}>
            <text x={sx(30) - 10} y={sy(t30.precision_pct) + 4} textAnchor="end">
              {pct(t30.precision_pct)}
            </text>
            <text x={sx(30) - 10} y={sy(t30.recall_with_score_pct) + 4} textAnchor="end">
              {pct(t30.recall_with_score_pct)}
            </text>
            <text x={sx(50)} y={sy(t50.precision_pct) - 10} textAnchor="middle">
              {pct(t50.precision_pct, 0)}
            </text>
            <text x={sx(50) + 10} y={sy(t50.recall_with_score_pct) - 6}>
              {pct(t50.recall_with_score_pct)}
            </text>
          </g>
          {thresholds.map((row, i) => {
            const x0 = sx(edges[i]);
            const x1 = i === thresholds.length - 1 ? right + 4 : sx(edges[i + 1]);
            const tip = bind(
              <TipBody
                title={t("analytics.thresholds.scoreOrMore", { n: row.threshold })}
                rows={[
                  [
                    <LineKey key="p" color={series[0].color}>
                      {t("analytics.thresholds.precision")}
                    </LineKey>,
                    pct(row.precision_pct),
                  ],
                  [
                    <LineKey key="r" color={series[1].color}>
                      {t("analytics.thresholds.recallWithScore")}
                    </LineKey>,
                    pct(row.recall_with_score_pct),
                  ],
                  [t("analytics.thresholds.recallAll"), pct(row.recall_all_frauds_pct)],
                  [t("analytics.thresholds.flaggedTx"), int(row.n_flagged)],
                  [t("analytics.thresholds.ofWhichFraud"), int(row.n_frauds_flagged)],
                ]}
                note={t("analytics.thresholds.note", { withScore: int(frauds.with_score), total: int(frauds.total) })}
              />,
            );
            return (
              <rect
                key={row.threshold}
                x={x0}
                y={top - 14}
                width={x1 - x0}
                height={bottom - top + 14}
                fill="transparent"
                tabIndex={0}
                role="img"
                aria-label={t("analytics.thresholds.columnAria", {
                  n: row.threshold,
                  precision: pct(row.precision_pct),
                  recall: pct(row.recall_with_score_pct),
                })}
                className="outline-none focus-visible:stroke-ring"
                onPointerMove={(e) => {
                  setActive(i);
                  tip.onPointerMove(e);
                }}
                onPointerLeave={() => {
                  setActive(null);
                  tip.onPointerLeave();
                }}
                onFocus={(e) => {
                  setActive(i);
                  tip.onFocus(e);
                }}
                onBlur={() => {
                  setActive(null);
                  tip.onBlur();
                }}
              />
            );
          })}
        </svg>
      </div>
      <TableView
        head={[
          t("analytics.thresholds.head.threshold"),
          t("analytics.thresholds.head.flagged"),
          t("analytics.thresholds.head.ofWhichFraud"),
          t("analytics.thresholds.head.precision"),
          t("analytics.thresholds.head.recallWith"),
          t("analytics.thresholds.head.recallAll"),
        ]}
        rows={thresholds.map((row) => [
          t("analytics.thresholds.scoreAtLeast", { n: row.threshold }),
          int(row.n_flagged),
          int(row.n_frauds_flagged),
          pct(row.precision_pct),
          pct(row.recall_with_score_pct),
          pct(row.recall_all_frauds_pct),
        ])}
      />
      {node}
    </ChartCard>
  );
}

function ZonesChart({ frauds }: { frauds: PitchNumbers["frauds"] }) {
  const { bind, node } = useTip();
  const t = useT();
  const { int, pct } = useNumbers();
  const human = frauds.zones.filter((z) => z.zone === "Human zone").reduce((sum, z) => sum + z.n, 0);
  const zoneName = (z: PitchNumbers["frauds"]["zones"][number]) => (isZone(z.key) ? t(`analytics.zones.names.${z.key}` as const) : z.zone);
  const zoneRange = (z: PitchNumbers["frauds"]["zones"][number]) => (z.key === "human_no_score" ? t("analytics.zones.noScore") : z.range);
  const zoneAction = (z: PitchNumbers["frauds"]["zones"][number]) => (isZone(z.key) ? t(`analytics.zones.actions.${z.key}` as const) : z.action);
  return (
    <ChartCard
      title={t("analytics.zones.title", { n: int(frauds.total) })}
      subtitle={t("analytics.zones.subtitle")}
      takeaway={t("analytics.zones.takeaway", { pct: pct((100 * human) / frauds.total) })}
      source="[data] queries/pitch/p08_fraud_score_thresholds.sql · p07_fraud_per_month.sql"
    >
      <div className="flex gap-0.5 text-xs tabular-nums text-muted-foreground">
        {frauds.zones.map((z) => (
          <span key={z.key} style={{ width: `${z.pct}%` }}>
            {pct(z.pct)}
          </span>
        ))}
      </div>
      <div className="mt-1 flex h-6 gap-0.5">
        {frauds.zones.map((z, i) => (
          <div
            key={z.key}
            tabIndex={0}
            role="img"
            aria-label={t("analytics.zones.barAria", { zone: zoneName(z), range: zoneRange(z), n: int(z.n), pct: pct(z.pct) })}
            className={`transition hover:brightness-110 ${FOCUS} ${i === 0 ? "rounded-l-sm" : ""} ${i === frauds.zones.length - 1 ? "rounded-r-sm" : ""}`}
            style={{ width: `${z.pct}%`, background: ZONE_FILL[z.key] }}
            {...bind(
              <TipBody
                title={`${zoneName(z)} · ${zoneRange(z)}`}
                rows={[
                  [t("analytics.zones.labeled"), int(z.n)],
                  [t("analytics.zones.shareOfAll"), pct(z.pct)],
                ]}
                note={zoneAction(z)}
              />,
            )}
          />
        ))}
      </div>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[520px] text-left text-sm">
          <thead className="text-xs text-muted-foreground">
            <tr>
              <th className="border-b py-1.5 pr-4 font-normal">{t("analytics.zones.head.zone")}</th>
              <th className="border-b py-1.5 pr-4 font-normal">{t("analytics.zones.head.does")}</th>
              <th className="border-b py-1.5 pr-4 text-right font-normal">{t("analytics.zones.head.frauds")}</th>
              <th className="border-b py-1.5 text-right font-normal">{t("analytics.zones.head.share")}</th>
            </tr>
          </thead>
          <tbody>
            {frauds.zones.map((z) => (
              <tr key={z.key}>
                <td className="border-b py-1.5 pr-4 whitespace-nowrap">
                  <span className="inline-flex items-center gap-2">
                    <Swatch color={ZONE_FILL[z.key]} />
                    {zoneName(z)} · {zoneRange(z)}
                  </span>
                </td>
                <td className="border-b py-1.5 pr-4 text-muted-foreground">{zoneAction(z)}</td>

                <td className="border-b py-1.5 pr-4 text-right tabular-nums">{int(z.n)}</td>
                <td className="border-b py-1.5 text-right tabular-nums">{pct(z.pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {node}
    </ChartCard>
  );
}

export function PitchCharts({ data }: { data: PitchNumbers }) {
  return (
    // One column in reading order; from xl, two columns that each stack their own cards (no stretched cards).
    <div className="flex flex-col gap-4 xl:flex-row xl:items-start">
      <div className="contents xl:flex xl:min-w-0 xl:flex-1 xl:flex-col xl:gap-4">
        <div className="order-1">
          <ShareChart share={data.share} />
        </div>
        <div className="order-3">
          <ThresholdChart thresholds={data.thresholds} frauds={data.frauds} />
        </div>
      </div>
      <div className="contents xl:flex xl:min-w-0 xl:flex-1 xl:flex-col xl:gap-4">
        <div className="order-2">
          <ContactsChart contacts={data.contacts} />
        </div>
        <div className="order-4">
          <ZonesChart frauds={data.frauds} />
        </div>
      </div>
    </div>
  );
}
