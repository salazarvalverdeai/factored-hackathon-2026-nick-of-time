import { PageShell } from "@/components/page-shell";
import pitch from "@/public/data/pitch_numbers.json";
import { PitchCharts, type PitchNumbers } from "./charts";

export default function Page() {
  return (
    <PageShell title="Analytics" description="The problem in numbers, score zones and business case.">
      <p className="mb-4 rounded-lg border border-dashed px-4 py-3 text-sm text-muted-foreground">
        Synthetic dataset. These figures describe the problem and the reason for each design decision; they do not measure
        the system (see Evaluation). Hover over a chart, or move to it with the Tab key, to see the detail behind each
        value.
      </p>
      <PitchCharts data={pitch.data as PitchNumbers} />
      <p className="mt-4 font-mono text-xs text-muted-foreground">
        {pitch.source} · generated {pitch.generated_at.slice(0, 10)} at {pitch.git_sha}
      </p>
    </PageShell>
  );
}
