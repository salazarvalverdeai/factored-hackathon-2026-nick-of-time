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

// The horizontal lockup's 1400 × 520 viewBox has the mark and the wordmark in its upper part and empty space below,
// so at header height the whole file drew the wordmark at about 9 px and the tagline at about 3 px. The header shows
// the approved file unchanged, cropped to the mark and the wordmark (viewBox x 56–1140, y 50–328), and clips the
// tagline (x ≥ 400, y ≥ 280), which no header height can make legible. Margins leave room for Sora when installed.
const CROP = { x: 56, y: 50, width: 1084, height: 278 } as const;
const VIEW = { width: 1400, height: 520 } as const;
const TAGLINE = { x: 400, y: 280 } as const;
const pct = (n: number) => `${(n * 100).toFixed(3)}%`;
const LOCKUP_STYLE = {
  width: pct(VIEW.width / CROP.width),
  height: pct(VIEW.height / CROP.height),
  left: pct(-CROP.x / CROP.width),
  top: pct(-CROP.y / CROP.height),
  clipPath: `polygon(0 0, 100% 0, 100% ${pct(TAGLINE.y / VIEW.height)}, ${pct(TAGLINE.x / VIEW.width)} ${pct(
    TAGLINE.y / VIEW.height,
  )}, ${pct(TAGLINE.x / VIEW.width)} 100%, 0 100%)`,
} as const;

function Lockup() {
  // The dark lockup has white text, the light one dark text.
  return (
    <span className="relative hidden h-10 overflow-hidden sm:block lg:h-11" style={{ aspectRatio: `${CROP.width} / ${CROP.height}` }}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/brand/logo-horizontal.svg" alt="" className="absolute hidden max-w-none dark:block" style={LOCKUP_STYLE} />
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/brand/logo-horizontal-light.svg" alt="" className="absolute block max-w-none dark:hidden" style={LOCKUP_STYLE} />
    </span>
  );
}

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-10 border-b bg-background/80 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-4 px-4">
        <Link href="/" aria-label="Nick of Time" className="shrink-0">
          {/* Approved logo assets (docs/brand): symbol on phones, horizontal lockup from 640 px. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/brand/logo-symbol.svg" alt="" className="size-9 sm:hidden" />
          <Lockup />
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
