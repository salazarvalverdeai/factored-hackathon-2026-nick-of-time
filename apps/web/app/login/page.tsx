"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { PageShell } from "@/components/page-shell";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, api } from "@/lib/api";
import { useMounted, useSession } from "@/lib/use-query";

/** Analyst login (spec 08). Mock accounts in mock mode; Amazon Cognito in live mode (ADR 0017). */
export default function LoginPage() {
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
      setError(err instanceof ApiError ? err.message : "unexpected error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <PageShell title="Analyst login" description="Sign in to see the case inbox. Every action you take is audited with your user.">
      <Card className="mx-auto max-w-sm">
        <CardHeader>
          <CardTitle>Sign in</CardTitle>
          <CardDescription>
            {api.mode === "mock"
              ? "Local test mode. Accounts: freddy, gianmarco, diego, judge, with any password."
              : "Use your analyst account (Amazon Cognito). Every action you take is recorded with your user."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {mounted && analystSession ? (
            <p className="mb-3 text-sm">
              Signed in as <b>{analystSession.displayName}</b>.{" "}
              <Link href="/console" className="underline">
                Go to the console
              </Link>
            </p>
          ) : null}
          <form onSubmit={submit} className="space-y-3">
            <label className="block text-sm">
              User
              <Input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required />
            </label>
            <label className="block text-sm">
              Password
              <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
            </label>
            {error ? <ErrorState title="Cannot sign in" message={error} /> : null}
            <Button type="submit" disabled={busy} className="w-full">
              {busy ? "Signing in…" : "Sign in"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </PageShell>
  );
}
