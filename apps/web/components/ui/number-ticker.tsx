"use client"

// Magic UI number ticker (added with `npx shadcn add https://magicui.design/r/number-ticker`), adapted for this app:
// - the server render and a page without JavaScript show the final value, never the start value;
// - it animates only when it scrolls into view after the page loads (a number already on screen never jumps back);
// - a fixed-duration tween instead of the spring, so it always lands on the exact value and never rests in between;
// - with `prefers-reduced-motion: reduce` it never animates;
// - screen readers get the final value once; the moving digits are hidden from them;
// - it inherits the text color (no hard-coded colors, apps/web/README.md style rules).
import { useEffect, useRef, type ComponentPropsWithoutRef } from "react"
import { animate, useInView } from "motion/react"

import { cn } from "@/lib/utils"

interface NumberTickerProps extends ComponentPropsWithoutRef<"span"> {
  value: number
  startValue?: number
  delay?: number
  /** Seconds. */
  duration?: number
  decimalPlaces?: number
}

function format(n: number, decimalPlaces: number) {
  return Intl.NumberFormat("en-US", {
    minimumFractionDigits: decimalPlaces,
    maximumFractionDigits: decimalPlaces,
  }).format(Number(n.toFixed(decimalPlaces)))
}

export function NumberTicker({
  value,
  startValue = 0,
  delay = 0,
  duration = 1.2,
  className,
  decimalPlaces = 0,
  ...props
}: NumberTickerProps) {
  const ref = useRef<HTMLSpanElement>(null)
  const armed = useRef(false)
  const isInView = useInView(ref, { once: true, margin: "0px" })

  // On mount: arm the animation only when motion is allowed and the number is still below the fold.
  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return
    const rect = el.getBoundingClientRect()
    if (rect.top < window.innerHeight && rect.bottom > 0) return
    armed.current = true
    el.textContent = format(startValue, decimalPlaces)
    return () => {
      armed.current = false
      el.textContent = format(value, decimalPlaces)
    }
  }, [startValue, value, decimalPlaces])

  useEffect(() => {
    const el = ref.current
    if (!el || !isInView || !armed.current) return
    const controls = animate(startValue, value, {
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
  }, [isInView, startValue, value, duration, delay, decimalPlaces])

  return (
    <span className={cn("inline-block tabular-nums", className)} {...props}>
      <span ref={ref} aria-hidden="true">
        {format(value, decimalPlaces)}
      </span>
      <span className="sr-only">{format(value, decimalPlaces)}</span>
    </span>
  )
}
