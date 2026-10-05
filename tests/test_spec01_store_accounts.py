"""Spec 01 — the store's sessions, policy denials and customer channels (T9, §6.5, AC-07, D-023, D-041). Every test runs
on both backends with the store suite's fixture: MemoryStore, and PostgresStore in a fresh schema when
TEST_DATABASE_URL is set (`-m postgres`; offline it skips)."""
from __future__ import annotations

import datetime as dt

import pytest

from nick_of_time import ids
from nick_of_time.store import Store, StoreError
from tests.test_spec01_store import RUN, backend, new_store, open_case, ticking_store, types  # noqa: F401

AT = dt.datetime(2026, 6, 1, 15, 0, tzinfo=dt.UTC)
NUL, SURROGATE = chr(0), chr(0xD800)


def new_session(store: Store, **changes):
    fields = dict(customer_id="CLI-000001", otp_hash="sha256:x", verified_at=AT, expires_at=AT + dt.timedelta(hours=1),
                  language="es", mode="replay")
    return store.create_session(**{**fields, **changes})


def deny(store: Store, **changes):
    fields = dict(trace_id="t", session_id=None, actor="agent", policy_id="POL-DEFAULT-DENY", detail={"tool": "x"})
    return store.add_denial(**{**fields, **changes})


def link(store: Store, case_id: str, channel: str, address: str, event: str, actor: str = "customer"):
    return store.add_channel_event(case_id, channel, address, event, actor=actor, trace_id="t")


def test_ac_07_a_session_is_stored_under_a_store_id_and_keeps_its_mode_and_run():
    """T9: the row comes back as created, with a fresh `S-` id and the store's clock; the interface has no session
    update, so `mode` and `run_id` never change (AC-07, §6.8)."""
    store = ticking_store()
    first = new_session(store, mode="live", display_currency="USD", tool_faults=("block_card",), run_id=RUN, arm="S1")
    second = new_session(store)
    assert ids.is_valid("session", first.session_id) and first.session_id != second.session_id
    assert first.created_at == dt.datetime(2026, 6, 1, 15, 0, tzinfo=dt.UTC)
    assert store.get_session(first.session_id) == first and store.get_session(second.session_id) == second
    assert (first.mode, first.run_id, first.arm, first.tool_faults) == ("live", RUN, "S1", ("block_card",))
    assert store.get_session("S-" + "x" * 16) is None
    for interface in (Store, type(store)):                                   # the protocol and this backend
        assert [n for n in dir(interface) if "session" in n and not n.startswith("_")] == ["create_session",
                                                                                          "get_session"]


def test_ac_07_the_eval_seed_sessions_none_and_expired_are_stored_as_given():
    """§6.8: the `none` session has no customer and no verification; the `expired` one expires in the past."""
    store = new_store()
    none = new_session(store, customer_id=None, verified_at=None, run_id=RUN)
    expired = new_session(store, expires_at=AT - dt.timedelta(minutes=1), run_id=RUN)
    read = store.get_session(none.session_id)
    assert (read.customer_id, read.verified_at, read.tool_faults) == (None, None, ())
    assert store.get_session(expired.session_id).expires_at == AT - dt.timedelta(minutes=1)


@pytest.mark.parametrize("bad", [dict(mode="later"), dict(language="en"), dict(otp_hash=""), dict(customer_id=7),
                                 dict(expires_at=AT.replace(tzinfo=None)), dict(session_id="S-" + "x" * 16),
                                 dict(otp_hash="h" + NUL), dict(tool_faults=("get_case" + SURROGATE,)),
                                 dict(arm=SURROGATE)])
def test_ac_07_a_bad_session_is_a_store_error_and_writes_nothing(bad):
    """T9: bad input is a StoreError on both backends, never a pydantic error (an extra field included), and NUL or
    a lone surrogate never reaches Postgres."""
    store = new_store()
    with pytest.raises(StoreError):
        new_session(store, **bad)
    with pytest.raises(StoreError):
        store.get_session("S-" + NUL * 16)


def test_d041_summary_sends_count_the_session_customer_on_request_sends_in_its_run_since_it_started():
    """D-041 (spec 03 AC-21): only `on_request` sends of the session's customer whose case is in the session's run,
    created at or after both `since` and the session's start."""
    store = ticking_store()
    case_id = open_case(store, run_id=RUN).case_id
    other = open_case(store, run_id=RUN, customer_id="CLI-000002").case_id
    production = open_case(store).case_id

    def send(case: str, trigger: str = "on_request"):
        return store.add_notification(case, event="receipt", channel="log", masked_address=None, text="Resumen",
                                      trigger=trigger, actor="customer", trace_id="t",
                                      action_id=ids.new_id("action") if trigger == "on_request" else None)

    before = send(case_id)                                                    # before the session started
    session = new_session(store, run_id=RUN)
    sends = [send(case_id), send(case_id)]
    send(case_id, "auto")
    send(other)
    send(production)
    assert before.created_at < session.created_at
    assert store.summary_sends(session.session_id, since=AT - dt.timedelta(days=1)) == 2
    assert store.summary_sends(session.session_id, since=sends[1].created_at) == 1
    assert store.summary_sends(new_session(store).session_id, since=AT) == 0        # production: its send came first
    for bad in (lambda: store.summary_sends("S-" + "x" * 16, since=AT),
                lambda: store.summary_sends(session.session_id, since=AT.replace(tzinfo=None))):
        with pytest.raises(StoreError):
            bad()


def test_ac_12_spec03_every_deny_is_one_row_with_its_trace_policy_and_guardrail():
    """Spec 03 AC-12, §6.5: a fresh denial id, the store's clock, G-POL-01 when the writer names no guardrail, the
    session's run_id; listed by run and session, oldest first."""
    store = ticking_store()
    session = new_session(store, run_id=RUN)
    rule_only = deny(store, session_id=session.session_id, run_id=RUN, trace_id="run-1")
    named = deny(store, session_id=session.session_id, run_id=RUN, guardrail_id="G-TOOL-01",
                 policy_id="POL-CROSS-CUSTOMER", detail={"tool": "search_transaction", "fields": ("customer_id",)})
    unset = deny(store, session_id=session.session_id, run_id=RUN, guardrail_id=None)
    api = deny(store, actor="analyst:sub-1", run_id=RUN)                     # api or analyst: no session (D-023)
    assert len({d.denial_id for d in (rule_only, named, unset, api)}) == 4 and rule_only.denial_id.startswith("PD-")
    assert (rule_only.trace_id, rule_only.guardrail_id, unset.guardrail_id, named.guardrail_id) == (
        "run-1", "G-POL-01", "G-POL-01", "G-TOOL-01")
    assert named.detail == {"tool": "search_transaction", "fields": ["customer_id"]}           # JSON, as in jsonb
    assert store.list_denials(run_id=RUN) == [rule_only, named, unset, api]
    assert store.list_denials(run_id=RUN, session_id=session.session_id) == [rule_only, named, unset]
    assert store.list_denials(run_id=None) == []                                               # runs never mix


def test_d023_a_denial_is_refused_before_writing_when_its_actor_session_or_detail_is_wrong():
    """D-023: the actor is `agent`, `customer` or `analyst:<sub>` (no `system`, no blank sub); a denial of a session
    names a known session and carries its run_id; the detail is JSON; every refusal is a StoreError."""
    store = new_store()
    session = new_session(store, run_id=RUN)
    bad_rows = [dict(actor="system"), dict(actor="analyst:"), dict(actor="analyst: "), dict(actor="bot"),
                dict(trace_id=""), dict(policy_id="DEFAULT-DENY"), dict(guardrail_id="G-POL"), dict(extra=1),
                dict(trace_id="t" + NUL), dict(policy_id="POL-X" + SURROGATE), dict(detail={"text": NUL}),
                dict(session_id="S-" + "x" * 16, run_id=RUN), dict(session_id=session.session_id),
                dict(session_id=session.session_id, run_id="EV-0002:S1:1"),
                dict(session_id=session.session_id, run_id=RUN, detail={"on": dt.date(2026, 6, 1)})]
    for bad in bad_rows:
        with pytest.raises(StoreError):
            deny(store, **bad)
    assert store.list_denials(run_id=RUN) == [] == store.list_denials(run_id=None)


def test_t9_rows_that_tie_on_created_at_come_back_in_a_fixed_order():
    """T9, §6.5: on both backends, denials that tie on `created_at` by `denial_id`, and a channel's latest row is the
    one inserted last, whatever the clock says."""
    store = new_store(now=lambda: AT)
    rows = [deny(store) for _ in range(4)]
    assert store.list_denials(run_id=None) == sorted(rows, key=lambda d: d.denial_id)
    case_id = open_case(store).case_id
    linked = [link(store, case_id, "email", f"j{n}@example.com", "linked") for n in range(3)]
    assert store.channels("CLI-000001") == [linked[-1]]


def test_ac_01_a_telegram_link_is_a_row_and_telegram_linked_on_the_case():
    """§6.5, spec 13 AC-02: the row and its case event in one operation; the event names the row, never the address."""
    store = ticking_store()
    case_id = open_case(store, run_id=RUN).case_id
    row = link(store, case_id, "telegram", "987654321", "linked")
    assert (row.channel_id[:3], row.customer_id, row.event) == ("CH-", "CLI-000001", "linked")
    event = store.events(case_id)[-1]
    assert (event.type, event.payload, event.actor, event.customer_visible) == (
        "telegram_linked", {"channel_id": row.channel_id, "channel": "telegram"}, "customer", True)
    assert store.channels("CLI-000001") == [row] and row.confirmed
    assert store.channels("CLI-000002") == []


def test_ac_01_an_email_takes_summaries_only_once_its_typed_address_is_confirmed():
    """Spec 03 AC-21, spec 13 AC-04: a typed address is `linked` (no case event, not confirmed); only that address
    is confirmed (`email_confirmed`); the latest row wins; a revoked channel takes nothing."""
    store = ticking_store()
    case_id = open_case(store).case_id
    typed = link(store, case_id, "email", "ana@example.com", "linked")
    assert not typed.confirmed and types(store, case_id) == ["case_opened"]
    with pytest.raises(StoreError, match="linked address"):
        link(store, case_id, "email", "other@example.com", "confirmed")
    confirmed = link(store, case_id, "email", "ana@example.com", "confirmed")
    telegram = link(store, case_id, "telegram", "42", "linked")
    assert confirmed.confirmed and types(store, case_id) == ["case_opened", "email_confirmed", "telegram_linked"]
    assert store.channels("CLI-000001") == [confirmed, telegram]                       # by channel name
    retyped = link(store, case_id, "email", "ana.new@example.com", "linked")
    assert store.channels("CLI-000001")[0] == retyped and not retyped.confirmed      # the latest row wins
    revoked = link(store, case_id, "telegram", "42", "revoked", actor="system")
    assert store.channels("CLI-000001") == [retyped, revoked] and not revoked.confirmed
    for channel, address, event in (("telegram", "42", "revoked"), ("telegram", "42", "confirmed"),
                                    ("email", "ana@example.com", "revoked")):
        with pytest.raises(StoreError):
            link(store, case_id, channel, address, event)
    assert len(types(store, case_id)) == 3


def test_ac_01_channels_come_back_by_name_and_a_telegram_link_is_never_confirmed():
    """§6.5, spec 03 AC-21: a Telegram link made before an e-mail still lists after it (by channel name, on both
    backends); a Telegram channel takes no `confirmed` row, since `/start` is the customer's own confirmation."""
    store = ticking_store()
    case_id = open_case(store).case_id
    telegram = link(store, case_id, "telegram", "42", "linked")
    email = link(store, case_id, "email", "ana@example.com", "linked")
    assert store.channels("CLI-000001") == [email, telegram]
    with pytest.raises(StoreError, match="not a customer channel event"):
        link(store, case_id, "telegram", "42", "confirmed")
    assert store.channels("CLI-000001") == [email, telegram] and telegram.confirmed and not email.confirmed
    assert types(store, case_id) == ["case_opened", "telegram_linked"]


@pytest.mark.parametrize("bad", [dict(actor="bot"), dict(trace_id=""), dict(case_id="K-999999"),
                                 dict(channel="log"), dict(channel=["telegram"]), dict(event="deleted"),
                                 dict(event=["linked"]), dict(event="confirmed"), dict(address=" "), dict(address=7),
                                 dict(address="4" + NUL), dict(address=SURROGATE), dict(trace_id=SURROGATE),
                                 dict(case_id="K-" + NUL)])
def test_ac_01_a_channel_row_checks_every_argument_before_writing(bad):
    """§6.5: every refusal is a StoreError on both backends, NUL and lone surrogates included, and writes nothing."""
    store = new_store()
    case_id = open_case(store).case_id
    call = {"case_id": case_id, "channel": "telegram", "address": "42", "event": "linked", "actor": "customer",
            "trace_id": "t", **bad}
    with pytest.raises(StoreError):
        store.add_channel_event(call.pop("case_id"), call.pop("channel"), call.pop("address"), call.pop("event"),
                                **call)
    assert store.channels("CLI-000001") == [] and types(store, case_id) == ["case_opened"]
    with pytest.raises(StoreError):
        store.channels("CLI-" + NUL)
