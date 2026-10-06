"use client";

// What a live demo session adds around the conversation (spec 07 §8.6 to §8.8): the visitor's recent charges as chips,
// the test-charge form (demo type C) and the six character chips (demo type D). None of it decides anything: a chip
// sends text the visitor could type, a test charge is a synthetic row on the session's own run (named "test charge" in
// plain words, spec 07 AC-14), and a persona
// answer is a draft in the composer, never sent on its own.
import { useState } from "react";
import { CHAT_STRINGS } from "@/lib/chat-strings";
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
          <CardTitle className="text-sm">{CHAT_STRINGS.pickTitle[lang]}</CardTitle>
          <CardDescription>{CHAT_STRINGS.pickDescription[lang]}</CardDescription>
        </CardHeader>
        <CardContent>
          {txs.status === "loading" ? <LoadingState label={CHAT_STRINGS.loadingCharges[lang]} /> : null}
          {txs.status === "error" ? <ErrorState title={CHAT_STRINGS.cannotLoadCharges[lang]} message={txs.error.message} /> : null}
          {txs.status === "ok" && txs.data.length === 0 ? <p className="text-sm text-muted-foreground">{CHAT_STRINGS.noCharges[lang]}</p> : null}
          {txs.status === "ok" && txs.data.length > 0 ? <ChargeChips txs={txs.data} lang={lang} disabled={disabled} chosen={chosen} onChoose={onChoose} onSend={onSend} /> : null}
        </CardContent>
      </Card>
      {mode === "live" ? <TestCharge lang={lang} /> : null}
      <Personas lang={lang} chosen={chosen} disabled={disabled} onDraft={onDraft} />
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
            {chipLabel(tx, CHAT_STRINGS.testChargeTag[lang])}
            {several && tx.last4 ? ` · ····${tx.last4}` : ""}
          </Button>
        </li>
      ))}
    </ul>
  );
}

/** Demo type C: a charge the visitor makes up, so the agent has something recent to dispute. Always called a test charge. */
function TestCharge({ lang }: { lang: Language }) {
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
      setDone(CHAT_STRINGS.registered[lang](charge.amount.toFixed(2), charge.currency, charge.merchant ?? ""));
      setAmount("");
      setMerchant("");
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) setHidden(true);
      else if (err instanceof ApiError && err.status === 429) setError(CHAT_STRINGS.rateLimited[lang]);
      else setError(err instanceof ApiError ? err.message : CHAT_STRINGS.unexpectedError[lang]); // a 422 shows the api's message
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">{CHAT_STRINGS.testTitle[lang]}</CardTitle>
        <CardDescription>{CHAT_STRINGS.testDescription[lang]}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-2">
          <div className="flex flex-wrap gap-2">
            <Input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" placeholder={CHAT_STRINGS.amountPlaceholder[lang]} aria-label={CHAT_STRINGS.amountLabel[lang]} className="w-40" required />
            <Input value={merchant} onChange={(e) => setMerchant(e.target.value)} maxLength={60} placeholder={CHAT_STRINGS.merchantPlaceholder[lang]} aria-label={CHAT_STRINGS.merchantLabel[lang]} className="min-w-40 flex-1" required />
          </div>
          <Button type="submit" size="sm" disabled={busy || parsed === null || !merchant.trim()}>
            {CHAT_STRINGS.register[lang]}
          </Button>
          {done ? <p role="status" className="text-xs text-muted-foreground">{done}</p> : null}
          {error ? <ErrorState title={CHAT_STRINGS.notRegistered[lang]} message={error} /> : null}
        </form>
      </CardContent>
    </Card>
  );
}

/** Demo type D: the answer goes into the composer as an editable draft, labeled by where it came from. */
function Personas({ lang, chosen, disabled, onDraft }: { lang: Language; chosen: string | null; disabled: boolean; onDraft: (draft: PersonaDraft) => void }) {
  const [busy, setBusy] = useState<PersonaCharacter | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function pick(character: PersonaCharacter) {
    setBusy(character);
    setError(null);
    try {
      onDraft(await api.suggestPersona(character, chosen ?? undefined));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : CHAT_STRINGS.unexpectedError[lang]);
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">{CHAT_STRINGS.personasTitle[lang]}</CardTitle>
        <CardDescription>{CHAT_STRINGS.personasDescription[lang]}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        <ul className="flex flex-wrap gap-2">
          {PERSONAS.map((p) => (
            <li key={p.id}>
              <Button size="xs" variant="outline" disabled={disabled || busy !== null} onClick={() => pick(p.id)}>
                {busy === p.id ? "…" : CHAT_STRINGS.personas[p.id][lang]}
              </Button>
            </li>
          ))}
        </ul>
        {error ? <ErrorState title={CHAT_STRINGS.noSuggestion[lang]} message={error} /> : null}
      </CardContent>
    </Card>
  );
}
