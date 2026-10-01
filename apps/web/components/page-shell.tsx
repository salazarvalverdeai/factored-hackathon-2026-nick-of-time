import type { ReactNode } from "react";

export function PageShell({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <p className="mt-1 text-muted-foreground">{description}</p>
      <div className="mt-6">
        {children ?? (
          <div className="rounded-lg border border-dashed p-10 text-center text-sm text-muted-foreground">
            Empty state · content pending
          </div>
        )}
      </div>
    </main>
  );
}
