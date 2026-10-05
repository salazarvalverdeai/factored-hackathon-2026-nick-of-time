import Link from "next/link";
import { ThemeToggle } from "@/components/theme-toggle";

export const NAV = [
  { href: "/chat", label: "Chat" },
  { href: "/console", label: "Console" },
  { href: "/data", label: "Data" },
  { href: "/evaluation", label: "Evaluation" },
  { href: "/analytics", label: "Analytics" },
  { href: "/agent", label: "Agent" },
];

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-10 border-b bg-background/80 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-4 px-4">
        <Link href="/" aria-label="Nick of Time" className="shrink-0">
          {/* Approved logo assets (docs/brand): symbol on phones, horizontal lockup from 640 px; the dark lockup has white text, the light one dark text. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/brand/logo-symbol.svg" alt="Nick of Time" className="size-8 sm:hidden" />
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/brand/logo-horizontal.svg" alt="Nick of Time" className="hidden h-12 w-auto sm:dark:block" />
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/brand/logo-horizontal-light.svg" alt="Nick of Time" className="hidden h-12 w-auto sm:block sm:dark:hidden" />
        </Link>
        <nav className="flex flex-1 gap-1 overflow-x-auto text-sm">
          {NAV.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              className="rounded-md px-2.5 py-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              {n.label}
            </Link>
          ))}
        </nav>
        <ThemeToggle />
      </div>
    </header>
  );
}
