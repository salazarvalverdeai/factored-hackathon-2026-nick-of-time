"use client";

// The one primitive under the motion kit: a root that plays its parts once, when it first enters the viewport.
// The start and end states live in motion.css; this file only flips data-revealed (pending → in → done). With reduced
// motion it goes to "done" on mount, so nothing moves and every part shows its final state.
import { createElement, useEffect, useRef, type ComponentPropsWithoutRef, type CSSProperties } from "react";
import { useInView, useReducedMotion } from "motion/react";
import { MOTION, MOTION_LIVE, MOTION_OK } from "@/lib/motion";

export type MotionTag = "div" | "section" | "figure" | "article" | "ol" | "ul" | "li" | "dl" | "span" | "p" | "g" | "path" | "polyline";
export type MotionKind = "reveal" | "stagger" | "grow" | "draw" | "flow" | "group";

export type MotionGroupProps<T extends MotionTag = "div"> = {
  as?: T;
  /** Milliseconds before the root's parts start. */
  delay?: number;
  /** Milliseconds from the start to the "after" parts (default: a grow, 500 ms). */
  after?: number;
  /** Milliseconds between two children of a stagger. */
  step?: number;
  /** How long the whole root plays, so it can hand transitions back to the page afterwards. */
  span?: number;
  kind?: MotionKind;
} & Omit<ComponentPropsWithoutRef<T>, "ref">;

const motionAllowed = () => typeof document !== "undefined" && document.documentElement.hasAttribute(MOTION_OK);

/** The root hook: returns the ref to put on the root element. */
export function useMotionOnce<E extends Element>(span: number) {
  const ref = useRef<E>(null);
  const reduced = useReducedMotion();
  // "some" plus a small bottom margin: a root starts when it is a little inside the viewport, not on its first pixel.
  const seen = useInView(ref, { once: true, margin: "0px 0px -6% 0px" });
  useEffect(() => {
    const el = ref.current;
    if (!el || el.getAttribute("data-revealed") === "done") return;
    if (reduced || !motionAllowed()) {
      el.setAttribute("data-revealed", "done");
      return;
    }
    if (!seen) return;
    el.setAttribute("data-revealed", "in");
    const timer = window.setTimeout(() => el.setAttribute("data-revealed", "done"), span + 50);
    return () => window.clearTimeout(timer);
  }, [reduced, seen, span]);
  return ref;
}

export function MotionGroup<T extends MotionTag = "div">({ as, delay = 0, after, step, span, kind = "group", style, ...rest }: MotionGroupProps<T>) {
  const total = span ?? delay + MOTION.sequence;
  const ref = useMotionOnce<Element>(total);
  const vars = {
    "--motion-delay": `${Math.round(delay)}ms`,
    "--motion-i": 0,
    ...(after !== undefined ? { "--motion-after": `${Math.round(after)}ms` } : {}),
    ...(step !== undefined ? { "--motion-step": `${Math.round(step)}ms` } : {}),
  } as CSSProperties;
  return createElement(as ?? "div", { ...rest, ref, "data-motion": kind, style: { ...vars, ...(style as CSSProperties | undefined) } });
}

/** Marks the app as hydrated, so the head script's safety timer keeps motion on (app/layout.tsx). */
export function MotionReady() {
  useEffect(() => {
    document.documentElement.setAttribute(MOTION_LIVE, "");
  }, []);
  return null;
}
