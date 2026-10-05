"""Robustness by character against a DEPLOYED public api (task PRODRUN). Same scripted characters and the same
deterministic checker as run.py, but over HTTP: POST /api/sessions (scenario + language), verify with the on-screen OTP,
open a thread, one SSE turn per message. The checker reads the customer's projection of the turn (no trace, no store),
so the store-side checks (case ownership, recorded V- ids, case queue status) are not available here.
    BASE_URL=https://... python -m eval.robustness.prod_run [--characters a,b] --out file.json
Stops at the first 429 or 5xx. Public limits per IP: 10 sessions/hour, 60 agent requests/hour (a thread counts as one).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

from eval.robustness.checker import World, check_turn
from eval.robustness.run import characters, scripted
from nick_of_time.contracts import TurnResult

# characters.yaml scenarios are dev cases; prod serves these demo scenarios (GET /api/demo/scenarios)
PROD_SCENARIO = {"aggressive": "SCN-MX-1", "passive": "SCN-AR-1", "terse": "SCN-CO-1", "verbose": "SCN-MX-2",
                 "confused": "SCN-MX-1", "manipulative": "SCN-MX-1", "manipulative_pt": "SCN-AR-2",
                 "code_switching": "SCN-AR-1", "other_language": "SCN-CO-1"}
DEFAULT = "aggressive,passive,terse,verbose,confused,manipulative,code_switching,other_language"
MAX_TURNS = 4


class Stop(Exception):
    pass


def sse(text: str) -> list[tuple[str, dict]]:
    out, event = [], None
    for line in text.splitlines():
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:") and event:
            out.append((event, json.loads(line[5:])))
    return out


def guard(r: httpx.Response) -> httpx.Response:
    if r.status_code == 429 or r.status_code >= 500:
        raise Stop(f"{r.request.method} {r.request.url.path} -> {r.status_code}")
    r.raise_for_status()
    return r


def converse(base: str, name: str, ch: dict, victim: str) -> dict:
    world = World(customer_id="", foreign={victim}, scores=set(), recorded=None)
    rows, speaker = [], scripted(ch)
    with httpx.Client(base_url=base, timeout=120) as c:
        s = guard(c.post("/api/sessions", json={"language": ch["language"], "scenario": PROD_SCENARIO[name],
                                                 "mode": "replay"})).json()
        guard(c.post(f"/api/sessions/{s['session_id']}/verify", json={"otp": s["otp_demo"]}))
        thread = guard(c.post("/api/agent/threads")).json()["thread_id"]
        for n in range(1, MAX_TURNS + 1):
            said = speaker(n, None)
            if said is None:
                break
            text, attack = said
            t0 = time.perf_counter()
            r = guard(c.post(f"/api/agent/threads/{thread}/runs/stream",
                             json={"input": {"messages": [{"role": "user", "content": text}]}}))
            ms = round((time.perf_counter() - t0) * 1000)
            events = sse(r.text)
            turns = [d for e, d in events if e == "turn"]
            if not turns:
                rows.append({"n": n, "said": text, "ms": ms,
                             "violations": [{"rule": "harness", "detail": "no turn event"}]})
                continue
            turn = TurnResult.model_validate(turns[-1])
            found = check_turn(n, text, attack, turn, world)
            rows.append({"n": n, "said": text, "attack": attack, "ms": ms, "decision": turn.decision,
                         "reply": turn.reply, "chips": [x.id for x in turn.suggestions],
                         "actions": [f"{a.tool}:{a.state}" for a in turn.actions],
                         "guardrails": turn.guardrails_triggered,
                         "progress_events": sum(e == "progress" for e, _ in events),
                         "violations": [{"rule": v.rule, "detail": v.detail} for v in found]})
    return {"character": name, "scenario": PROD_SCENARIO[name], "language": ch["language"], "turns": rows,
            "violations": [{"turn": r["n"], **v} for r in rows for v in r["violations"]]}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--characters", default=DEFAULT)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    base = os.environ["BASE_URL"].rstrip("/")
    cfg, results = characters(), []
    try:
        for name in a.characters.split(","):
            results.append(converse(base, name, cfg["characters"][name], cfg["victim"]))
            print(name, len(results[-1]["turns"]), "turns", len(results[-1]["violations"]), "violations", flush=True)
    except Stop as stop:
        print("STOPPED:", stop, file=sys.stderr)
    a.out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
