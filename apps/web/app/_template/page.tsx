"use client";

// TEMPLATE for a new page (spec 16). Copy this folder, rename it, edit. `_template` starts with an underscore, so
// Next.js does not route it, but lint, type-check and build still run on it: a page built from here cannot rot.
//
//   cp -r app/_template app/my-page      # then change the title, the query and the columns
//
// It shows the whole standard: a PageShell, data through `useQuery`, the four states (loading, error, empty, content),
// shared components, and a chart whose source is labelled.
import { ZoneBadge } from "@/components/badges";
import { BarChartCard } from "@/components/chart";
import { PageShell } from "@/components/page-shell";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDeadline } from "@/lib/format";
import { useQuery } from "@/lib/use-query";

export default function TemplatePage() {
  // Read through useQuery (any `api` call); act through `api` (lib/api.ts). Without an analyst login this shows the error state.
  const cases = useQuery((api) => api.listCases());

  return (
    <PageShell title="Template page" description="Copy this folder to start a page. Replace the query and the columns.">
      {cases.status === "loading" ? <LoadingState /> : null}
      {cases.status === "error" ? (
        <ErrorState title="Cannot load the data" message={cases.error.message} />
      ) : null}
      {cases.status === "ok" && cases.data.length === 0 ? <EmptyState title="No cases yet" /> : null}
      {cases.status === "ok" && cases.data.length > 0 ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Cases</CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Case</TableHead>
                    <TableHead>Zone</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Deadline</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {cases.data.map((c) => (
                    <TableRow key={c.id}>
                      <TableCell className="font-mono text-xs">{c.id}</TableCell>
                      <TableCell>
                        <ZoneBadge zone={c.zone} />
                      </TableCell>
                      <TableCell>{c.status}</TableCell>
                      <TableCell>{formatDeadline(c.deadline)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
          <BarChartCard
            title="Cases by zone"
            source="[simulated] mock store, not the dataset"
            data={(["high", "medium", "human"] as const).map((z) => ({
              label: z,
              value: cases.data.filter((c) => c.zone === z).length,
            }))}
          />
        </div>
      ) : null}
    </PageShell>
  );
}
