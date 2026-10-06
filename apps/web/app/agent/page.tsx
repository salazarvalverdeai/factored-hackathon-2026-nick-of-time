import type { Metadata } from "next";
import type { ReactNode } from "react";
import { ArchitectureView } from "@/components/agent/architecture-view";
import { DetailTrigger } from "@/components/agent/detail-trigger";
import { GraphView } from "@/components/agent/graph-view";
import { GuardrailList, ModelGrid, Rich, ToolGroups, ZoneDiagram } from "@/components/agent/reference-visuals";
import { PageShell } from "@/components/page-shell";
import { AGENT_REFERENCE } from "@/lib/agent-reference";
import { AGENT_UI, fill } from "@/lib/agent-strings";
import {
  CONSTITUTION,
  DIAGRAM,
  INVENTORY,
  NODE_INFO,
  REPO_URL,
  nextOf,
  ruleHasMore,
  ruleSummary,
  rulesCiting,
  type GraphNode,
} from "@/lib/agent";

// /agent (spec 04 AC-08, spec 02 T6): the architecture, the graph, the policies, the tools, the guardrails and the
// models, each as a visual with one plain line; the tables stay behind "View as table" and the details open in the
// shared side panel. Every view comes from lib/agent-reference.ts, generated from the repo's sources by
// scripts/sync-agent.mjs, so the same drift tests bind the visuals and the tables.
export const metadata: Metadata = { title: "Agent" };

const { policies, tools, graph, sources } = AGENT_REFERENCE;
const P = AGENT_UI.page;
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

/** A section: its title, one plain line, a "Detail →" that opens the sources in the side panel, then the visual. */
function Section({ id, title, line, detail, children }: { id: string; title: string; line: string; detail: ReactNode; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="min-w-0 scroll-mt-20 rounded-lg border bg-card p-4 text-card-foreground sm:p-5">
      <h2 id={`${id}-title`} className="text-base font-semibold">
        {title}
      </h2>
      <p className="mt-0.5 text-sm text-muted-foreground">
        {line}{" "}
        <DetailTrigger
          className="whitespace-nowrap rounded-sm underline underline-offset-2 hover:text-foreground"
          ariaLabel={`${title}: ${P.sources}`}
          title={title}
          description={P.sources}
          label={P.detail}
        >
          <div className="grid gap-3 text-muted-foreground">{detail}</div>
        </DetailTrigger>
      </p>
      <div className="mt-4">{children}</div>
    </section>
  );
}

/** A table behind a disclosure, collapsed by default; the summary is keyboard reachable. */
function AsTable({ label, head, rows }: { label: string; head: string[]; rows: ReactNode[][] }) {
  return (
    <details className="group mt-4">
      <summary className="w-fit cursor-pointer rounded-sm text-sm text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring">
        {P.viewAsTable} <span className="text-xs">({label})</span>
      </summary>
      <div className="mt-2 overflow-x-auto">
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
    </details>
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

const Dash = () => <span className="text-muted-foreground">—</span>;

export default function Page() {
  const start = nextOf("START").to;
  const last = graph.edges.find((e) => (e.to as readonly string[]).includes("END"))?.from;
  return (
    <PageShell title="Agent" description="How a dispute turn runs: the graph, the policy that decides, the tools that act and the models.">
      <p className="text-lg font-semibold leading-snug tracking-tight sm:text-xl">
        <span className="text-primary">{CONSTITUTION.split(",")[0]},</span>
        {CONSTITUTION.slice(CONSTITUTION.indexOf(",") + 1)}
      </p>
      <p className="mt-2 max-w-3xl text-sm text-muted-foreground">{P.lead}</p>
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
          line={P.lines.architecture}
          detail={
            <>
              <p>
                Services from <Source path="docs/infrastructure.md" />, <Source path="infra/compose.yml" /> and{" "}
                <Source path="infra/caddy/Caddyfile" />; the drawing&apos;s data is <Source path="apps/web/lib/agent-architecture.ts" />.
              </p>
              <p>
                The static diagram is <Source path={DIAGRAM.source} />, as shown in the README. Where a diagram and the tables differ, the
                tables are current.
              </p>
            </>
          }
        >
          <ArchitectureView />
          <p className="mt-3 text-xs text-muted-foreground">
            <a href={DIAGRAM.src} className="underline decoration-muted-foreground/40 underline-offset-2 hover:text-foreground">
              {AGENT_UI.arch.staticView}
            </a>{" "}
            {AGENT_UI.arch.staticNote}
          </p>
        </Section>

        <Section
          id="graph"
          title={`Graph ${graph.name}`}
          line={fill(P.lines.graph, { nodes: graph.nodes.length })}
          detail={
            <>
              <p>
                The run starts at <Mono>{start.join(", ")}</Mono> and ends after <Mono>{last}</Mono>. Each branch label is read from the
                graph&apos;s routers. Source: <Source path={sources.graph} />.
              </p>
              <p>
                Generated by <Source path="apps/web/scripts/sync-agent.mjs" />; the web tests fail when it drifts from the graph.
              </p>
            </>
          }
        >
          <GraphView />
          <AsTable
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
        </Section>

        <Section
          id="policies"
          title="Policies"
          line={P.lines.policies}
          detail={
            <>
              <p>
                <Source path={sources.policies} /> version {policies.version}, <Mono>default: {policies.default}</Mono>. Every decision cites one
                of its {policies.rules.length} policy ids; the LLM never reads or edits the file.
              </p>
              <p>The zone thresholds come from the EDA [data]; the amount gate tiers are provisional [assumption].</p>
            </>
          }
        >
          <ZoneDiagram />
          <AsTable
            label="Policy ids"
            head={["Policy id", "What it decides", "Guardrail"]}
            rows={policies.rules.map((rule) => [
              <Mono key="id">{rule.id}</Mono>,
              <RuleText key="text" text={rule.text} />,
              rule.guardrail ? <Mono key="g">{rule.guardrail}</Mono> : <Dash key="g" />,
            ])}
          />
        </Section>

        <Section
          id="tools"
          title="Customer tools"
          line={fill(P.lines.tools, { count: tools.length })}
          detail={
            <>
              <p>
                The tools of the FastMCP server. Each takes the session, never a customer id; writes take an idempotency key and are reported
                as verified only after their read.
              </p>
              <p>
                Sources: <Source path={sources.tools} /> and <Source path={sources.toolPurposes} /> §6.3.
              </p>
            </>
          }
        >
          <ToolGroups />
          <AsTable
            label="Customer tools"
            head={["Tool", "Kind", "Purpose", "Verified with"]}
            rows={tools.map((tool) => [
              <Mono key="name">{tool.name}</Mono>,
              KIND[tool.kind],
              <Rich key="purpose" text={tool.purpose} />,
              tool.verifiedWith ? <Mono key="v">{tool.verifiedWith}</Mono> : <Dash key="v" />,
            ])}
          />
        </Section>

        <Section
          id="guardrails"
          title="Guardrails"
          line={fill(P.lines.guardrails, { count: policies.guardrails.length })}
          detail={
            <p>
              Every deny cites its guardrail id. Source: <Source path={sources.policies} /> <Mono>guardrails</Mono>.
            </p>
          }
        >
          <GuardrailList />
          <AsTable
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
                  <Dash key="c" />
                ),
              ];
            })}
          />
        </Section>

        <Section
          id="models"
          title="Models and decision engines"
          line={P.lines.models}
          detail={
            <>
              <p>
                The model inventory of ADR 0021. A run with no arm is S0, with no LLM call; the S1 and S2 ids are the defaults in{" "}
                <Source path={sources.config} />.
              </p>
              <p>
                The active score provider is <Mono>{policies.scoring.provider}</Mono>. A score from a source that cannot place a zone sends the
                case to a person.
              </p>
            </>
          }
        >
          <ModelGrid />
          <AsTable
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
          <AsTable
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
        </Section>
      </div>
    </PageShell>
  );
}
