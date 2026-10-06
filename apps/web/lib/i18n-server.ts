// Server components only: the request's UI locale from the cookie the header selector writes (spec 16 AC-06).
// Reading the cookie renders the route per request, so `<html lang>` and every server string are right on the first
// byte: no flash of the wrong language.
import { cookies } from "next/headers";
import { LOCALE_COOKIE, type Locale, parseLocale, type Translate, translator } from "@/lib/i18n";

export async function getLocale(): Promise<Locale> {
  return parseLocale((await cookies()).get(LOCALE_COOKIE)?.value);
}

/** The translate function and the locale for a server component: `const { t, locale } = await getT();`. */
export async function getT(): Promise<{ t: Translate; locale: Locale }> {
  const locale = await getLocale();
  return { t: translator(locale), locale };
}
