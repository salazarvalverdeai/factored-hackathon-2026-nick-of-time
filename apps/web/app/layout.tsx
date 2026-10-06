import type { Metadata } from "next";
import { JetBrains_Mono, Sora } from "next/font/google";
import "./globals.css";
import { I18nProvider } from "@/components/i18n-provider";
import { ThemeProvider } from "@/components/theme-provider";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { getLocale } from "@/lib/i18n-server";

const sora = Sora({
  variable: "--font-sora",
  subsets: ["latin"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  // "/" shows the default; every other route sets its own title in its segment: "<Page> · Nick of Time".
  title: { default: "Nick of Time", template: "%s · Nick of Time" },
  description: "Verified action. Before the deadline.",
};

export default async function RootLayout({ children }: LayoutProps<"/">) {
  // The UI language (spec 16 AC-06) comes from the selector's cookie, read per request: `<html lang>` is right on the
  // first byte. The agent's conversation language is the chat session's ES/PT choice, not this.
  const locale = await getLocale();
  return (
    <html
      lang={locale}
      suppressHydrationWarning
      className={`${sora.variable} ${jetbrainsMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false}>
          <I18nProvider locale={locale}>
            <SiteHeader />
            {children}
            <SiteFooter />
          </I18nProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
