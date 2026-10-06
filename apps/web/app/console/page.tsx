"use client";

import { copilotActionLabel, formatTime, handoffReasonLabel } from "@/lib/handoff-labels";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { StatusBadge, ZoneBadge } from "@/components/badges";
import { PageShell } from "@/components/page-shell";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Timeline } from "@/components/timeline";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError, api } from "@/lib/api";
import { type AnalystActionName, type ConsoleAction, consoleActions } from "@/lib/console-actions";
import { DONE_STATUSES, OPEN_STATUSES, loadBoard, slaOf } from "@/lib/console-metrics";
import { formatDeadline } from "@/lib/format";
import type { ConsoleCase } from "@/lib/types";
import { useMounted, useQuery, useSession } from "@/lib/use-query";
import { ClosedList, KpiStrip, SlaLight } from "./board";

export default function ConsolePage() {
  const router = useRouter();
  const mounted = useMounted();
  const { analystSession } = useSession();

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
  const { supervised, audit } = useSession();
  // The inbox with each case's events and the api's countdown: the KPI strip, the SLA lights and the Closed tab read it.
  const cases = useQuery((a) => loadBoard(a));
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tab, setTab] = useState("inbox");
  const [inboxTab, setInboxTab] = useState("open");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<{ caseId: string; action: AnalystActionName } | null>(null);
  const [reason, setReason] = useState("");

  // The inbox lists summaries; the selected case (the first open one until a person picks) is read with its handoff card.
  const firstId =
    cases.status === "ok" ? (cases.data.find((c) => OPEN_STATUSES.includes(c.status))?.id ?? cases.data[0]?.id ?? null) : null;
  const activeId = selectedId ?? firstId;
  const detail = useQuery((a) => (activeId ? a.getConsoleCase(activeId) : Promise.resolve(null)), [activeId]);

  if (cases.status === "loading") return <PageShell title="Console" description="Analyst inbox."><LoadingState /></PageShell>;
  if (cases.status === "error") {
    return (
      <PageShell title="Console" description="Analyst inbox.">
        <ErrorState title="Cannot load the inbox" message={cases.error.message} />
      </PageShell>
    );
  }

  const all = cases.data;

  async function run(caseId: string, action: AnalystActionName, confirmed = false) {
    setBusy(true);
    setMessage(null);
    try {
      await api.analystAction(caseId, action, { reason, confirmed });
      setConfirming(null);
      setReason("");
    } catch (err) {
      if (err instanceof ApiError && err.code === "APPROVAL_REQUIRED") setConfirming({ caseId, action });
      else setMessage(err instanceof ApiError ? err.message : "unexpected error");
    } finally {
      setBusy(false);
    }
  }

  async function runSetting(on: boolean) {
    setBusy(true);
    setMessage(null);
    try {
      await api.setSupervised(on);
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "unexpected error");
    } finally {
      setBusy(false);
    }
  }

  function select(id: string) {
    setSelectedId(id);
    setConfirming(null);
    setMessage(null);
    setReason("");
    setTab("case");
  }

  const openCount = all.filter((c) => OPEN_STATUSES.includes(c.status)).length;
  const doneCount = all.filter((c) => DONE_STATUSES.includes(c.status)).length;
  const openList = (
    <div className="space-y-4">
      {openCount === 0 ? <EmptyState title="No open cases" hint={all.length === 0 ? "Open one from /chat." : undefined} /> : null}
      {OPEN_STATUSES.map((status) => {
        const rows = all.filter((c) => c.status === status);
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
                    onClick={() => select(c.id)}
                    aria-current={activeId === c.id}
                    className="w-full space-y-1 rounded-lg border p-2 text-left text-sm hover:bg-accent aria-[current=true]:border-foreground"
                  >
                    <span className="flex items-center justify-between gap-2">
                      <span className="font-mono text-xs">{c.id}</span>
                      <ZoneBadge zone={c.zone} />
                    </span>
                    <span className="block truncate">{c.customerName}</span>
                    <span className="block text-xs text-muted-foreground">
                      Deadline {formatDeadline(c.deadline)} · priority {c.priority}
                    </span>
                    {/* SLA light: text + icon, never color alone (spec 08 AC-08). */}
                    <SlaLight sla={slaOf(c)} />
                  </button>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );

  const inbox = (
    <Card>
      <CardHeader>
        <CardTitle>Inbox</CardTitle>
        <CardDescription>Open cases by status · zone · deadline · priority; resolved and closed ones under Closed</CardDescription>
      </CardHeader>
      <CardContent>
        <Tabs value={inboxTab} onValueChange={(v) => setInboxTab(String(v))}>
          <TabsList className="w-full">
            <TabsTrigger value="open">Open ({openCount})</TabsTrigger>
            <TabsTrigger value="closed">Closed ({doneCount})</TabsTrigger>
          </TabsList>
          <TabsContent value="open">{openList}</TabsContent>
          <TabsContent value="closed">
            <ClosedList board={all} activeId={activeId} onSelect={select} />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );

  const shown = detail.status === "ok" && detail.data && detail.data.id === activeId ? detail.data : null;
  const detailPanel = !activeId ? (
    <EmptyState title="Select a case" />
  ) : detail.status === "error" ? (
    <ErrorState title="Cannot load the case" message={detail.error.message} />
  ) : shown ? (
    <CaseDetail
      c={shown}
      busy={busy}
      confirming={confirming?.caseId === shown.id ? confirming.action : null}
      message={message}
      supervised={supervised}
      reason={reason}
      onReason={setReason}
      onRun={(action, confirmed) => run(shown.id, action, confirmed)}
    />
  ) : (
    <LoadingState label="Loading the case…" />
  );

  const auditPanel = (
    <Card>
      <CardHeader>
        <CardTitle>Audit</CardTitle>
        <CardDescription>Every action and supervised-mode change of this session, with its user. The case timeline holds the server&apos;s record.</CardDescription>
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
                  {a.actor} · {formatTime(a.at)}
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
          onClick={() => runSetting(!supervised)}
          className="inline-flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-sm hover:bg-accent"
        >
          <span
            aria-hidden
            className={`inline-block h-4 w-7 rounded-full p-0.5 transition-colors ${supervised ? "bg-brand-violet" : "bg-muted"}`}
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

      <KpiStrip board={all} />

      {/* Three columns from 1024 px up; tabs below that (spec 08 AC-06). */}
      <div className="hidden gap-4 lg:grid lg:grid-cols-3">
        {inbox}
        {detailPanel}
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
          <TabsContent value="case">{detailPanel}</TabsContent>
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
  reason,
  onReason,
  onRun,
}: {
  c: ConsoleCase;
  busy: boolean;
  /** The approval waiting for its second click (supervised mode), if any. */
  confirming: AnalystActionName | null;
  message: string | null;
  supervised: boolean;
  reason: string;
  onReason: (reason: string) => void;
  onRun: (action: AnalystActionName, confirmed?: boolean) => void;
}) {
  const status = c.status;
  const h = c.handoff;
  const actions = consoleActions(status, api.mode);
  const needsReason = actions.some((a) => a.needsReason);
  const canApprove = actions.some((a) => a.approval);
  const label = (a: ConsoleAction) => (confirming === a.action ? "Confirm approval (supervised mode)" : a.label);
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
          {c.handoffEmitted === false ? (
            <p className="text-muted-foreground">The agent has not written the handoff card for this case yet.</p>
          ) : null}
          <p>
            <b>Request:</b> {h.request || "—"}
          </p>
          <p>
            <b>Deadline:</b> {formatDeadline(c.deadline)}
            <span className="block text-xs text-muted-foreground">{h.deadline.deadline_source}</span>
          </p>
          {h.handoff_reason ? (
            <p>
              <b>Handoff reason:</b> {handoffReasonLabel(h.handoff_reason)}
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
            <b>Evidence:</b> {h.evidence.join("; ") || "—"}
          </p>
          <p>
            <b>Open questions:</b> {h.open_questions.join("; ") || "—"}
          </p>
          {h.copilot_proposal ? (
            <p>
              <b>Copilot proposal:</b> {copilotActionLabel(h.copilot_proposal.action)} (a person decides)
            </p>
          ) : null}
          <p className="text-xs text-muted-foreground">
            {h.score === null || h.score === undefined ? "Score del banco: sin dato" : `Score del banco: ${h.score}`}
            {h.trace_id ? ` · trace ${h.trace_id}` : ""}
          </p>
        </section>

        <section aria-label="Actions" className="space-y-2">
          {needsReason ? (
            <label className="block text-xs">
              Reason (recorded with your user)
              <Input value={reason} onChange={(e) => onReason(e.target.value)} placeholder="Why this decision" />
            </label>
          ) : null}
          <div className="flex flex-wrap gap-2">
            {actions.map((a) => (
              <Button
                key={a.action}
                size="sm"
                variant={a.approval || a.action === "take" ? "default" : "outline"}
                disabled={busy || (a.needsReason && !reason.trim())}
                onClick={() => onRun(a.action, a.approval ? confirming === a.action : undefined)}
              >
                {label(a)}
              </Button>
            ))}
          </div>
          {supervised && canApprove ? <p className="text-xs text-muted-foreground">Supervised mode is on: approvals need a second click.</p> : null}
          {message ? <ErrorState title="Action refused" message={message} /> : null}
        </section>

        <section aria-label="Timeline">
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">Timeline</h3>
          <Timeline
            events={c.events.map((e) => ({
              id: e.id,
              at: e.at,
              type: e.type,
              badge: e.status ? <StatusBadge status={e.status} /> : null,
              meta: `${e.actor}${e.reason ? ` · ${e.reason}` : ""}`,
            }))}
          />
        </section>
      </CardContent>
    </Card>
  );
}
