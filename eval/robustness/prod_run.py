"""Robustness by character against a DEPLOYED public api (task PRODRUN). Same scripted characters and the same
deterministic checker as run.py, but over HTTP: POST /api/sessions (scenario + language), verify with the on-screen OTP,
open a thread, one SSE turn per message. The checker reads the customer's projection of the turn (no trace, no store),
so the store-side checks (case ownership, recorded V- ids, case queue status) are not available here.
    BASE_URL=https://... python -m eval.robustness.prod_run [--characters a,b] [--pause 3] --out file.json
Gentle by design: one request at a time, `--pause` seconds before each agent turn, and it stops at the first 429 or
5xx (never retries). It prints the requests it spent in the limiter's two buckets (session; turn = thread + stream).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx

from eval.robustness.checker import World, check_turn
from eval.robustness.run import DEV, characters, scripted
from nick_of_time.contracts import TurnResult

# characters.yaml scenarios are dev cases; prod serves these demo scenarios (GET /api/demo/scenarios)
PROD_SCENARIO = {"aggressive": "SCN-MX-1", "passive": "SCN-AR-1", "terse": "SCN-CO-1", "verbose": "SCN-MX-2",
                 "confused": "SCN-MX-1", "manipulative": "SCN-MX-1", "manipulative_pt": "SCN-AR-2",
                 "code_switching": "SCN-AR-1", "other_language": "SCN-CO-1"}
DEFAULT = "aggressive,passive,terse,verbose,confused,manipulative,code_switching,other_language"
MAX_TURNS = 4
# [assumption] a figure next to a score word: the client does not know the demo gold's scores (the checker's
# never-send needs them), so this only flags a reply for a person to read; it is not a checker rule
SCORE_WORDS = re.compile(r"(puntuaci[oó]n|pontua[cç][aã]o|score|riesgo|risco)\D{0,25}\d", re.I)
spent = {"session": 0, "turn": 0}


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
        raise Stop(f"{r.request.method} {r.request.url.path} -> {r.status_code} "
                   f"Retry-After {r.headers.get('retry-after')}")
    r.raise_for_status()
    return r


def converse(base: str, name: str, ch: dict, victim: str, pause: float = 0.0,
             transport: httpx.BaseTransport | None = None) -> dict:
    """One character's scripted conversation, every turn checked. `victim` is a dev case id: its customer's id is the
    foreign id the checker looks for in every output (the manipulative character asks for it)."""
    world = World(customer_id="", foreign={DEV[victim]["initial_state"]["customer_id"]}, scores=set(), recorded=None)
    rows, speaker = [], scripted(ch)
    with httpx.Client(base_url=base, timeout=120, transport=transport) as c:
        spent["session"] += 1
        s = guard(c.post("/api/sessions", json={"language": ch["language"], "scenario": PROD_SCENARIO[name],
                                                 "mode": "replay"})).json()
        guard(c.post(f"/api/sessions/{s['session_id']}/verify", json={"otp": s["otp_demo"]}))
        spent["turn"] += 1
        thread = guard(c.post("/api/agent/threads")).json()["thread_id"]
        for n in range(1, MAX_TURNS + 1):
            said = speaker(n, None)
            if said is None:
                break
            text, attack = said
            time.sleep(pause)
            spent["turn"] += 1
            t0, first, raw = time.perf_counter(), None, []
            with c.stream("POST", f"/api/agent/threads/{thread}/runs/stream",
                          json={"input": {"messages": [{"role": "user", "content": text}]}}) as r:
                if r.status_code >= 400:
                    r.read()
                guard(r)
                for line in r.iter_lines():
                    if first is None and line.startswith("event:"):
                        first = round((time.perf_counter() - t0) * 1000)
                    raw.append(line)
            ms = round((time.perf_counter() - t0) * 1000)
            events = sse("\n".join(raw))
            turns = [d for e, d in events if e == "turn"]
            if not turns:
                rows.append({"n": n, "said": text, "ms": ms,
                             "violations": [{"rule": "harness", "detail": "no turn event"}]})
                continue
            turn = TurnResult.model_validate(turns[-1])
            found = check_turn(n, text, attack, turn, world)
            chips = [x.id for x in turn.suggestions]
            rows.append({"n": n, "said": text, "attack": attack, "ms": ms, "first_event_ms": first,
                         "language": turn.language, "intent": turn.intent, "decision": turn.decision,
                         "reply": turn.reply, "chips": chips, "actions": [f"{a.tool}:{a.state}" for a in turn.actions],
                         "guardrails": turn.guardrails_triggered, "denials": [d.guardrail_id for d in turn.denials],
                         "degraded": "retry" in chips, "score_mention": bool(SCORE_WORDS.search(turn.reply)),
                         "progress_events": sum(e == "progress" for e, _ in events),
                         "violations": [{"rule": v.rule, "detail": v.detail} for v in found]})
    return {"character": name, "scenario": PROD_SCENARIO[name], "language": ch["language"], "turns": rows,
            "violations": [{"turn": r["n"], **v} for r in rows for v in r["violations"]]}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--characters", default=DEFAULT)
    p.add_argument("--pause", type=float, default=3.0, help="seconds before each agent turn and between characters")
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    base = os.environ["BASE_URL"].rstrip("/")
    cfg, results = characters(), []
    health = httpx.get(f"{base}/api/health", timeout=30).json()
    try:
        for name in a.characters.split(","):
            results.append(converse(base, name, cfg["characters"][name], cfg["victim"], a.pause))
            print(name, len(results[-1]["turns"]), "turns", len(results[-1]["violations"]), "violations", flush=True)
            time.sleep(a.pause)
    except Stop as stop:
        print("STOPPED:", stop, file=sys.stderr)
    print("requests spent:", spent, flush=True)
    a.out.write_text(json.dumps({"git_sha": health.get("git_sha"), "contract_version": health.get("contract_version"),
                                 "requests": spent, "characters": results}, ensure_ascii=False, indent=1),
                     encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
