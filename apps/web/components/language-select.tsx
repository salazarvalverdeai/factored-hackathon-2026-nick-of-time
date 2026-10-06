"use client";

// The ES · PT · EN selector (spec 16 AC-06): a group of three toggle buttons, the current one pressed. Tab reaches the
// group, arrow keys move between languages, Enter or Space picks one; the choice is announced in a polite live region.
// It changes the interface only: the agent still converses in ES or PT (spec 04).
import { type KeyboardEvent, useRef, useState } from "react";
import { useLocale, useT } from "@/components/i18n-provider";
import { LOCALES, LOCALE_NAMES, type Locale } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export function LanguageSelect({ className }: { className?: string }) {
  const t = useT();
  const { locale, setLocale } = useLocale();
  const [announce, setAnnounce] = useState("");
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);

  const pick = (l: Locale) => {
    if (l !== locale) setLocale(l);
    // Announced in the new language's own words, so a screen reader confirms the switch.
    setAnnounce(LOCALE_NAMES[l]);
  };

  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const i = buttons.current.findIndex((b) => b === document.activeElement);
    if (i < 0) return;
    const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    buttons.current[(i + step + LOCALES.length) % LOCALES.length]?.focus();
  };

  return (
    <div
      role="group"
      aria-label={t("shell.language.current", { name: LOCALE_NAMES[locale] })}
      onKeyDown={onKey}
      className={cn("inline-flex shrink-0 items-center rounded-md border p-0.5 text-xs", className)}
    >
      {LOCALES.map((l, i) => {
        const current = l === locale;
        return (
          <button
            key={l}
            ref={(el) => {
              buttons.current[i] = el;
            }}
            type="button"
            lang={l}
            aria-pressed={current}
            title={t("shell.language.switchTo", { name: LOCALE_NAMES[l] })}
            onClick={() => pick(l)}
            className={cn(
              "min-w-8 rounded px-1.5 py-1 font-medium uppercase outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
              current ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-accent hover:text-foreground",
            )}
          >
            <span aria-hidden="true">{l}</span>
            <span className="sr-only">{LOCALE_NAMES[l]}</span>
          </button>
        );
      })}
      <span role="status" aria-live="polite" className="sr-only">
        {announce ? t("shell.language.current", { name: announce }) : ""}
      </span>
    </div>
  );
}
