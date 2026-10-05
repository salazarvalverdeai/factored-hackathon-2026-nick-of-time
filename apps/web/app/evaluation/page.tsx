import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { EmptyState } from "@/components/states";
import { PageShell } from "@/components/page-shell";
import {
  RESULT_FILES,
  pending,
  type BenchmarkData,
  type ClassifierData,
  type EvaluationData,
  type FraudData,
  type Insight,
} from "@/lib/evaluation";
import { EvaluationResults } from "./results";
import { BenchmarkSection, ClassifierSection, FraudSection } from "./sections";

const PROTOCOL_URL = "https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/blob/main/eval/PROTOCOL.md";
const DATA_DIR = path.join(process.cwd(), "public", "data");

// The result files are read when the page is built. A file that does not exist yet gives the "results pending"
// state of spec 12 AC-04; there are no placeholder result files (eval/PROTOCOL.md counts them as results).
function load<T>(file: (typeof RESULT_FILES)[number]) {
  const exists = existsSync(path.join(DATA_DIR, file.file));
  return { missing: pending(file, exists), file: exists ? (JSON.parse(readFileSync(path.join(DATA_DIR, file.file), "utf-8")) as Insight<T>) : null };
}

export default function Page() {
  const [summaryFile, benchmarkFile, classifierFile, fraudFile] = RESULT_FILES;
  const summary = load<EvaluationData>(summaryFile);
  const benchmark = load<BenchmarkData>(benchmarkFile);
  const classifier = load<ClassifierData>(classifierFile);
  const fraud = load<FraudData>(fraudFile);
  return (
    <PageShell title="Evaluation" description="Does the system work, and how do we know? Final state of scripted cases, never the reply text.">
      <p className="mb-4 rounded-lg border border-dashed px-4 py-3 text-sm text-muted-foreground">
        Every figure on this page is <span className="font-mono">[simulated]</span> (the fraud model, <span className="font-mono">[data]</span>): real customers and transactions
        of the synthetic dataset with team-written messages, run through the system and compared with the outcome the
        policy engine expects. The rules were written down before any result existed:{" "}
        <a className="underline underline-offset-2" href={PROTOCOL_URL}>
          evaluation protocol
        </a>
        .
      </p>
      <div className="space-y-4">
        {summary.file ? <EvaluationResults file={summary.file} /> : <Pending {...summary.missing!} />}
        {/* spec 12 §7.3 order: benchmark (5), classifier (6), fraud model (7). */}
        {benchmark.file ? <BenchmarkSection file={benchmark.file} /> : <Pending {...benchmark.missing!} />}
        {classifier.file ? <ClassifierSection file={classifier.file} /> : <Pending {...classifier.missing!} />}
        {fraud.file ? <FraudSection file={fraud.file} /> : <Pending {...fraud.missing!} />}
      </div>
    </PageShell>
  );
}

function Pending({ title, missing }: { title: string; missing: string }) {
  return <EmptyState title={title} hint={missing} />;
}
