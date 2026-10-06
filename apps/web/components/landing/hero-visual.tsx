/**
 * HERO VISUAL SLOT — the lead is designing the hero visual of the home page.
 *
 * Replace the body of `HeroVisual` with it; the home page (`app/page.tsx`) already places this component beside the
 * lockup, the tagline and the calls to action, and hides nothing else when it changes. Keep it decorative
 * (`aria-hidden`), calm and precise per docs/brand/BRAND.md: no glow, beams or dense star fields, and never a redrawn
 * mark (use the SVGs in `public/brand/`). Until then it shows a calm card with the five-step summary (no product screenshot of the verified receipt exists in the repo yet).
 */
const STEPS = [
  ["Understands", "Spanish or Portuguese, in the customer's words"],
  ["Rules decide", "Zone, block and legal deadline from the policy file"],
  ["Tools act", "Only on the session's own customer"],
  ["Verification confirms", "Reported only once it is read back"],
  ["A person closes", "Provisional credit is always a human decision"],
] as const;

export function HeroVisual() {
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
              <span className="block font-medium">{title}</span>
              <span className="block text-muted-foreground">{text}</span>
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
