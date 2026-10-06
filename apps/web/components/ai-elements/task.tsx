"use client";

// AI Elements `task` (registry.ai-sdk.dev/task.json), adapted to this repo's Base UI collapsible (no `asChild`; Base
// UI marks an open trigger with `data-panel-open`) and restyled to docs/brand/BRAND.md: calm, no slide animations.
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import { ChevronDownIcon, ListChecksIcon } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";

export type TaskItemProps = ComponentProps<"div">;

export const TaskItem = ({ children, className, ...props }: TaskItemProps) => (
  <div className={cn("text-muted-foreground text-sm", className)} {...props}>
    {children}
  </div>
);

export type TaskProps = ComponentProps<typeof Collapsible>;

export const Task = ({ defaultOpen = true, className, ...props }: TaskProps) => (
  <Collapsible className={cn(className)} defaultOpen={defaultOpen} {...props} />
);

export type TaskTriggerProps = Omit<ComponentProps<typeof CollapsibleTrigger>, "title"> & {
  title: ReactNode;
};

export const TaskTrigger = ({ children, className, title, ...props }: TaskTriggerProps) => (
  <CollapsibleTrigger
    className={cn(
      "group flex w-full cursor-pointer items-center gap-2 rounded-md text-left text-muted-foreground text-sm transition-colors hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring",
      className,
    )}
    {...props}
  >
    {children ?? (
      <>
        <ListChecksIcon aria-hidden className="size-4 shrink-0" />
        <span className="min-w-0 flex-1">{title}</span>
        <ChevronDownIcon aria-hidden className="size-4 shrink-0 motion-safe:transition-transform group-data-[panel-open]:rotate-180" />
      </>
    )}
  </CollapsibleTrigger>
);

export type TaskContentProps = ComponentProps<typeof CollapsibleContent>;

export const TaskContent = ({ children, className, ...props }: TaskContentProps) => (
  <CollapsibleContent className={cn("text-popover-foreground outline-none", className)} {...props}>
    <div className="mt-3 space-y-2 border-l-2 border-muted pl-4">{children}</div>
  </CollapsibleContent>
);
