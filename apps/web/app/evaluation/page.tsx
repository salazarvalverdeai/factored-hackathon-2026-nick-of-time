import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { Fragment } from "react";
import type { Locale } from "@/lib/i18n";
import { getT } from "@/lib/i18n-server";
import { dataDir } from "@/lib/data-dir";
import Link from "next/link";
import { EmptyState } from "@/components/states";
import { PageShell } from "@/components/page-shell";
import {
  RESULT_FILES,
  detailUrl,
  limitations,
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
function load<T>(file: (typeof RESULT_FILES)[number], locale: Locale) {
  const exists = existsSync(path.join(DATA_DIR, file.file));
  return { missing: pending(file, exists, locale), file: exists ? (JSON.parse(readFileSync(path.join(DATA_DIR, file.file), "utf-8")) as Insight<T>) : null };
}

export default async function Page() {
  const { t, locale } = await getT();
  const [summaryFile, benchmarkFile, classifierFile, fraudFile] = RESULT_FILES;
  const summary = load<EvaluationData>(summaryFile, locale);
  const benchmark = load<BenchmarkData>(benchmarkFile, locale);
  const classifier = load<ClassifierData>(classifierFile, locale);
  const fraud = load<FraudData>(fraudFile, locale);
  // The intro is one translated sentence; its two links fill the {protocol} and {agent} placeholders.
  const links = {
    protocol: (
      <a className="underline underline-offset-2" href={detailUrl("protocol")}>
        {t("evaluation.protocolLink")}
      </a>
    ),
    agent: (
      <Link className="underline underline-offset-2" href="/agent">
        {t("evaluation.agentLink")}
      </Link>
    ),
  };
  return (
    <PageShell title={t("evaluation.title")} description={t("evaluation.description")}>
      <p className="mb-4 rounded-lg border border-dashed px-4 py-3 text-sm text-muted-foreground">
        {t("evaluation.intro")
          .split(/\{(protocol|agent)\}/)
          .map((part, i) => (
            <Fragment key={i}>{i % 2 === 1 ? links[part as keyof typeof links] : part}</Fragment>
          ))}
      </p>
      <div className="space-y-4">
        <AsIsPanel contacts={pitch.data.contacts as PitchContacts} source={pitch.source} generatedAt={pitch.generated_at} summary={summary.file} benchmark={benchmark.file?.data ?? null} locale={locale} />
        {summary.file ? <EvaluationResults file={summary.file} /> : <Pending {...summary.missing!} />}
        {/* spec 12 §7.3 order: benchmark (5), classifier (6), fraud model (7). */}
        {benchmark.file ? <BenchmarkSection file={benchmark.file} /> : <Pending {...benchmark.missing!} />}
        {classifier.file ? <ClassifierSection file={classifier.file} /> : <Pending {...classifier.missing!} />}
        {fraud.file ? <FraudSection file={fraud.file} /> : <Pending {...fraud.missing!} />}
        <Limitations items={limitations({ summary: summary.file, benchmark: benchmark.file, classifier: classifier.file, fraud: fraud.file }, locale)} />

      </div>
    </PageShell>
  );
}

function Pending({ title, missing }: { title: string; missing: string }) {
  return <EmptyState title={title} hint={missing} />;
}
