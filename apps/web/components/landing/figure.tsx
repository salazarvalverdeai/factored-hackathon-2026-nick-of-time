import { NumberTicker } from "@/components/ui/number-ticker";
import type { FigureLabel, Side, Source, Stat } from "@/lib/landing";

/** The label every figure carries (constitution #8), as text, never as color only. */
export function LabelTag({ label }: { label: FigureLabel }) {
  return (
    <span className="inline-flex items-center rounded-md border px-1.5 py-0.5 font-mono text-[0.7rem] leading-none text-muted-foreground">
      [{label}]
    </span>
  );
}

export function SourceLinks({ sources }: { sources: Source[] }) {
  return (
    <span className="text-xs text-muted-foreground">
      Source:{" "}
      {sources.map((s, i) => (
        <span key={s.href}>
          {i > 0 ? " · " : null}
          <a href={s.href} className="underline underline-offset-2 hover:text-foreground" target="_blank" rel="noreferrer">
            {s.label}
          </a>
        </span>
      ))}
    </span>
  );
}

function SideValue({ side, large }: { side: Side; large?: boolean }) {
  const size = large ? "text-4xl sm:text-5xl" : "text-2xl";
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{side.name}</dt>
      <dd className={`${size} font-semibold tracking-tight tabular-nums`}>
        {side.ticker ? (
          <NumberTicker value={side.ticker.value} decimalPlaces={side.ticker.decimals} />
        ) : (
          side.value
        )}
        {side.ticker ? side.ticker.suffix : null}
      </dd>
      {side.note ? <dd className="mt-0.5 font-mono text-[0.7rem] text-muted-foreground">{side.note}</dd> : null}
    </div>
  );
}

/** One figure from docs/problem_in_numbers.md: the values, a sentence, the label and the linked source. */
export function StatCard({ stat, large }: { stat: Stat; large?: boolean }) {
  return (
    <article className="flex h-full flex-col gap-3 rounded-xl border bg-card p-4 text-card-foreground sm:p-5">
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-sm font-medium">{stat.title}</h3>
        <LabelTag label={stat.label} />
      </div>
      <dl className="flex flex-wrap gap-x-8 gap-y-3">
        {stat.sides.map((side) => (
          <SideValue key={side.name} side={side} large={large} />
        ))}
      </dl>
      <p className="text-sm text-muted-foreground">{stat.detail}</p>
      {stat.caveat ? (
        <p className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
          <span>{stat.caveat.text}</span> <LabelTag label={stat.caveat.label} />
        </p>
      ) : null}
      <div className="mt-auto">
        <SourceLinks sources={stat.sources} />
      </div>
    </article>
  );
}
