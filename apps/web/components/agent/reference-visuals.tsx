// Visual views of /agent's policies, tools, guardrails and model inventory (spec 04 AC-08). Every item comes from
// lib/agent-visuals.ts, derived from the generated lib/agent-reference.ts, so the same drift tests bind them to the
// sources. Each item opens the shared side panel with its details; the tables stay behind "View as table".
import { ArrowRight, Ban, Check, KeyRound, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import { ZoneBadge } from "@/components/badges";
import { codeSpans, zoneRange } from "@/lib/agent";
import { AGENT_REFERENCE } from "@/lib/agent-reference";
import { getT } from "@/lib/i18n-server";
import type { MessageKey } from "@/lib/i18n";
import { AMOUNT_GATE, GUARDRAIL_LAYERS, MODEL_GRID, SCORE_RULES, TOOL_GROUPS, ZONE_BANDS, ruleLine, type ZoneBand } from "@/lib/agent-visuals";
import { cn } from "@/lib/utils";
import { DetailField, DetailFields } from "@/components/detail-panel";
import { DetailTrigger } from "./detail-trigger";

const CHIP = "rounded-md border bg-background/40 text-left transition-colors duration-150 hover:border-primary/60 hover:bg-accent/40";
const BAND: Record<ZoneBand["name"], string> = {
  high: "border-zone-high bg-zone-high/15",
  medium: "border-zone-medium bg-zone-medium/15",
  human: "border-zone-human bg-zone-human/15",
};

export function Rich({ text }: { text: string }) {
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

const zoneOf = (name: string) => AGENT_REFERENCE.policies.zones.find((z) => z.name === name)!;

async function RuleDetail({ id, text, guardrail }: { id: string; text: string; guardrail?: string | null }) {
  const { t } = await getT();
  return (
    <DetailFields>
      <DetailField label={t("agent.ui.zones.rule")} mono>
        {id}
      </DetailField>
      <DetailField label={t("agent.ui.zones.fullRule")}>
        <Rich text={text.replaceAll("->", "→")} />
      </DetailField>
      {guardrail ? (
        <DetailField label="Guardrail" mono>
          {guardrail}
        </DetailField>
      ) : null}
    </DetailFields>
  );
}

/** Score bands → zone → decision, the amount gate beside it touching only the approval mode. */
export async function ZoneDiagram() {
  const { t } = await getT();
  const axis = [...ZONE_BANDS].reverse(); // low score on the left
  return (
    <div className="grid gap-5">
      <figure className="min-w-0">
        <figcaption className="mb-1.5 text-xs text-muted-foreground">{t("agent.ui.zones.axis")}</figcaption>
        <div className="flex items-stretch gap-1.5">
          {axis.some((b) => b.includesNull) ? (
            <div className={cn("flex shrink-0 items-center rounded-md border border-dashed px-2 text-xs", BAND.human)}>{t("agent.ui.zones.noScore")}</div>
          ) : null}
          <div className="flex min-w-0 flex-1 overflow-hidden rounded-md border">
            {axis.map((b) => (
              <div
                key={b.name}
                data-zone-band={b.name}
                className={cn("min-w-[4.75rem] border-l-2 px-2 py-2 first:border-l-0", BAND[b.name])}
                style={{ flexGrow: b.share, flexBasis: 0 }}
              >
                <ZoneBadge zone={b.name} />
                <p className="mt-1 font-mono text-xs tabular-nums">{zoneRange(zoneOf(b.name)).replace(" or no score", "")}</p>
              </div>
            ))}
          </div>
        </div>
      </figure>

      <ol className="grid gap-3 sm:grid-cols-3">
        {axis.map((b) => (
          <li key={b.name}>
            <DetailTrigger
              className={cn(CHIP, "h-full w-full border-t-4 p-3", BAND[b.name].split(" ")[0])}
              ariaLabel={`${b.name} zone: ${b.decision}. ${t("agent.ui.zones.detailOpen")}`}
              title={<>{b.rule.id}</>}
              description={`${t("agent.ui.zones.score")} ${zoneRange(zoneOf(b.name))}`}
              label={
                <>
                  <span className="flex items-center justify-between gap-2">
                    <ZoneBadge zone={b.name} />
                    <span className="font-mono text-[0.7rem] text-muted-foreground">{b.rule.id}</span>
                  </span>
                  <span className="mt-2 block font-mono text-sm [overflow-wrap:anywhere]">{b.decision}</span>
                  {b.block ? (
                    <span className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
                      {b.block === "blocks and verifies" ? <Check aria-hidden className="size-3.5 text-teal-text" /> : <Ban aria-hidden className="size-3.5" />}
                      {t("agent.ui.zones.block")}: {b.block}
                    </span>
                  ) : null}
                </>
              }
            >
              <RuleDetail id={b.rule.id} text={b.rule.text} />
            </DetailTrigger>
          </li>
        ))}
      </ol>

      <div className="grid gap-3 lg:grid-cols-2">
        <div className="rounded-md border p-3">
          <p className="text-xs font-medium">{t("agent.ui.zones.alsoHuman")}</p>
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {SCORE_RULES.map((r) => (
              <li key={r.id}>
                <DetailTrigger className={cn(CHIP, "px-2 py-1 text-xs")} title={r.id} label={<Rich text={ruleLine(r)} />} ariaLabel={`${r.id}: ${ruleLine(r)}`}>
                  <RuleDetail id={r.id} text={r.text} guardrail={r.guardrail} />
                </DetailTrigger>
              </li>
            ))}
            {AMOUNT_GATE.ticketAlways ? (
              <li>
                <DetailTrigger className={cn(CHIP, "border-brand-teal/60 px-2 py-1 text-xs")} title={AMOUNT_GATE.ticketAlways.id} label={t("agent.ui.zones.ticketAlways")}>
                  <RuleDetail id={AMOUNT_GATE.ticketAlways.id} text={AMOUNT_GATE.ticketAlways.text} />
                </DetailTrigger>
              </li>
            ) : null}
          </ul>
        </div>

        <div className="rounded-md border p-3">
          <p className="text-xs font-medium">{t("agent.ui.zones.amountGate")}</p>
          <ul className="mt-2 grid gap-1.5 text-xs">
            <GateRow target={t("agent.ui.zones.approvalMode")} changes={AMOUNT_GATE.changesApprovalMode} />
            <GateRow target={t("agent.ui.zones.clock")} changes={AMOUNT_GATE.changesClock} />
          </ul>
          <p className="mt-2 text-xs text-muted-foreground">{t("agent.ui.zones.gateNote")}</p>
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {[...AMOUNT_GATE.rules, ...(AMOUNT_GATE.clockUnknown ? [AMOUNT_GATE.clockUnknown] : [])].map((r) => (
              <li key={r.id}>
                <DetailTrigger className={cn(CHIP, "px-2 py-0.5 font-mono text-[0.7rem]")} title={r.id} label={r.id} ariaLabel={`${r.id}: ${ruleLine(r)}`}>
                  <RuleDetail id={r.id} text={r.text} guardrail={r.guardrail} />
                </DetailTrigger>
              </li>
            ))}
          </ul>
        </div>
      </div>
      <p className="font-mono text-xs text-muted-foreground">{t("agent.ui.zones.dataLabel")}</p>
    </div>
  );
}

async function GateRow({ target, changes }: { target: string; changes: boolean }) {
  const { t } = await getT();
  return (
    <li className="flex flex-wrap items-center gap-1.5">
      <span className="rounded border px-1.5 py-0.5">{t("agent.ui.zones.amountGate")}</span>
      <ArrowRight aria-hidden className={cn("size-3.5", changes ? "text-foreground" : "text-muted-foreground/60")} />
      <span className={cn("rounded border px-1.5 py-0.5", !changes && "border-dashed text-muted-foreground line-through decoration-muted-foreground/60")}>{target}</span>
      <span className={cn("inline-flex items-center gap-1", changes ? "text-teal-text" : "text-muted-foreground")}>
        {changes ? <Check aria-hidden className="size-3.5" /> : <Ban aria-hidden className="size-3.5" />}
        {changes ? t("agent.ui.zones.changes") : t("agent.ui.zones.never")}
      </span>
    </li>
  );
}

/** An icon with a tooltip that opens on hover and on keyboard focus. */
function IconTip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <span tabIndex={0} role="img" aria-label={label} className="group/tip relative inline-flex rounded-sm text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring">
      {children}
      <span
        role="tooltip"
        className="pointer-events-none invisible absolute right-0 bottom-full z-20 mb-1.5 w-max max-w-56 rounded-md border bg-popover px-2 py-1 text-xs text-popover-foreground opacity-0 transition-opacity duration-150 group-hover/tip:visible group-hover/tip:opacity-100 group-focus-visible/tip:visible group-focus-visible/tip:opacity-100 motion-reduce:transition-none"
      >
        {label}
      </span>
    </span>
  );
}

/** The customer tools grouped by what they do, with idempotency and post-condition as icons. */
export async function ToolGroups() {
  const { t } = await getT();
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {TOOL_GROUPS.map(({ group, tools }) => (
        <section key={group} aria-label={t(`agent.ui.tools.groups.${group}` as MessageKey)} className="rounded-md border p-3">
          <h3 className="flex items-baseline justify-between text-sm font-medium">
            {t(`agent.ui.tools.groups.${group}` as MessageKey)} <span className="text-xs tabular-nums text-muted-foreground">{tools.length}</span>
          </h3>
          <p className="mt-0.5 text-xs text-muted-foreground">{t(`agent.ui.tools.groupNotes.${group}` as MessageKey)}</p>
          <ul className="mt-2 grid gap-1">
            {tools.map((tool) => (
              <li key={tool.name} className="flex items-center justify-between gap-2">
                <DetailTrigger
                  className="min-w-0 truncate rounded-sm text-left font-mono text-xs underline decoration-muted-foreground/30 underline-offset-2 hover:decoration-foreground"
                  title={<span className="font-mono">{tool.name}</span>}
                  description={t(`agent.ui.tools.groups.${group}` as MessageKey)}
                  label={tool.name}
                >
                  <DetailFields>
                    <DetailField label={t("agent.ui.tools.purpose")}>
                      <Rich text={tool.purpose} />
                    </DetailField>
                    <DetailField label={t("agent.ui.tools.kind")} mono>
                      {tool.kind}
                    </DetailField>
                    <DetailField label={t("agent.ui.tools.idempotency")}>{tool.idempotent ? t("agent.ui.tools.yes") : t("agent.ui.tools.no")}</DetailField>
                    <DetailField label={t("agent.ui.tools.verifiedWith")} mono>
                      {tool.verifiedWith ?? "—"}
                    </DetailField>
                  </DetailFields>
                </DetailTrigger>
                <span className="flex shrink-0 items-center gap-1">
                  {tool.idempotent ? (
                    <IconTip label={t("agent.ui.tools.idempotent")}>
                      <KeyRound aria-hidden className="size-3.5" />
                    </IconTip>
                  ) : null}
                  {tool.verifiedWith ? (
                    <IconTip label={t("agent.ui.tools.verified", { tool: tool.verifiedWith })}>
                      <ShieldCheck aria-hidden className="size-3.5 text-teal-text" />
                    </IconTip>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

/** The guardrails as compact chips grouped by layer. */
export async function GuardrailList() {
  const { t } = await getT();
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {GUARDRAIL_LAYERS.map(({ layer, guardrails }) => (
        <section key={layer} aria-label={`${t("agent.ui.guardrails.layer")} ${layer}`} className="rounded-md border p-3">
          <h3 className="text-xs font-medium capitalize text-muted-foreground">{layer}</h3>
          <ul className="mt-2 grid gap-1.5">
            {guardrails.map((g) => (
              <li key={g.id}>
                <DetailTrigger
                  className={cn(CHIP, "flex w-full items-baseline gap-2 px-2 py-1.5 text-xs")}
                  title={<span className="font-mono">{g.id}</span>}
                  description={g.name}
                  label={
                    <>
                      <span className="shrink-0 font-mono text-[0.7rem] text-muted-foreground">{g.id}</span>
                      <span className="min-w-0">{g.name}</span>
                    </>
                  }
                >
                  <DetailFields>
                    <DetailField label={t("agent.ui.guardrails.layer")}>{g.layer}</DetailField>
                    <DetailField label={t("agent.ui.guardrails.how")}>{g.impl}</DetailField>
                    <DetailField label={t("agent.ui.guardrails.citedBy")} mono>
                      {g.citedBy.length ? g.citedBy.join(" · ") : t("agent.ui.guardrails.none")}
                    </DetailField>
                  </DetailFields>
                </DetailTrigger>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

/** The model inventory as a task × engine grid, each engine with its version. */
export async function ModelGrid() {
  const { t } = await getT();
  return (
    <div className="grid gap-2">
      {MODEL_GRID.map(({ task, engines }) => (
        <div key={task} className="grid gap-2 sm:grid-cols-[7rem_minmax(0,1fr)] sm:items-start">
          <p className="pt-2 text-xs font-medium text-muted-foreground">{t(`agent.ui.models.tasks.${task}` as MessageKey)}</p>
          <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {engines.map((row) => (
              <li key={row.engine}>
                <DetailTrigger
                  className={cn(CHIP, "h-full w-full p-2.5")}
                  title={row.engine}
                  description={row.kind}
                  label={
                    <>
                      <span className="block text-sm font-medium">{row.engine}</span>
                      <span className="mt-0.5 block text-xs text-muted-foreground">{row.kind}</span>
                      <span className="mt-1 block font-mono text-[0.7rem] [overflow-wrap:anywhere]">{row.version}</span>
                    </>
                  }
                >
                  <DetailFields>
                    <DetailField label={t("agent.ui.models.role")}>{row.role}</DetailField>
                    <DetailField label={t("agent.ui.models.version")} mono>
                      {row.version}
                    </DetailField>
                    <DetailField label={t("agent.ui.models.source")} mono>
                      {row.source}
                    </DetailField>
                  </DetailFields>
                </DetailTrigger>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
