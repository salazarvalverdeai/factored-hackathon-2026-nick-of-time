"""Small load test of the public demo flow (task PRODRUN): N parallel demo sessions (scenario + language), each verified
with its on-screen OTP, one thread, a few turns streamed over SSE. Prints p50/p95 per turn, the time to the first
`progress` event, errors and 429s. Stops sending new work on the first 5xx.
    BASE_URL=https://... SESSIONS=5 TURNS=3 python eval/robustness/prod_loadtest.py [out.json]
Counts against the public per-IP limits (10 sessions and 60 agent requests an hour; a thread is one request).
"""
from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
import time

import httpx

BASE = os.environ["BASE_URL"].rstrip("/")
SESSIONS, TURNS = min(int(os.environ.get("SESSIONS", "5")), 10), int(os.environ.get("TURNS", "3"))
SCENARIOS = [("SCN-MX-1", "es"), ("SCN-CO-1", "es"), ("SCN-MX-2", "es"), ("SCN-AR-1", "pt"), ("SCN-AR-2", "pt")]
MESSAGES = {"es": ["Hola, no reconozco un cargo en mi tarjeta", "Si, bloquea la tarjeta por favor", "¿Cómo va mi caso?"],
            "pt": ["Oi, não reconheço uma cobrança no meu cartão", "Sim, bloqueie o cartão por favor",
                   "Como está meu caso?"]}
stats = {"turn_ms": [], "first_progress_ms": [], "errors": [], "rate_limited": 0, "server_errors": 0}


async def session(i: int) -> None:
    scenario, lang = SCENARIOS[i % len(SCENARIOS)]
    async with httpx.AsyncClient(base_url=BASE, timeout=120) as c:
        async def call(method: str, path: str, **kw):
            r = await c.request(method, path, **kw)
            if r.status_code == 429:
                stats["rate_limited"] += 1
            elif r.status_code >= 500:
                stats["server_errors"] += 1
            if r.status_code >= 400:
                stats["errors"].append(f"{method} {path.split('/')[2] if path.count('/') > 1 else path} {r.status_code}")
                return None
            return r
        s = await call("POST", "/api/sessions", json={"language": lang, "scenario": scenario, "mode": "replay"})
        if s is None or not await call("POST", f"/api/sessions/{s.json()['session_id']}/verify",
                                       json={"otp": s.json()["otp_demo"]}):
            return
        t = await call("POST", "/api/agent/threads")
        if t is None:
            return
        for k in range(TURNS):
            if stats["server_errors"]:
                return
            body = {"input": {"messages": [{"role": "user", "content": MESSAGES[lang][k % 3]}]}}
            t0, first, got_turn = time.perf_counter(), None, False
            try:
                async with c.stream("POST", f"/api/agent/threads/{t.json()['thread_id']}/runs/stream", json=body) as r:
                    if r.status_code >= 400:
                        stats["rate_limited"] += r.status_code == 429
                        stats["server_errors"] += r.status_code >= 500
                        stats["errors"].append(f"turn {r.status_code}")
                        continue
                    event = None
                    async for line in r.aiter_lines():
                        if line.startswith("event:"):
                            event = line[6:].strip()
                            if event == "progress" and first is None:
                                first = (time.perf_counter() - t0) * 1000
                            got_turn |= event == "turn"
            except httpx.HTTPError as exc:
                stats["errors"].append(f"turn {type(exc).__name__}")
                continue
            stats["turn_ms"].append((time.perf_counter() - t0) * 1000)
            if first is not None:
                stats["first_progress_ms"].append(first)
            if not got_turn:
                stats["errors"].append("turn: no final turn event")


def pct(v: list[float], q: float) -> float:
    v = sorted(v)
    return v[min(len(v) - 1, round(q * (len(v) - 1)))] if v else float("nan")


async def main() -> None:
    started = time.perf_counter()
    await asyncio.gather(*(session(i) for i in range(SESSIONS)))
    wall = time.perf_counter() - started
    out = {"sessions": SESSIONS, "turns_each": TURNS, "wall_s": round(wall, 1), "turns_ok": len(stats["turn_ms"]),
           "turn_p50_ms": round(statistics.median(stats["turn_ms"])) if stats["turn_ms"] else None,
           "turn_p95_ms": round(pct(stats["turn_ms"], 0.95)) if stats["turn_ms"] else None,
           "turn_max_ms": round(max(stats["turn_ms"])) if stats["turn_ms"] else None,
           "first_progress_p50_ms": round(statistics.median(stats["first_progress_ms"])) if stats["first_progress_ms"] else None,
           "first_progress_p95_ms": round(pct(stats["first_progress_ms"], 0.95)) if stats["first_progress_ms"] else None,
           "errors": len(stats["errors"]), "rate_limited": stats["rate_limited"], "server_errors": stats["server_errors"],
           "error_list": stats["errors"][:20], "turn_ms": [round(x) for x in stats["turn_ms"]]}
    print(json.dumps(out, indent=1))
    if len(sys.argv) > 1:
        open(sys.argv[1], "w").write(json.dumps(out, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
