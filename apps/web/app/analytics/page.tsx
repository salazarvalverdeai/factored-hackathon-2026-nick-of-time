import { PageShell } from "@/components/page-shell";
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
    </PageShell>
  );
}
