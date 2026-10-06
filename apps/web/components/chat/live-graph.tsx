"use client";

// The live graph beside /chat (spec 07 AC-28): the dispute_intake drawing of /agent (components/agent/graph-view.tsx),
// with the node the agent is on marked as the turn runs and the nodes it passed standing out. Closed by default so the
// conversation keeps its width: on wide screens a slim rail at the right edge opens a floating panel that does not block
// the chat; on narrow screens a header button opens it as a sheet (the shared detail panel). The run comes from
// lib/chat-graph.ts; its one entrance is the shared motion kit's opacity-only Reveal, still under reduced motion.
import { WorkflowIcon, XIcon } from "lucide-react";
import { useId, useRef, useSyncExternalStore, type KeyboardEvent } from "react";
import { GraphView } from "@/components/agent/graph-view";
import { Reveal } from "@/components/motion";
import { DetailPanel } from "@/components/detail-panel";
import { Button } from "@/components/ui/button";
import type { GraphRun } from "@/lib/chat-graph";
import { CHAT_STRINGS as S } from "@/lib/chat-strings";
import type { Language } from "@/lib/types";

const WIDE = "(min-width: 64rem)"; // Tailwind `lg`

function subscribe(onChange: () => void) {
  const mq = window.matchMedia(WIDE);
  mq.addEventListener("change", onChange);
  return () => mq.removeEventListener("change", onChange);
}

/** True on screens where the graph opens as a side panel (lg and up); false on the server and on phones. */
function useWide(): boolean {
  return useSyncExternalStore(subscribe, () => window.matchMedia(WIDE).matches, () => false);
}

/** "Ahora: Buscar el cargo", or the idle and finished lines; read out politely as it changes. */
function NowLine({ run, lang }: { run: GraphRun; lang: Language }) {
  const words = run.active ? S.graphNodes[run.active]?.[lang] : null;
  return (
    <p aria-live="polite" className="text-sm" data-slot="graph-now">
      {words ? (
        <>
          <span className="font-medium text-primary-text">{S.graphNow[lang]}:</span> {words}{" "}
          <span className="font-mono text-xs text-muted-foreground">({run.active})</span>
        </>
      ) : (
        <span className="text-muted-foreground">{run.path.includes("END") ? S.graphDone[lang] : S.graphIdle[lang]}</span>
      )}
    </p>
  );
}

function GraphBody({ run, lang }: { run: GraphRun; lang: Language }) {
  return (
    <div className="space-y-3">
      <NowLine run={run} lang={lang} />
      <GraphView fit reveal={false} activeNode={run.active ?? undefined} path={run.path} />
    </div>
  );
}

/** The header button that opens the graph on narrow screens (the rail does it on wide ones). */
export function LiveGraphToggle({ lang, open, onToggle }: { lang: Language; open: boolean; onToggle: () => void }) {
  return (
    <Button size="sm" variant="ghost" onClick={onToggle} aria-expanded={open} aria-label={S.graphToggle[lang]} title={S.graphToggle[lang]} className="text-muted-foreground lg:hidden">
      <WorkflowIcon aria-hidden className="size-3.5" />
    </Button>
  );
}

export function LiveGraph({ lang, run, open, onOpenChange }: { lang: Language; run: GraphRun; open: boolean; onOpenChange: (open: boolean) => void }) {
  const wide = useWide();
  const id = useId();
  const titleId = `${id}-title`;
  // Focus follows the toggle: opening moves it to the panel's close button, closing back to the rail.
  const moveFocus = useRef(false);
  const focusOnMount = (el: HTMLElement | null) => {
    if (el && moveFocus.current) {
      moveFocus.current = false;
      el.focus();
    }
  };
  const toggle = (next: boolean) => {
    moveFocus.current = true;
    onOpenChange(next);
  };
  const close = () => toggle(false);

  if (!wide) {
    return (
      <DetailPanel open={open} onClose={() => onOpenChange(false)} title={S.graphTitle[lang]} description={S.graphCaption[lang]} closeLabel={S.close[lang]}>
        <GraphBody run={run} lang={lang} />
      </DetailPanel>
    );
  }

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Escape" && !e.defaultPrevented) close();
  };

  return (
    <>
      {/* The slim rail: takes no width from the conversation; vertical text, a real button. */}
      {!open ? (
        <button
          ref={focusOnMount}
          type="button"
          onClick={() => toggle(true)}
          aria-expanded={false}
          aria-controls={id}
          className="fixed right-0 top-1/2 z-30 flex -translate-y-1/2 items-center gap-2 rounded-l-lg border border-r-0 bg-card px-1.5 py-3 text-xs font-medium text-muted-foreground shadow-sm transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none"
          data-slot="graph-rail"
        >
          <WorkflowIcon aria-hidden className="size-3.5" />
          <span className="[writing-mode:vertical-rl]">{S.graphToggle[lang]}</span>
        </button>
      ) : (
        <Reveal
          fade
          id={id}
          role="complementary"
          aria-labelledby={titleId}
          onKeyDown={onKeyDown}
          className="fixed bottom-4 right-4 top-20 z-30 flex w-[min(30rem,40vw)] flex-col overflow-hidden rounded-2xl border bg-background shadow-lg"
          data-slot="graph-panel"
        >
          <div className="flex items-start gap-2 border-b px-4 py-3">
            <div className="min-w-0 flex-1">
              <h2 id={titleId} className="text-sm font-semibold">
                {S.graphTitle[lang]}
              </h2>
              <p className="mt-0.5 text-xs text-muted-foreground">{S.graphCaption[lang]}</p>
            </div>
            <Button ref={focusOnMount} size="icon-sm" variant="ghost" onClick={close} aria-expanded aria-controls={id} aria-label={S.graphHide[lang]} title={S.graphHide[lang]}>
              <XIcon aria-hidden />
            </Button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            <GraphBody run={run} lang={lang} />
          </div>
        </Reveal>
      )}
    </>
  );
}
