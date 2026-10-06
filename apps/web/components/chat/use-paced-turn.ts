"use client";

// The running turn as the customer sees it (spec 07 AC-17, AC-18): frames from the stream go through the pacer
// (lib/chat-reveal.ts) so each step dwells, then the reply is revealed word by word; when the last word shows, the turn
// completes and becomes a message. Display only: the frames keep their order and nothing is added. Reduced motion
// shows everything at once.
import { useCallback, useEffect, useRef, useState } from "react";
import { Pacer, type TurnFrame, frameGap, revealMarkdown, wordCount, wordsAt } from "@/lib/chat-reveal";
import { EMPTY_STREAM, type ToolEvent, type TurnStream, applyText, applyTool } from "@/lib/chat-stream";
import { useReducedMotionGuard } from "./motion";
import type { LiveTurnView } from "./thread";

interface Model<R> {
  stream: TurnStream;
  progress: string[];
  reply: R | null;
  /** The text being revealed: the streamed chunks, then the final reply in their place. */
  target: string;
  revealStart: number | null;
  shown: number;
  started: boolean;
}

export interface PacedTurnOptions<R> {
  /** The customer text of streamed chunks (no bracket labels, no raw URL). */
  streamText: (raw: string) => string;
  /** The text that replaces the stream when the turn ends. */
  finalText: (reply: R) => string;
  /** The whole turn has been shown: it becomes a message. */
  onComplete: (reply: R, view: { tools: ToolEvent[]; progress: string[] }) => void;
  /** Each frame as it is shown, after its dwell (the live graph follows the steps the customer sees, AC-31). */
  onFrame?: (frame: TurnFrame<R>) => void;
}

const TICK_MS = 30;

export function usePacedTurn<R>({ streamText, finalText, onComplete, onFrame }: PacedTurnOptions<R>) {
  const reduce = useReducedMotionGuard();
  const model = useRef<Model<R> | null>(null);
  const pacer = useRef<Pacer<TurnFrame<R>> | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const opts = useRef({ streamText, finalText, onComplete, onFrame, reduce });
  useEffect(() => {
    opts.current = { streamText, finalText, onComplete, onFrame, reduce };
  });
  // What renders: a snapshot of the model, published after every change (the model itself lives in a ref).
  const [snap, setSnap] = useState<{ view: LiveTurnView | null; thinking: boolean }>({ view: null, thinking: false });
  const bump = useCallback(() => {
    const m = model.current;
    setSnap(
      m
        ? {
            view: { tools: m.stream.tools, progress: m.progress, text: opts.current.reduce ? m.target : revealMarkdown(m.target, m.shown) },
            thinking: !m.started,
          }
        : { view: null, thinking: false },
    );
  }, []);

  const stopTimer = () => {
    if (timer.current !== null) clearInterval(timer.current);
    timer.current = null;
  };

  const finishIfDone = useCallback(() => {
    const m = model.current;
    if (!m || m.reply === null) return false;
    if (!opts.current.reduce && m.shown < wordCount(m.target)) return false;
    stopTimer();
    model.current = null;
    pacer.current = null;
    opts.current.onComplete(m.reply, { tools: m.stream.tools, progress: m.progress });
    bump();
    return true;
  }, [bump]);

  const startReveal = useCallback(() => {
    const m = model.current;
    if (!m || m.revealStart !== null || !m.target) return;
    m.revealStart = Date.now();
    if (opts.current.reduce) return;
    timer.current = setInterval(() => {
      const cur = model.current;
      if (!cur || cur.revealStart === null) return stopTimer();
      cur.shown = wordsAt(Date.now() - cur.revealStart);
      if (!finishIfDone()) bump();
    }, TICK_MS);
  }, [finishIfDone, bump]);

  const release = useCallback(
    (frame: TurnFrame<R>) => {
      const m = model.current;
      if (!m) return;
      m.started = true;
      opts.current.onFrame?.(frame);
      if (frame.kind === "progress") m.progress = [...m.progress, frame.label];
      else if (frame.kind === "tool") m.stream = applyTool(m.stream, frame.event);
      else if (frame.kind === "text") {
        m.stream = applyText(m.stream, { message_id: frame.messageId, delta: frame.delta });
        if (m.reply === null) m.target = opts.current.streamText(m.stream.text);
      } else {
        m.reply = frame.reply;
        m.target = opts.current.finalText(frame.reply);
      }
      startReveal();
      if (!finishIfDone()) bump();
    },
    [startReveal, finishIfDone, bump],
  );

  /** Starts a new turn and returns the function that feeds it frames; a turn still running is dropped. */
  const start = useCallback(() => {
    pacer.current?.cancel();
    stopTimer();
    model.current = { stream: EMPTY_STREAM, progress: [], reply: null, target: "", revealStart: null, shown: 0, started: false };
    const p = new Pacer<TurnFrame<R>>(release, frameGap, { instant: opts.current.reduce });
    pacer.current = p;
    bump();
    return (frame: TurnFrame<R>) => {
      if (pacer.current === p) p.push(frame);
    };
  }, [release, bump]);

  /** Drops the running turn (an error, a reset): nothing more of it shows. */
  const cancel = useCallback(() => {
    pacer.current?.cancel();
    pacer.current = null;
    stopTimer();
    model.current = null;
    bump();
  }, [bump]);

  useEffect(() => () => {
    pacer.current?.cancel();
    stopTimer();
  }, []);

  return { view: snap.view, thinking: snap.thinking, start, cancel };
}
