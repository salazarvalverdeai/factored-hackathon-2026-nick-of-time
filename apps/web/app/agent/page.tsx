import type { Metadata } from "next";
import type { ReactNode } from "react";
import { GraphView } from "@/components/agent/graph-view";
import { PageShell } from "@/components/page-shell";
import { AGENT_REFERENCE } from "@/lib/agent-reference";
import {
  CONSTITUTION,
  DIAGRAM,
  INVENTORY,
  NODE_INFO,
  REPO_URL,
  codeSpans,
  nextOf,
  ruleHasMore,
  ruleSummary,
  rulesCiting,
  zoneRange,
  type GraphNode,
} from "@/lib/agent";

// /agent (spec 04 AC-08, spec 02 T6): the architecture, the graph, the policy ids, the tools, the guardrails and the
// models. Every row comes from lib/agent-reference.ts, generated from the repo's sources by scripts/sync-agent.mjs.
export const metadata: Metadata = { title: "Agent" };

const { policies, tools, graph, sources } = AGENT_REFERENCE;
const branchLabel = (from: string, to: string) => graph.branches.find((b) => b.from === from && b.to === to)?.label;
const TH = "border-b py-2 pr-4 align-bottom font-normal";
const TD = "border-b py-2 pr-4 align-top";
const KIND = { R: "Read", W: "Write", N: "Notification" } as const;
const SECTIONS = [
  ["architecture", "Architecture"],
  ["graph", "Graph"],
  ["policies", "Policies"],
  ["tools", "Tools"],
  ["guardrails", "Guardrails"],
  ["models", "Models"],
] as const;

function Rich({ text }: { text: string }) {
  return codeSpans(text).map((part, i) =>
    part.code ? (
      <code key={i} className="font-mono text-[0.92em]">
        {part.text}
      </code>
    ) : (
      <span key={i}>{part.text}</span>
    ),
  );
}

function Mono({ children }: { children: ReactNode }) {
  return <span className="whitespace-nowrap font-mono">{children}</span>;
}

function Source({ path }: { path: string }) {
  return (
    <a href={`${REPO_URL}/${path}`} className="break-all font-mono underline decoration-muted-foreground/40 underline-offset-2 hover:text-foreground">
      {path}
    </a>
  );
}

function Section({ id, title, note, children }: { id: string; title: string; note: ReactNode; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="min-w-0 scroll-mt-20 rounded-lg border bg-card p-4 text-card-foreground sm:p-5">
      <h2 id={`${id}-title`} className="text-base font-semibold">
        {title}
      </h2>
      <p className="mt-0.5 text-sm text-muted-foreground">{note}</p>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function Table({ label, head, rows }: { label: string; head: string[]; rows: ReactNode[][] }) {
  return (
    <div className="overflow-x-auto">
      <table aria-label={label} className="w-full min-w-[36rem] text-left text-xs">
        <thead className="text-muted-foreground">
          <tr>
            {head.map((h) => (
              <th key={h} scope="col" className={TH}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {row.map((cell, j) => (
                <td key={j} className={TD}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RuleText({ text }: { text: string }) {
  const summary = ruleSummary(text);
  const full = text.replaceAll("->", "→");
  if (!ruleHasMore(text)) return <Rich text={summary} />;
  return (
    <details className="group">
      <summary className="cursor-pointer list-none [&::-webkit-details-marker]:hidden">
        <Rich text={summary} />{" "}
        <span className="text-muted-foreground underline underline-offset-2 group-open:hidden">Full rule</span>
      </summary>
      <p className="mt-1.5 text-muted-foreground">
        <Rich text={full} />
      </p>
    </details>
  );
}

export default function Page() {
  const start = nextOf("START").to;
  return (
    <PageShell title="Agent" description="How a dispute turn runs: the graph, the policy that decides, the tools that act and the models.">
      <p className="text-lg font-semibold leading-snug tracking-tight sm:text-xl">
        <span className="text-primary">{CONSTITUTION.split(",")[0]},</span>
        {CONSTITUTION.slice(CONSTITUTION.indexOf(",") + 1)}
      </p>
      <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
        The constitution of the system. Every table on this page is generated from the repository&apos;s code and contracts by{" "}
        <Source path="apps/web/scripts/sync-agent.mjs" />, and the web tests fail when it drifts from them.
      </p>
      <nav aria-label="On this page" className="mt-4 flex flex-wrap gap-1.5 text-sm">
        {SECTIONS.map(([id, label]) => (
          <a key={id} href={`#${id}`} className="rounded-md border px-2.5 py-1 text-muted-foreground hover:bg-accent hover:text-foreground">
            {label}
          </a>
        ))}
      </nav>

      <div className="mt-6 grid gap-6">
        <Section
          id="architecture"
          title="Architecture"
          note={
            <>
              Agent on LangGraph Platform, customer tools as an MCP server, case state in Postgres. Diagram from{" "}
              <Source path={DIAGRAM.source} />, as shown in the README; where it and the tables below differ, the tables are
              current.
            </>
          }
        >
          <a href={DIAGRAM.src} className="block overflow-hidden rounded-md border bg-white" aria-label="Open the architecture diagram at full size">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={DIAGRAM.src}
              alt="Architecture: customer and analyst web pages, the FastAPI api, the FastMCP tool server, Postgres and gold data on one EC2; the dispute_intake graph on LangGraph Platform calling Amazon Bedrock and the MCP tools."
              className="h-auto w-full"
              width={1500}
              height={1010}
            />
          </a>
        </Section>

        <Section
          id="graph"
          title={`Graph ${graph.name}`}
          note={
            <>
              {graph.nodes.length} nodes; the run starts at <Mono>{start.join(", ")}</Mono> and ends after{" "}
              <Mono>{graph.edges.find((e) => (e.to as readonly string[]).includes("END"))?.from}</Mono>. A branch follows the policy engine&apos;s
              result, a tool read or the understood input, never the LLM&apos;s text; each label is read from the
              graph&apos;s routers. Source: <Source path={sources.graph} />.
            </>
          }
        >
          <GraphView />
          <h3 className="mt-6 text-sm font-semibold">Table view</h3>
          <p className="mt-0.5 text-xs text-muted-foreground">The same nodes and edges; a branch shows what decides it.</p>
          <div className="mt-2">
            <Table
              label="Graph nodes"
              head={["#", "Node", "What it does", "Next"]}
              rows={graph.nodes.map((node, i) => {
                const next = nextOf(node);
                return [
                  <span key="n" className="tabular-nums text-muted-foreground">
                    {i + 1}
                  </span>,
                  <Mono key="id">{node}</Mono>,
                  NODE_INFO[node as GraphNode],
                  <span key="next" className="font-mono">
                    {next.conditional ? <span className="font-sans text-muted-foreground">one of </span> : null}
                    {next.to.map((to, j) => {
                      const label = branchLabel(node, to);
                      return (
                        <span key={to}>
                          {j ? " · " : ""}
                          {to}
                          {label ? <span className="text-muted-foreground"> ({label})</span> : null}
                        </span>
                      );
                    })}
                  </span>,
                ];
              })}
            />
          </div>
        </Section>

        <Section
          id="policies"
          title="Policies"
          note={
            <>
              <Source path={sources.policies} /> version {policies.version}, <Mono>default: {policies.default}</Mono>. Every
              decision cites one of these {policies.rules.length} ids; the LLM never reads or edits the file.
            </>
          }
        >
          <h3 className="text-sm font-medium">Zones from the bank&apos;s fraud score</h3>
          <ul className="mt-2 flex flex-wrap gap-2 text-xs">
            {policies.zones.map((zone) => (
              <li key={zone.name} className="rounded-md border px-2.5 py-1.5">
                <span className="font-medium">{zone.name}</span> <span className="text-muted-foreground">score {zoneRange(zone)}</span>
              </li>
            ))}
            <li className="self-center font-mono text-muted-foreground">[data] thresholds from the EDA, policies.yaml zones</li>
          </ul>
          <h3 className="mt-5 text-sm font-medium">Policy ids</h3>
          <div className="mt-2">
            <Table
              label="Policy ids"
              head={["Policy id", "What it decides", "Guardrail"]}
              rows={policies.rules.map((rule) => [
                <Mono key="id">{rule.id}</Mono>,
                <RuleText key="text" text={rule.text} />,
                rule.guardrail ? <Mono key="g">{rule.guardrail}</Mono> : <span className="text-muted-foreground">—</span>,
              ])}
            />
          </div>
        </Section>

        <Section
          id="tools"
          title="Customer tools"
          note={
            <>
              The {tools.length} tools of the FastMCP server, the only way the agent reaches data. Each takes the session, never a
              customer id, and a write is reported as verified only after its read. Sources: <Source path={sources.tools} /> and{" "}
              <Source path={sources.toolPurposes} /> §6.3.
            </>
          }
        >
          <Table
            label="Customer tools"
            head={["Tool", "Kind", "Purpose", "Verified with"]}
            rows={tools.map((tool) => [
              <Mono key="name">{tool.name}</Mono>,
              KIND[tool.kind],
              <Rich key="purpose" text={tool.purpose} />,
              tool.verifiedWith ? <Mono key="v">{tool.verifiedWith}</Mono> : <span className="text-muted-foreground">—</span>,
            ])}
          />
        </Section>

        <Section
          id="guardrails"
          title="Guardrails"
          note={
            <>
              {policies.guardrails.length} guardrails, each in code with a case in the evaluation set; every deny cites its id.
              Source: <Source path={`${sources.policies}`} /> <Mono>guardrails</Mono>.
            </>
          }
        >
          <Table
            label="Guardrails"
            head={["Id", "Layer", "Guardrail", "How", "Cited by"]}
            rows={policies.guardrails.map((g) => {
              const cited = rulesCiting(g.id);
              return [
                <Mono key="id">{g.id}</Mono>,
                g.layer,
                <span key="name" className="font-medium">
                  {g.name}
                </span>,
                <span key="impl" className="text-muted-foreground">
                  {g.impl}
                </span>,
                cited.length ? (
                  <span key="c" className="font-mono">
                    {cited.join(" · ")}
                  </span>
                ) : (
                  <span key="c" className="text-muted-foreground">
                    —
                  </span>
                ),
              ];
            })}
          />
        </Section>

        <Section
          id="models"
          title="Models and decision engines"
          note={
            <>
              Everything that decides, scores or advises (ADR 0021). A run with no arm is S0, with no LLM call; the S1 and S2
              ids are the defaults in <Source path={sources.config} />.
            </>
          }
        >
          <Table
            label="Model inventory"
            head={["Engine", "Kind", "Version", "Role", "Source"]}
            rows={INVENTORY.map((row) => [
              <span key="e" className="font-medium">
                {row.engine}
              </span>,
              row.kind,
              <span key="v" className="break-all font-mono">
                {row.version}
              </span>,
              row.role,
              <span key="s" className="text-muted-foreground">
                {row.source}
              </span>,
            ])}
          />
          <h3 className="mt-5 text-sm font-medium">Score providers</h3>
          <p className="mt-0.5 text-xs text-muted-foreground">
            The active provider is <Mono>{policies.scoring.provider}</Mono>. A score from a source that cannot place a zone sends the
            case to a person.
          </p>
          <div className="mt-2">
            <Table
              label="Score providers"
              head={["Provider", "Version", "Can place a zone", "Note"]}
              rows={policies.scoring.providers.map((p) => [
                <Mono key="n">{p.name}</Mono>,
                <Mono key="v">{p.version}</Mono>,
                p.decidesZone ? "yes" : "no, zone human",
                <span key="note" className="text-muted-foreground">
                  {p.note}
                </span>,
              ])}
            />
          </div>
        </Section>
      </div>
    </PageShell>
  );
}
