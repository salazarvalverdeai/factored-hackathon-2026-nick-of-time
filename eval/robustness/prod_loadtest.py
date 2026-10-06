"""Small load test of the public demo flow (task PRODRUN): N concurrent demo visitors (scenario + language, replay),
each verified with its on-screen OTP, one thread, a few turns streamed over SSE. Prints p50/p95 of the turn and of the
first SSE event, the time to the first `progress` event, errors, degraded turns (the api's "agent unavailable" turn)
and 429s. Gentle: visitors start `RAMP_S` apart, at most 10 visitors and 40 turns, and every visitor stops sending at
the first 429 or 5xx anyone sees (no retries).
    BASE_URL=https://... SESSIONS=10 TURNS=4 python -m eval.robustness.prod_loadtest [out.json]
Before sending anything it projects an upper bound of the LLM spend from eval/bench/prices.yaml (`projected_usd`) for
this run plus PRIOR_TURNS already sent, and aborts when it is above BUDGET_USD (default 1.5): the deployed daily cap is
shared with every visitor. Counts against the public per-IP limits (session; turn = thread + each stream).
"""
from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
import time
from typing import Optional

import httpx

MAX_SESSIONS, MAX_TURNS_TOTAL = 10, 40
SCENARIOS = [("SCN-MX-1", "es"), ("SCN-CO-1", "es"), ("SCN-MX-2", "es"), ("SCN-AR-1", "pt"), ("SCN-AR-2", "pt")]
# a visitor's path: report a charge, list the latest charges (the D-085 chip label), ask for status, ask for a person
MESSAGES = {"es": ["Hola, no reconozco un cargo en mi tarjeta", "Muéstrame mis últimos cargos", "¿Cómo va mi caso?",
                   "Quiero hablar con una persona"],
            "pt": ["Oi, não reconheço uma cobrança no meu cartão", "Mostre minhas últimas cobranças",
                   "Como está meu caso?", "Quero falar com uma pessoa"]}
# [assumption] upper-bound tokens per turn: one `understand` call on S1 and one writer call on S2, each with a payload
# of at most this many characters besides its system prompt, and each at its max_tokens. A real turn makes fewer
# calls: `understand` runs only below tau, the writer only when the console setting is `llm`.
PAYLOAD_CHARS = {"understand": 2_000, "writer": 6_000}


def projected_usd(turns: int) -> tuple[float, float]:
    """(USD per turn, USD for `turns`) as an upper bound, priced from prices.yaml through config.price()."""
    from nick_of_time.config import price, resolve
    from nick_of_time.llm import base, steps, writer
    env = {"LLM_PROVIDER": "bedrock"}
    understand = base.cost_usd(price(resolve("S1", env)), (len(steps.UNDERSTAND) + PAYLOAD_CHARS["understand"]) // 4,
                               steps.MAX_TOKENS)
    word = base.cost_usd(price(resolve(writer.ARM, env)), (len(writer.SYSTEM) + PAYLOAD_CHARS["writer"]) // 4,
                         writer.MAX_TOKENS)
    per_turn = understand + word
    return per_turn, per_turn * turns


class Load:
    def __init__(self, base: str, sessions: int, turns: int, ramp_s: float,
                 transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
        self.base, self.sessions, self.turns, self.ramp_s, self.transport = base, sessions, turns, ramp_s, transport
        self.turn_ms: list[float] = []
        self.first_event_ms: list[float] = []
        self.first_progress_ms: list[float] = []
        self.errors: list[str] = []
        self.rate_limited = self.server_errors = self.degraded = 0
        self.spent = {"session": 0, "turn": 0}

    @property
    def stopped(self) -> bool:
        return bool(self.rate_limited or self.server_errors)

    def failed(self, what: str, status: int) -> None:
        self.rate_limited += status == 429
        self.server_errors += status >= 500
        self.errors.append(f"{what} {status}")

    async def call(self, c: httpx.AsyncClient, what: str, method: str, path: str, **kw) -> Optional[httpx.Response]:
        try:
            r = await c.request(method, path, **kw)
        except httpx.HTTPError as exc:
            self.errors.append(f"{what} {type(exc).__name__}")
            return None
        if r.status_code >= 400:
            self.failed(what, r.status_code)
            return None
        return r

    async def visitor(self, i: int) -> None:
        scenario, lang = SCENARIOS[i % len(SCENARIOS)]
        await asyncio.sleep(i * self.ramp_s)
        if self.stopped:
            return
        async with httpx.AsyncClient(base_url=self.base, timeout=120, transport=self.transport) as c:
            self.spent["session"] += 1
            s = await self.call(c, "session", "POST", "/api/sessions",
                                json={"language": lang, "scenario": scenario, "mode": "replay"})
            if s is None or await self.call(c, "verify", "POST", f"/api/sessions/{s.json()['session_id']}/verify",
                                            json={"otp": s.json()["otp_demo"]}) is None:
                return
            self.spent["turn"] += 1
            t = await self.call(c, "thread", "POST", "/api/agent/threads")
            if t is None:
                return
            thread = t.json()["thread_id"]
            for k in range(self.turns):
                if self.stopped:
                    return
                await self.turn(c, thread, MESSAGES[lang][k % len(MESSAGES[lang])])

    async def turn(self, c: httpx.AsyncClient, thread: str, text: str) -> None:
        body = {"input": {"messages": [{"role": "user", "content": text}]}}
        t0, first, progress, final = time.perf_counter(), None, None, None
        self.spent["turn"] += 1
        try:
            async with c.stream("POST", f"/api/agent/threads/{thread}/runs/stream", json=body) as r:
                if r.status_code >= 400:
                    await r.aread()
                    self.failed("turn", r.status_code)
                    return
                event = None
                async for line in r.aiter_lines():
                    if line.startswith("event:"):
                        event = line[6:].strip()
                        elapsed = (time.perf_counter() - t0) * 1000
                        first = elapsed if first is None else first
                        if event == "progress" and progress is None:
                            progress = elapsed
                    elif line.startswith("data:") and event == "turn":
                        final = json.loads(line[5:])
        except httpx.HTTPError as exc:
            self.errors.append(f"turn {type(exc).__name__}")
            return
        self.turn_ms.append((time.perf_counter() - t0) * 1000)
        if first is not None:
            self.first_event_ms.append(first)
        if progress is not None:
            self.first_progress_ms.append(progress)
        if final is None:
            self.errors.append("turn: no final turn event")
        elif any(s.get("id") == "retry" for s in final.get("suggestions") or []):
            self.degraded += 1                    # the api's agent-unavailable turn (Platform failed)

    async def run(self) -> dict:
        started = time.perf_counter()
        await asyncio.gather(*(self.visitor(i) for i in range(self.sessions)))
        wall = time.perf_counter() - started
        total = self.sessions * self.turns
        return {"sessions": self.sessions, "turns_each": self.turns, "ramp_s": self.ramp_s, "wall_s": round(wall, 1),
                "turns_planned": total, "turns_ok": len(self.turn_ms), "requests": self.spent,
                **summary("turn", self.turn_ms), **summary("first_event", self.first_event_ms),
                **summary("first_progress", self.first_progress_ms),
                "errors": len(self.errors), "error_rate": round(len(self.errors) / max(1, total), 3),
                "degraded_turns": self.degraded, "rate_limited": self.rate_limited,
                "server_errors": self.server_errors, "error_list": self.errors[:20],
                "turn_ms": [round(x) for x in self.turn_ms]}


def pct(v: list[float], q: float) -> float:
    """Nearest-rank percentile (q in 0..1)."""
    v = sorted(v)
    return v[min(len(v) - 1, round(q * (len(v) - 1)))] if v else float("nan")


def summary(name: str, values: list[float]) -> dict:
    if not values:
        return {f"{name}_p50_ms": None, f"{name}_p95_ms": None, f"{name}_max_ms": None}
    return {f"{name}_p50_ms": round(statistics.median(values)), f"{name}_p95_ms": round(pct(values, 0.95)),
            f"{name}_max_ms": round(max(values))}


def main() -> int:
    sessions = min(int(os.environ.get("SESSIONS", "5")), MAX_SESSIONS)
    turns = min(int(os.environ.get("TURNS", "3")), MAX_TURNS_TOTAL // sessions)
    prior, budget = int(os.environ.get("PRIOR_TURNS", "0")), float(os.environ.get("BUDGET_USD", "1.5"))
    per_turn, projected = projected_usd(prior + sessions * turns)
    print(f"projection [projected]: <= {per_turn:.4f} USD per turn, <= {projected:.3f} USD for {prior} prior + "
          f"{sessions * turns} turns (budget {budget} USD)", flush=True)
    if projected > budget:
        print("ABORT: the projected spend exceeds the budget", file=sys.stderr)
        return 2
    load = Load(os.environ["BASE_URL"].rstrip("/"), sessions, turns, float(os.environ.get("RAMP_S", "0.5")))
    out = {**asyncio.run(load.run()), "projected_usd_upper": round(projected, 4)}
    print(json.dumps(out, indent=1))
    if len(sys.argv) > 1:
        with open(sys.argv[1], "w", encoding="utf-8") as f:
            f.write(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
