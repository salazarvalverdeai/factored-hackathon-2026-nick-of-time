"""Small load test for the public demo flow (draft, for the lead to run).

Opens N parallel replay demo sessions against BASE_URL, verifies each with its on-screen OTP, opens an agent thread and
sends a few customer turns, then prints p50/p95 latency per step and the error count.

    BASE_URL=http://localhost:8000 python loadtest/loadtest.py            # local api
    BASE_URL=https://<public host> SESSIONS=5 TURNS=3 python loadtest/loadtest.py

Environment: BASE_URL (required), SESSIONS (default 5, max 10), TURNS (default 3), TIMEOUT seconds (default 90).
It sends real chat turns, which cost LLM calls and count against the demo rate limits: keep SESSIONS small.
Routes: specs/01-integration-contract.md section 6.2 and apps/api/app/main.py.
"""

from __future__ import annotations

import asyncio
import os
import statistics
import sys
import time

import httpx

BASE_URL = os.environ.get("BASE_URL", "").rstrip("/")
SESSIONS = min(int(os.environ.get("SESSIONS", "5")), 10)
TURNS = int(os.environ.get("TURNS", "3"))
TIMEOUT = float(os.environ.get("TIMEOUT", "90"))
COOKIE = "not_session"  # apps/api/app/main.py: session cookie name
MESSAGES = [
    "Hola, no reconozco un cargo en mi tarjeta",
    "Si, bloquea la tarjeta por favor",
    "¿Cómo va mi caso?",
    "¿Ya está bloqueada mi tarjeta?",
]


def pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]


async def timed(
    client: httpx.AsyncClient,
    samples: dict[str, list[float]],
    errors: list[str],
    step: str,
    method: str,
    path: str,
    **kwargs,
) -> httpx.Response | None:
    start = time.perf_counter()
    try:
        response = await client.request(method, path, **kwargs)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        errors.append(f"{step}: {type(exc).__name__} {exc}")
        return None
    finally:
        samples.setdefault(step, []).append(time.perf_counter() - start)
    return response


async def one_session(index: int, customer_id: str, samples: dict[str, list[float]], errors: list[str]) -> None:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        created = await timed(
            client, samples, errors, "session", "POST", "/api/sessions", json={"customer_id": customer_id, "mode": "replay"}
        )
        if created is None:
            return
        session = created.json()
        # The cookie is `secure`, so over plain http it is sent by hand.
        headers = {"Cookie": f"{COOKIE}={session['session_id']}"}
        verified = await timed(
            client, samples, errors, "verify", "POST", f"/api/sessions/{session['session_id']}/verify",
            json={"otp": session["otp_demo"]},
        )
        if verified is None:
            return
        thread = await timed(client, samples, errors, "thread", "POST", "/api/agent/threads", headers=headers)
        if thread is None:
            return
        thread_id = thread.json()["thread_id"]
        for turn in range(TURNS):
            body = {"input": {"messages": [{"role": "user", "content": MESSAGES[turn % len(MESSAGES)]}]}}
            response = await timed(
                client, samples, errors, "turn", "POST", f"/api/agent/threads/{thread_id}/runs/stream",
                headers=headers, json=body,
            )
            if response is not None and "event: turn" not in response.text:
                errors.append(f"turn: session {index} got a stream without a final turn event")


async def main() -> int:
    if not BASE_URL:
        print("Set BASE_URL, e.g. BASE_URL=http://localhost:8000", file=sys.stderr)
        return 2
    samples: dict[str, list[float]] = {}
    errors: list[str] = []
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        listed = await timed(client, samples, errors, "demo_customers", "GET", "/api/demo/customers")
    if listed is None:
        print("\n".join(errors), file=sys.stderr)
        return 1
    customers = [c["customer_id"] for c in listed.json()]
    started = time.perf_counter()
    await asyncio.gather(*(one_session(i, customers[i % len(customers)], samples, errors) for i in range(SESSIONS)))
    wall = time.perf_counter() - started
    print(f"BASE_URL={BASE_URL} sessions={SESSIONS} turns_each={TURNS} wall={wall:.1f}s")
    print(f"{'step':<15}{'n':>4}{'p50 s':>9}{'p95 s':>9}{'max s':>9}")
    for step, values in samples.items():
        print(f"{step:<15}{len(values):>4}{statistics.median(values):>9.2f}{pct(values, 0.95):>9.2f}{max(values):>9.2f}")
    print(f"errors: {len(errors)}")
    for line in errors[:20]:
        print(f"  {line}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
