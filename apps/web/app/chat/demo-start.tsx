"use client";

// Start screen of demo mode (spec 07 §8, D-068, ADR 0026): name, language, country and a scenario. The visitor never
// picks or sends a customer id: the api chooses the customer from the scenario (spec 05 AC-16).
import { useEffect, useState } from "react";
import { ErrorState, LoadingState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, api } from "@/lib/api";
import { COUNTRIES, MAX_NAME_LENGTH, nameProblem, nameToSend } from "@/lib/demo";
import type { Language, Scenario } from "@/lib/types";

const AUTO = "auto";

function Toggle({ pressed, onClick, children }: { pressed: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={pressed}
      className="inline-flex h-8 items-center rounded-lg border px-3 text-sm hover:bg-accent aria-pressed:border-foreground aria-pressed:bg-accent"
    >
      {children}
    </button>
  );
}

export function DemoStart({ onStarted }: { onStarted: (otp: string) => void }) {
  const [name, setName] = useState("");
  const [language, setLanguage] = useState<Language | null>(null);
  const [country, setCountry] = useState<(typeof COUNTRIES)[number] | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[] | null>(null);
  const [scenario, setScenario] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hint = nameProblem(name);

  // The cards depend on the language (required) and the country (optional filter).
  useEffect(() => {
    if (!language) return;
    let alive = true;
    api.listScenarios({ language, ...(country ? { country } : {}) }).then(
      (list) => {
        if (!alive) return;
        setScenarios(list);
        setScenario((current) => (current === AUTO || list.some((s) => s.scenario_id === current) ? current : null));
        setError(null);
      },
      (e: unknown) => {
        if (!alive) return;
        setScenarios([]);
        setError(e instanceof ApiError ? e.message : "Could not load the scenarios.");
      },
    );
    return () => {
      alive = false;
    };
  }, [language, country]);

  async function start() {
    if (!language || !scenario || hint) return;
    setBusy(true);
    setError(null);
    try {
      onStarted(await api.startDemoSession({ displayName: nameToSend(name), language, country: country ?? undefined, scenario }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "unexpected error"); // a 422 shows the api's own message
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>1 · Start a demo [simulated]</CardTitle>
        <CardDescription>
          Pick a language and a scenario. The customer is simulated and chosen for you: you never type a customer id.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <label className="block text-sm">
          Your name (optional)
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={MAX_NAME_LENGTH + 10}
            placeholder="How should the agent greet you?"
            aria-invalid={hint ? true : undefined}
            autoComplete="given-name"
          />
          {hint ? <span className="mt-1 block text-xs text-red-600 dark:text-red-400">{hint}</span> : null}
        </label>

        <fieldset className="space-y-1">
          <legend className="text-sm">Language (required)</legend>
          <div className="flex gap-2">
            <Toggle pressed={language === "es"} onClick={() => setLanguage("es")}>
              Español
            </Toggle>
            <Toggle pressed={language === "pt"} onClick={() => setLanguage("pt")}>
              Português
            </Toggle>
          </div>
        </fieldset>

        <fieldset className="space-y-1">
          <legend className="text-sm">Country (optional)</legend>
          <div className="flex flex-wrap gap-2">
            <Toggle pressed={country === null} onClick={() => setCountry(null)}>
              Any
            </Toggle>
            {COUNTRIES.map((c) => (
              <Toggle key={c} pressed={country === c} onClick={() => setCountry(c)}>
                {c}
              </Toggle>
            ))}
          </div>
        </fieldset>

        <fieldset className="space-y-2">
          <legend className="text-sm">Scenario</legend>
          {!language ? <p className="text-xs text-muted-foreground">Choose a language to see the scenarios.</p> : null}
          {language && scenarios === null ? <LoadingState label="Loading scenarios…" /> : null}
          {language && scenarios ? (
            <div className="grid gap-2">
              {scenarios.map((s) => (
                <button
                  key={s.scenario_id}
                  type="button"
                  onClick={() => setScenario(s.scenario_id)}
                  aria-pressed={scenario === s.scenario_id}
                  className="flex w-full items-center justify-between gap-2 rounded-lg border p-2 text-left text-sm hover:bg-accent aria-pressed:border-foreground"
                >
                  <span className="min-w-0">
                    <span className="block truncate">{s.title}</span>
                    <span className="block truncate text-xs text-muted-foreground">{s.customer_name ?? "Demo customer"}</span>
                  </span>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {s.country} · {s.language.toUpperCase()}
                  </span>
                </button>
              ))}
              {scenarios.length === 0 && !error ? <p className="text-xs text-muted-foreground">No scenario for this country in that language. Try another country, or let us assign one.</p> : null}
              <button
                type="button"
                onClick={() => setScenario(AUTO)}
                aria-pressed={scenario === AUTO}
                className="rounded-lg border p-2 text-left text-sm hover:bg-accent aria-pressed:border-foreground"
              >
                Assign me one
                <span className="block text-xs text-muted-foreground">Random within the country, in your language when possible.</span>
              </button>
            </div>
          ) : null}
        </fieldset>

        <Button disabled={!language || !scenario || Boolean(hint) || busy} onClick={start}>
          Send me a code
        </Button>
        {busy ? <LoadingState label="Working…" /> : null}
        {error ? <ErrorState title="Cannot continue" message={error} /> : null}
      </CardContent>
    </Card>
  );
}
