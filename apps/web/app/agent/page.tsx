import type { Metadata } from "next";
import { Fragment, type ReactNode } from "react";
import { PageShell } from "@/components/page-shell";
import { AGENT_REFERENCE } from "@/lib/agent-reference";
import {
  DIAGRAM,
  REPO_URL,
  codeSpans,
  inventory,
  nextOf,
  nodeInfo,
  ruleHasMore,
  ruleSummary,
  rulesCiting,
  zoneRange,
  type GraphNode,
} from "@/lib/agent";
import { getT } from "@/lib/i18n-server";

// /agent (spec 04 AC-08, spec 02 T6): the architecture, the graph, the policy ids, the tools, the guardrails and the
// models. Every row comes from lib/agent-reference.ts, generated from the repo's sources by scripts/sync-agent.mjs.
// The page's prose follows the UI language (spec 16 AC-06); identifiers and the generated rows stay as written.
export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getT();
  return { title: t("agent.meta.title") };
}

const { policies, tools, graph, sources } = AGENT_REFERENCE;
const TH = "border-b py-2 pr-4 align-bottom font-normal";
const TD = "border-b py-2 pr-4 align-top";
const SECTIONS = ["architecture", "graph", "policies", "tools", "guardrails", "models"] as const;

/** A translated sentence whose `{name}` placeholders are filled with React nodes (links, mono spans). */
function fill(text: string, nodes: Record<string, ReactNode>): ReactNode {
  return text.split(/\{(\w+)\}/).map((part, i) => <Fragment key={i}>{i % 2 === 1 ? (nodes[part] ?? `{${part}}`) : part}</Fragment>);
}

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

function RuleText({ text, more }: { text: string; more: string }) {
  const summary = ruleSummary(text);
  const full = text.replaceAll("->", "→");
  if (!ruleHasMore(text)) return <Rich text={summary} />;
  return (
    <details className="group">
      <summary className="cursor-pointer list-none [&::-webkit-details-marker]:hidden">
        <Rich text={summary} /> <span className="text-muted-foreground underline underline-offset-2 group-open:hidden">{more}</span>
      </summary>
      <p className="mt-1.5 text-muted-foreground">
        <Rich text={full} />
      </p>
    </details>
  );
}

export default async function Page() {
  const { t, locale } = await getT();
  const start = nextOf("START").to;
  const constitution = t("agent.constitution");
  const nodes = nodeInfo(locale);
  const none = <span className="text-muted-foreground">—</span>;
  return (
    <PageShell title={t("agent.title")} description={t("agent.description")}>
      <p className="text-lg font-semibold leading-snug tracking-tight sm:text-xl">
        <span className="text-primary">{constitution.split(",")[0]},</span>
        {constitution.slice(constitution.indexOf(",") + 1)}
      </p>
      <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
        {fill(t("agent.constitutionNote"), { script: <Source path="apps/web/scripts/sync-agent.mjs" /> })}
      </p>
      <nav aria-label={t("agent.onThisPage")} className="mt-4 flex flex-wrap gap-1.5 text-sm">
        {SECTIONS.map((id) => (
          <a key={id} href={`#${id}`} className="rounded-md border px-2.5 py-1 text-muted-foreground hover:bg-accent hover:text-foreground">
            {t(`agent.nav.${id}` as const)}
          </a>
        ))}
      </nav>

      <div className="mt-6 grid gap-6">
        <Section
          id="architecture"
          title={t("agent.architecture.title")}
          note={fill(t("agent.architecture.note"), { source: <Source path={DIAGRAM.source} /> })}
        >
          <a href={DIAGRAM.src} className="block overflow-hidden rounded-md border bg-white" aria-label={t("agent.architecture.open")}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={DIAGRAM.src} alt={t("agent.architecture.alt")} className="h-auto w-full" width={1500} height={1010} />
          </a>
        </Section>

        <Section
          id="graph"
          title={t("agent.graph.title", { name: graph.name })}
          note={fill(t("agent.graph.note"), {
            count: graph.nodes.length,
            start: <Mono>{start.join(", ")}</Mono>,
            end: <Mono>{graph.edges.find((e) => (e.to as readonly string[]).includes("END"))?.from}</Mono>,
            source: <Source path={sources.graph} />,
          })}
        >
          <Table
            label={t("agent.graph.label")}
            head={["#", t("agent.graph.head.node"), t("agent.graph.head.does"), t("agent.graph.head.next")]}
            rows={graph.nodes.map((node, i) => {
              const next = nextOf(node);
              return [
                <span key="n" className="tabular-nums text-muted-foreground">
                  {i + 1}
                </span>,
                <Mono key="id">{node}</Mono>,
                nodes[node as GraphNode],
                <span key="next" className="font-mono">
                  {next.conditional ? <span className="font-sans text-muted-foreground">{t("agent.graph.oneOf")}</span> : null}
                  {next.to.join(" · ")}
                </span>,
              ];
            })}
          />
        </Section>

        <Section
          id="policies"
          title={t("agent.policies.title")}
          note={fill(t("agent.policies.note"), {
            source: <Source path={sources.policies} />,
            version: policies.version,
            default: <Mono>default: {policies.default}</Mono>,
            count: policies.rules.length,
          })}
        >
          <h3 className="text-sm font-medium">{t("agent.policies.zonesTitle")}</h3>
          <ul className="mt-2 flex flex-wrap gap-2 text-xs">
            {policies.zones.map((zone) => (
              <li key={zone.name} className="rounded-md border px-2.5 py-1.5">
                <span className="font-medium">{zone.name}</span>{" "}
                <span className="text-muted-foreground">{t("agent.policies.score", { range: zoneRange(zone, locale) })}</span>
              </li>
            ))}
            <li className="self-center font-mono text-muted-foreground">[data] thresholds from the EDA, policies.yaml zones</li>
          </ul>
          <h3 className="mt-5 text-sm font-medium">{t("agent.policies.idsTitle")}</h3>
          <div className="mt-2">
            <Table
              label={t("agent.policies.idsTitle")}
              head={[t("agent.policies.head.id"), t("agent.policies.head.decides"), t("agent.policies.head.guardrail")]}
              rows={policies.rules.map((rule) => [
                <Mono key="id">{rule.id}</Mono>,
                <RuleText key="text" text={rule.text} more={t("agent.common.fullRule")} />,
                rule.guardrail ? <Mono key="g">{rule.guardrail}</Mono> : none,
              ])}
            />
          </div>
        </Section>

        <Section
          id="tools"
          title={t("agent.tools.title")}
          note={fill(t("agent.tools.note"), {
            count: tools.length,
            tools: <Source path={sources.tools} />,
            purposes: <Source path={sources.toolPurposes} />,
          })}
        >
          <Table
            label={t("agent.tools.title")}
            head={[t("agent.tools.head.tool"), t("agent.tools.head.kind"), t("agent.tools.head.purpose"), t("agent.tools.head.verified")]}
            rows={tools.map((tool) => [
              <Mono key="name">{tool.name}</Mono>,
              t(`agent.tools.kind.${tool.kind}` as const),
              <Rich key="purpose" text={tool.purpose} />,
              tool.verifiedWith ? <Mono key="v">{tool.verifiedWith}</Mono> : none,
            ])}
          />
        </Section>

        <Section
          id="guardrails"
          title={t("agent.guardrails.title")}
          note={fill(t("agent.guardrails.note"), {
            count: policies.guardrails.length,
            source: <Source path={`${sources.policies}`} />,
            key: <Mono>guardrails</Mono>,
          })}
        >
          <Table
            label={t("agent.guardrails.title")}
            head={[
              t("agent.guardrails.head.id"),
              t("agent.guardrails.head.layer"),
              t("agent.guardrails.head.guardrail"),
              t("agent.guardrails.head.how"),
              t("agent.guardrails.head.cited"),
            ]}
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
          title={t("agent.models.title")}
          note={fill(t("agent.models.note"), { source: <Source path={sources.config} /> })}
        >
          <Table
            label={t("agent.models.label")}
            head={[
              t("agent.models.head.engine"),
              t("agent.models.head.kind"),
              t("agent.models.head.version"),
              t("agent.models.head.role"),
              t("agent.models.head.source"),
            ]}
            rows={inventory(locale).map((row) => [
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
          <h3 className="mt-5 text-sm font-medium">{t("agent.models.providersTitle")}</h3>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {fill(t("agent.models.providersNote"), { provider: <Mono>{policies.scoring.provider}</Mono> })}
          </p>
          <div className="mt-2">
            <Table
              label={t("agent.models.providersTitle")}
              head={[
                t("agent.models.providersHead.provider"),
                t("agent.models.providersHead.version"),
                t("agent.models.providersHead.canPlace"),
                t("agent.models.providersHead.note"),
              ]}
              rows={policies.scoring.providers.map((p) => [
                <Mono key="n">{p.name}</Mono>,
                <Mono key="v">{p.version}</Mono>,
                p.decidesZone ? t("agent.common.yes") : t("agent.common.noZoneHuman"),
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
