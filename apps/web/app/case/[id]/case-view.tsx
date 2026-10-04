"use client";

import Link from "next/link";
import { useState } from "react";
import { StatusBadge } from "@/components/badges";
import { PageShell } from "@/components/page-shell";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Timeline } from "@/components/timeline";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Textarea } from "@/components/ui/input";
import { ApiError, api } from "@/lib/api";
import { formatDeadline } from "@/lib/format";
import { DEMO_TODAY, caseStatus, daysBetween } from "@/lib/mock/store";
import type { NotificationEntry } from "@/lib/types";
import { useMockState, useQuery } from "@/lib/use-query";

/** The customer's case page: proof, not promises (ADR 0013). Never shows the score, policy ids or the transcript. */
export function CaseView({ id }: { id: string }) {
  const found = useQuery((s) => s.getCase(id));
  const notifications = useQuery((s) => s.notificationsFor(id));
  const { telegram, emails } = useMockState();
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
  const status = caseStatus(c);
  const left = c.deadline.creditDeadline ? daysBetween(DEMO_TODAY, c.deadline.creditDeadline) : null;
  const linked = telegram[id]?.linked ?? false;
  const confirmedEmail = emails[id]?.confirmed ? emails[id].address : null;

  async function act(action: () => Promise<unknown>, done: string) {
    setBusy(true);
    setError(null);
    setFeedback(null);
    try {
      await action();
      setFeedback(done);
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
                Status <StatusBadge status={status} />
              </CardTitle>
              <CardDescription>A person always closes the case.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div data-slot="countdown" className="rounded-lg border p-3">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">Legal deadline</p>
                <p className="text-2xl font-semibold">{left === null ? "Pending" : left <= 0 ? "Due today" : `${left} day${left === 1 ? "" : "s"} left`}</p>
                <p>{formatDeadline(c.deadline)}</p>
                <p className="text-xs text-muted-foreground">Source: {c.deadline.deadlineSource} · demo date {DEMO_TODAY} [simulated]</p>
              </div>
              <Button disabled={busy} variant="outline" onClick={() => act(() => api.requestCall(id), "We registered your request: an analyst will call you.")}>
                Request a call
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Timeline</CardTitle>
            </CardHeader>
            <CardContent>
              <Timeline events={c.events} />
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

          {feedback ? <p role="status" className="rounded-lg border border-emerald-500/40 bg-emerald-500/5 p-2 text-sm">{feedback}</p> : null}
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
                    <NotificationItem key={n.id} n={n} />
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
                <p className="font-medium">Telegram {linked ? <span className="text-emerald-600 dark:text-emerald-400">· linked ✓</span> : null}</p>
                {!linked ? (
                  <>
                    <Button size="sm" disabled={busy} onClick={() => act(async () => setLink(await api.createTelegramLink(id)), "Link created: it works for 15 minutes.")}>
                      Get updates on Telegram
                    </Button>
                    {link ? (
                      <div className="space-y-2 rounded-lg border p-2 text-xs">
                        <p className="break-all">
                          Deep link [simulated]: <span className="font-mono">{link.deepLink}</span>
                        </p>
                        <Button size="xs" variant="outline" disabled={busy} onClick={() => act(() => api.simulateTelegramStart(id, link.token), "Telegram linked.")}>
                          Simulate “/start” in Telegram
                        </Button>
                      </div>
                    ) : null}
                  </>
                ) : null}
              </div>

              <div className="space-y-2">
                <p className="font-medium">E-mail {confirmedEmail ? <span className="text-emerald-600 dark:text-emerald-400">· {confirmedEmail} ✓</span> : null}</p>
                {!confirmedEmail ? (
                  <form
                    className="flex gap-2"
                    onSubmit={(e) => {
                      e.preventDefault();
                      act(() => api.confirmEmail(id, email.trim()), "E-mail confirmed.");
                    }}
                  >
                    <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" aria-label="E-mail address" required />
                    <Button type="submit" size="sm" disabled={busy}>
                      Confirm
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

function NotificationItem({ n }: { n: NotificationEntry }) {
  return (
    <li className="rounded-lg border p-2">
      <span className="flex items-center justify-between gap-2">
        <span className="font-medium">{n.title}</span>
        <StatusBadge status={n.status} />
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
