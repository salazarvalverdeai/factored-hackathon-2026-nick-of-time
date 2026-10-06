"use client";

// The UI locale for client components (spec 16 AC-06). The root layout reads the cookie on the server and passes it
// here, so the first render already has the right language (no flash). `setLocale` writes the cookie, updates
// `<html lang>` and refreshes the server components.
import { useRouter } from "next/navigation";
import { createContext, type ReactNode, useCallback, useContext, useMemo, useState, useTransition } from "react";
import { LOCALE_COOKIE, LOCALE_MAX_AGE, type Locale, type Translate, translator } from "@/lib/i18n";

interface I18nValue {
  locale: Locale;
  t: Translate;
  setLocale: (next: Locale) => void;
  pending: boolean;
}

const I18nContext = createContext<I18nValue | null>(null);

export function I18nProvider({ locale: initial, children }: { locale: Locale; children: ReactNode }) {
  const router = useRouter();
  const [locale, setState] = useState<Locale>(initial);
  const [pending, startTransition] = useTransition();
  const setLocale = useCallback(
    (next: Locale) => {
      document.cookie = `${LOCALE_COOKIE}=${next}; path=/; max-age=${LOCALE_MAX_AGE}; samesite=lax`;
      document.documentElement.lang = next;
      setState(next);
      startTransition(() => router.refresh());
    },
    [router],
  );
  const value = useMemo(() => ({ locale, t: translator(locale), setLocale, pending }), [locale, setLocale, pending]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

function useI18n(): I18nValue {
  const v = useContext(I18nContext);
  if (!v) throw new Error("useT must be used inside <I18nProvider>");
  return v;
}

/** `const t = useT(); t("header.nav.chat")`. */
export function useT(): Translate {
  return useI18n().t;
}

/** The UI locale and its setter (the header selector; pages that format dates and numbers). */
export function useLocale(): Pick<I18nValue, "locale" | "setLocale" | "pending"> {
  const { locale, setLocale, pending } = useI18n();
  return { locale, setLocale, pending };
}
