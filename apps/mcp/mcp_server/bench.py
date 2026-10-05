"""Tool latency benchmark (spec 03 AC-13, T5): p50/p95 per tool through the real gate over gold and an in-memory store.

`python -m mcp_server.bench --gold data/gold [--customers 50] [--seed 7]` (PYTHONPATH=.:packages:apps/mcp). Offline:
no network, no Postgres, no LLM. It samples customers among every customer with a card transaction in gold, runs one dispute
per customer through the tools the agent uses (profile, search, score, open_case, block_card, the four reads), and
prints each tool's p50, p95 and max in ms with the `[data]` label, plus the load time and the process's peak
RSS (spec 03 §8: does the in-memory load fit the t3.medium). AC-13 holds when every p95 is
under `reliability.tool_timeout_ms`; the exit code is 1 otherwise. [assumption] It times `Gate.call` (session, limits,
schema, handler, audit to a null sink) without the HTTP transport, and the in-memory store stands in for Postgres, so
it measures the gold reads and the handlers' work, not the network or the database round trips.
"""
from __future__ import annotations

import argparse
import datetime as dt
import random
import resource
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Optional

from contracts import tools as t
from mcp_server import case_reads, gate, reads, writes
from mcp_server.cards import GoldCards
from mcp_server.gold import Gold
from nick_of_time import ids
from nick_of_time.policy import load_policies
from nick_of_time.policy.clock import DEMO_TODAY
from nick_of_time.store.memory import MemoryStore

RUN = "EV-BENCH:S1:1"


class _NoLimit(gate.RateLimiter):
    def admit(self, session_id: str, tool: str) -> Optional[str]:   # the benchmark measures tools, not the limiter
        return None


def run(gold_path: Path, customers: int = 50, seed: int = 7) -> dict[str, Any]:
    """Load gold, play one dispute per sampled customer, return the load time and each tool's latencies (ms)."""
    started = time.perf_counter()
    policies, gold, cards, store = load_policies(), Gold(gold_path), GoldCards(gold_path), MemoryStore()
    load_s = time.perf_counter() - started
    handlers = {**reads.read_handlers(gold, policies), **writes.writes_handlers(gold, policies, store, cards=cards),
                **case_reads.case_reads_handlers(gold, policies, store, cards=cards)}
    now = dt.datetime.now(dt.UTC)
    sessions: dict[str, gate.SessionRow] = {}
    the_gate = gate.Gate(sessions, handlers, denials=lambda row: None, audit=lambda entry: None, limiter=_NoLimit())
    pool = [row[0] for row in cards._rows(                    # customers with a card transaction in gold
        "SELECT DISTINCT customer_id FROM trx_country ORDER BY customer_id", [])]
    picked = random.Random(seed).sample(pool, min(customers, len(pool)))
    timings: dict[str, list[float]] = {}

    def call(tool: str, session_id: str, **args: Any):
        if tool in t.VERIFIED_WITH:
            args["idempotency_key"] = ids.new_id("action")
        begin = time.perf_counter()
        out = the_gate.call(tool, {"session_id": session_id, **args}, "bench")
        timings.setdefault(tool, []).append((time.perf_counter() - begin) * 1000)
        return out

    for n, customer in enumerate(picked):
        session_id = f"S-bench{n:011d}"
        sessions[session_id] = gate.SessionRow(session_id=session_id, customer_id=customer, verified_at=now,
                                               expires_at=now + dt.timedelta(hours=1), language="es", mode="replay",
                                               run_id=RUN)
        call("get_customer_profile", session_id)
        found = call("search_transaction", session_id)
        call("list_my_cards", session_id)
        candidates = getattr(found, "candidates", []) or gold.transactions(   # else any charge of the customer
            customer, DEMO_TODAY - dt.timedelta(days=400), DEMO_TODAY, reads.STATUSES)[:1]
        if not candidates:
            continue
        trx = candidates[0]
        score = call("get_fraud_score", session_id, transaction_id=trx.transaction_id)
        zone = writes.zone_of(getattr(score, "score", None), policies)
        opened = call("open_case", session_id, transaction_id=trx.transaction_id, dispute_type="unrecognized_charge",
                      zone=zone)
        if isinstance(opened, t.OpenCaseOut):
            call("get_case", session_id, case_id=opened.case_id, action_id=opened.action_id)
            blocked = call("block_card", session_id, product_id=trx.product_id, reason="high_zone_dispute")
            call("get_product_status", session_id, product_id=trx.product_id,
                 action_id=getattr(blocked, "action_id", None))
        call("list_my_cases", session_id)
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss            # bytes on macOS, KiB on Linux
    peak_mb = peak / 2**20 if sys.platform == "darwin" else peak / 2**10
    return {"load_s": load_s, "customers": len(picked), "timings": timings, "peak_rss_mb": peak_mb}


def p95(values: list[float]) -> float:
    return statistics.quantiles(values, n=20, method="inclusive")[-1] if len(values) > 1 else values[0]


def report(result: dict[str, Any], budget_ms: float) -> tuple[list[str], bool]:
    lines = [f"[data] gold load {result['load_s']:.2f} s · peak RSS {result['peak_rss_mb']:.0f} MB · "
             f"{result['customers']} customers · budget p95 < {budget_ms:.0f} ms (policies.yaml "
             "reliability.tool_timeout_ms)"]
    ok = True
    for tool, values in sorted(result["timings"].items()):
        tail = p95(values)
        ok = ok and tail < budget_ms
        lines.append(f"[data] {tool:22} n={len(values):4d} p50={statistics.median(values):7.2f} ms "
                     f"p95={tail:7.2f} ms max={max(values):7.2f} ms")
    lines.append(f"[data] AC-13 {'holds' if ok else 'FAILS'}: every tool p95 < {budget_ms:.0f} ms")
    return lines, ok


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m mcp_server.bench", description="Spec 03 AC-13 tool latency")
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--customers", type=int, default=50)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args(argv)
    lines, ok = report(run(args.gold, args.customers, args.seed), load_policies().reliability["tool_timeout_ms"])
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

