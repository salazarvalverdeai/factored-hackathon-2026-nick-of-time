import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, ChartColumn, Inbox, MessageSquareText } from "lucide-react";
import { HeroVisual } from "@/components/landing/hero-visual";
import { HowItWorks } from "@/components/landing/how-it-works";
import { JuryGuide } from "@/components/landing/jury-guide";
import { ProblemNumbers } from "@/components/landing/problem-numbers";
import { buttonVariants } from "@/components/ui/button";

const TAGLINE = "Verified action. Before the deadline.";
const DESCRIPTION =
  "Card dispute intake for a synthetic LATAM bank, in Spanish and Portuguese. The LLM understands, the rules decide, the tools act, verification confirms and a person closes the case.";

export const metadata: Metadata = {
  metadataBase: new URL("https://nickoftime.salazarvalverdeai.com"),
  title: `Nick of Time · ${TAGLINE}`,
  description: DESCRIPTION,
  openGraph: {
    type: "website",
    siteName: "Nick of Time",
    title: `Nick of Time · ${TAGLINE}`,
    description: DESCRIPTION,
    // TODO(lead): OG IMAGE SLOT — add the 1200×630 image the lead is designing at apps/web/public/og/home.png.
    // The path is a placeholder until that file exists.
    images: [{ url: "/og/home.png", width: 1200, height: 630, alt: `Nick of Time — ${TAGLINE}` }],
  },
};

const CTAS = [
  {
    href: "/chat",
    label: "Try it as a customer",
    hint: "Report a charge in Spanish or Portuguese",
    Icon: MessageSquareText,
    primary: true,
  },
  { href: "/console", label: "Open the analyst console", hint: "Handoff cards, actions and audit", Icon: Inbox, primary: false },
  { href: "/evaluation", label: "See the evaluation", hint: "How we know it works", Icon: ChartColumn, primary: false },
] as const;

export default function Home() {
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
              {TAGLINE}
            </h1>
            <p className="max-w-xl text-lg text-muted-foreground">
              A customer reports a card charge they do not recognize, in Spanish or Portuguese. Nick of Time finds their own transaction, lets
              the rules decide whether to block the card, opens a case, reports each action only once it is verified and states the
              country&apos;s legal deadline. A person always closes the case.
            </p>
            <nav aria-label="Start here" className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
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
                    <span>{label}</span>
                    <span className={`text-xs font-normal ${primary ? "text-primary-foreground/80" : "text-muted-foreground"}`}>
                      {hint}
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
      <footer className="mx-auto w-full max-w-7xl border-t px-4 py-6 text-xs text-muted-foreground">
        <p>
          Factored AI &amp; Data Hackathon 2026 · workflow W3, card dispute intake. The bank, its customers and its transactions are
          synthetic. Labels: <span className="font-mono">[data]</span> from the dataset, <span className="font-mono">[external]</span> from an
          official source, <span className="font-mono">[assumption]</span> stated by the team, <span className="font-mono">[simulated]</span>{" "}
          produced by the demo or the evaluation.
        </p>
      </footer>
    </>
  );
}
