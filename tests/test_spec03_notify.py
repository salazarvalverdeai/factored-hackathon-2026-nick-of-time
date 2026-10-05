"""Spec 03 T7: `send_case_summary` and `list_my_notifications` through the real gate over the case store (AC-21,
AC-22; D-025, D-035, D-041, D-052). MemoryStore always, PostgresStore with TEST_DATABASE_URL (`-m postgres`). A fake
sender stands in for Telegram and Resend: no provider is ever called and no secret is read."""
from __future__ import annotations

import datetime as dt
import itertools
import secrets
from types import SimpleNamespace

from contracts import tools
from nick_of_time import ids
from nick_of_time.receipt import text
from tests.test_spec01_store import backend, new_store, open_case  # noqa: F401
from tests.test_spec03_followups import ANA, BRUNO, NOW, POLICIES, Sessions
from mcp_server import gate, notify  # noqa: E402  (apps/mcp is on the path through the import above)

EMAIL = "ana.perez@example.com"
# Gold as the entry point passes it: the charge only (the loader never selects e-mails, AC-11, AC-21).
GOLD = SimpleNamespace(transaction=lambda c, _: SimpleNamespace(amount=69.44, currency="USD",
                                                                merchant="Tienda Don José") if c == ANA else None)


def in_transaction(store) -> bool:
    """PostgresStore: whether its connection is inside a transaction now (MemoryStore has none)."""
    conn = getattr(store, "_conn", None)
    return conn is not None and conn.info.transaction_status != conn.info.transaction_status.IDLE


def last_provider_event(store, notification_id):
    """The latest delivery's provider_event; the Store interface exposes only its status, so the test reads the row."""
    if hasattr(store, "_deliveries"):
        return store._deliveries[notification_id][-1][1]
    return store._rows("select provider_event from notification_deliveries where notification_id = %s "
                       "order by row_no desc limit 1", (notification_id,))[0]["provider_event"]


class Run:
    def __init__(self, limiter=None, sender="fake"):
        self.store, self.denials, self.sent = new_store(), [], []

        def fake(*message):                                # a provider: records the call, returns its message id
            self.sent.append((*message, in_transaction(self.store)))
            return f"pm-{len(self.sent)}"
        fake = fake if sender == "fake" else sender
        guardrails = {rule_id: rule.guardrail for rule_id, rule in POLICIES.rules.items() if rule.guardrail}
        self.gate = gate.Gate(Sessions(self.store), notify.notify_handlers(self.store, GOLD, sender=fake),
                              denials=self.denials.append, audit=lambda _: None, now=lambda: NOW, guardrails=guardrails,
                              limiter=limiter or gate.RateLimiter(clock=itertools.count(0, 4000).__next__))
        self.ana = self.session()
        self.case_id = open_case(self.store, customer_id=ANA).case_id

    def session(self, customer=ANA):
        return self.store.create_session(customer_id=customer, otp_hash="h", verified_at=NOW, language="es",
                                         expires_at=NOW + dt.timedelta(hours=1), mode="replay").session_id

    def link(self, channel="email", address=EMAIL, events=("linked", "confirmed")):
        for event in events:
            self.store.add_channel_event(self.case_id, channel, address, event, actor="customer", trace_id="t")

    def mine(self):                                   # this run's case: Postgres runs share one scratch schema
        return [n for n in self.store.list_notifications(ANA, run_id=None) if n.case_id == self.case_id]

    def __call__(self, tool, session=None, **args):
        if tool == "send_case_summary":
            args = {"idempotency_key": secrets.token_hex(4), "case_id": self.case_id, "channel": "email", **args}
        return self.gate.call(tool, {"session_id": session or self.ana, **args}, "trace-t7")


def test_ac_21_the_summary_is_the_receipt_template_sent_once_to_the_confirmed_channel_masked():
    run = Run()
    run.link()
    out = run("send_case_summary", idempotency_key="k1")
    assert isinstance(out, tools.SendCaseSummaryOut) and (out.state, out.masked_address) == ("requested",
                                                                                              "a···@example.com")
    [sent] = run.mine()
    source = dict(deadline_source="Banxico Circular 3/2012", source_url="https://www.banxico.org.mx/",
                  verified_on="2026-10-04")
    assert sent.text.splitlines() == [
        text("receipt.title", "es", case_id=run.case_id),
        text("receipt.transaction", "es", merchant="Tienda Don José", amount="69.44", currency="USD"),
        text("receipt.credit_deadline", "es", credit_deadline="2026-06-03", **source),
        text("receipt.what_ai_did_case_only", "es"), text("receipt.what_a_person_does", "es")]
    assert (sent.notification_id, sent.trigger, sent.delivery_status) == (out.notification_id, "on_request", "sent")
    assert run.sent == [("email", EMAIL, sent.text, False)] and EMAIL not in out.model_dump_json()  # after commit
    assert last_provider_event(run.store, sent.notification_id) == {"provider_message_id": "pm-1"}    # D-035 match
    assert run.store.events(run.case_id)[-1].payload["action_id"] == out.action_id
    assert run("send_case_summary", idempotency_key="k1") == out and len(run.sent) == 1       # replayed, not resent


def test_ac_21_only_a_channel_the_customer_confirmed_and_only_their_own_case():
    run = Run()
    run.link(events=("linked",))                                          # typed, never confirmed
    assert run("send_case_summary").policy_id == "POL-DEFAULT-DENY"
    assert run("send_case_summary", channel="telegram").policy_id == "POL-DEFAULT-DENY"      # never linked
    theirs = open_case(run.store, customer_id=BRUNO).case_id
    run.link("telegram", "123456789", events=("linked",))                  # a Telegram link is confirmed
    probe = run("send_case_summary", case_id=theirs, channel="telegram")
    assert (probe.code, probe.policy_id) == ("NOT_FOUND", None) and run.sent == []
    assert run.store.list_notifications(BRUNO, run_id=None) == []
    assert isinstance(run("send_case_summary", channel="telegram"), tools.SendCaseSummaryOut)
    assert [d.policy_id for d in run.denials] == ["POL-DEFAULT-DENY", "POL-DEFAULT-DENY", "POL-CROSS-CUSTOMER"]


def test_ac_21_at_most_3_summaries_per_hour_per_session_in_the_gate_and_in_the_store():
    for limiter, guardrail in ((gate.RateLimiter(), "G-TOOL-01"), (None, "G-POL-01")):
        run = Run(limiter=limiter)
        run.link()
        assert all(isinstance(run("send_case_summary"), tools.SendCaseSummaryOut) for _ in range(3))
        fourth = run("send_case_summary")
        assert (fourth.code, fourth.policy_id, run.denials[-1].guardrail_id) == ("DENY", "POL-DEFAULT-DENY", guardrail)
        assert len(run.mine()) == 3 and len(run.sent) == 3


def test_ac_22_each_notification_has_its_masked_address_and_latest_delivery_status():
    run = Run(sender=None)                                                # no sender: the api's notifier sends
    run.link()
    auto = run.store.add_notification(run.case_id, event="case_opened", channel="log", masked_address=None,
                                      text="Abrimos tu caso.", trigger="auto", actor="system", trace_id="t")
    for status in ("sent", "delivered"):
        run.store.add_delivery(auto.notification_id, status)
    summary = run("send_case_summary")
    out = run("list_my_notifications", case_id=run.case_id)
    assert [(n.notification_id, n.channel, n.masked_address, n.delivery_status) for n in out.notifications] == [
        (summary.notification_id, "email", "a···@example.com", "queued"),
        (auto.notification_id, "log", None, "delivered")]
    assert (out.action_id, out.verification_id) == (None, None) and out.read_at is not None
    theirs = open_case(run.store, customer_id=BRUNO).case_id
    assert run("list_my_notifications", case_id=theirs).code == "NOT_FOUND"


def test_d035_a_send_is_verified_only_while_its_latest_delivery_did_not_fail_or_bounce():
    run = Run(sender=None)
    run.link()
    send = run("send_case_summary")
    read = run("list_my_notifications", action_id=send.action_id)
    assert read.action_id == send.action_id and read.verification_id.startswith("V-")
    opened = run.store.events(run.case_id)[0].payload["action_id"]          # another tool's write: a plain read
    assert run("list_my_notifications", action_id=opened).verification_id is None
    run.store.add_delivery(send.notification_id, "bounced")
    assert run("list_my_notifications", action_id=send.action_id).verification_id is None
    def timing_out(*_):
        raise TimeoutError
    failing = Run(sender=timing_out)
    failing.link()
    lost = failing("send_case_summary")
    [row] = failing.mine()
    assert row.delivery_status == "failed" and failing("list_my_notifications",
                                                       action_id=lost.action_id).verification_id is None


def test_ac_21_the_what_the_assistant_did_line_follows_the_verified_block():
    run = Run(sender=None)
    run.link()
    block, product_id = ids.new_id("action"), run.store.get_case(run.case_id, run_id=None, customer_id=ANA).product_id
    run.store.block_product(run.case_id, product_id, action_id=block, actor="agent", trace_id="t")
    run("send_case_summary")                                              # blocked, not yet verified
    run.store.record_verification(run.case_id, block, read="get_product_status", run_id=None, customer_id=ANA,
                                  actor="agent", trace_id="t")
    run("send_case_summary")
    lines = [n.text.splitlines()[-2] for n in reversed(run.mine())]
    assert lines == [text("receipt.what_ai_did_block_unconfirmed", "es"), text("receipt.what_ai_did_blocked", "es")]


def test_d041_a_new_session_gets_a_fresh_allowance_and_another_customers_send_reads_plain():
    run = Run()
    run.link()
    assert all(isinstance(run("send_case_summary"), tools.SendCaseSummaryOut) for _ in range(3))
    assert run("send_case_summary").policy_id == "POL-DEFAULT-DENY"
    assert isinstance(run("send_case_summary", session=run.session()), tools.SendCaseSummaryOut)   # D-041: per session
    bruno_case = open_case(run.store, customer_id=BRUNO).case_id
    run.store.add_channel_event(bruno_case, "telegram", "987654321", "linked", actor="customer", trace_id="t")
    theirs = run("send_case_summary", session=run.session(BRUNO), case_id=bruno_case, channel="telegram")
    read = run("list_my_notifications", action_id=theirs.action_id)
    assert (read.action_id, read.verification_id) == (None, None)
    assert theirs.notification_id not in {n.notification_id for n in read.notifications}


def test_ac_21_a_delivery_row_that_fails_after_the_send_leaves_it_queued_and_answers_requested(caplog):
    """The message went out, so the customer is not told UNAVAILABLE: the failure is logged (type only), the
    notification stays `queued` for the api's reconciler and the tool answers `requested` [assumption]."""
    run = Run()
    run.link()

    def broken(notification_id, status, provider_event=None):
        raise RuntimeError(EMAIL)                         # a message that must not reach the log
    run.store.add_delivery = broken
    out = run("send_case_summary")
    assert isinstance(out, tools.SendCaseSummaryOut) and out.state == "requested" and len(run.sent) == 1
    [row] = run.mine()
    assert row.delivery_status == "queued" and "not recorded: RuntimeError" in caplog.text and EMAIL not in caplog.text
