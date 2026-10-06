"use client";

// Loading, empty, error and DENY states shared by every page. A client component so the default words follow the UI
// language (spec 16 AC-06); server pages still render it and pass their own text.
import type { ReactNode } from "react";
import { useT } from "@/components/i18n-provider";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const BOX = "rounded-lg border p-6 text-center text-sm";

export function LoadingState({ label, className }: { label?: string; className?: string }) {
  const t = useT();
  return (
    <div role="status" aria-live="polite" data-slot="loading-state" className={cn(BOX, "border-dashed text-muted-foreground", className)}>
      <span className="mr-2 inline-block size-3 animate-spin rounded-full border-2 border-current border-t-transparent align-[-1px]" />
      {label ?? t("ui.states.loading")}
    </div>
  );
}

export function EmptyState({ title, hint, className }: { title?: string; hint?: string; className?: string }) {
  const t = useT();
  return (
    <div data-slot="empty-state" className={cn(BOX, "border-dashed text-muted-foreground", className)}>
      <p className="font-medium text-foreground">{title ?? t("ui.states.empty")}</p>
      {hint ? <p className="mt-1">{hint}</p> : null}
    </div>
  );
}

export function ErrorState({
  title,
  message,
  onRetry,
  action,
  className,
}: {
  title?: string;
  message?: string;
  onRetry?: () => void;
  action?: ReactNode;
  className?: string;
}) {
  const t = useT();
  return (
    <div role="alert" data-slot="error-state" className={cn(BOX, "border-destructive/40 bg-destructive/5", className)}>
      <p className="font-medium text-destructive">{title ?? t("ui.states.error")}</p>
      {message ? <p className="mt-1 text-muted-foreground">{message}</p> : null}
      <div className="mt-3 flex justify-center gap-2">
        {onRetry ? (
          <Button size="sm" variant="outline" onClick={onRetry}>
            {t("ui.states.retry")}
          </Button>
        ) : null}
        {action}
      </div>
    </div>
  );
}

/** A request the rules refused. Shown as DENY on purpose: nothing was executed, and the customer is told so plainly. */
export function DenyState({ message, className }: { message: string; className?: string }) {
  return (
    <div role="status" data-slot="deny-state" className={cn(BOX, "border-red-500/40 bg-red-500/5 text-left", className)}>
      <span className="mr-2 inline-flex h-5 items-center rounded-4xl bg-red-500/15 px-2 text-xs font-semibold text-red-700 dark:text-red-400">
        DENY
      </span>
      <span>{message}</span>
    </div>
  );
}
