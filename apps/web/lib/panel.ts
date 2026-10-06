// "As-is vs with Nick of Time" panel of /evaluation (spec 12 AC-10). Pure, so `npm test` covers it.
// AS-IS is the bank's own contact data [data] (pitch_numbers.json); WITH US is the harness [simulated]
// (evaluation_summary.json, arm S1); the contacts avoided are [projected] from those two inputs only.
// On the sealed held-out the panel shows both scores of ADR 0031 (spec 10 AC-15): the official sealed-rules score and
// the secondary D-070 score, each with its own projection. The secondary is never relabeled as official (D-083).
import {
  ARM_MODEL_NOTE,
  D070_SENTENCE,
  OFFICIAL_LABEL,
  SECONDARY_LABEL,
  developmentNotice,
  type BenchmarkData,
  type EvaluationData,
  type Insight,
  type Rate,
} from "./evaluation.ts";

type Group = { name: string; value: number; denominator: number };
export type PitchContacts = { key: string; label: string; unit: string; groups: Group[] }[];

export const WITH_US_ARM = "S1";
export const COMPLAINTS = "Complaint contacts";
export const BANK = "Whole bank";

export type AsIsRow = { key: string; label: string; unit: string; complaints: number; bank: number };

/** The bank's rows as they are in pitch_numbers.json; a missing row or group is skipped, never defaulted. */
export function asIsRows(contacts: PitchContacts): AsIsRow[] {
  return contacts.flatMap((c) => {
    const complaints = c.groups.find((g) => g.name === COMPLAINTS);
    const bank = c.groups.find((g) => g.name === BANK);
    return complaints && bank ? [{ key: c.key, label: c.label, unit: c.unit, complaints: complaints.value, bank: bank.value }] : [];
  });
}

export type Projection = { low: number; high: number; fcrAsIs: number; volume: number };

const avoided = (fcrAsIsPct: number, volume: number, rate: number) => Math.round(Math.max(0, rate - fcrAsIsPct / 100) * volume);

/**
 * [projected]: a range from the rate's 95% CI. The rate is measured only on the runs that end in an automatic block
 * and case, so applying it to every complaint contact is an upper-bound illustration, never a forecast.
 */
export function project(fcrAsIsPct: number, volume: number, rate: Rate): Projection {
  const value = rate.value ?? 0;
  return { low: avoided(fcrAsIsPct, volume, rate.ci_low ?? value), high: avoided(fcrAsIsPct, volume, rate.ci_high ?? value), fcrAsIs: fcrAsIsPct / 100, volume };
}

/** The benchmark's no-LLM arm (spec 15 B0). */
export const NO_LLM_ARM = "b0_rules";
export const PENDING_NOTE = `arm ${WITH_US_ARM} (lean-rule result pending)`;

/**
 * The arm whose model graph is the model the benchmark chose for "understand". When benchmark.json has a choice but
 * no held-out arm runs it, the note says what the benchmark kept and which arm is shown. "lean-rule result pending"
 * only when there is no benchmark choice at all.
 */
export function withUsArm(arms: EvaluationData["arms"], benchmark: BenchmarkData | null) {
  const chosen = benchmark?.model_map?.understand?.chosen;
  const production = chosen ? arms.find((a) => a.run_meta.model_graph?.includes(chosen)) : undefined;
  if (production) return { arm: production, note: null };
  const fallback = arms.find((a) => a.arm === WITH_US_ARM);
  if (!chosen) return { arm: fallback, note: PENDING_NOTE };
  const kept = chosen === NO_LLM_ARM ? "B0 kept: no arm meets the floors (spec 15)" : `${chosen} chosen (spec 15), not run on the held-out`;
  return { arm: fallback, note: `${kept}; held-out arm shown: ${WITH_US_ARM} = ${ARM_MODEL_NOTE[WITH_US_ARM]} (D-080)` };
}

export type PanelScore = { key: "official" | "secondary"; label: string; rate: Rate; n: number; projection: Projection | null };

export type PanelState =
  | { kind: "pending"; reason: string }
  | {
      kind: "ready";
      arm: string;
      note: string | null;
      /** The official score (sealed rules), as before. */
      rate: Rate;
      n: number;
      projection: Projection | null;
      /** Official first; the secondary D-070 score only when the file has `scores_d070` for this arm. */
      scores: PanelScore[];
      /** ADR 0031's reason for the two scores, shown with them; null with a single score. */
      sentence: string | null;
    };

/** spec 12 AC-10: WITH US needs a sealed held-out run; otherwise "results pending", with no figure and no projection. */
export function panelState(file: Insight<EvaluationData> | null, contacts: PitchContacts, benchmark: BenchmarkData | null = null): PanelState {
  if (!file) return { kind: "pending", reason: "Missing evaluation_summary.json, written by the evaluation harness (spec 10)." };
  if (developmentNotice(file.data)) return { kind: "pending", reason: "The run is not the sealed held-out yet (spec 12 AC-05)." };
  const { arm, note } = withUsArm(file.data.arms, benchmark);
  const rate = arm?.overall.safe_automated_resolution;
  if (!arm || !rate || rate.value === null) return { kind: "pending", reason: "No result for safe automated resolution." };
  const fcr = contacts.find((c) => c.key === "fcr")?.groups.find((g) => g.name === COMPLAINTS);
  const score = (key: PanelScore["key"], label: string, r: Rate): PanelScore => ({
    key,
    label,
    rate: r,
    n: r.denominator,
    projection: fcr ? project(fcr.value, fcr.denominator, r) : null,
  });
  const d070 = file.data.scores_d070?.arms?.[arm.arm];
  const official = score("official", OFFICIAL_LABEL, d070?.official?.safe_automated_resolution ?? rate);
  const secondaryRate = d070?.secondary?.safe_automated_resolution;
  const scores = secondaryRate && secondaryRate.value !== null ? [official, score("secondary", SECONDARY_LABEL, secondaryRate)] : [official];
  return {
    kind: "ready",
    arm: arm.arm,
    note,
    rate: official.rate,
    n: official.n,
    projection: official.projection,
    scores,
    sentence: scores.length > 1 ? D070_SENTENCE : null,
  };
}
