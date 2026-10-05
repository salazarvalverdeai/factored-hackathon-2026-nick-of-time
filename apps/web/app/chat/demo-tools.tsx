"use client";

// What a live demo session adds around the conversation (spec 07 §8.6 to §8.8): the visitor's recent charges as chips,
// the test-charge form (demo type C) and the six character chips (demo type D). None of it decides anything: a chip
// sends text the visitor could type, a test charge is a labeled [simulated] row on the session's own run, and a persona
// answer is a draft in the composer, never sent on its own.
import { useState } from "react";
import { ErrorState, LoadingState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, api } from "@/lib/api";
import { PERSONAS, chipLabel, chipMessage, hasSeveralCards, parseAmount } from "@/lib/demo";
import type { Language, PersonaCharacter, PersonaDraft, RecentTransaction } from "@/lib/types";
import { useQuery } from "@/lib/use-query";

export function DemoTools({
  lang,
  mode,
  disabled,
  chosen,
  onChoose,
  onSend,
  onDraft,
}: {
  lang: Language;
  /** The session's mode: a test charge exists only in a `live` session (a replay session gets 403 and hides the form). */
  mode: "live" | "replay" | undefined;
  disabled: boolean;
  chosen: string | null;
  onChoose: (transactionId: string) => void;
  /** Sends a message as if the visitor typed it. */
  onSend: (text: string) => void;
  /** Puts a suggested message in the composer for the visitor to edit. */
  onDraft: (draft: PersonaDraft) => void;
}) {
  const txs = useQuery((a) => a.listRecentTransactions(), []);
  return (
    <div className="space-y-3">
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Pick a charge to dispute</CardTitle>
          <CardDescription>Your recent card charges. A chip sends a message that names the charge; you can also just type.</CardDescription>
        </CardHeader>
        <CardContent>
          {txs.status === "loading" ? <LoadingState label="Loading your charges…" /> : null}
          {txs.status === "error" ? <ErrorState title="Cannot load your charges" message={txs.error.message} /> : null}
          {txs.status === "ok" && txs.data.length === 0 ? <p className="text-sm text-muted-foreground">No recent charges.</p> : null}
          {txs.status === "ok" && txs.data.length > 0 ? <ChargeChips txs={txs.data} lang={lang} disabled={disabled} chosen={chosen} onChoose={onChoose} onSend={onSend} /> : null}
        </CardContent>
      </Card>
      {mode === "live" ? <TestCharge /> : null}
      <Personas chosen={chosen} disabled={disabled} onDraft={onDraft} />
    </div>
  );
}

function ChargeChips({
  txs,
  lang,
  disabled,
  chosen,
  onChoose,
  onSend,
}: {
  txs: RecentTransaction[];
  lang: Language;
  disabled: boolean;
  chosen: string | null;
  onChoose: (id: string) => void;
  onSend: (text: string) => void;
}) {
  const several = hasSeveralCards(txs);
  return (
    <ul className="flex flex-wrap gap-2">
      {txs.map((tx) => (
        <li key={tx.transaction_id}>
          <Button
            size="xs"
            variant="outline"
            disabled={disabled}
            aria-pressed={chosen === tx.transaction_id}
            onClick={() => {
              onChoose(tx.transaction_id);
              onSend(chipMessage(tx, lang, several));
            }}
            className="h-auto whitespace-normal py-1 text-left aria-pressed:border-foreground"
          >
            {chipLabel(tx)}
            {several && tx.last4 ? ` · ····${tx.last4}` : ""}
          </Button>
        </li>
      ))}
    </ul>
  );
}

/** Demo type C: a charge the visitor makes up, so the agent has something recent to dispute. Always labeled [simulated]. */
function TestCharge() {
  const [amount, setAmount] = useState("");
  const [merchant, setMerchant] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [hidden, setHidden] = useState(false);
  const parsed = parseAmount(amount);
  if (hidden) return null; // 403: this is a replay or production session, which has no test charges

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (parsed === null) return;
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      const charge = await api.registerTestCharge(parsed, merchant.trim());
      setDone(`Registered ${charge.amount.toFixed(2)} ${charge.currency} at ${charge.merchant} ${charge.label ?? "[simulated]"}`);
      setAmount("");
      setMerchant("");
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) setHidden(true);
      else if (err instanceof ApiError && err.status === 429) setError("One test charge per minute (three per session).");
      else setError(err instanceof ApiError ? err.message : "unexpected error"); // a 422 shows the api's message
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Register a test charge [simulated]</CardTitle>
        <CardDescription>Amount in your customer&apos;s currency and a store name. It shows first in the list above.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-2">
          <div className="flex flex-wrap gap-2">
            <Input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" placeholder="Amount, e.g. 1250.50" aria-label="Test charge amount" className="w-40" required />
            <Input value={merchant} onChange={(e) => setMerchant(e.target.value)} maxLength={60} placeholder="Store name" aria-label="Test charge merchant" className="min-w-40 flex-1" required />
          </div>
          <Button type="submit" size="sm" disabled={busy || parsed === null || !merchant.trim()}>
            Register
          </Button>
          {done ? <p role="status" className="text-xs text-muted-foreground">{done}</p> : null}
          {error ? <ErrorState title="Not registered" message={error} /> : null}
        </form>
      </CardContent>
    </Card>
  );
}

/** Demo type D: the answer goes into the composer as an editable draft, labeled by where it came from. */
function Personas({ chosen, disabled, onDraft }: { chosen: string | null; disabled: boolean; onDraft: (draft: PersonaDraft) => void }) {
  const [busy, setBusy] = useState<PersonaCharacter | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function pick(character: PersonaCharacter) {
    setBusy(character);
    setError(null);
    try {
      onDraft(await api.suggestPersona(character, chosen ?? undefined));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "unexpected error");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Try a type of customer</CardTitle>
        <CardDescription>Suggests a first message in that character&apos;s voice. You edit it and send it yourself.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        <ul className="flex flex-wrap gap-2">
          {PERSONAS.map((p) => (
            <li key={p.id}>
              <Button size="xs" variant="outline" disabled={disabled || busy !== null} onClick={() => pick(p.id)}>
                {busy === p.id ? "…" : p.label}
              </Button>
            </li>
          ))}
        </ul>
        {error ? <ErrorState title="No suggestion" message={error} /> : null}
      </CardContent>
    </Card>
  );
}
