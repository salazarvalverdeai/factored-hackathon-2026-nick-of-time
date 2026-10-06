"use client"

// Magic UI number ticker (added with `npx shadcn add https://magicui.design/r/number-ticker`), adapted for this app:
// - the server render, the first client render and any capture that never scrolls show the final value, never a start value;
// - it counts up subtly (from 90% of the value, never 0) only when it scrolls into view after the page loads (a number already on screen never jumps back);
// - a fixed-duration tween instead of the spring, so it always lands on the exact value and never rests in between;
// - with `prefers-reduced-motion: reduce` it never animates;
// - screen readers get the final value once; the moving digits are hidden from them;
// - it inherits the text color (no hard-coded colors, apps/web/README.md style rules).
import { useEffect, useRef, type ComponentPropsWithoutRef } from "react"
import { animate, useInView } from "motion/react"

import { cn } from "@/lib/utils"
import { formatTicker as format, tickerStart } from "@/lib/ticker"

interface NumberTickerProps extends ComponentPropsWithoutRef<"span"> {
  value: number
  /** Optional start of the subtle count; defaults to 90% of the value, never 0. */
  startValue?: number
  delay?: number
  /** Seconds. */
  duration?: number
  decimalPlaces?: number
}

export function NumberTicker({
  value,
  startValue,
  delay = 0,
  duration = 1.2,
  className,
  decimalPlaces = 0,
  ...props
}: NumberTickerProps) {
  const ref = useRef<HTMLSpanElement>(null)
  const armed = useRef(false)
  const from = tickerStart(value, startValue)
  const isInView = useInView(ref, { once: true, margin: "0px" })

  // On mount: arm the animation only when motion is allowed and the number is still below the fold.
  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return
    const rect = el.getBoundingClientRect()
    if (rect.top < window.innerHeight && rect.bottom > 0) return
    // The final value stays in the DOM: a capture that never triggers the observer must show it, not a start state.
    armed.current = true
    return () => {
      armed.current = false
      el.textContent = format(value, decimalPlaces)
    }
  }, [value, decimalPlaces])

  useEffect(() => {
    const el = ref.current
    if (!el || !isInView || !armed.current) return
    const controls = animate(from, value, {
      duration,
      delay,
      ease: "easeOut",
      onUpdate: (latest) => {
        el.textContent = format(latest, decimalPlaces)
      },
      onComplete: () => {
        el.textContent = format(value, decimalPlaces)
      },
    })
    return () => {
      controls.stop()
      el.textContent = format(value, decimalPlaces)
    }
  }, [isInView, from, value, duration, delay, decimalPlaces])

  return (
    <span className={cn("inline-block tabular-nums", className)} {...props}>
      <span ref={ref} aria-hidden="true">
        {format(value, decimalPlaces)}
      </span>
      <span className="sr-only">{format(value, decimalPlaces)}</span>
    </span>
  )
}
