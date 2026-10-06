import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, ChartColumn, Inbox, MessageSquareText } from "lucide-react";
import { HeroVisual } from "@/components/landing/hero-visual";
import { HowItWorks } from "@/components/landing/how-it-works";
import { JuryGuide } from "@/components/landing/jury-guide";
import { ProblemNumbers } from "@/components/landing/problem-numbers";
import { buttonVariants } from "@/components/ui/button";
import { getT } from "@/lib/i18n-server";

export async function generateMetadata(): Promise<Metadata> {
  const { t, locale } = await getT();
  const tagline = t("landing.meta.tagline");
  const description = t("landing.meta.description");
  return {
    metadataBase: new URL("https://nickoftime.salazarvalverdeai.com"),
    title: `Nick of Time · ${tagline}`,
    description,
    openGraph: {
      type: "website",
      siteName: "Nick of Time",
      locale: { es: "es_MX", pt: "pt_BR", en: "en_US" }[locale],
      title: `Nick of Time · ${tagline}`,
      description,
      // TODO(lead): OG IMAGE SLOT — add the 1200×630 image the lead is designing at apps/web/public/og/home.png.
      // The path is a placeholder until that file exists.
      images: [{ url: "/og/home.png", width: 1200, height: 630, alt: `Nick of Time — ${tagline}` }],
    },
  };
}

const CTAS = [
  { href: "/chat", label: "landing.hero.chat", hint: "landing.hero.chatHint", Icon: MessageSquareText, primary: true },
  { href: "/console", label: "landing.hero.console", hint: "landing.hero.consoleHint", Icon: Inbox, primary: false },
  { href: "/evaluation", label: "landing.hero.evaluation", hint: "landing.hero.evaluationHint", Icon: ChartColumn, primary: false },
] as const;

export default async function Home() {
  const { t } = await getT();
  return (
    <>
      <main id="main" className="mx-auto w-full max-w-7xl flex-1 space-y-20 px-4 py-10 sm:py-16">
        <section aria-labelledby="hero-title" className="grid items-center gap-10 lg:grid-cols-[1.2fr_1fr]">
          <div className="space-y-6">
            {/* Approved lockups (docs/brand, copied to public/brand): white wordmark on dark, dark wordmark on light. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/brand/logo-horizontal.svg" alt="Nick of Time" className="hidden h-24 w-auto sm:h-32 dark:block" />
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/brand/logo-horizontal-light.svg" alt="Nick of Time" className="h-24 w-auto sm:h-32 dark:hidden" />
            <h1 id="hero-title" className="text-4xl font-bold tracking-tight text-balance sm:text-5xl">
              {t("landing.meta.tagline")}
            </h1>
            <p className="max-w-xl text-lg text-muted-foreground">{t("landing.hero.lead")}</p>
            <nav aria-label={t("landing.hero.start")} className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
              {CTAS.map(({ href, label, hint, Icon, primary }) => (
                <Link
                  key={href}
                  href={href}
                  className={buttonVariants({
                    variant: primary ? "default" : "outline",
                    className: "h-auto justify-start gap-3 px-4 py-2.5 text-left",
                  })}
                >
                  <Icon aria-hidden="true" className="size-4" />
                  <span className="flex flex-col">
                    <span>{t(label)}</span>
                    <span className={`text-xs font-normal ${primary ? "text-primary-foreground" : "text-muted-foreground"}`}>
                      {t(hint)}
                    </span>
                  </span>
                  <ArrowRight aria-hidden="true" className="ml-auto size-4 sm:ml-2" />
                </Link>
              ))}
            </nav>
          </div>
          <div className="flex justify-center lg:justify-end">
            <HeroVisual />
          </div>
        </section>

        <ProblemNumbers />
        <HowItWorks />
        <JuryGuide />
      </main>
    </>
  );
}
