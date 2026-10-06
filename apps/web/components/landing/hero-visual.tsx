/**
 * HERO VISUAL SLOT — the lead is designing the hero visual of the home page.
 *
 * Replace the body of `HeroVisual` with it; the home page (`app/page.tsx`) already places this component beside the
 * lockup, the tagline and the calls to action, and hides nothing else when it changes. Keep it decorative
 * (`aria-hidden`), calm and precise per docs/brand/BRAND.md: no glow, beams or dense star fields, and never a redrawn
 * mark (use the SVGs in `public/brand/`). Until then it shows a calm card with the five-step summary (no product screenshot of the verified receipt exists in the repo yet).
 */
import { getT } from "@/lib/i18n-server";

const STEPS = [
  ["landing.visual.s1", "landing.visual.s1Text"],
  ["landing.visual.s2", "landing.visual.s2Text"],
  ["landing.visual.s3", "landing.visual.s3Text"],
  ["landing.visual.s4", "landing.visual.s4Text"],
  ["landing.visual.s5", "landing.visual.s5Text"],
] as const;

export async function HeroVisual() {
  const { t } = await getT();
  return (
    <div data-slot="hero-visual" aria-hidden="true" className="w-full max-w-sm space-y-4 rounded-2xl border bg-card p-6">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/brand/logo-symbol.svg" alt="" className="h-10 w-auto" />
      <ol className="space-y-3">
        {STEPS.map(([title, text], i) => (
          <li key={title} className="flex gap-3">
            <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full border font-mono text-xs text-muted-foreground">
              {i + 1}
            </span>
            <span className="text-sm">
              <span className="block font-medium">{t(title)}</span>
              <span className="block text-muted-foreground">{t(text)}</span>
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
