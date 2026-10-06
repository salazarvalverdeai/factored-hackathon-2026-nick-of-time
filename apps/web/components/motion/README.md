# Motion kit

Small, typed motion parts for the web app: charts that grow, lines that draw, diagrams that walk, figures that count.
Import the components from `@/components/motion` and the plain data and helpers (`part`, `lift`, `MOTION`,
`staggerDelay`, `fitStep`, `growTarget`, `walkSchedule`) from `@/lib/motion`: the kit is a `"use client"` module, and a
constant or function exported by it reaches a server component as a client reference, not as its value. No new dependency: `motion/react` (for `useReducedMotion` and `useInView`) plus CSS.

## Rules every part follows
- **Once, on entering the viewport.** A part plays the first time it is seen, never again on scroll.
- **Short and calm.** At most 600 ms each and 1.5 s for a whole sequence, ease-out (`cubic-bezier(0.22, 1, 0.36, 1)`), no
  bounce or overshoot, per the brand voice ([BRAND.md](../../../../docs/brand/BRAND.md)). Timings: `MOTION` in `lib/motion.ts`,
  mirrored in `motion.css` (a test checks both).
- **Reduced motion means nothing moves.** With `prefers-reduced-motion: reduce` every part renders its final state: the
  head script never sets `data-motion-ok` on `<html>`, `motion.css` only applies under `no-preference`, and each component
  reads `useReducedMotion()` and goes straight to its end state. The same holds with no JavaScript, in print, and if the app
  never hydrates (the head script's 4 s safety timer turns motion off).
- **No layout shift.** Only `transform`, `opacity` and `stroke-dashoffset` animate. Sizes are set from the first frame
  (a bar is drawn at its full width and scaled from 0), so the space is reserved and nothing pushes the page.
- **Keyboard access unchanged.** No wrapper takes focus, every prop (`tabIndex`, `role`, `aria-label`, pointer and focus
  handlers) passes through, and the final text is in the DOM from the server render (screen readers and captures read it).

## Components
| Component | Use it for | Notes |
|---|---|---|
| `Reveal` | a card or section that fades and rises 8 px into view | `as`, `delay` (ms), `fade` (opacity only, for marks that must not move) |
| `Stagger` | a grid or list whose direct children rise in sequence | no wrapper per child; `step` (ms, default 70), `count` fits the step into 1.5 s |
| `GrowBar` | a bar or a stacked row that grows from 0 to its size | `axis="x" \| "y"`, `delay`; size it with `growTarget(value, max, span)`; it can be the focusable mark itself |
| `GrowGroup` + `part.growX/growY/after` | a composite mark: a bar, then its interval band and dot fade in | spread `part.*` on the inner elements |
| `DrawPath` | an SVG line that draws along its length | `points` (polyline) or `d` (path); `pathLength=1` is set for you |
| `MotionGroup` + `part.draw/after/fade` | an SVG `<g>` with a line, then its markers and labels | `after` (ms) sets when the `after` parts fade in |
| `FlowConnector` | a diagram edge: dashes flow once toward an arrowhead | `direction` right/down/left/up, `length` (px), `delay`; `loop` only for an edge that is live now; `aria-hidden` |
| `Lift` / `lift` | subtle hover and focus elevation: 2 px up and a violet-tinted border, no shadow | the class string fits existing elements |
| `Crossfade` | a switch or tab that swaps series in place | `id`: a change crossfades the content without remounting it (open tables and focus stay) |
| `CountText` | a formatted figure that counts up (`"88.9%"`, `"1,234,567 rows [data]"`) | a number counts only if it formats back to the same text; dates and versions stay text |
| `NumberTicker` | a single number that counts up | re-exported from `components/ui/number-ticker.tsx` |

Helpers, from `@/lib/motion`: `part`, `lift`, `MOTION`, `staggerDelay(i, step)`, `fitStep(count)`, `growTarget(value, max, span)`, `walkSchedule(nodes, outputs)` (the
step-by-step walk of `PipelineDiagram`).

```tsx
import { CountText, GrowBar, MotionGroup, Stagger } from "@/components/motion";
import { growTarget, part } from "@/lib/motion";

<Stagger className="grid gap-4 md:grid-cols-2">{cards}</Stagger>
<GrowBar tabIndex={0} role="img" aria-label="FCR 43.6%" style={{ width: `${growTarget(0.436)}%` }} {...bind(tip)} />
<MotionGroup as="g" after={600}><polyline {...part.draw} points={pts} /><circle {...part.after} … /></MotionGroup>
<p className="text-5xl"><CountText text={pct(value)} /></p>
```

## Pitfalls
- A count-up shows on load only inside a `Reveal`/`Stagger` that is still hidden, or below the fold; a number already on
  screen never jumps back to a lower value.
- `position: fixed` children (the charts' tooltip) are placed relative to an ancestor with a transform. A `Reveal` only
  transforms while it plays; do not put `lift` on an element that contains a fixed tooltip.
- A part inside a closed `<details>` or `display: none` plays when it is first shown.
- Screenshots: `scripts/web/insight_screenshots.py` emulates reduced motion by default, so shots show final states;
  `--motion` captures with the animations on.
