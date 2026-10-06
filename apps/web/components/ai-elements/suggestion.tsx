"use client";

// AI Elements `suggestion` (registry.ai-sdk.dev/suggestion.json), restyled to docs/brand/BRAND.md: pills that wrap
// instead of a horizontal scroller, so the chat keeps no horizontal scroll at 390 px (spec 07 AC-05).
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ComponentProps } from "react";

export type SuggestionsProps = ComponentProps<"div">;

export const Suggestions = ({ className, children, ...props }: SuggestionsProps) => (
  <div className={cn("flex flex-wrap items-center gap-2", className)} {...props}>
    {children}
  </div>
);

export type SuggestionProps = Omit<ComponentProps<typeof Button>, "onClick"> & {
  suggestion: string;
  onClick?: (suggestion: string) => void;
};

export const Suggestion = ({
  suggestion,
  onClick,
  className,
  variant = "outline",
  size = "sm",
  children,
  ...props
}: SuggestionProps) => (
  <Button
    className={cn("h-auto min-h-8 cursor-pointer whitespace-normal rounded-full px-3.5 py-1.5 text-left", className)}
    onClick={() => onClick?.(suggestion)}
    size={size}
    type="button"
    variant={variant}
    {...props}
  >
    {children || suggestion}
  </Button>
);
