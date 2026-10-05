"""Robustness runner (task ROBUST): one conversation per character against `dispute_intake`, in-process, on the REAL MCP
server of INT1 (tests/local_mcp.py) over a MemoryStore and a fixture gold of the scenario's customer plus another
customer (the victim). Every turn goes through the deterministic checker; the report lists violations by rule and turn.

The customer is a speaker: `scripted` (the fixed messages of characters.yaml; CI's smoke, offline), or any callable
with the same shape (the live LLM simulator comes in a follow-up and never runs in CI). Replay mode only.
    PYTHONPATH=.:packages python -m eval.robustness.run [--arm S0] [--characters a,b]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import tempfile
from pathlib import Path
from typing import Any, Callable, Optional

import polars as pl
import yaml

from eval.robustness.checker import RULES, World, check_turn
from nick_of_time.contracts import TurnResult
from tests import local_mcp as L

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DEV = {c["id"]: c for c in map(json.loads, (ROOT / "eval/cases/dev.jsonl").read_text().splitlines())}
# speaker(n, last turn or None) → (text, attack) or None to end the conversation
Speaker = Callable[[int, Optional[TurnResult]], Optional[tuple[str, Optional[str]]]]


def characters() -> dict[str, Any]:
    return yaml.safe_load((HERE / "characters.yaml").read_text(encoding="utf-8"))


def scripted(character: dict[str, Any]) -> Speaker:
    """The character's fixed messages, in order; a dict item carries its attack tag."""
    items = [m if isinstance(m, dict) else {"text": m} for m in character["script"]]
    return lambda n, _last: (items[n - 1]["text"], items[n - 1].get("attack")) if n <= len(items) else None


def build_gold(folder: Path, case: dict[str, Any], victim: dict[str, Any]) -> Path:
    """INT1's fixture gold for the scenario's customer, plus the victim's rows in the same tables."""
    own, other = L.fixture_gold(folder / "own", case), L.fixture_gold(folder / "victim", victim)
    for table in ("transactions_enriched", "customers", "products"):
        pl.concat([pl.read_parquet(own / f"{table}.parquet"), pl.read_parquet(other / f"{table}.parquet")],
                  how="diagonal_relaxed").write_parquet(own / f"{table}.parquet")
    return own


def world_of(case: dict[str, Any], victim: dict[str, Any]) -> World:
    state, other = case["initial_state"], victim["initial_state"]
    foreign = {other["customer_id"]} | {f[k] for f in other["fixtures"] for k in ("transaction_id", "product_id")}
    scores = {f["fraud_score"] for c in (state, other) for f in c["fixtures"] if f.get("fraud_score") is not None}
    return World(customer_id=state["customer_id"], foreign=foreign, scores=scores)


def converse(name: str, character: dict[str, Any], victim_id: str, speaker: Speaker, *, arm: str = "S0",
             turns: int = 8, llm_client: Any = None) -> dict[str, Any]:
    """One conversation: up to `turns` turns, each checked; returns the character's report row."""
    case, victim = DEV[character["scenario"]], DEV[victim_id]
    run_id, language = f"ROBUST:{name}:{arm}", character["language"]
    world, rows = world_of(case, victim), []
    with tempfile.TemporaryDirectory(prefix="robust-") as tmp, L.memory_store() as (store, kind):
        mcp = L.LocalMCP(build_gold(Path(tmp), case, victim), store, kind, {}).start()
        try:
            sid = L.seed_session(store, world.customer_id, language, run_id)
            chat = L.Chat(mcp, sid, thread=f"robust-{name}", arm=arm,
                          **({"llm_client": llm_client} if llm_client else {}))
            last = None
            for n in range(1, turns + 1):
                said = speaker(n, last)
                if said is None:
                    break
                text, attack = said
                last = chat.say(text, language=language)
                cases = store.list_all_cases(run_id=run_id)
                world.cases = [(c.case_id, c.customer_id, store.queue_status(c.case_id)) for c in cases]
                world.recorded = {e.payload["action_id"]: e.payload["verification_id"] for c in cases
                                  for e in store.events(c.case_id) if e.type == "action_verified"}
                found = check_turn(n, text, attack, last, world)
                rows.append({"n": n, "said": text, "attack": attack, "decision": last.decision,
                             "reply": last.reply, "chips": [s.id for s in last.suggestions],
                             "actions": [f"{a.tool}:{a.state}" for a in last.actions],
                             "violations": [{"rule": v.rule, "detail": v.detail} for v in found]})
        finally:
            mcp.close()
    return {"character": name, "tags": ["robustness", f"character:{name}", f"scenario:{character['scenario']}",
                                        f"language:{language}"],
            "scenario": character["scenario"], "language": language, "arm": arm, "turns": rows,
            "violations": [{"turn": r["n"], **v} for r in rows for v in r["violations"]]}


def report(rows: list[dict[str, Any]], out: Path, **meta: Any) -> Path:
    """results/<stamp>.json and .md: per character its turns and violations (rule and turn)."""
    out.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    data = {**meta, "rules": RULES, "characters": rows,
            "violations": sum(len(r["violations"]) for r in rows)}
    (out / f"{stamp}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = [f"# Robustness run {stamp}", "", f"{json.dumps(meta, ensure_ascii=False)}", "",
             "| character | scenario | turns | violations |", "|---|---|---|---|"]
    lines += [f"| {r['character']} | {r['scenario']} | {len(r['turns'])} | "
              + ("; ".join(f"T{v['turn']} {v['rule']}: {v['detail']}" for v in r["violations"]) or "none") + " |"
              for r in rows]
    (out / f"{stamp}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out / f"{stamp}.json"


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Robustness suite: simulated customers vs dispute_intake")
    parser.add_argument("--arm", default="S0", help="the graph's arm: S0, S1 or S2")
    parser.add_argument("--characters", default="", help="comma-separated names; default all")
    parser.add_argument("--out", type=Path, default=HERE / "results")
    args = parser.parse_args(argv)
    config = characters()
    names = [n for n in args.characters.split(",") if n] or list(config["characters"])
    rows = [converse(name, config["characters"][name], config["victim"], scripted(config["characters"][name]),
                     arm=args.arm) for name in names]
    path = report(rows, args.out, arm=args.arm, speaker="scripted")
    total = sum(len(r["violations"]) for r in rows)
    print(f"{len(rows)} characters, {total} violation(s); report {path}")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
