# Load test (draft)

`loadtest.py` opens a few parallel **replay** demo sessions, verifies each with its on-screen OTP, opens an agent thread
and sends a few chat turns. It prints p50, p95 and max latency per step and the error count. Python 3.11+ and `httpx`
(already in `requirements.txt`'s environment).

## How the lead runs it
```bash
BASE_URL=https://nickoftime.salazarvalverdeai.com SESSIONS=5 TURNS=3 .venv/bin/python loadtest/loadtest.py
```
- `SESSIONS` 1 to 10 (default 5), `TURNS` per session (default 3), `TIMEOUT` seconds per request (default 90).
- Exit code 0 means no errors; 1 means errors (first 20 are printed); 2 means `BASE_URL` is missing.
- Each turn is a real agent run and costs LLM calls on Bedrock; start with `SESSIONS=2 TURNS=1`, then raise. The public
  demo has per-IP rate limits and a daily LLM spend cap in open PR #148 (spec 05 AC-18); a run from one IP can hit
  them and the 429 answers are reported as errors. Run it outside the pitch window, and not from several machines.
- Replay sessions use the frozen demo date (ADR 0020), so results do not depend on the day.

## Dry run
Done on 2026-10-05 against the **local stub api** (no `DATABASE_URL`, no Platform), not against production:
5 sessions x 3 turns, 0 errors, all steps under 0.05 s (the stub echoes fixtures, so this checks the script, not
capacity). Command used: `PYTHONPATH=packages:contracts:. uvicorn app.main:app --app-dir apps/api --port 8765`, then
`BASE_URL=http://127.0.0.1:8765 python loadtest/loadtest.py`.

**Untested against the store-backed api and the live agent.** Open PR #152 changes how demo sessions are opened (by
scenario with a typed name), and the script posts the older `{customer_id, mode}` body of spec 01 section 6.2; adjust the
`session` step if #152 lands without keeping that shape.
