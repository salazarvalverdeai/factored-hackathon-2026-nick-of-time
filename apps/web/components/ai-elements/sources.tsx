"use client";

// AI Elements `sources` (registry.ai-sdk.dev/sources.json), adapted to the Base UI collapsible and restyled to
// docs/brand/BRAND.md. A source is always a named link: the URL is its target, never its text (design pass 1).
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import { BookIcon, ChevronDownIcon } from "lucide-react";
import type { ComponentProps } from "react";

export type SourcesProps = ComponentProps<typeof Collapsible>;

export const Sources = ({ className, ...props }: SourcesProps) => (
  <Collapsible className={cn("not-prose text-xs", className)} {...props} />
);

export type SourcesTriggerProps = ComponentProps<typeof CollapsibleTrigger> & {
  count: number;
  label?: string;
};

export const SourcesTrigger = ({ className, count, label, children, ...props }: SourcesTriggerProps) => (
  <CollapsibleTrigger
    className={cn(
      "group flex items-center gap-1.5 rounded-md font-medium text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring",
      className,
    )}
    {...props}
  >
    {children ?? (
      <>
        <span>{label ?? `Sources (${count})`}</span>
        <ChevronDownIcon aria-hidden className="size-3.5 motion-safe:transition-transform group-data-[panel-open]:rotate-180" />
      </>
    )}
  </CollapsibleTrigger>
);

export type SourcesContentProps = ComponentProps<typeof CollapsibleContent>;

export const SourcesContent = ({ className, ...props }: SourcesContentProps) => (
  <CollapsibleContent className={cn("mt-2 flex flex-col gap-2 outline-none", className)} {...props} />
);

export type SourceProps = ComponentProps<"a">;

export const Source = ({ href, title, children, className, ...props }: SourceProps) => (
  <a
    className={cn("inline-flex items-start gap-2 text-primary underline-offset-2 hover:underline", className)}
    href={href}
    rel="noreferrer"
    target="_blank"
    {...props}
  >
    {children ?? (
      <>
        <BookIcon aria-hidden className="mt-0.5 size-3.5 shrink-0" />
        <span className="block">{title}</span>
      </>
    )}
  </a>
);
