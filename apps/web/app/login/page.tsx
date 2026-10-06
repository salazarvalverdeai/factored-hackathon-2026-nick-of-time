"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useT } from "@/components/i18n-provider";
import { PageShell } from "@/components/page-shell";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, api } from "@/lib/api";
import { useMounted, useSession } from "@/lib/use-query";

/** Analyst login (spec 08), in the UI language (spec 16 AC-06). Mock accounts in mock mode; Amazon Cognito in live mode (ADR 0017). */
export default function LoginPage() {
  const t = useT();
  const router = useRouter();
  const mounted = useMounted();
  const { analystSession } = useSession();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.analystLogin(username, password);
      router.push("/console");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("login.unexpectedError"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <PageShell title={t("login.title")} description={t("login.description")}>
      <Card className="mx-auto max-w-sm">
        <CardHeader>
          <CardTitle>{t("login.card")}</CardTitle>
          <CardDescription>
            {api.mode === "mock" ? t("login.mockHint", { accounts: "freddy, gianmarco, diego, judge" }) : t("login.liveHint")}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {mounted && analystSession ? (
            <p className="mb-3 text-sm">
              {t("login.signedInAs", { name: analystSession.displayName })}{" "}
              <Link href="/console" className="underline">
                {t("login.goToConsole")}
              </Link>
            </p>
          ) : null}
          <form onSubmit={submit} className="space-y-3">
            <label className="block text-sm">
              {t("login.user")}
              <Input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required />
            </label>
            <label className="block text-sm">
              {t("login.password")}
              <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
            </label>
            {error ? <ErrorState title={t("login.cannotSignIn")} message={error} /> : null}
            <Button type="submit" disabled={busy} className="w-full">
              {busy ? t("login.signingIn") : t("login.submit")}
            </Button>
          </form>
        </CardContent>
      </Card>
    </PageShell>
  );
}
