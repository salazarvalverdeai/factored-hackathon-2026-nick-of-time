"use client";

// Interactive charts of /analytics. Every mark shows its detail on hover and on keyboard focus; the same values are
// always reachable without hovering, through the direct labels and the "View as table" block under each chart.
// Each card reads: title, the big figure, the chart, one plain line with "Detail →" (the rest of the explanation, in the
// shared side panel), the table (collapsed) and the source in a muted footer.
import { useState } from "react";
import type { CSSProperties, FocusEvent, PointerEvent, ReactNode } from "react";
import { BigFigure } from "@/app/evaluation/explain";
import { DetailButton } from "@/components/detail-button";
import { GrowBar, MotionGroup, Reveal } from "@/components/motion";
import { part } from "@/lib/motion";
import { repoUrl } from "@/lib/pipelines";

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
export const PALETTE =
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

const int = (n: number) => n.toLocaleString("en-US");
const pct = (n: number, digits = 1) => `${n.toFixed(digits)}%`;

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

const SPEC = repoUrl("specs/12-insight-pages.md");

function ChartCard({
  title,
  figure,
  line,
  detail,
  source,
  table,
  children,
}: {
  title: string;
  figure: ReactNode;
  /** The one plain line under the chart. */
  line: string;
  /** What the side panel adds: what the chart shows and how it is computed. */
  detail: { meaning: string; method: string };
  /** "[label] query …": the label and the source of every figure on the card. */
  source: string;
  table?: ReactNode;
  children: ReactNode;
}) {
  const [label, ...rest] = source.split(" ");
  return (
    <figure className={`rounded-lg border bg-card p-6 text-card-foreground ${PALETTE}`}>
      <h2 className="text-base font-semibold">{title}</h2>
      <div className="mt-4 flex flex-wrap gap-x-10 gap-y-3">{figure}</div>
      <div className="mt-5">{children}</div>
      <p className="mt-5 text-sm">
        {line} <DetailButton title={title} detail={{ ...detail, source: rest.join(" "), label, spec: SPEC }} className="text-muted-foreground" />
      </p>
      {table}
      <figcaption className="mt-5 font-mono text-xs text-muted-foreground">{source}</figcaption>
    </figure>
  );
}

export function TableView({ head, rows }: { head: string[]; rows: string[][] }) {
  return (
    <details className="mt-4">
      <summary className={`cursor-pointer rounded-sm text-xs text-muted-foreground ${FOCUS}`}>View as table</summary>
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
  const other = share.n_complaints - share.n_w3;
  const perMonth = `${int(Math.round(share.w3_per_month))} per month`;
  return (
    <ChartCard
      title="More than a third of complaints are unrecognized or wrongful charges"
      figure={<BigFigure value={pct(share.pct_w3)} label="[data]" caption={`${int(share.n_w3)} of ${int(share.n_complaints)} complaints`} />}
      line="One workflow is more than a third of all complaints."
      detail={{
        meaning: "The share of all the bank's complaints in the dataset that are unrecognized or wrongful charges (W3). Improving its first contact moves a number the bank already tracks.",
        method: `W3 complaints over all complaints; about ${perMonth} over ${share.n_full_months} full months.`,
      }}
      source="[data] queries/pitch/p01_w3_share_complaints.sql"
    >
      {/* the stacked row grows as one bar (motion kit); each part keeps its focus and tooltip */}
      <GrowBar className="flex h-5 gap-0.5">
        <div
          tabIndex={0}
          role="img"
          aria-label={`Unrecognized or wrongful charges: ${int(share.n_w3)} complaints, ${pct(share.pct_w3)}`}
          className={`rounded-l-sm transition hover:brightness-110 ${FOCUS}`}
          style={{ width: `${share.pct_w3}%`, background: "var(--series-1)" }}
          {...bind(
            <TipBody
              title="Unrecognized or wrongful charges (W3)"
              rows={[
                ["Complaints", int(share.n_w3)],
                ["Share of all complaints", pct(share.pct_w3)],
                [`In ${share.n_full_months} full months`, int(share.n_w3_full_months)],
                ["Average", perMonth],
              ]}
            />,
          )}
        />
        <div
          tabIndex={0}
          role="img"
          aria-label={`All other complaints: ${int(other)}, ${pct(100 - share.pct_w3)}`}
          className={`flex-1 rounded-r-sm transition hover:brightness-110 ${FOCUS}`}
          style={{ background: "color-mix(in oklab, var(--series-1) 22%, transparent)" }}
          {...bind(
            <TipBody
              title="All other complaints"
              rows={[
                ["Complaints", int(other)],
                ["Share of all complaints", pct(100 - share.pct_w3)],
              ]}
            />,
          )}
        />
      </GrowBar>
      <div className="mt-2 flex justify-between gap-4 text-xs text-muted-foreground">
        <span>Unrecognized or wrongful charges (W3)</span>
        <span className="text-right">All other complaints · {pct(100 - share.pct_w3)}</span>
      </div>
      {node}
    </ChartCard>
  );
}

function ContactsChart({ contacts }: { contacts: PitchNumbers["contacts"] }) {
  const { bind, node } = useTip();
  const fills = ["var(--series-1)", CONTEXT];
  const fmt = (unit: string, v: number) => (unit === "%" ? pct(v) : `${v.toFixed(2)} ${unit}`);
  const fcr = contacts.find((m) => m.key === "fcr") ?? contacts[0];
  const [complaints, bank] = fcr.groups;
  return (
    <ChartCard
      title="Complaint contacts resolve less, last longer and leave follow-up"
      figure={<>
        <BigFigure value={fmt(fcr.unit, complaints.value)} label="[data]" caption="complaint contacts resolved at first contact" />
        <BigFigure value={fmt(fcr.unit, bank.value)} label="[data]" caption="the whole bank" size="md" />
      </>}
      line="More than half are not resolved the first time: the goal is first-contact resolution."
      detail={{
        meaning: `Call-center contacts: ${int(complaints.denominator)} complaint contacts against ${int(bank.denominator)} in the whole bank. Almost two in three complaint contacts leave work pending.`,
        method: "Contacts with reason “Queja”, a low-confidence match to W3, against every contact of the bank; rates with their 95% interval, durations as medians.",
      }}
      source="[data] queries/pitch/p02 · p03 · p04"
      table={<TableView head={["Measure", "Complaint contacts", "Whole bank"]} rows={contacts.map((m) => [m.label, ...m.groups.map((g) => fmt(m.unit, g.value))])} />}
    >
      <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <Swatch color={fills[0]} />
          Complaint contacts
        </span>
        <span className="inline-flex items-center gap-1.5">
          <Swatch color={fills[1]} />
          Whole bank
        </span>
      </div>
      <div className="mt-4 space-y-5">
        {contacts.map((m, k) => (
          <div key={m.key}>
            <p className="text-sm font-medium">
              {m.label}{" "}
              <span className="font-normal text-muted-foreground">
                {m.unit === "%" ? "· % of contacts" : `· ${m.unit}, scale 0–${m.scale_max}`}
              </span>
            </p>
            <div className="mt-1.5 space-y-0.5 border-l pl-px">
              {m.groups.map((g, i) => (
                <div key={g.name} className="flex items-center gap-2">
                  <GrowBar
                    delay={(k * 2 + i) * 60}
                    tabIndex={0}
                    role="img"
                    aria-label={`${m.label}, ${g.name}: ${fmt(m.unit, g.value)}`}
                    className={`h-[18px] rounded-r-sm transition hover:brightness-110 ${FOCUS}`}
                    style={{ width: `${(g.value / m.scale_max) * 78}%`, background: fills[i] }}
                    {...bind(
                      <TipBody
                        title={`${g.name} · ${m.label}`}
                        rows={
                          g.numerator === undefined
                            ? [
                                ["Median", fmt(m.unit, g.value)],
                                ["Contacts with a duration", int(g.denominator)],
                              ]
                            : [
                                ["Rate", fmt(m.unit, g.value)],
                                ["Contacts", `${int(g.numerator)} of ${int(g.denominator)}`],
                                ["95% interval", `${pct(g.ci_low ?? 0)} – ${pct(g.ci_high ?? 0)}`],
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
      {node}
    </ChartCard>
  );
}

function ThresholdChart({ thresholds, frauds }: Pick<PitchNumbers, "thresholds" | "frauds">) {
  const { bind, node } = useTip();
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
    { name: "Precision", color: "var(--series-1)", get: (t: PitchNumbers["thresholds"][number]) => t.precision_pct },
    { name: "Recall", color: "var(--series-2)", get: (t: PitchNumbers["thresholds"][number]) => t.recall_with_score_pct },
  ];
  // Hover and focus columns: each one runs from the midpoint with the previous threshold to the midpoint with the next.
  const edges = thresholds.map((t, i) => (i === 0 ? 20 : (thresholds[i - 1].threshold + t.threshold) / 2));
  const label: CSSProperties = { fontSize: 12 };
  const tick: CSSProperties = { fontSize: 11 };
  const [t30, t50] = thresholds;
  return (
    <ChartCard
      title="At a score of 50 or more every flagged transaction was fraud"
      figure={<BigFigure value={pct(t50.precision_pct, 0)} label="[data]" caption={`precision at a score of ${t50.threshold} or more; recall ${pct(t50.recall_with_score_pct)}`} />}
      line="Above 50 the system acts at once; from 30 to 49 the customer confirms and a person approves."
      detail={{
        meaning: "Historical precision and recall of the bank's fraud_score, by threshold. Between 30 and 49 almost half of the flagged charges are legitimate.",
        method: "Transactions flagged at or above each threshold, against the fraud label, over the whole window of the synthetic dataset: not a held-out set.",
      }}
      source="[data] queries/pitch/p08_fraud_score_thresholds.sql"
      table={
        <TableView
          head={["Threshold", "Flagged", "Of which fraud", "Precision", "Recall (with score)", "Recall (all frauds)"]}
          rows={thresholds.map((t) => [
            `score ≥ ${t.threshold}`,
            int(t.n_flagged),
            int(t.n_frauds_flagged),
            pct(t.precision_pct),
            pct(t.recall_with_score_pct),
            pct(t.recall_all_frauds_pct),
          ])}
        />
      }
    >
      <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
        <LineKey color={series[0].color}>Precision: flagged transactions that are fraud</LineKey>
        <LineKey color={series[1].color}>Recall: frauds with a score that are flagged</LineKey>
      </div>
      <div className="mt-2 overflow-x-auto">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full min-w-[520px]" role="group" aria-label="Precision and recall by fraud_score threshold">
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
              [25, "human"],
              [40, "medium zone"],
              [72.5, "high zone"],
            ] as const
          ).map(([v, name]) => (
            <text key={name} x={sx(v)} y={bottom - 8} textAnchor="middle" className="fill-muted-foreground" style={tick}>
              {name}
            </text>
          ))}
          <line x1={left} x2={right} y1={bottom} y2={bottom} className="stroke-muted-foreground/50" />
          {thresholds.map((t) => (
            <text key={t.threshold} x={sx(t.threshold)} y={bottom + 17} textAnchor="middle" className="fill-muted-foreground" style={tick}>
              {t.threshold}
            </text>
          ))}
          <text x={(left + right) / 2} y={bottom + 38} textAnchor="middle" className="fill-muted-foreground" style={tick}>
            fraud_score threshold (flag transactions at or above)
          </text>
          {active !== null ? (
            <line x1={sx(thresholds[active].threshold)} x2={sx(thresholds[active].threshold)} y1={top} y2={bottom} className="stroke-foreground/60" />
          ) : null}
          {/* each line draws itself, then its markers and its name fade in (motion kit; in place at once with reduced motion) */}
          {series.map((s, si) => (
            <MotionGroup as="g" key={s.name} delay={si * 150} after={600}>
              <polyline
                {...part.draw}
                points={thresholds.map((t) => `${sx(t.threshold)},${sy(s.get(t))}`).join(" ")}
                fill="none"
                stroke={s.color}
                strokeWidth={2}
                strokeLinejoin="round"
                strokeLinecap="round"
              />
              {thresholds.map((t, i) => (
                <circle {...part.after} key={t.threshold} cx={sx(t.threshold)} cy={sy(s.get(t))} r={active === i ? 6 : 4} fill={s.color} strokeWidth={2} className="stroke-card" />
              ))}
              <text {...part.after} x={right + 10} y={sy(s.get(thresholds[thresholds.length - 1])) + 4} className="fill-foreground" style={label}>
                {s.name}
              </text>
            </MotionGroup>
          ))}
          <MotionGroup as="g" delay={750} {...part.fade} className="fill-foreground" style={label}>
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
          </MotionGroup>
          {thresholds.map((t, i) => {
            const x0 = sx(edges[i]);
            const x1 = i === thresholds.length - 1 ? right + 4 : sx(edges[i + 1]);
            const tip = bind(
              <TipBody
                title={`Score ${t.threshold} or more`}
                rows={[
                  [<LineKey key="p" color={series[0].color}>Precision</LineKey>, pct(t.precision_pct)],
                  [<LineKey key="r" color={series[1].color}>Recall, frauds with a score</LineKey>, pct(t.recall_with_score_pct)],
                  ["Recall, all frauds", pct(t.recall_all_frauds_pct)],
                  ["Flagged transactions", int(t.n_flagged)],
                  ["Of which fraud", int(t.n_frauds_flagged)],
                ]}
                note={`${int(frauds.with_score)} frauds have a score; ${int(frauds.total)} in total.`}
              />,
            );
            return (
              <rect
                key={t.threshold}
                x={x0}
                y={top - 14}
                width={x1 - x0}
                height={bottom - top + 14}
                fill="transparent"
                tabIndex={0}
                role="img"
                aria-label={`Score ${t.threshold} or more: precision ${pct(t.precision_pct)}, recall ${pct(t.recall_with_score_pct)}`}
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
      {node}
    </ChartCard>
  );
}

function ZonesChart({ frauds }: { frauds: PitchNumbers["frauds"] }) {
  const { bind, node } = useTip();
  const human = frauds.zones.filter((z) => z.zone === "Human zone").reduce((sum, z) => sum + z.n, 0);
  return (
    <ChartCard
      title={`Where the ${int(frauds.total)} labeled frauds fall in the three zones`}
      figure={<BigFigure value={pct((100 * human) / frauds.total)} label="[data]" caption="of the frauds have a low score or none" />}
      line="The handoff to a person is a main path, so the system always opens a case."
      detail={{
        meaning: "The share of all transactions labeled as fraud, by the score the bank gave them, in the zones of contracts/policies.yaml.",
        method: "Labeled frauds grouped by the bank's fraud_score: high 50 or more, medium 30 to 49, human below 30 or no score.",
      }}
      source="[data] queries/pitch/p08_fraud_score_thresholds.sql · p07_fraud_per_month.sql"
      table={
        <TableView
          head={["Zone (contracts/policies.yaml)", "What the system does", "Frauds", "Share"]}
          rows={frauds.zones.map((z) => [`${z.zone} · ${z.range}`, z.action, int(z.n), pct(z.pct)])}
        />
      }
    >
      <ul className="mb-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {frauds.zones.map((z) => (
          <li key={z.key} className="inline-flex items-center gap-1.5">
            <Swatch color={ZONE_FILL[z.key]} />
            {z.zone} · {z.range}
          </li>
        ))}
      </ul>
      <div className="flex gap-0.5 text-xs tabular-nums text-muted-foreground">
        {frauds.zones.map((z) => (
          <span key={z.key} style={{ width: `${z.pct}%` }}>
            {pct(z.pct)}
          </span>
        ))}
      </div>
      <GrowBar className="mt-1 flex h-6 gap-0.5">
        {frauds.zones.map((z, i) => (
          <div
            key={z.key}
            tabIndex={0}
            role="img"
            aria-label={`${z.zone}, ${z.range}: ${int(z.n)} frauds, ${pct(z.pct)}`}
            className={`transition hover:brightness-110 ${FOCUS} ${i === 0 ? "rounded-l-sm" : ""} ${i === frauds.zones.length - 1 ? "rounded-r-sm" : ""}`}
            style={{ width: `${z.pct}%`, background: ZONE_FILL[z.key] }}
            {...bind(
              <TipBody
                title={`${z.zone} · ${z.range}`}
                rows={[
                  ["Labeled frauds", int(z.n)],
                  ["Share of all frauds", pct(z.pct)],
                ]}
                note={z.action}
              />,
            )}
          />
        ))}
      </GrowBar>
      {node}
    </ChartCard>
  );
}

export function PitchCharts({ data }: { data: PitchNumbers }) {
  return (
    // One column in reading order; from xl, two columns that each stack their own cards (no stretched cards).
    <div className="flex flex-col gap-4 xl:flex-row xl:items-start">
      <div className="contents xl:flex xl:min-w-0 xl:flex-1 xl:flex-col xl:gap-4">
        <Reveal className="order-1">
          <ShareChart share={data.share} />
        </Reveal>
        <Reveal className="order-3">
          <ThresholdChart thresholds={data.thresholds} frauds={data.frauds} />
        </Reveal>
      </div>
      <div className="contents xl:flex xl:min-w-0 xl:flex-1 xl:flex-col xl:gap-4">
        <Reveal className="order-2" delay={90}>
          <ContactsChart contacts={data.contacts} />
        </Reveal>
        <Reveal className="order-4" delay={90}>
          <ZonesChart frauds={data.frauds} />
        </Reveal>
      </div>
    </div>
  );
}
