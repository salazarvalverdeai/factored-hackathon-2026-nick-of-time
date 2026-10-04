"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { StatusBadge, ZoneBadge } from "@/components/badges";
import { PageShell } from "@/components/page-shell";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Timeline } from "@/components/timeline";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError, api } from "@/lib/api";
import { formatDeadline } from "@/lib/format";
import { caseStatus } from "@/lib/mock/store";
import type { CaseRecord, CaseStatus } from "@/lib/types";
import { useMockState, useMounted, useQuery } from "@/lib/use-query";

const ORDER: CaseStatus[] = ["new", "verification", "review", "resolved", "closed"];

export default function ConsolePage() {
  const router = useRouter();
  const mounted = useMounted();
  const { analystSession } = useMockState();

  // Without an analyst session the console is never shown: it sends the person to /login (spec 08 AC-01).
  useEffect(() => {
    if (mounted && !analystSession) router.replace("/login");
  }, [mounted, analystSession, router]);

  if (!mounted || !analystSession) {
    return (
      <PageShell title="Console" description="Analyst inbox, handoff card and audit trail.">
        <LoadingState label="Checking your session…" />
      </PageShell>
    );
  }
  return <Console actor={analystSession.displayName} />;
}

function Console({ actor }: { actor: string }) {
  const router = useRouter();
  const { supervised, audit } = useMockState();
  const cases = useQuery((s) => s.listCases());
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tab, setTab] = useState("inbox");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);

  if (cases.status === "loading") return <PageShell title="Console" description="Analyst inbox."><LoadingState /></PageShell>;
  if (cases.status === "error") {
    return (
      <PageShell title="Console" description="Analyst inbox.">
        <ErrorState title="Cannot load the inbox" message={cases.error.message} />
      </PageShell>
    );
  }

  const all = cases.data;
  const selected = all.find((c) => c.id === selectedId) ?? all[0] ?? null;

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setMessage(null);
    try {
      await action();
      setConfirming(null);
    } catch (err) {
      if (err instanceof ApiError && err.code === "APPROVAL_REQUIRED") setConfirming(selected?.id ?? null);
      else setMessage(err instanceof ApiError ? err.message : "unexpected error");
    } finally {
      setBusy(false);
    }
  }

  const inbox = (
    <Card>
      <CardHeader>
        <CardTitle>Inbox</CardTitle>
        <CardDescription>Cases by status · zone · deadline · priority</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {all.length === 0 ? <EmptyState title="No cases yet" hint="Open one from /chat." /> : null}
        {ORDER.map((status) => {
          const rows = all.filter((c) => caseStatus(c) === status);
          if (rows.length === 0) return null;
          return (
            <section key={status} aria-label={status}>
              <h3 className="mb-1 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                <StatusBadge status={status} /> {rows.length}
              </h3>
              <ul className="space-y-1">
                {rows.map((c) => (
                  <li key={c.id}>
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedId(c.id);
                        setConfirming(null);
                        setMessage(null);
                        setTab("case");
                      }}
                      aria-current={selected?.id === c.id}
                      className="w-full rounded-lg border p-2 text-left text-sm hover:bg-accent aria-[current=true]:border-foreground"
                    >
                      <span className="flex items-center justify-between gap-2">
                        <span className="font-mono text-xs">{c.id}</span>
                        <ZoneBadge zone={c.zone} />
                      </span>
                      <span className="block truncate">{c.customerName}</span>
                      <span className="block text-xs text-muted-foreground">
                        Deadline {formatDeadline(c.deadline)} · priority {c.priority}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      </CardContent>
    </Card>
  );

  const detail = selected ? (
    <CaseDetail
      c={selected}
      busy={busy}
      confirming={confirming === selected.id}
      message={message}
      supervised={supervised}
      onApprove={() => run(() => api.approveCredit(selected.id))}
      onConfirmApprove={() => run(() => api.approveCredit(selected.id, { confirmed: true }))}
      onClose={() => run(() => api.closeCase(selected.id))}
    />
  ) : (
    <EmptyState title="Select a case" />
  );

  const auditPanel = (
    <Card>
      <CardHeader>
        <CardTitle>Audit</CardTitle>
        <CardDescription>Every action and every supervised-mode change, with its user</CardDescription>
      </CardHeader>
      <CardContent>
        {audit.length === 0 ? (
          <EmptyState title="No actions yet" />
        ) : (
          <ul className="space-y-2 text-sm">
            {audit.map((a) => (
              <li key={a.id} className="rounded-lg border p-2">
                <span className="font-medium">{a.action}</span> · {a.target}
                {a.reason ? ` · ${a.reason}` : ""}
                <p className="text-xs text-muted-foreground">
                  {a.actor} · {new Date(a.at).toLocaleTimeString()}
                </p>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );

  return (
    <PageShell title="Console" description={`Signed in as ${actor}. The analyst receives evidence, not a chat.`}>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          role="switch"
          aria-checked={supervised}
          onClick={() => run(() => api.setSupervised(!supervised))}
          className="inline-flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-sm hover:bg-accent"
        >
          <span
            aria-hidden
            className={`inline-block h-4 w-7 rounded-full p-0.5 transition-colors ${supervised ? "bg-emerald-500" : "bg-muted"}`}
          >
            <span className={`block size-3 rounded-full bg-background transition-transform ${supervised ? "translate-x-3" : ""}`} />
          </span>
          Supervised mode: {supervised ? "on" : "off"}
        </button>
        <Button
          size="sm"
          variant="outline"
          onClick={async () => {
            await api.analystLogout();
            router.push("/login");
          }}
        >
          Sign out
        </Button>
      </div>

      {/* Three columns from 1024 px up; tabs below that (spec 08 AC-06). */}
      <div className="hidden gap-4 lg:grid lg:grid-cols-3">
        {inbox}
        {detail}
        {auditPanel}
      </div>
      <div className="lg:hidden">
        <Tabs value={tab} onValueChange={(v) => setTab(String(v))}>
          <TabsList className="w-full">
            <TabsTrigger value="inbox">Inbox</TabsTrigger>
            <TabsTrigger value="case">Case</TabsTrigger>
            <TabsTrigger value="audit">Audit</TabsTrigger>
          </TabsList>
          <TabsContent value="inbox">{inbox}</TabsContent>
          <TabsContent value="case">{detail}</TabsContent>
          <TabsContent value="audit">{auditPanel}</TabsContent>
        </Tabs>
      </div>
    </PageShell>
  );
}

function CaseDetail({
  c,
  busy,
  confirming,
  message,
  supervised,
  onApprove,
  onConfirmApprove,
  onClose,
}: {
  c: CaseRecord;
  busy: boolean;
  confirming: boolean;
  message: string | null;
  supervised: boolean;
  onApprove: () => void;
  onConfirmApprove: () => void;
  onClose: () => void;
}) {
  const status = caseStatus(c);
  const h = c.handoff;
  const canApprove = status === "verification" || status === "review";
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          <span className="font-mono">{c.id}</span> <ZoneBadge zone={c.zone} /> <StatusBadge status={status} />
        </CardTitle>
        <CardDescription>{c.customerName}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <section aria-label="Handoff card" className="space-y-2">
          <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Handoff card</h3>
          <p>
            <b>Request:</b> {h.request}
          </p>
          <p>
            <b>Deadline:</b> {formatDeadline(c.deadline)}
            <span className="block text-xs text-muted-foreground">{h.deadline.deadline_source}</span>
          </p>
          {h.handoff_reason ? (
            <p>
              <b>Handoff reason:</b> {h.handoff_reason}
            </p>
          ) : null}
          <p>
            <b>Verified facts:</b> {h.verified_facts.map((f) => f.fact).join("; ") || "—"}
          </p>
          <p>
            <b>Actions:</b>{" "}
            {h.actions.length
              ? h.actions.map((a) => `${a.tool}: ${a.result}${a.verified ? " (verified ✓)" : ""}`).join("; ")
              : "none taken"}
          </p>
          <p>
            <b>Evidence:</b> {h.evidence.join("; ")}
          </p>
          <p>
            <b>Open questions:</b> {h.open_questions.join("; ")}
          </p>
          {h.copilot_proposal ? (
            <p>
              <b>Copilot proposal:</b> {h.copilot_proposal.action} (a person decides)
            </p>
          ) : null}
          <p className="text-xs text-muted-foreground">
            Bank fraud score [simulated]: {h.score ?? "none"} · trace {h.trace_id}
          </p>
        </section>

        <section aria-label="Actions" className="space-y-2">
          <div className="flex flex-wrap gap-2">
            {canApprove && !confirming ? (
              <Button size="sm" disabled={busy} onClick={onApprove}>
                Approve credit
              </Button>
            ) : null}
            {confirming ? (
              <Button size="sm" disabled={busy} onClick={onConfirmApprove}>
                Confirm approval (supervised mode)
              </Button>
            ) : null}
            {status === "resolved" ? (
              <Button size="sm" variant="outline" disabled={busy} onClick={onClose}>
                Close case
              </Button>
            ) : null}
          </div>
          {supervised && canApprove ? <p className="text-xs text-muted-foreground">Supervised mode is on: approvals need a second click.</p> : null}
          {message ? <ErrorState title="Action refused" message={message} /> : null}
        </section>

        <section aria-label="Timeline">
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">Timeline</h3>
          <Timeline events={c.events} />
        </section>
      </CardContent>
    </Card>
  );
}
