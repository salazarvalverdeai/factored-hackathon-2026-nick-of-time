import { DEADLINES, FCR, POLICIES, PROBLEM_DOC, RESOLUTION, STATS } from "@/lib/landing";
import { LabelTag, SourceLinks, StatCard } from "./figure";

/** "The problem in numbers": the figures of docs/problem_in_numbers.md, each with its label and its linked source. */
export function ProblemNumbers() {
  return (
    <section aria-labelledby="problem-title" className="space-y-6">
      <div className="max-w-2xl space-y-2">
        <h2 id="problem-title" className="text-2xl font-semibold tracking-tight">
          The problem in numbers
        </h2>
        <p className="text-muted-foreground">
          Unrecognized and wrongful card charges, from the bank&apos;s synthetic dataset. These numbers describe the problem; none of
          them measures this system. Its results are on the evaluation page, labeled <span className="font-mono text-xs">[simulated]</span>.
          All figures and their queries:{" "}
          <a href={PROBLEM_DOC.href} className="underline underline-offset-2 hover:text-foreground" target="_blank" rel="noreferrer">
            {PROBLEM_DOC.label}
          </a>
          .
        </p>
      </div>

      <StatCard stat={FCR} large />

      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {STATS.map((stat) => (
          <li key={stat.id}>
            <StatCard stat={stat} />
          </li>
        ))}
        <li>
          <StatCard stat={RESOLUTION} />
        </li>
      </ul>

      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-lg font-semibold tracking-tight">The only workflow with a legal clock</h3>
          <LabelTag label="external" />
        </div>
        <p className="max-w-2xl text-sm text-muted-foreground">
          The system computes the deadline per country and product from the policy file and puts it on the customer&apos;s receipt and on the
          analyst&apos;s card. For any other country the case still opens and a person decides; no deadline is invented.
        </p>
        <div className="overflow-hidden rounded-xl border border-l-4 border-l-brand-amber bg-card">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Legal deadlines for a disputed card charge, by country</caption>
            <thead className="border-b text-xs text-muted-foreground">
              <tr>
                <th scope="col" className="px-4 py-2 font-medium">
                  Country
                </th>
                <th scope="col" className="px-4 py-2 font-medium">
                  Obligation
                </th>
                <th scope="col" className="hidden px-4 py-2 font-medium sm:table-cell">
                  Source
                </th>
              </tr>
            </thead>
            <tbody>
              {DEADLINES.map((d) => (
                <tr key={d.country} className="border-b align-top last:border-0">
                  <th scope="row" className="whitespace-nowrap px-4 py-2.5 font-medium">
                    {d.country}
                  </th>
                  <td className="px-4 py-2.5">
                    {d.obligation}
                    <a
                      href={d.source.href}
                      className="mt-1 block text-xs text-muted-foreground underline underline-offset-2 sm:hidden"
                      target="_blank"
                      rel="noreferrer"
                    >
                      {d.source.label}
                    </a>
                  </td>
                  <td className="hidden px-4 py-2.5 sm:table-cell">
                    <a
                      href={d.source.href}
                      className="text-muted-foreground underline underline-offset-2 hover:text-foreground"
                      target="_blank"
                      rel="noreferrer"
                    >
                      {d.source.label}
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <SourceLinks sources={[PROBLEM_DOC, POLICIES]} />
      </div>
    </section>
  );
}
