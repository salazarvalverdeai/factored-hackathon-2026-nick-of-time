"use client";

// The right detail panel, shared by every page (plan §14): a card's "Detail →" opens it with whatever the page puts in
// it (the chat: a charge, a rule, a case, the receipt, the steps; the insight pages: method, source query, repo link).
// Generic on purpose: it knows nothing about the chat. A modal sheet from the right on every width, full width at
// 390 px; Escape and the close button close it, focus stays inside while open and goes back where it was after.
import { XIcon } from "lucide-react";
import { type ReactNode, useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";
import { useT } from "@/components/i18n-provider";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface DetailPanelProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  /** One or two lines under the title. */
  description?: ReactNode;
  children?: ReactNode;
  /** Pinned under the content: links ("Read the method →") or actions. */
  footer?: ReactNode;
  /** Accessible name of the close button (the UI locale's "Close" by default). */
  closeLabel?: string;
  className?: string;
}

const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]),select,textarea,[tabindex]:not([tabindex="-1"])';

export function DetailPanel({ open, onClose, title, description, children, footer, closeLabel, className }: DetailPanelProps) {
  const t = useT();
  const titleId = useId();
  const descriptionId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  useEffect(() => {
    close.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) return;
    const before = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panel.current?.querySelector<HTMLElement>("[data-detail-close]")?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        close.current();
        return;
      }
      if (e.key !== "Tab" || !panel.current) return;
      const items = [...panel.current.querySelectorAll<HTMLElement>(FOCUSABLE)];
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      before?.focus?.();
    };
  }, [open]);

  if (!open || typeof document === "undefined") return null;
  return createPortal(
    <div className="fixed inset-0 z-50 flex justify-end" data-slot="detail-panel-root">
      <div aria-hidden className="absolute inset-0 bg-background/70 motion-safe:animate-in motion-safe:fade-in-0" onClick={() => close.current()} />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        data-slot="detail-panel"
        className={cn(
          "relative flex h-full w-full max-w-md flex-col border-l bg-card text-card-foreground",
          "motion-safe:animate-in motion-safe:fade-in-0 motion-safe:slide-in-from-right-4 motion-safe:duration-200",
          className,
        )}
      >
        <header className="flex items-start gap-3 border-b px-4 py-3">
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-base font-semibold leading-snug">
              {title}
            </h2>
            {description ? (
              <p id={descriptionId} className="mt-0.5 text-sm text-muted-foreground">
                {description}
              </p>
            ) : null}
          </div>
          <Button data-detail-close variant="ghost" size="icon-sm" aria-label={closeLabel ?? t("shell.common.close")} onClick={() => close.current()}>
            <XIcon aria-hidden />
          </Button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 text-sm">{children}</div>
        {footer ? <footer className="border-t px-4 py-3 text-sm">{footer}</footer> : null}
      </div>
    </div>,
    document.body,
  );
}

/** A label and its value, the row every detail view is made of. */
export function DetailField({ label, children, mono = false }: { label: ReactNode; children: ReactNode; mono?: boolean }) {
  return (
    <div className="grid gap-0.5 py-2 first:pt-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className={cn("break-words", mono && "font-mono text-xs")}>{children}</dd>
    </div>
  );
}

export function DetailFields({ children, className }: { children: ReactNode; className?: string }) {
  return <dl className={cn("divide-y", className)}>{children}</dl>;
}
