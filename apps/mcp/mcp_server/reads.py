"""Read tools over gold (spec 03 T2 and T3): `get_customer_profile`, `search_transaction`, `get_fraud_score`,
`compute_deadline`, `convert_amount`. Each handler takes the customer only from `call.session` (constitution #3); a
transaction outside that customer's cards is NOT_FOUND, whoever owns it. Facts are returned as stored: exact amount,
original currency. "Today" comes only from `clock.today(mode, country)` (ADR 0020).
"""
from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable, Iterable
from typing import Any, Optional

from contracts import tools as t
from mcp_server.gate import UNAVAILABLE, Call, Handler
from mcp_server.gold import Gold, GoldCustomer, GoldTransaction
from nick_of_time.nlu.text import fold
from nick_of_time.policy import Policies, clock
from nick_of_time.store import is_demo_run

# gold customers.country, folded → the code of policies.yaml `countries` (spec 03 §6, compute_deadline)
COUNTRY = {"mexico": "MX", "argentina": "AR", "colombia": "CO", "brasil": "BR", "brazil": "BR", "peru": "PE",
           "chile": "CL"}
PRODUCT = {"Tarjeta Débito": "debit", "Tarjeta Crédito": "credit"}   # spec 02 §4.3 product mapping
STATUSES = ("Approved", "Pending")                                # Q2: Declined and Reversed are never candidates
TOLERANCE, NO_DATE_DAYS, MAX_CANDIDATES = 0.02, 30, 4
STOP = frozenset("de del la las el los y e en da das do dos em".split())   # [assumption] merchant tokens to ignore
NOT_FOUND = t.ToolError(code="NOT_FOUND", message="No such transaction among your cards.")
# A refusal answered as NOT_FOUND: the gate logs it as a denial and strips the policy id (scope.cross_customer_request)
PROBE = NOT_FOUND.model_copy(update={"policy_id": "POL-CROSS-CUSTOMER"})
# [assumption] ComputeDeadlineOut requires a source, so "no verified entry" is this error, never an invented date: the
# case is still opened and a person decides (spec 02 AC-14); UNAVAILABLE keeps the policy id visible to the agent
NO_CLOCK = t.ToolError(code="UNAVAILABLE", policy_id=clock.UNKNOWN,
                       message="No verified legal deadline for this country; a person sets it.")
Converter = Callable[[float, str, str], Optional[dict[str, Any]]]   # spec 02 §6 fx.convert(amount, from, to)


def no_verified_rate(amount: float, from_currency: str, to_currency: str) -> None:
    """[assumption] the default until spec 02 T7 ships fx.convert with official rates: no verified rate, so nothing is
    converted (ADR 0019). The amount_gate rates serve only search matching and the internal amount_usd fill; they are
    never shown to a customer (spec 02 §4.2), so convert_amount never uses them."""
    return None


def mask(channel: str, address: str) -> str:
    """AC-11 [assumption]: e-mail `a···@domain`, Telegram `···` + its last 4 characters."""
    if channel == "email":
        local, _, domain = address.partition("@")
        return f"{local[:1]}···@{domain}"
    return "···" + address[-4:]


def _tokens(text: Optional[str]) -> set[str]:
    return set(re.findall(r"\w+", fold(text or ""))) - STOP


def _code(country: Optional[str]) -> Optional[str]:
    folded = fold(country or "").strip()
    return COUNTRY.get(folded, folded.upper() or None)


def read_handlers(gold: Gold, policies: Policies, *, channels: Optional[Callable[[str], Iterable[Any]]] = None,
                  convert: Converter = no_verified_rate,
                  utc_now: Optional[Callable[[], dt.datetime]] = None) -> dict[str, Handler]:
    """`channels(customer_id)` yields the store's customer channels (task 01g, PR #87) with `channel`, `address` and
    `confirmed`; without it no channel is listed [assumption]. `utc_now` serves tests; without it `clock.today` reads
    the real date, and only in live mode."""
    gates = policies.amount_gate.by_country

    def today(call: Call, country: str) -> dt.date:
        return clock.today(call.session.mode, country, utc_now=utc_now() if utc_now else None, policies=policies)

    def customer(call: Call) -> Optional[tuple[GoldCustomer, str]]:
        row = gold.customer(call.session.customer_id)
        country = _code(row.country) if row else None
        return (row, country) if country in gates else None

    def display_currency(call: Call, country: str) -> str:
        preferred = call.session.display_currency           # the session preference, else the country's currency
        return preferred if preferred and re.fullmatch(r"[A-Z]{3}", preferred) else gates[country].currency

    def profile(call: Call, args: t.GetCustomerProfileIn):
        found = customer(call)
        if found is None or call.session.language not in ("es", "pt"):
            return UNAVAILABLE                              # no fact to state: never a guess
        row, country = found
        # channels are per customer, and a demo customer is shared by every visitor: a demo run lists none (ADR 0026)
        linked = channels(row.customer_id) if channels and not is_demo_run(call.session.run_id) else ()
        listed = [t.ConfirmedChannel(channel=c.channel, masked_address=mask(c.channel, c.address))
                  for c in linked if c.confirmed]
        # the name the demo visitor typed (stored on the session, ADR 0026), else gold's: a tool fact either way
        name = call.session.display_name or row.first_name
        return t.GetCustomerProfileOut(first_name=name, language=call.session.language, country=country,
                                       display_currency=display_currency(call, country), channels=listed)

    def usd(trx: GoldTransaction) -> Optional[float]:
        """Internal: for matching and `Transaction.amount_usd`, which is never rendered to the customer (spec 03 §6)."""
        if trx.currency == "USD":
            return trx.amount
        if trx.amount_usd is not None:
            return trx.amount_usd
        # [assumption] gold leaves amount_usd null on some ARS/COP rows; the dataset's fixed rate (350, 4000) fills it
        rate = next((g.usd_rate for g in gates.values() if g.currency == trx.currency), None)
        return round(trx.amount / rate, 2) if rate else None

    def amount_error(said: float, currency: Optional[str], trx: GoldTransaction, country: str) -> Optional[float]:
        """AC-07: the smallest relative gap in the transaction currency or, through the policy rate, in the customer's
        local currency; None beyond ±2%."""
        local, stored = gates[country], []
        if currency in (None, trx.currency):
            stored.append(trx.amount)
        if currency in (None, local.currency) and trx.currency != local.currency and usd(trx) is not None:
            stored.append(usd(trx) * local.usd_rate)
        gaps = [abs(said - value) / value for value in stored if value > 0]
        return min((g for g in gaps if g <= TOLERANCE), default=None)

    def search(call: Call, args: t.SearchTransactionIn):
        found = customer(call)
        if found is None:
            return UNAVAILABLE
        row, country = found
        now = today(call, country)          # live: the country's real date; demo_transactions wait for AC-14 (P1)
        anchor = args.approx_date or now
        start, end = ((anchor - dt.timedelta(days=args.window_days), anchor + dt.timedelta(days=args.window_days))
                      if args.approx_date else (now - dt.timedelta(days=NO_DATE_DAYS), now))
        wanted, ranked = _tokens(args.merchant), []
        for trx in gold.transactions(row.customer_id, start, min(end, now), STATUSES):
            gap = 0.0 if args.amount is None else amount_error(args.amount, args.currency, trx, country)
            similarity = len(wanted & _tokens(trx.merchant)) / len(wanted) if wanted else 0.0
            if gap is None or (wanted and trx.merchant and not similarity) or usd(trx) is None:
                continue                                    # a null merchant still matches on amount and date
            ranked.append(((gap, abs((trx.transaction_date - anchor).days), -similarity, trx.transaction_id), trx))
        return t.SearchTransactionOut(candidates=[t.Transaction(
            transaction_id=trx.transaction_id, product_id=trx.product_id, transaction_date=trx.transaction_date,
            amount=trx.amount, currency=trx.currency, amount_usd=usd(trx), merchant=trx.merchant,
            transaction_status=trx.transaction_status) for _, trx in sorted(ranked)[:MAX_CANDIDATES]])

    def score(call: Call, args: t.GetFraudScoreIn):
        trx = gold.transaction(call.session.customer_id, args.transaction_id)
        if trx is None:                                     # unknown or another customer's: the same answer
            return PROBE if gold.owner(args.transaction_id) else NOT_FOUND
        return t.GetFraudScoreOut(transaction_id=trx.transaction_id, score=trx.fraud_score, source="dataset",
                                  version=policies.scoring.providers["dataset"]["version"])

    def deadline(call: Call, args: t.ComputeDeadlineIn):
        """Spec 03 §6: delegates to `clock.deadline()` (spec 02 §4.3), opened today in the customer's country."""
        trx = gold.transaction(call.session.customer_id, args.transaction_id)
        if trx is None:                                     # unknown or another customer's: the same answer
            return PROBE if gold.owner(args.transaction_id) else NOT_FOUND
        row = gold.customer(call.session.customer_id)
        if row is None:
            return UNAVAILABLE
        country = _code(row.country)
        if country not in policies.countries:               # no code, no time zone, no verified entry (spec 02 AC-14)
            return NO_CLOCK
        where = _code(trx.transaction_country)              # [assumption] an unknown place is not abroad: 45, not 180
        # [assumption] the gold date, not its naive timestamp: spec 02 §4.3's date rule settles a UTC date shift
        found = clock.deadline(country, PRODUCT[trx.product_type], today(call, country),
                               abroad=where is not None and where != country, charged_at=trx.transaction_date,
                               policies=policies)
        if not (found.source_url and found.deadline_source and found.verified_on):
            return NO_CLOCK                                 # POL-CLOCK-UNKNOWN: no date is invented
        return t.ComputeDeadlineOut(country=country, product=found.product, credit_deadline=found.credit_deadline,
                                    ruling_deadline=found.ruling_deadline, deadline_source=found.deadline_source,
                                    deadline_source_label=clock.source_label(found.deadline_source,
                                                                             call.session.language, policies),
                                    source_url=found.source_url, verified_on=found.verified_on)

    def convert_amount(call: Call, args: t.ConvertAmountIn):
        to = args.to_currency
        if to is None:
            found = customer(call)
            if found is None:
                return UNAVAILABLE
            to = display_currency(call, found[1])
        result = convert(args.amount, args.currency, to)
        if (not result or not str(result.get("rate_source") or "").strip()
                or result.get("currency", to) != to):        # never relabel a result in another currency
            return t.ConvertAmountOut(converted=None)       # AC-20: no verified, labeled rate → nothing converted
        return t.ConvertAmountOut(converted=t.ConvertedAmount.model_validate({**result, "currency": to}))

    return {"get_customer_profile": profile, "search_transaction": search, "get_fraud_score": score,
            "compute_deadline": deadline, "convert_amount": convert_amount}
