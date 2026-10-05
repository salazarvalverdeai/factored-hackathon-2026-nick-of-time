import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { EmptyState } from "@/components/states";
import { PageShell } from "@/components/page-shell";
import { RESULT_FILES, pending, type EvaluationData, type Insight } from "@/lib/evaluation";
import { EvaluationResults } from "./results";

const PROTOCOL_URL = "https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/blob/main/eval/PROTOCOL.md";
const DATA_DIR = path.join(process.cwd(), "public", "data");

// The result files are read when the page is built. A file that does not exist yet gives the "results pending"
// state of spec 12 AC-04; there are no placeholder result files (eval/PROTOCOL.md counts them as results).
export default function Page() {
  const [summary, ...later] = RESULT_FILES.map((file) => ({ file, exists: existsSync(path.join(DATA_DIR, file.file)) }));
  const results = summary.exists
    ? (JSON.parse(readFileSync(path.join(DATA_DIR, summary.file.file), "utf-8")) as Insight<EvaluationData>)
    : null;
  return (
    <PageShell title="Evaluation" description="Does the system work, and how do we know? Final state of scripted cases, never the reply text.">
      <p className="mb-4 rounded-lg border border-dashed px-4 py-3 text-sm text-muted-foreground">
        Every figure on this page is <span className="font-mono">[simulated]</span>: real customers and transactions
        of the synthetic dataset with team-written messages, run through the system and compared with the outcome the
        policy engine expects. The rules were written down before any result existed:{" "}
        <a className="underline underline-offset-2" href={PROTOCOL_URL}>
          evaluation protocol
        </a>
        .
      </p>
      <div className="space-y-4">
        {results ? <EvaluationResults file={results} /> : <Pending {...pending(summary.file, false)!} />}
        {later.map(({ file, exists }) => {
          const missing = pending(file, exists);
          // The shapes of these three files are fixed by specs 15, 11 and 17 (spec 12 Q1); their sections come then.
          return missing ? <Pending key={file.file} {...missing} /> : null;
        })}
      </div>
    </PageShell>
  );
}

function Pending({ title, missing }: { title: string; missing: string }) {
  return <EmptyState title={title} hint={missing} />;
}
