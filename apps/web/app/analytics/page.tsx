import { PageShell } from "@/components/page-shell";
import { PipelineDiagram } from "@/components/pipeline-diagram";
import { ANALYTICS_STEPS } from "@/lib/pipelines";
import type { OpsSeries } from "@/lib/ops";
import ops from "@/public/data/ops_kpis.json";
import pitch from "@/public/data/pitch_numbers.json";
import { PitchCharts, type PitchNumbers } from "./charts";
import { Operations } from "./operations";

export default function Page() {
  return (
    <PageShell title="Analytics" description="The problem in numbers, score zones, business case and operation.">
      <p className="mb-4 rounded-lg border border-dashed px-4 py-3 text-sm text-muted-foreground">
        Synthetic dataset. The first charts describe the problem and the reason for each design decision; they do not measure
        the system (see Evaluation). Hover over a chart, or move to it with the Tab key, to see the detail behind each
        value.
      </p>
      <PitchCharts data={pitch.data as PitchNumbers} />
      <p className="mt-4 font-mono text-xs text-muted-foreground">
        {pitch.source} · generated {pitch.generated_at.slice(0, 10)} at {pitch.git_sha}
      </p>
      {/* only the series reach the client: the per-day rows of the file stay on the server */}
      <Operations file={{ data: { series: ops.data.series as unknown as OpsSeries } }} />
      <p className="mt-4 font-mono text-xs text-muted-foreground">
        {ops.source} · generated {ops.generated_at.slice(0, 10)} at {ops.git_sha}
      </p>
      {/* spec 12: where the problem numbers come from. A block of its own at the end of the page. */}
      <section aria-label="How it's built" className="mt-4 rounded-lg border bg-card p-5 text-card-foreground">
        <h2 className="text-base font-semibold">How it&apos;s built</h2>
        <p className="mt-0.5 mb-4 text-sm text-muted-foreground">Where the problem numbers above come from: every figure is a committed query output, never typed.</p>
        <PipelineDiagram label="How the problem numbers are built" steps={ANALYTICS_STEPS} />
      </section>
    </PageShell>
  );
}
