import Link from "next/link";
import { NAV } from "@/components/site-header";
import { PageShell } from "@/components/page-shell";

export default function Home() {
  return (
    <PageShell
      title="Nick of Time"
      description="Dispute handling: customer chat, analyst console and the evidence behind them."
    >
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {NAV.map((n) => (
          <Link key={n.href} href={n.href} className="rounded-lg border p-4 hover:bg-accent">
            <span className="font-medium">{n.label}</span>
            <span className="ml-2 font-mono text-xs text-muted-foreground">{n.href}</span>
          </Link>
        ))}
      </div>
    </PageShell>
  );
}
