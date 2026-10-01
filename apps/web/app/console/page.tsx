import { PageShell } from "@/components/page-shell";

const PANELS = ["Inbox", "Case", "Evidence"];

export default function ConsolePage() {
  return (
    <PageShell title="Console" description="Analyst inbox, handoff card and evidence graph.">
      <div className="grid gap-4 lg:grid-cols-3">
        {PANELS.map((p) => (
          <section key={p} className="min-h-64 rounded-lg border p-4">
            <h2 className="text-sm font-medium">{p}</h2>
            <p className="mt-6 text-center text-sm text-muted-foreground">Empty state</p>
          </section>
        ))}
      </div>
    </PageShell>
  );
}
