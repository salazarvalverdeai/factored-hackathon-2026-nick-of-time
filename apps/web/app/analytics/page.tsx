import { PageShell } from "@/components/page-shell";
import { getT } from "@/lib/i18n-server";
import pitch from "@/public/data/pitch_numbers.json";
import { PitchCharts, type PitchNumbers } from "./charts";

export default async function Page() {
  const { t } = await getT();
  return (
    <PageShell title={t("analytics.title")} description={t("analytics.description")}>
      <p className="mb-4 rounded-lg border border-dashed px-4 py-3 text-sm text-muted-foreground">{t("analytics.intro")}</p>
      <PitchCharts data={pitch.data as PitchNumbers} />
      <p className="mt-4 font-mono text-xs text-muted-foreground">
        {t("analytics.generated", { source: pitch.source, date: pitch.generated_at.slice(0, 10), sha: pitch.git_sha })}
      </p>
    </PageShell>
  );
}
