"use client";

// The analyst console (spec 08) in the UI language (spec 16 AC-06): only labels are translated; the handoff card's
// facts, evidence, tool names, ids and figures are shown exactly as the tools returned them (constitution #5).
import { copilotActionLabel, formatTime, handoffReasonLabel } from "@/lib/handoff-labels";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { StatusBadge, ZoneBadge } from "@/components/badges";
import { useLocale, useT } from "@/components/i18n-provider";
import { AgentSummary } from "@/components/console/agent-summary";
import { CaseHeader } from "@/components/console/case-header";
import { ConversationTranscript } from "@/components/console/conversation-transcript";
import { CopilotProposal } from "@/components/console/copilot-proposal";
import { CustomerHistory } from "@/components/console/customer-history";
import { AuditChecklist, SecondOpinionPanel } from "@/components/console/oversight";
import { PageShell } from "@/components/page-shell";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Timeline } from "@/components/timeline";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError, api } from "@/lib/api";
import { type AnalystActionName, type ConsoleAction, consoleActions } from "@/lib/console-actions";
import { type CopilotProposal as CopilotProposalShape, consoleApi } from "@/lib/console-api";
import { DONE_STATUSES, OPEN_STATUSES, loadBoard, slaOf } from "@/lib/console-metrics";
import { plain } from "@/lib/console-view";
import { formatDeadline } from "@/lib/format";
import type { ConsoleCase } from "@/lib/types";
import { useMounted, useQuery, useSession } from "@/lib/use-query";
import { ClosedList, KpiStrip, SlaLight } from "./board";

export default function ConsolePage() {
  const t = useT();
  const router = useRouter();
  const mounted = useMounted();
  const { analystSession } = useSession();

  // Without an analyst session the console is never shown: it sends the person to /login (spec 08 AC-01).
  useEffect(() => {
    if (mounted && !analystSession) router.replace("/login");
  }, [mounted, analystSession, router]);

  if (!mounted || !analystSession) {
    return (
      <PageShell title={t("console.page.title")} description={t("console.page.description")}>
        <LoadingState label={t("console.page.checkingSession")} />
      </PageShell>
    );
  }
  return <Console actor={analystSession.displayName} />;
}

function Console({ actor }: { actor: string }) {
  const t = useT();
  const { locale } = useLocale();
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

  if (cases.status === "loading") {
    return (
      <PageShell title={t("console.page.title")} description={t("console.page.shortDescription")}>
        <LoadingState />
      </PageShell>
    );
  }
  if (cases.status === "error") {
    return (
      <PageShell title={t("console.page.title")} description={t("console.page.shortDescription")}>
        <ErrorState title={t("console.page.cannotLoadInbox")} message={cases.error.message} />
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
      else setMessage(err instanceof ApiError ? err.message : t("console.page.unexpectedError"));
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
      setMessage(err instanceof ApiError ? err.message : t("console.page.unexpectedError"));
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
      {openCount === 0 ? (
        <EmptyState title={t("console.inbox.noOpen")} hint={all.length === 0 ? t("console.inbox.openFromChat") : undefined} />
      ) : null}
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
                      {t("console.inbox.rowMeta", { deadline: formatDeadline(c.deadline, locale), priority: t(`console.priority.${c.priority}`) })}
                    </span>
                    {/* SLA light: text + icon, never color alone (spec 08 AC-08). */}
                    <SlaLight sla={slaOf(c, locale)} />
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
        <CardTitle>{t("console.inbox.title")}</CardTitle>
        <CardDescription>{t("console.inbox.description")}</CardDescription>
      </CardHeader>
      <CardContent>
        <Tabs value={inboxTab} onValueChange={(v) => setInboxTab(String(v))}>
          <TabsList className="w-full">
            <TabsTrigger value="open">{t("console.inbox.open", { n: openCount })}</TabsTrigger>
            <TabsTrigger value="closed">{t("console.inbox.closed", { n: doneCount })}</TabsTrigger>
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
    <EmptyState title={t("console.inbox.selectCase")} />
  ) : detail.status === "error" ? (
    <ErrorState title={t("console.inbox.cannotLoadCase")} message={detail.error.message} />
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
    <LoadingState label={t("console.inbox.loadingCase")} />
  );

  const auditPanel = (
    <Card>
      <CardHeader>
        <CardTitle>{t("console.audit.title")}</CardTitle>
        <CardDescription>{t("console.audit.description")}</CardDescription>
      </CardHeader>
      <CardContent>
        {audit.length === 0 ? (
          <EmptyState title={t("console.audit.empty")} />
        ) : (
          <ul className="space-y-2 text-sm">
            {audit.map((a) => (
              <li key={a.id} className="rounded-lg border p-2">
                <span className="font-medium">{a.action}</span> · {a.target}
                {a.reason ? ` · ${a.reason}` : ""}
                <p className="text-xs text-muted-foreground">
                  {a.actor} · {formatTime(locale, a.at)}
                </p>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );

  return (
    <PageShell title={t("console.page.title")} description={t("console.page.signedInAs", { name: actor })}>
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
          {t("console.page.supervised", { state: supervised ? t("console.page.on") : t("console.page.off") })}
        </button>
        <Button
          size="sm"
          variant="outline"
          onClick={async () => {
            await api.analystLogout();
            router.push("/login");
          }}
        >
          {t("console.page.signOut")}
        </Button>
      </div>

      <KpiStrip board={all} />

      {/* Three columns from 1024 px up; tabs below that (spec 08 AC-06). */}
      {/* The case column is the widest: it carries the assisted view (summary, history, oversight). */}
      <div className="hidden items-start gap-4 lg:grid lg:grid-cols-[15rem_minmax(0,1fr)_14rem] xl:grid-cols-[18rem_minmax(0,1fr)_17rem]">
        {inbox}
        {detailPanel}
        {auditPanel}
      </div>
      <div className="lg:hidden">
        <Tabs value={tab} onValueChange={(v) => setTab(String(v))}>
          <TabsList className="w-full">
            <TabsTrigger value="inbox">{t("console.page.tabs.inbox")}</TabsTrigger>
            <TabsTrigger value="case">{t("console.page.tabs.case")}</TabsTrigger>
            <TabsTrigger value="audit">{t("console.page.tabs.audit")}</TabsTrigger>
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
  const t = useT();
  const { locale } = useLocale();
  const status = c.status;
  const h = c.handoff;
  const actions = consoleActions(status, api.mode);
  const needsReason = actions.some((a) => a.needsReason);
  const canApprove = actions.some((a) => a.approval);
  const label = (a: ConsoleAction) => (confirming === a.action ? t("console.detail.confirmApproval") : t(`console.actions.${a.action}`));
  // The assisted view (spec 08, spec 18 T5/T5b): read again after every action, like the case itself.
  const summary = useQuery(() => consoleApi.getSummary(c.id), [c.id]);
  const context = useQuery(() => consoleApi.getContext(c.id), [c.id]);
  const auditor = useQuery(() => consoleApi.getAudit(c.id), [c.id]);
  const [viewOf, setViewOf] = useState<{ caseId: string; view: string }>({ caseId: c.id, view: "handoff" });
  const view = viewOf.caseId === c.id ? viewOf.view : "handoff";
  const setView = (v: string) => setViewOf({ caseId: c.id, view: v });
  const conversation = useQuery(() => (view === "conversation" ? consoleApi.getConversation(c.id) : Promise.resolve({ threads: [] })), [c.id, view]);
  const path = {
    verification: c.events.some((e) => e.status === "verification" || e.type.includes("verification")),
    review: c.events.some((e) => e.status === "review" || e.type.includes("review")),
  };
  const proposal = h.copilot_proposal as CopilotProposalShape | undefined;
  return (
    <Card>
      <CardHeader>
        <CaseHeader
          id={c.id}
          customerName={c.customerName}
          zone={c.zone}
          priority={c.priority}
          status={status}
          path={path}
          sla={<SlaLight sla={slaOf(c, locale)} />}
        />
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {/* The handoff card stays first; the conversation is a read-only transcript next to it (spec 08 AC-15). */}
        <Tabs value={view} onValueChange={(v) => setView(String(v))}>
          <TabsList className="w-full">
            <TabsTrigger value="handoff">{t("console.detail.tabs.handoff")}</TabsTrigger>
            <TabsTrigger value="conversation">{t("console.detail.tabs.conversation")}</TabsTrigger>
          </TabsList>
          <TabsContent value="handoff" className="space-y-4">
            <AgentSummary query={summary} />
            {/* Only the field labels follow the UI language; every value is the tool's, as returned (constitution #5). */}
            <section aria-label={t("console.handoff.title")} className="space-y-2 rounded-xl border bg-card p-3">
              <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("console.handoff.title")}</h3>
              {c.handoffEmitted === false ? (
                <p className="text-muted-foreground">{t("console.handoff.notWritten")}</p>
              ) : null}
              <p>
                <b>{t("console.handoff.request")}</b> {h.request || "—"}
              </p>
              <p>
                <b>{t("console.handoff.deadline")}</b> {formatDeadline(c.deadline, locale)}
                <span className="block text-xs text-muted-foreground">{plain(h.deadline.deadline_source)}</span>
              </p>
              {h.handoff_reason ? (
                <p>
                  <b>{t("console.handoff.reason")}</b> {handoffReasonLabel(h.handoff_reason, locale)}
                </p>
              ) : null}
              <p>
                <b>{t("console.handoff.facts")}</b> {h.verified_facts.map((f) => plain(f.fact)).join("; ") || "—"}
              </p>
              <p>
                <b>{t("console.handoff.actions")}</b>{" "}
                {h.actions.length
                  ? h.actions
                      .map((a) => `${a.tool.replace(/_/g, " ")}: ${a.result}${a.verified ? ` (${t("console.handoff.verified")})` : ""}`)
                      .join("; ")
                  : t("console.handoff.noneTaken")}
              </p>
              <p>
                <b>{t("console.handoff.evidence")}</b> {h.evidence.map(plain).join("; ") || "—"}
              </p>
              <p>
                <b>{t("console.handoff.openQuestions")}</b> {h.open_questions.map(plain).join("; ") || "—"}
              </p>
              {h.copilot_proposal ? (
                <p>
                  <b>{t("console.handoff.copilot")}</b> {copilotActionLabel(h.copilot_proposal.action, locale)}{" "}
                  {t("console.handoff.personDecides")}
                </p>
              ) : null}
              <p className="text-xs text-muted-foreground">
                {h.score === null || h.score === undefined ? t("console.handoff.scoreNone") : t("console.handoff.score", { score: h.score })}
                {h.trace_id ? ` · trace ${h.trace_id}` : ""}
              </p>
            </section>
          </TabsContent>
          <TabsContent value="conversation">
            {view === "conversation" ? <ConversationTranscript query={conversation} /> : null}
          </TabsContent>
        </Tabs>

        {proposal ? (
          <CopilotProposal
            caseId={c.id}
            proposal={proposal}
            offered={actions}
            busy={busy}
            confirming={confirming}
            reason={reason}
            onReason={onReason}
            onRun={onRun}
          />
        ) : null}

        <section aria-label={t("console.detail.decisionAria")} className="space-y-2">
          <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("console.detail.decision")}</h3>
          {needsReason ? (
            <label className="block text-xs">
              {t("console.detail.reason")}
              <Input value={reason} onChange={(e) => onReason(e.target.value)} placeholder={t("console.detail.reasonPlaceholder")} />
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
          {actions.length === 0 ? <p className="text-xs text-muted-foreground">{t("console.detail.noAction")}</p> : null}
          {supervised && canApprove ? <p className="text-xs text-muted-foreground">{t("console.detail.supervisedHint")}</p> : null}
          {message ? <ErrorState title={t("console.detail.refused")} message={message} /> : null}
        </section>

        <CustomerHistory query={context} />

        {/* The auditor's facts first, then the advisory opinion (spec 18 AC-09). */}
        <AuditChecklist query={auditor} />
        <SecondOpinionPanel caseId={c.id} />

        <section aria-label={t("console.detail.timeline")}>
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("console.detail.timeline")}</h3>
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
