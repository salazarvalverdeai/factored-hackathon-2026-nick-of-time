import Link from "next/link";

export const REPO_URL = "https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time";
export const LABELS = ["[data]", "[external]", "[assumption]", "[simulated]", "[projected]"] as const;
export const TEAM = ["Freddy", "GianMarco", "Diego"] as const;

/** Site footer (spec 16): team, event, repo, and the label legend. Labels are explained on /evaluation. */
export function SiteFooter() {
  return (
    <footer className="mx-auto w-full max-w-7xl border-t px-4 py-6 text-xs text-muted-foreground">
      <p>
        Nick of Time · {TEAM.join(", ")} · Factored AI &amp; Data Hackathon 2026 ·{" "}
        <a href={REPO_URL} target="_blank" rel="noreferrer" className="underline underline-offset-2 hover:text-foreground">
          GitHub
        </a>
      </p>
      <p className="mt-2 break-words">
        Figure labels:{" "}
        {LABELS.map((l) => (
          <span key={l} className="mr-2 inline-block font-mono">
            {l}
          </span>
        ))}
        <Link href="/evaluation" className="underline underline-offset-2 hover:text-foreground">
          what they mean
        </Link>
      </p>
    </footer>
  );
}
