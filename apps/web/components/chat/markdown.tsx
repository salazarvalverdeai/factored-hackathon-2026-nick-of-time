"use client";

// An agent reply as safe markdown (spec 07 AC-09): bold, italics, lists, inline code and links only. Raw HTML is
// skipped, never rendered; line breaks are kept; a link opens only an http(s) or same-site target; a mark still being
// typed is held back while the reply streams (lib/chat-stream.ts `stableMarkdown`).
import ReactMarkdown, { type Components } from "react-markdown";
import { stableMarkdown } from "@/lib/chat-stream";
import { cn } from "@/lib/utils";

const ALLOWED = ["p", "strong", "em", "ul", "ol", "li", "code", "a", "br"];

const COMPONENTS: Components = {
  p: ({ children }) => <p className="whitespace-pre-line [&:not(:first-child)]:mt-2">{children}</p>,
  ul: ({ children }) => <ul className="mt-1 list-disc space-y-0.5 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="mt-1 list-decimal space-y-0.5 pl-5">{children}</ol>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  code: ({ children }) => <code className="rounded bg-muted px-1 font-mono text-[0.85em]">{children}</code>,
  a: ({ href, children }) => {
    const external = /^https:\/\//.test(href ?? "");
    return (
      <a href={href} className="text-primary underline underline-offset-2" {...(external ? { target: "_blank", rel: "noreferrer" } : {})}>
        {children}
      </a>
    );
  },
};

/** Only https links and our own paths survive; anything else (javascript:, data:…) loses its target. */
const safeUrl = (url: string) => (/^https:\/\//.test(url) || /^\/(?!\/)/.test(url) ? url : "");

export function Markdown({ text, streaming = false, className }: { text: string; streaming?: boolean; className?: string }) {
  return (
    <div className={cn("min-w-0 break-words text-sm leading-relaxed", className)}>
      <ReactMarkdown skipHtml allowedElements={ALLOWED} unwrapDisallowed urlTransform={safeUrl} components={COMPONENTS}>
        {streaming ? stableMarkdown(text) : text}
      </ReactMarkdown>
    </div>
  );
}
