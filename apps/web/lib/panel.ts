// "As-is vs with Nick of Time" panel of /evaluation (spec 12 AC-10). Pure, so `npm test` covers it.
// AS-IS is the bank's own contact data [data] (pitch_numbers.json); WITH US is the harness [simulated]
// (evaluation_summary.json, arm S1); the contacts avoided are [projected] from those two inputs only.
import { developmentNotice, type EvaluationData, type Insight, type Rate } from "./evaluation.ts";

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

export type Projection = { contacts: number; fcrWithUs: number; fcrAsIs: number; volume: number };

/** [projected]: if the run's rate held on the bank's complaint contacts, the extra contacts resolved at first contact. */
export function project(fcrAsIsPct: number, volume: number, withUsRate: number): Projection {
  const contacts = Math.round(Math.max(0, withUsRate - fcrAsIsPct / 100) * volume);
  return { contacts, fcrWithUs: withUsRate, fcrAsIs: fcrAsIsPct / 100, volume };
}

export type PanelState = { kind: "pending"; reason: string } | { kind: "ready"; rate: Rate; projection: Projection | null };

/** spec 12 AC-10: WITH US needs a sealed held-out run; otherwise "results pending", with no figure and no projection. */
export function panelState(file: Insight<EvaluationData> | null, contacts: PitchContacts): PanelState {
  if (!file) return { kind: "pending", reason: "Missing evaluation_summary.json, written by the evaluation harness (spec 10)." };
  if (developmentNotice(file.data)) return { kind: "pending", reason: "The run is not the sealed held-out yet (spec 12 AC-05)." };
  const rate = file.data.arms.find((a) => a.arm === WITH_US_ARM)?.overall.safe_automated_resolution;
  if (!rate || rate.value === null) return { kind: "pending", reason: `No ${WITH_US_ARM} result for safe automated resolution.` };
  const fcr = contacts.find((c) => c.key === "fcr")?.groups.find((g) => g.name === COMPLAINTS);
  return { kind: "ready", rate, projection: fcr ? project(fcr.value, fcr.denominator, rate.value) : null };
}
