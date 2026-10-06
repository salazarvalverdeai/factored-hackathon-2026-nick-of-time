"use client";

import Link from "next/link";
import { useState } from "react";
import { PageShell } from "@/components/page-shell";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Timeline } from "@/components/timeline";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Textarea } from "@/components/ui/input";
import { ApiError, api } from "@/lib/api";
import { MESSAGES, fill } from "@/lib/mock/messages";
import { demoDateLabel } from "@/lib/demo-date";
import { DEMO_TODAY, statusLabel } from "@/lib/mock/store";
import type { Language, NotificationEntry } from "@/lib/types";
import { useQuery } from "@/lib/use-query";

/** The customer's case page: proof, not promises (ADR 0013). Never shows the score, policy ids or the transcript. */
export function CaseView({ id }: { id: string }) {
  const found = useQuery((a) => a.getCase(id), [id]);
  const notifications = useQuery((a) => a.getNotifications(id), [id]);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState("");
  const [email, setEmail] = useState("");
  const [link, setLink] = useState<{ token: string; deepLink: string } | null>(null);

  const title = `Case ${id}`;
  if (found.status === "loading") return <PageShell title={title} description="Your case, step by step."><LoadingState /></PageShell>;
  if (found.status === "error") {
    const { code, message } = found.error;
    return (
      <PageShell title={title} description="Your case, step by step.">
        {code === "NOT_FOUND" ? (
          <EmptyState title="We cannot find this case" hint="Check the link, or verify with the customer that owns it." />
        ) : (
          <ErrorState
            title={code === "SESSION_EXPIRED" ? "Your session expired" : "Verify your identity first"}
            message={message}
            action={
              <Link href="/chat" className="inline-flex h-7 items-center rounded-lg border px-2.5 text-sm hover:bg-muted">
                Go to the chat
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
      setError(e instanceof ApiError ? e.message : "unexpected error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <PageShell title={title} description="Your case, step by step. You do not need to call us to know where it stands.">
      <div className="grid gap-4 lg:grid-cols-[1fr_22rem]">
        <div className="min-w-0 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex flex-wrap items-center gap-2">
                Status <span data-slot="status-label" className="inline-flex h-5 items-center rounded-4xl bg-primary/15 px-2 text-xs font-medium text-violet-700 dark:text-violet-300">{c.status_label}</span>
              </CardTitle>
              <CardDescription>A person always closes the case.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div data-slot="countdown" className="rounded-lg border border-brand-amber/50 bg-brand-amber/5 p-3">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">Legal deadline</p>
                <p className="text-2xl font-semibold text-amber-700 dark:text-amber-400">{left === null ? "Pending" : left <= 0 ? "Due today" : `${left} day${left === 1 ? "" : "s"} left`}</p>
                <p>{c.credit_deadline ?? "Pending: a person will confirm it"}</p>
                <p className="text-xs text-muted-foreground">
                  Source: {c.deadline_source ?? "pending"}
                  {demoDate ? ` · ${demoDateLabel(demoDate, c.language)}` : ""}
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
                Request a call
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Timeline</CardTitle>
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
              <CardTitle>Add information</CardTitle>
              <CardDescription>The analyst sees it in your case right away.</CardDescription>
            </CardHeader>
            <CardContent>
              <form
                className="space-y-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  act(async () => {
                    await api.addCustomerInfo(id, info);
                    setInfo("");
                  }, "Thanks, we added it to your case.");
                }}
              >
                <Textarea value={info} onChange={(e) => setInfo(e.target.value)} aria-label="Additional information" placeholder="Anything that helps us review the charge…" />
                <Button type="submit" disabled={busy || !info.trim()}>
                  Send to the analyst
                </Button>
              </form>
            </CardContent>
          </Card>

          {feedback ? <p role="status" className="rounded-lg border border-brand-teal/40 bg-brand-teal/5 p-2 text-sm">{feedback}</p> : null}
          {error ? <ErrorState title="That did not work" message={error} /> : null}
        </div>

        <aside className="min-w-0 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>My notifications</CardTitle>
              <CardDescription>Every status change is logged here, even if a channel fails.</CardDescription>
            </CardHeader>
            <CardContent>
              {notifications.status === "ok" && notifications.data.length > 0 ? (
                <ul className="space-y-2 text-sm">
                  {notifications.data.map((n) => (
                    <NotificationItem key={n.id} n={n} lang={c.language} />
                  ))}
                </ul>
              ) : (
                <EmptyState title="No notifications yet" />
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Get updates</CardTitle>
              <CardDescription>Optional channels. They carry the status only, never your data.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              <div className="space-y-2">
                <p className="font-medium">Telegram {linked ? <span className="text-teal-700 dark:text-teal-300">· linked ✓</span> : null}</p>
                {!linked ? (
                  <>
                    <Button size="sm" disabled={busy} onClick={() => act(async () => setLink(await api.createTelegramLink(id)), "Link created: it works for 15 minutes.")}>
                      Get updates on Telegram
                    </Button>
                    {link ? (
                      <div className="space-y-2 rounded-lg border p-2 text-xs">
                        {live ? (
                          <a href={link.deepLink} target="_blank" rel="noreferrer" className="break-all underline">
                            Open Telegram and press Start
                          </a>
                        ) : (
                          <>
                            <Button size="xs" variant="outline" disabled={busy} onClick={() => act(() => api.simulateTelegramStart(id, link.token), "Telegram linked.")}>
                              Simulate “/start” in Telegram
                            </Button>
                          </>
                        )}
                      </div>
                    ) : null}
                  </>
                ) : null}
              </div>

              <div className="space-y-2">
                <p className="font-medium">E-mail {confirmedEmail ? <span className="text-teal-700 dark:text-teal-300">· confirmed ✓</span> : null}</p>
                {!confirmedEmail ? (
                  <form
                    className="flex gap-2"
                    onSubmit={(e) => {
                      e.preventDefault();
                      act(
                        () => api.confirmEmail(id, email.trim()),
                        live ? "We sent you a link. Open it to confirm your e-mail." : "E-mail confirmed.",
                      );
                    }}
                  >
                    <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" aria-label="E-mail address" required />
                    <Button type="submit" size="sm" disabled={busy}>
                      {live ? "Send link" : "Confirm"}
                    </Button>
                  </form>
                ) : null}
                <p className="text-xs text-muted-foreground">We write only to an address you type and confirm here.</p>
              </div>
            </CardContent>
          </Card>
        </aside>
      </div>
    </PageShell>
  );
}

function NotificationItem({ n, lang }: { n: NotificationEntry; lang: Language }) {
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
            {ch.channel === "in_app" ? "in-app" : ch.channel} {ch.delivered ? "✓" : "failed"}
          </span>
        ))}
      </span>
      <span className="mt-1 block text-xs text-muted-foreground">{new Date(n.at).toLocaleString()}</span>
    </li>
  );
}
