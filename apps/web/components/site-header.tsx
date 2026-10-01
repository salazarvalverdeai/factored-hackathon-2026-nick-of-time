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
        <Link href="/" className="font-semibold">
          Nick of Time
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
