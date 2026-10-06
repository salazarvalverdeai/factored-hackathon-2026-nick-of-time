"use client";

import Link from "next/link";
import { useState } from "react";
import { useLocale, useT } from "@/components/i18n-provider";
import { PageShell } from "@/components/page-shell";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Timeline } from "@/components/timeline";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Textarea } from "@/components/ui/input";
import { ApiError, api } from "@/lib/api";
import { channelLinksOffered } from "@/lib/demo";
import { MESSAGES, fill } from "@/lib/mock/messages";
import { formatDateTime } from "@/lib/handoff-labels";
import { formatDay } from "@/lib/i18n";
import { DEMO_TODAY, statusLabel } from "@/lib/mock/store";
import type { Language, NotificationEntry } from "@/lib/types";
import { useQuery } from "@/lib/use-query";

/** The customer's case page: proof, not promises (ADR 0013). Never shows the score, policy ids or the transcript.
 *  The page's own words follow the UI language (spec 16 AC-06); status labels, notification titles and the call
 *  message come from the api or the agent in the case's language and are shown as they are. */
export function CaseView({ id }: { id: string }) {
  const t = useT();
  const { locale } = useLocale();
  const found = useQuery((a) => a.getCase(id), [id]);
  const notifications = useQuery((a) => a.getNotifications(id), [id]);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState("");
  const [email, setEmail] = useState("");
  const [link, setLink] = useState<{ token: string; deepLink: string } | null>(null);

  const title = t("caseView.title", { id });
  if (found.status === "loading") {
    return (
      <PageShell title={title} description={t("caseView.description")}>
        <LoadingState />
      </PageShell>
    );
  }
  if (found.status === "error") {
    const { code, message } = found.error;
    return (
      <PageShell title={title} description={t("caseView.description")}>
        {code === "NOT_FOUND" ? (
          <EmptyState title={t("caseView.notFound")} hint={t("caseView.notFoundHint")} />
        ) : (
          <ErrorState
            title={code === "SESSION_EXPIRED" ? t("caseView.sessionExpired") : t("caseView.verifyFirst")}
            message={message}
            action={
              <Link href="/chat" className="inline-flex h-7 items-center rounded-lg border px-2.5 text-sm hover:bg-muted">
                {t("caseView.goToChat")}
              </Link>
            }
          />
        )}
      </PageShell>
    );
  }

  const c = found.data;
  const left = c.deadline_countdown_days;
  const linked = c.channels.telegram;
  const confirmedEmail = c.channels.email;
  const live = api.mode === "live";
  // The mock api runs on the frozen demo date; the live api sends no date for this page, so nothing is invented there.
  const demoDate = c.mode === "live" || live ? null : DEMO_TODAY;

  /** Runs an action; the feedback is the text the action returns, or `done`. */
  async function act(action: () => Promise<unknown>, done = "") {
    setBusy(true);
    setError(null);
    setFeedback(null);
    try {
      const result = await action();
      setFeedback(typeof result === "string" ? result : done);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("caseView.unexpectedError"));
    } finally {
      setBusy(false);
    }
  }

  const countdownText =
    left === null
      ? t("caseView.pending")
      : left <= 0
        ? t("ui.time.dueToday")
        : t(left === 1 ? "ui.time.daysLeft.one" : "ui.time.daysLeft.other", { n: left });

  return (
    <PageShell title={title} description={t("caseView.descriptionLong")}>
      <div className="grid gap-4 lg:grid-cols-[1fr_22rem]">
        <div className="min-w-0 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex flex-wrap items-center gap-2">
                {t("caseView.status")} <span data-slot="status-label" className="inline-flex h-5 items-center rounded-4xl bg-primary/15 px-2 text-xs font-medium text-violet-700 dark:text-violet-300">{c.status_label}</span>
              </CardTitle>
              <CardDescription>{t("caseView.personCloses")}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div data-slot="countdown" className="rounded-lg border border-brand-amber/50 bg-brand-amber/5 p-3">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">{t("caseView.legalDeadline")}</p>
                <p className="text-2xl font-semibold text-amber-700 dark:text-amber-400">{countdownText}</p>
                <p>{c.credit_deadline ?? t("caseView.creditPending")}</p>
                <p className="text-xs text-muted-foreground">
                  {t("caseView.source", { source: c.deadline_source ?? t("caseView.sourcePending") })}
                  {demoDate ? ` · ${t("caseView.demoDate", { date: formatDay(locale, demoDate, { month: "long" }) })}` : ""}
                </p>
              </div>
              <Button disabled={busy} variant="outline" onClick={() =>
                  act(async () => {
                    const result = await api.requestCall(id);
                    // messages.yaml connect.requested*: the date comes from the tool (D-008), never computed here.
                    return result.expected_contact_by
                      ? fill(MESSAGES.connect.requested, c.language, { expected_contact_by: result.expected_contact_by })
                      : MESSAGES.connect.requested_no_window[c.language];
                  })
                }>
                {t("caseView.requestCall")}
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t("caseView.timeline")}</CardTitle>
            </CardHeader>
            <CardContent>
              <Timeline
                events={c.timeline.map((e) => ({
                  id: e.event_id,
                  at: e.created_at,
                  type: e.type,
                  badge: <span className="inline-flex h-5 items-center rounded-4xl bg-muted px-2 text-xs font-medium text-muted-foreground">{e.status_label}</span>,
                }))}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t("caseView.addInfo.title")}</CardTitle>
              <CardDescription>{t("caseView.addInfo.description")}</CardDescription>
            </CardHeader>
            <CardContent>
              <form
                className="space-y-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  act(async () => {
                    await api.addCustomerInfo(id, info);
                    setInfo("");
                  }, t("caseView.addInfo.added"));
                }}
              >
                <Textarea value={info} onChange={(e) => setInfo(e.target.value)} aria-label={t("caseView.addInfo.aria")} placeholder={t("caseView.addInfo.placeholder")} />
                <Button type="submit" disabled={busy || !info.trim()}>
                  {t("caseView.addInfo.send")}
                </Button>
              </form>
            </CardContent>
          </Card>

          {feedback ? <p role="status" className="rounded-lg border border-brand-teal/40 bg-brand-teal/5 p-2 text-sm">{feedback}</p> : null}
          {error ? <ErrorState title={t("caseView.didNotWork")} message={error} /> : null}
        </div>

        <aside className="min-w-0 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>{t("caseView.notifications.title")}</CardTitle>
              <CardDescription>{t("caseView.notifications.description")}</CardDescription>
            </CardHeader>
            <CardContent>
              {notifications.status === "ok" && notifications.data.length > 0 ? (
                <ul className="space-y-2 text-sm">
                  {notifications.data.map((n) => (
                    <NotificationItem key={n.id} n={n} lang={c.language} />
                  ))}
                </ul>
              ) : (
                <EmptyState title={t("caseView.notifications.empty")} />
              )}
            </CardContent>
          </Card>

          {/* spec 07 §8, spec 05 AC-16: no Telegram or e-mail in a demo session (the link routes answer 403). */}
          {!channelLinksOffered(api.mode) ? (
            <p className="rounded-lg border p-3 text-sm text-muted-foreground">{t("caseView.channelsOff")}</p>
          ) : (
          <Card>
            <CardHeader>
              <CardTitle>{t("caseView.updates.title")}</CardTitle>
              <CardDescription>{t("caseView.updates.description")}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              <div className="space-y-2">
                <p className="font-medium">
                  {t("caseView.telegram.name")}{" "}
                  {linked ? <span className="text-teal-700 dark:text-teal-300">{t("caseView.telegram.linked")}</span> : null}
                </p>
                {!linked ? (
                  <>
                    <Button size="sm" disabled={busy} onClick={() => act(async () => setLink(await api.createTelegramLink(id)), t("caseView.telegram.linkCreated"))}>
                      {t("caseView.telegram.get")}
                    </Button>
                    {link ? (
                      <div className="space-y-2 rounded-lg border p-2 text-xs">
                        {live ? (
                          <a href={link.deepLink} target="_blank" rel="noreferrer" className="break-all underline">
                            {t("caseView.telegram.open")}
                          </a>
                        ) : (
                          <>
                            <Button size="xs" variant="outline" disabled={busy} onClick={() => act(() => api.simulateTelegramStart(id, link.token), t("caseView.telegram.done"))}>
                              {t("caseView.telegram.simulate")}
                            </Button>
                          </>
                        )}
                      </div>
                    ) : null}
                  </>
                ) : null}
              </div>

              <div className="space-y-2">
                <p className="font-medium">
                  {t("caseView.email.name")}{" "}
                  {confirmedEmail ? <span className="text-teal-700 dark:text-teal-300">{t("caseView.email.confirmed")}</span> : null}
                </p>
                {!confirmedEmail ? (
                  <form
                    className="flex gap-2"
                    onSubmit={(e) => {
                      e.preventDefault();
                      act(() => api.confirmEmail(id, email.trim()), live ? t("caseView.email.sentLink") : t("caseView.email.done"));
                    }}
                  >
                    <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder={t("caseView.email.placeholder")} aria-label={t("caseView.email.aria")} required />
                    <Button type="submit" size="sm" disabled={busy}>
                      {live ? t("caseView.email.sendLink") : t("caseView.email.confirm")}
                    </Button>
                  </form>
                ) : null}
                <p className="text-xs text-muted-foreground">{t("caseView.email.note")}</p>
              </div>
            </CardContent>
          </Card>
          )}
        </aside>
      </div>
    </PageShell>
  );
}

/** One entry of the notification log. Its title and status come from the api in the case's language (not translated);
 *  only the channel chips and the date follow the UI language. */
function NotificationItem({ n, lang }: { n: NotificationEntry; lang: Language }) {
  const t = useT();
  const { locale } = useLocale();
  return (
    <li className="rounded-lg border p-2">
      <span className="flex items-center justify-between gap-2">
        <span className="font-medium">{n.title}</span>
        <span className="inline-flex h-5 items-center rounded-4xl bg-muted px-2 text-xs font-medium text-muted-foreground">{statusLabel(n.status, lang)}</span>
      </span>
      <span className="mt-1 flex flex-wrap gap-1.5 text-xs">
        {n.channels.map((ch) => (
          <span
            key={ch.channel}
            className={`rounded-4xl px-2 py-0.5 ${ch.delivered ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400" : "bg-red-500/15 text-red-700 dark:text-red-400"}`}
          >
            {ch.channel === "in_app" ? t("caseView.notifications.inApp") : ch.channel} {ch.delivered ? "✓" : t("caseView.notifications.failed")}
          </span>
        ))}
      </span>
      <span className="mt-1 block text-xs text-muted-foreground">{formatDateTime(locale, n.at)}</span>
    </li>
  );
}
