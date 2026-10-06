import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { dataDir } from "@/lib/data-dir";
import Link from "next/link";
import { EmptyState } from "@/components/states";
import { PageShell } from "@/components/page-shell";
import { PipelineDiagram } from "@/components/pipeline-diagram";
import { EVALUATION_OTHER_FILES, EVALUATION_STEPS } from "@/lib/pipelines";
import {
  RESULT_FILES,
  detailUrl,
  limitations,
  pageNotice,
  pending,
  type BenchmarkData,
  type ClassifierData,
  type EvaluationData,
  type FraudData,
  type Insight,
} from "@/lib/evaluation";
import pitch from "@/public/data/pitch_numbers.json";
import type { PitchContacts } from "@/lib/panel";
import { AsIsPanel } from "./panel";
import { Limitations } from "./explain";
import { EvaluationResults } from "./results";
import { BenchmarkSection, ClassifierSection, FraudSection } from "./sections";

// EVALUATION_DATA_DIR (see apps/web/README.md) lets a local build read the test fixtures for a screenshot check; it is unset in production.
const DATA_DIR = dataDir(process.env.EVALUATION_DATA_DIR);

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
  const files = { summary: summary.file, benchmark: benchmark.file, classifier: classifier.file, fraud: fraud.file };
  // spec 12 AC-05: one notice for every development-run file; each of their sections carries a chip.
  const notice = pageNotice(files);
  return (
    <PageShell title="Evaluation" description="Does the system work, and how do we know? Final state of scripted cases, never the reply text.">
      <p className="mb-4 rounded-lg border border-dashed px-4 py-3 text-sm text-muted-foreground">
        Each section says what its figures are made from and carries its own label. The scripted agent cases are written by the team with AI assistance on real dataset state, run through the
        real system and compared with the outcome the policy engine expects. The rules were written down before any result existed:{" "}
        <a className="underline underline-offset-2" href={detailUrl("protocol")}>
          evaluation protocol
        </a>
        . How the system is built:{" "}
        <Link className="underline underline-offset-2" href="/agent">
          the agent
        </Link>
        .
      </p>
      <div className="space-y-4">
        {notice ? (
          <p role="note" data-slot="development-notice" className="rounded-lg border border-brand-amber bg-muted px-4 py-3 text-sm font-medium text-foreground">
            {notice}
          </p>
        ) : null}
        <AsIsPanel contacts={pitch.data.contacts as PitchContacts} source={pitch.source} generatedAt={pitch.generated_at} summary={summary.file} benchmark={benchmark.file?.data ?? null} />
        {summary.file ? <EvaluationResults file={summary.file} /> : <Pending {...summary.missing!} />}
        {/* spec 12 §7.3 order: benchmark (5), classifier (6), fraud model (7). */}
        {benchmark.file ? <BenchmarkSection file={benchmark.file} /> : <Pending {...benchmark.missing!} />}
        {classifier.file ? <ClassifierSection file={classifier.file} /> : <Pending {...classifier.missing!} />}
        {fraud.file ? <FraudSection file={fraud.file} /> : <Pending {...fraud.missing!} />}
        <Limitations items={limitations(files)} />
        <section aria-label="How it's built" className="rounded-lg border bg-card p-5 text-card-foreground">
          <h2 className="text-base font-semibold">How it&apos;s built</h2>
          <p className="mt-0.5 mb-4 text-sm text-muted-foreground">
            How an agent figure on this page is made, from the sealed case file to this page. The system itself is drawn on{" "}
            <Link className="underline underline-offset-2" href="/agent">
              the agent page
            </Link>
            .
          </p>
          <PipelineDiagram label="How the agent evaluation is built" steps={EVALUATION_STEPS} columns={4} />
          <p className="mt-4 text-sm text-muted-foreground">{EVALUATION_OTHER_FILES}</p>
        </section>
      </div>
    </PageShell>
  );
}

function Pending({ title, missing }: { title: string; missing: string }) {
  return <EmptyState title={title} hint={missing} />;
}
