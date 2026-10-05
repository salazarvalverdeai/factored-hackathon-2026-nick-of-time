/**
 * HERO VISUAL SLOT — the lead is designing the hero visual of the home page.
 *
 * Replace the body of `HeroVisual` with it; the home page (`app/page.tsx`) already places this component beside the
 * lockup, the tagline and the calls to action, and hides nothing else when it changes. Keep it decorative
 * (`aria-hidden`), calm and precise per docs/brand/BRAND.md: no glow, beams or dense star fields, and never a redrawn
 * mark (use the SVGs in `public/brand/`). Until then it shows the approved symbol on a brand surface.
 */
export function HeroVisual() {
  return (
    <div
      data-slot="hero-visual"
      aria-hidden="true"
      className="relative flex aspect-square w-full max-w-sm items-center justify-center rounded-2xl border bg-card"
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/brand/logo-symbol.svg" alt="" className="w-1/2" />
    </div>
  );
}
