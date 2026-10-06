"use client";

// An agent reply as safe markdown (spec 07 AC-09, AC-12) on AI Elements `MessageResponse` (Streamdown): bold, italics,
// lists, inline code and links only. Raw HTML is skipped, never rendered; line breaks are kept; a link opens only an
// https or same-site target. A figure a tool returned links to that tool as an AI Elements inline citation
// (`#cite-<id>`, lib/chat-stream.ts `citeFigures`, AC-22). While the reply is revealed, a half-written mark is held back
// by lib/chat-reveal.ts before it gets here.
import { createContext, useContext } from "react";
import type { Components } from "streamdown";
import { MessageResponse } from "@/components/ai-elements/message";
import {
  InlineCitation,
  InlineCitationCard,
  InlineCitationCardBody,
  InlineCitationCardTrigger,
  InlineCitationSource,
  InlineCitationText,
} from "@/components/ai-elements/inline-citation";
import { Button } from "@/components/ui/button";
import { type ToolEvent, CITE_PREFIX, citeTarget, customerText } from "@/lib/chat-stream";
import { CHAT_STRINGS } from "@/lib/chat-strings";
import type { Language } from "@/lib/types";
import { cn } from "@/lib/utils";

/** The tools of the turn a reply cites, and how to open one in the right panel. */
export const CitationContext = createContext<{ tools: readonly ToolEvent[]; lang: Language; onOpen?: (tool: ToolEvent) => void } | null>(null);

const ALLOWED = ["p", "strong", "em", "ul", "ol", "li", "code", "a", "br"];

function CitedFigure({ id, children }: { id: string; children: React.ReactNode }) {
  const ctx = useContext(CitationContext);
  const tool = ctx?.tools.find((t) => t.id === id);
  if (!ctx || !tool) return <>{children}</>;
  const name = customerText(tool.title);
  return (
    <InlineCitation>
      <InlineCitationText className="font-semibold">{children}</InlineCitationText>
      <InlineCitationCard>
        <InlineCitationCardTrigger sources={[name]} className="max-w-40 truncate align-middle font-normal" aria-label={`${CHAT_STRINGS.citedFrom[ctx.lang]}: ${name}`} />
        <InlineCitationCardBody className="space-y-2 p-3">
          <InlineCitationSource title={name} description={tool.summary ? customerText(tool.summary) : CHAT_STRINGS.citedFrom[ctx.lang]} />
          {ctx.onOpen ? (
            <Button size="xs" variant="ghost" className="-ml-2" onClick={() => ctx.onOpen?.(tool)}>
              {CHAT_STRINGS.openDetail[ctx.lang]} →
            </Button>
          ) : null}
        </InlineCitationCardBody>
      </InlineCitationCard>
    </InlineCitation>
  );
}

const COMPONENTS: Components = {
  p: ({ children }) => <p className="whitespace-pre-line [&:not(:first-child)]:mt-2">{children}</p>,
  ul: ({ children }) => <ul className="mt-1 list-disc space-y-0.5 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="mt-1 list-decimal space-y-0.5 pl-5">{children}</ol>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  code: ({ children }) => <code className="rounded bg-muted px-1 font-mono text-[0.85em]">{children}</code>,
  a: ({ href, children }) => {
    const cited = citeTarget(href);
    if (cited) return <CitedFigure id={cited}>{children}</CitedFigure>;
    const external = /^https:\/\//.test(href ?? "");
    return (
      <a href={href} className="text-primary underline underline-offset-2" {...(external ? { target: "_blank", rel: "noreferrer" } : {})}>
        {children}
      </a>
    );
  },
};

/** Only https links, our own paths and cite targets survive; anything else (javascript:, data:…) loses its target. */
const safeUrl = (url: string) => (/^https:\/\//.test(url) || /^\/(?!\/)/.test(url) || url.startsWith(CITE_PREFIX) ? url : "");

export function Markdown({ text, streaming = false, className }: { text: string; streaming?: boolean; className?: string }) {
  return (
    <MessageResponse
      className={cn("min-w-0 break-words text-sm leading-relaxed", className)}
      mode={streaming ? "streaming" : "static"}
      skipHtml
      rehypePlugins={[]}
      allowedElements={ALLOWED}
      unwrapDisallowed
      urlTransform={safeUrl}
      components={COMPONENTS}
      linkSafety={{ enabled: false }}
    >
      {text}
    </MessageResponse>
  );
}
