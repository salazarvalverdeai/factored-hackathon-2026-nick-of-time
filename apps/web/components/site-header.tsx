"use client";

import { Menu, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { useT } from "@/components/i18n-provider";
import { LanguageSelect } from "@/components/language-select";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import type { MessageKey } from "@/lib/i18n";

export const NAV: { href: string; key: MessageKey }[] = [
  { href: "/chat", key: "shell.nav.chat" },
  { href: "/console", key: "shell.nav.console" },
  { href: "/data", key: "shell.nav.data" },
  { href: "/evaluation", key: "shell.nav.evaluation" },
  { href: "/analytics", key: "shell.nav.analytics" },
  { href: "/agent", key: "shell.nav.agent" },
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

const LINK = "rounded-md px-2.5 py-1.5 text-muted-foreground hover:bg-accent hover:text-foreground aria-[current=page]:text-foreground";

/**
 * The site header (spec 16): logo, navigation, the ES · PT · EN selector (AC-06) and the theme toggle. From 1024 px the
 * links sit inline; below, a menu button opens them as a disclosure under the header (Escape closes it and focus goes
 * back to the button), and below 640 px the language selector moves into that menu too, so 390 px never clips a word.
 */
export function SiteHeader() {
  const t = useT();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [openedAt, setOpenedAt] = useState(pathname);
  const menuId = useId();
  const button = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);

  // A link press navigates: close the menu on the new page.
  if (open && openedAt !== pathname) {
    setOpen(false);
    setOpenedAt(pathname);
  }

  useEffect(() => {
    if (!open) return;
    panel.current?.querySelector<HTMLElement>("a,button")?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.preventDefault();
      setOpen(false);
      button.current?.focus();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  const links = (className: string) =>
    NAV.map((n) => (
      <Link
        key={n.href}
        href={n.href}
        aria-current={pathname === n.href || pathname.startsWith(`${n.href}/`) ? "page" : undefined}
        className={className}
      >
        {t(n.key)}
      </Link>
    ));

  return (
    <header className="sticky top-0 z-10 border-b bg-background/80 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-2 px-4 sm:gap-4">
        <Link href="/" aria-label={t("shell.home")} className="shrink-0">
          {/* Approved logo assets (docs/brand): symbol on phones, horizontal lockup from 640 px. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/brand/logo-symbol.svg" alt="" className="size-9 sm:hidden" />
          <Lockup />
        </Link>
        <nav aria-label={t("shell.nav.label")} className="hidden flex-1 gap-1 text-sm lg:flex">
          {links(`${LINK} whitespace-nowrap`)}
        </nav>
        <div className="ml-auto flex items-center gap-1 sm:gap-2">
          <LanguageSelect className="hidden sm:inline-flex" />
          <ThemeToggle />
          <Button
            ref={button}
            variant="ghost"
            size="icon"
            className="lg:hidden"
            aria-expanded={open}
            aria-controls={menuId}
            aria-label={open ? t("shell.nav.closeMenu") : t("shell.nav.openMenu")}
            onClick={() => {
              setOpenedAt(pathname);
              setOpen((o) => !o);
            }}
          >
            {open ? <X className="size-4" /> : <Menu className="size-4" />}
          </Button>
        </div>
      </div>
      <div id={menuId} ref={panel} hidden={!open} className="border-t lg:hidden">
        <nav aria-label={t("shell.nav.menu")} className="mx-auto grid max-w-7xl gap-1 px-4 py-3 text-sm">
          {links(`${LINK} block py-2`)}
        </nav>
        <div className="mx-auto max-w-7xl px-4 pb-3 sm:hidden">
          <LanguageSelect />
        </div>
      </div>
    </header>
  );
}
