"use client";

// Start screen of demo mode (spec 07 §8, D-068, ADR 0026): name, language, country and a scenario. The visitor never
// picks or sends a customer id: the api chooses the customer from the scenario (spec 05 AC-16). The screen's chrome
// follows the UI locale (spec 16 AC-06); the conversation language stays an explicit ES/PT choice, preset to the UI
// locale when it is ES or PT, else Spanish.
import { useEffect, useState } from "react";
import { useLocale, useT } from "@/components/i18n-provider";
import { ErrorState, LoadingState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, api } from "@/lib/api";
import { LOCALE_NAMES } from "@/lib/i18n";
import { COUNTRIES, MAX_NAME_LENGTH, nameProblem, nameToSend } from "@/lib/demo";
import type { Language, Scenario } from "@/lib/types";

const AUTO = "auto";

export function Toggle({ pressed, onClick, children }: { pressed: boolean; onClick: () => void; children: React.ReactNode }) {
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

export function DemoStart({ title, onStarted }: { title: string; onStarted: (otp: string) => void }) {
  const t = useT();
  const { locale } = useLocale();
  const [name, setName] = useState("");
  // The conversation language: the UI locale when it is ES or PT, else Spanish; the visitor can still switch it.
  const [language, setLanguage] = useState<Language>(locale === "pt" ? "pt" : "es");
  // Demo type C needs a live session (today's date); the dataset scenarios keep the api's default, replay (#188).
  const [testCharge, setTestCharge] = useState(false);
  const [country, setCountry] = useState<(typeof COUNTRIES)[number] | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[] | null>(null);
  const [scenario, setScenario] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hint = nameProblem(name, locale);

  // The cards depend on the language (required) and the country (optional filter).
  useEffect(() => {
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
        setError(e instanceof ApiError ? e.message : t("chat.start.scenariosError"));
      },
    );
    return () => {
      alive = false;
    };
  }, [language, country, t]);

  async function start() {
    if (!scenario || hint) return;
    setBusy(true);
    setError(null);
    try {
      // The greeting uses the typed name, else the scenario's gold name; "assign me one" has none (spec 07 AC-07).
      const customerName = scenario === AUTO ? undefined : (scenarios?.find((s) => s.scenario_id === scenario)?.customer_name ?? undefined);
      onStarted(
        await api.startDemoSession({
          displayName: nameToSend(name),
          language,
          country: country ?? undefined,
          scenario,
          customerName,
          ...(testCharge ? { mode: "live" as const } : {}),
        }),
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("chat.verify.unexpected")); // a 422 shows the api's own message
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{t("chat.start.description")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <label className="block text-sm">
          {t("chat.start.name")}
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={MAX_NAME_LENGTH + 10}
            placeholder={t("chat.start.namePlaceholder")}
            aria-invalid={hint ? true : undefined}
            autoComplete="given-name"
          />
          {hint ? <span className="mt-1 block text-xs text-red-600 dark:text-red-400">{hint}</span> : null}
        </label>

        <fieldset className="space-y-1">
          <legend className="text-sm">{t("chat.start.language")}</legend>
          <div className="flex gap-2">
            <Toggle pressed={language === "es"} onClick={() => setLanguage("es")}>
              <span lang="es">{LOCALE_NAMES.es}</span>
            </Toggle>
            <Toggle pressed={language === "pt"} onClick={() => setLanguage("pt")}>
              <span lang="pt">{LOCALE_NAMES.pt}</span>
            </Toggle>
          </div>
        </fieldset>

        <fieldset className="space-y-1">
          <legend className="text-sm">{t("chat.start.country")}</legend>
          <div className="flex flex-wrap gap-2">
            <Toggle pressed={country === null} onClick={() => setCountry(null)}>
              {t("chat.start.anyCountry")}
            </Toggle>
            {COUNTRIES.map((c) => (
              <Toggle key={c} pressed={country === c} onClick={() => setCountry(c)}>
                {c}
              </Toggle>
            ))}
          </div>
        </fieldset>

        <fieldset className="space-y-2">
          <legend className="text-sm">{t("chat.start.scenario")}</legend>
          {scenarios === null ? <LoadingState label={t("chat.start.loadingScenarios")} /> : null}
          {scenarios ? (
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
                    <span className="block truncate text-xs text-muted-foreground">{s.customer_name ?? t("chat.start.demoCustomer")}</span>
                  </span>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {s.country} · {s.language.toUpperCase()}
                  </span>
                </button>
              ))}
              {scenarios.length === 0 && !error ? <p className="text-xs text-muted-foreground">{t("chat.start.noScenario")}</p> : null}
              <button
                type="button"
                onClick={() => setScenario(AUTO)}
                aria-pressed={scenario === AUTO}
                className="rounded-lg border p-2 text-left text-sm hover:bg-accent aria-pressed:border-foreground"
              >
                {t("chat.start.assign")}
                <span className="block text-xs text-muted-foreground">{t("chat.start.assignHint")}</span>
              </button>
            </div>
          ) : null}
        </fieldset>

        <fieldset className="space-y-1">
          <legend className="text-sm">{t("chat.start.what")}</legend>
          <div className="flex flex-wrap gap-2">
            <Toggle pressed={!testCharge} onClick={() => setTestCharge(false)}>
              {t("chat.start.fromScenario")}
            </Toggle>
            <Toggle pressed={testCharge} onClick={() => setTestCharge(true)}>
              {t("chat.start.testCharge")}
            </Toggle>
          </div>
          <p className="text-xs text-muted-foreground">
            {testCharge ? t("chat.start.testChargeHint") : t("chat.start.scenarioHint")}
          </p>
        </fieldset>

        <Button disabled={!scenario || Boolean(hint) || busy} onClick={start}>
          {t("chat.verify.sendCode")}
        </Button>
        {busy ? <LoadingState label={t("chat.verify.working")} /> : null}
        {error ? <ErrorState title={t("chat.verify.cannotContinue")} message={error} /> : null}
      </CardContent>
    </Card>
  );
}
