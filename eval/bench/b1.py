"""B1 runner (spec 15 T2: AC-01, AC-06, AC-08, AC-11): every arm of arms.yaml over the same frozen sentences, with
the budget guard first and one usage row per sentence. LLM arms send exactly `smoke.converse_request` (D-011) with the
`understand` prompt and schema of the graph (spec 04), after a smoke call of that same request picks the toolChoice
mode and the temperature (D-016) recorded per arm. A missing or invalid tool call is a wrong prediction (D-022), and
so is a sentence whose call fails after the arm started: it is counted in the arm's `errors` and the run goes on."""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Optional

import jsonschema

from eval.bench import core, smoke
from nick_of_time.config import DEMO_TODAY
from nick_of_time.llm.steps import INTENT_SCHEMA, UNDERSTAND

ROOT = Path(__file__).resolve().parents[2]
SPLITS = ROOT / "eval/classifier"
TODAY = DEMO_TODAY                       # replay only (AC-09): every arm reads relative dates against the same day
PROMPT = UNDERSTAND + json.dumps(INTENT_SCHEMA, sort_keys=True)     # what the prompt hash covers (AC-05)
SLOT_KEYS = ("amount", "currency", "date", "merchant")
SMOKE_TEXT = "No reconozco un cargo de 45 dólares en mi tarjeta."
IN_TOKENS, OUT_TOKENS = 900, 120         # [assumption] per-message projection: prompt + schema + message; tool input
JEV_URL = "https://api.typesafe.ai/v1/systemone"
JEV_CRITERIA = {  # the five intents of spec 11, as in scripts/checks/check_jev.py
    "unrecognized_charge": "The customer does not recognize a charge on their card (possible fraud).",
    "wrongful_charge": "The customer recognizes the merchant but the charge is wrong: duplicated, wrong amount, "
                       "not delivered or cancelled.",
    "status_inquiry": "The customer asks about the status of an existing case, dispute or card block.",
    "human_request": "The customer asks to talk to a person or a human agent.",
    "out_of_scope": "Anything that is not about disputing a card charge."}

Sink = Callable[[dict], None]            # receives each scored item as soon as it exists (`run` writes it to disk)
B1_FILE = "intent-b1-v1.joblib"          # the file name spec 11 exports B1 under (eval/classifier/evaluate.py)
CLASSIFIER_RECORD = "apps/web/public/data/classifier.json"                     # spec 11 §7.1: classifier-test export
CLASSIFIER_CLAIM = "eval/results/classifier-test/classifier-test.start.json"   # that run's claim_run marker (spec 10)
HEX64 = re.compile(r"[0-9a-f]{64}")


class BenchError(RuntimeError):
    """The run cannot start as asked (no split file, unsealed protocol for the test split, no recorded B1 file)."""


@dataclass(frozen=True)
class B1Model:
    """The spec 11 B1 arm for one bench run: the loaded model and the record benchmark.json keeps as `b1_model` (path,
    sha256, scikit-learn version, where it came from), or the reason the arm cannot run (AC-06)."""
    nlu: object = None
    record: dict = field(default_factory=dict)
    reason: Optional[str] = None


def train_b1_model(root: Path, out_dir: Path) -> B1Model:
    """Development runs: B1 built exactly as `make classifier` builds it (spec 11 T3): fit on train, sigmoid-calibrated
    on validation, fixed seed, from the same split source (the promoted files, or the reviewed drafts before
    promotion); the test split is never read. Saved into the run folder and recorded by path and sha256. It is
    calibrated on validation, so its validation score is a development figure only (PROTOCOL §1.1)."""
    from eval.classifier import evaluate as ev
    data, source = ev.load_splits("validation", root)
    train, val = ev.intents_only(data["train"]), ev.intents_only(data["validation"])
    nlu = ev.B1NLU(ev.train_b1([r["text"] for r in train], [r["intent"] for r in train],
                               [r["text"] for r in val], [r["intent"] for r in val]))
    out_dir.mkdir(parents=True, exist_ok=True)
    nlu.save(out_dir / B1_FILE)
    return B1Model(nlu, {**ev.model_record(out_dir / B1_FILE, root),
                         "source": f"trained by this development run: fit on train, calibrated on validation ({source})"})


def official_b1_model(root: Path, seal: dict) -> B1Model:
    """The test run (`make bench`) never fits B1: it loads the exact file the one classifier-test run exported and
    recorded in classifier.json `b1_model` (path and sha256), under the same seal. Refused (BenchError) when that run
    has not happened, its record is not a sealed test run or names another protocol, or the file is missing or its
    bytes differ from the recorded sha256. The model is unpickled from the very bytes that were hashed."""
    root = Path(root)
    rec_path = root / CLASSIFIER_RECORD
    if not rec_path.is_file() or not (root / CLASSIFIER_CLAIM).is_file():
        raise BenchError(f"no classifier-test run ({CLASSIFIER_RECORD}, {CLASSIFIER_CLAIM}): run `make classifier-test` "
                         "first, it exports the B1 file this run loads")
    data = json.loads(rec_path.read_text(encoding="utf-8")).get("data") or {}
    proto = data.get("protocol") or {}
    if data.get("run") != "test" or proto.get("status") != "SEALED":
        raise BenchError(f"{CLASSIFIER_RECORD} is not the sealed classifier-test record (run={data.get('run')!r})")
    if proto.get("sha256") != seal.get("sha256"):
        raise BenchError(f"{CLASSIFIER_RECORD} was written under protocol {proto.get('sha256')}, not the sealed "
                         f"{seal.get('sha256')}")
    rec = data.get("b1_model") or {}
    rel, sha = rec.get("path"), rec.get("sha256") or ""
    if not rel or not HEX64.fullmatch(sha):
        raise BenchError(f"{CLASSIFIER_RECORD} records no B1 file (b1_model path and sha256)")
    path = (root / rel).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise BenchError(f"the B1 file {rel} recorded by the classifier-test run is missing")
    blob = path.read_bytes()
    if hashlib.sha256(blob).hexdigest() != sha:
        raise BenchError(f"the B1 file {rel} differs from the sha256 the classifier-test run recorded ({sha[:12]}…)")
    import joblib
    from nick_of_time.nlu.learned import B1NLU
    loaded = joblib.load(io.BytesIO(blob))
    return B1Model(B1NLU(loaded["model"], loaded["version"]),
                   {"path": rel, "sha256": sha, "sklearn_version": rec.get("sklearn_version"),
                    "source": f"loaded from the classifier-test run ({CLASSIFIER_RECORD} b1_model); never refit"})


def load_split(split: str, root: Path = ROOT) -> list[dict]:
    """The sentences of one split, injection rows apart (D-022). The test split must be the promoted file; before
    promotion, validation and train are read from the reviewed drafts in memory (development runs only)."""
    path = root / "eval/classifier" / f"{split}.jsonl"
    if path.exists():
        rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    elif split == "test":
        raise BenchError("no eval/classifier/test.jsonl: promote the reviewed splits first (eval.classifier.review)")
    else:
        from eval.classifier import review
        rows = review._reviewed(root, split)
    return [r for r in rows if r.get("label") != "injection"]


def user_text(message: str) -> str:
    return json.dumps({"today": TODAY, "message": message}, ensure_ascii=False)       # as steps.ask sends it


def item(row: dict, intent, slots, *, tool_call: bool, latency_ms, usage: dict, price: dict | None,
         error: str | None = None) -> dict:
    tin, tout = usage.get("inputTokens", 0), usage.get("outputTokens", 0)
    cost = (tin * price["input_per_1m"] + tout * price["output_per_1m"]) / 1e6 if price else 0.0
    return {"id": row["id"], "language": row["language"], "gold": row["intent"], "pred": intent,
            "gold_slots": row.get("slots") or {}, "pred_slots": slots or {}, "tool_call": tool_call,
            "latency_ms": latency_ms, "tokens_in": tin, "tokens_out": tout, "cost_usd": cost, "error": error}


def failed(row: dict, exc: BaseException, errors: dict[str, int], price: dict | None) -> dict:
    """A sentence whose call or reply failed after the arm started (throttling after retries, a dropped connection,
    an input the provider rejects, an unreadable answer): a wrong prediction that stays in the denominator (D-022),
    with no tokens known, counted per error class in the arm's `errors`. One bad sentence never ends the arm."""
    name = type(exc).__name__
    errors[name] = errors.get(name, 0) + 1
    return item(row, None, None, tool_call=False, latency_ms=None, usage={}, price=price,
                error=f"{name}: {exc}"[:300])


def _emit(out: list[dict], it: dict, sink: Sink | None) -> None:
    out.append(it)
    if sink is not None:
        sink(it)


def llm_items(arm: dict, rows: list[dict], provider: smoke.Provider, price: dict, sink: Sink | None = None) -> dict:
    """Smoke first (AC-11): the arm runs B1 only on a pass, with the mode the smoke accepted. The arm is unavailable
    only when it cannot start (the smoke call fails, AC-06); after that, an error on one sentence scores it wrong."""
    try:
        first = smoke.smoke_arm(arm["model_id"], provider, system=UNDERSTAND, user=user_text(SMOKE_TEXT),
                                schema=INTENT_SCHEMA)
    except Exception as exc:              # an unmapped error at the smoke step: this arm cannot start, the run goes on
        raise core.ProviderUnavailable(f"smoke {type(exc).__name__}: {exc}"[:300]) from exc
    if first["result"] == "unavailable":
        raise core.ProviderUnavailable(first["reason"])
    if first["result"] != "pass":
        return {"status": "no structured output", "reason": first["reason"], "items": [],
                "tool_choice_mode": first["tool_choice_mode"], "temperature": first.get("temperature"), "errors": {}}
    used = first.get("usage") or {}
    smoke_cost = (used.get("inputTokens", 0) * price["input_per_1m"] + used.get("outputTokens", 0) * price["output_per_1m"]) / 1e6
    mode, out, temps, errors = first["tool_choice_mode"], [], set(), {}
    for row in rows:
        try:
            r = provider(arm["model_id"], UNDERSTAND, user_text(row["text"]), INTENT_SCHEMA, mode)
            tool = r.get("tool_input")
            try:
                jsonschema.validate(tool, INTENT_SCHEMA)
            except jsonschema.ValidationError:
                tool = None               # D-022: no tool call or a schema failure scores as a wrong prediction
            slots = tool and {k: tool["slots"].get(k) for k in SLOT_KEYS}    # D-078: a missing slot key is null
            it = item(row, tool and tool["intent"], slots, tool_call=tool is not None,
                      latency_ms=r.get("latency_ms"), usage=r.get("usage") or {}, price=price)
            temps.add(r.get("temperature"))
        except Exception as exc:
            it = failed(row, exc, errors, price)
        _emit(out, it, sink)
    temp = temps.pop() if len(temps) == 1 else ("mixed" if temps else first.get("temperature"))
    return {"items": out, "tool_choice_mode": mode, "temperature": temp, "smoke_cost_usd": smoke_cost,
            "errors": errors}


def b0_items(rows: list[dict], sink: Sink | None = None) -> dict:
    """The B0 rules arm of spec 11 (no model file)."""
    from nick_of_time.nlu import load_nlu
    return nlu_items(load_nlu("B0"), rows, sink)


def b1_items(rows: list[dict], model: B1Model | None, sink: Sink | None = None) -> dict:
    """The B1 TF-IDF + LR arm of spec 11, from the model the command trained (development) or loaded by its recorded
    sha256 (test); without one the arm is unavailable with the reason (AC-06). Its version names the file's hash."""
    if model is None or model.nlu is None:
        raise core.ProviderUnavailable((model and model.reason) or "no B1 model was given to this run")
    out = nlu_items(model.nlu, rows, sink)
    return {**out, "version": f"{model.nlu.version} sha256:{model.record['sha256'][:12]}"}


def nlu_items(nlu, rows: list[dict], sink: Sink | None = None) -> dict:
    """One no-LLM reading per sentence (no tokens, no price)."""
    out: list[dict] = []
    for row in rows:
        t0 = time.perf_counter()
        r = nlu.parse(row["text"], None, today=date.fromisoformat(TODAY))
        _emit(out, item(row, r.intent, r.slots.model_dump(), tool_call=True,
                        latency_ms=round((time.perf_counter() - t0) * 1000, 3), usage={}, price=None), sink)
    return {"items": out, "tool_choice_mode": None, "temperature": None, "errors": {}}


def jev_call(arm: dict, key: str, text: str) -> tuple[str | None, dict, int]:
    """One Jev typed choice: (choice, usage in Converse keys, latency in ms). Raises on any transport or parse error."""
    body = json.dumps({"model": arm["model_id"], "state": text, "questions": {"intent": {
        "type": "choice", "instructions": "What does the bank customer want in this message?",
        "criteria": JEV_CRITERIA}}}).encode()
    req = urllib.request.Request(JEV_URL, data=body, headers={"Authorization": f"Bearer {key}",
                                 "Content-Type": "application/json", "User-Agent": "nickoftime-bench/1.0"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=20) as resp:
        ans = json.load(resp)
    usage = ans.get("usage") or {}
    choice = (ans.get("answers", {}).get("intent") or {}).get("choice")
    return choice, {"inputTokens": usage.get("input_tokens", 0)}, round((time.perf_counter() - t0) * 1000)


def jev_items(arm: dict, rows: list[dict], price: dict, sink: Sink | None = None) -> dict:
    """Jev answers one typed choice (intent only, no slots); its usage is billed per input token [assumption]. One
    smoke call on SMOKE_TEXT decides whether the arm can start (AC-06, inside the budget's smoke allowance); after it,
    an error on one sentence scores that sentence wrong."""
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key:
        raise core.ProviderUnavailable("TYPESAFE_API_KEY is not in the environment")
    try:
        _, used, _ = jev_call(arm, key, SMOKE_TEXT)
    except Exception as exc:
        raise core.ProviderUnavailable(f"jev smoke {type(exc).__name__}: {exc}"[:300]) from exc
    out: list[dict] = []
    errors: dict[str, int] = {}
    for row in rows:
        try:
            choice, usage, latency = jev_call(arm, key, row["text"])
            it = item(row, choice, None, tool_call=choice in JEV_CRITERIA, latency_ms=latency, usage=usage,
                      price=price)
        except Exception as exc:
            it = failed(row, exc, errors, price)
        _emit(out, it, sink)
    return {"items": out, "tool_choice_mode": None, "temperature": None, "errors": errors,
            "smoke_cost_usd": used["inputTokens"] * price["input_per_1m"] / 1e6}


def fake_provider(model_id: str, system: str, user: str, schema: dict, mode: str) -> dict:
    """Offline stand-in for Bedrock (CI and runs without credentials): answers with the B0 reading, so every 'LLM'
    arm is a copy of B0 and nothing it reports is a model measurement."""
    from nick_of_time.nlu import load_nlu
    r = load_nlu("B0").parse(json.loads(user)["message"], None, today=date.fromisoformat(TODAY))
    tool = {"intent": r.intent, "confidence": r.confidence, "dispute_detected": r.dispute_detected,
            "slots": r.slots.model_dump()}
    return {"tool_input": tool, "text": "", "stop_reason": "tool_use", "temperature": 0, "latency_ms": 1,
            "usage": {"inputTokens": len(system + user) // 4, "outputTokens": 40}}


def run(arms: list[dict], rows: list[dict], provider: smoke.Provider, prices: dict, run_date: str,
        workers: int = 6, budget: float = core.BUDGET_USD, items_path: Path | None = None,
        b1_model: B1Model | None = None) -> list[dict]:
    """The budget guard on the whole run first (AC-08: smoke ladder + every sentence, per billable arm), then the
    arms in parallel (each arm's sentences in order, so its latency is its own). Unavailable arms are recorded and
    the run goes on (AC-06); an error an arm cannot recover from is recorded on that arm and never aborts the others.
    With `items_path`, each scored item is appended to that JSONL with its arm and flushed as soon as it exists, so
    a crash leaves on disk every item already paid for; the file is opened for append and never truncated. The B1
    arm scores `b1_model`, which the command trains (development) or loads by its recorded hash (test), never this."""
    n = len(rows) + len(smoke.LADDER) + 1
    core.check_budget(core.projected_spend(arms, prices, n, IN_TOKENS, OUT_TOKENS), budget)
    lock, fh = threading.Lock(), None
    if items_path is not None:
        items_path.parent.mkdir(parents=True, exist_ok=True)
        fh = items_path.open("a", encoding="utf-8")

    def sink_for(arm_id: str) -> Sink | None:
        if fh is None:
            return None

        def write(it: dict) -> None:
            with lock:
                fh.write(json.dumps({"arm": arm_id, **it}, ensure_ascii=False) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
        return write

    def evaluate(arm: dict) -> dict:
        sink = sink_for(arm["id"])
        if arm["provider"] == "rules":
            return b0_items(rows, sink)
        if arm["provider"] == "classifier":
            return b1_items(rows, b1_model, sink)
        if arm["provider"] == "typesafe":
            return jev_items(arm, rows, prices[arm["id"]], sink)
        return llm_items(arm, rows, provider, prices[arm["id"]], sink)

    def one(arm: dict) -> dict:
        try:
            return core.run_arms([arm], prices, PROMPT, run_date, evaluate, n_messages=0, in_tokens=0,
                                 out_tokens=0)[0]
        except Exception as exc:          # a harness bug on one arm: recorded with its reason, the other arms go on
            row = core.make_row(arm, prices, PROMPT, run_date)
            row.update(status="unavailable", reason=f"harness error {type(exc).__name__}: {exc}"[:300], items=[],
                       errors={type(exc).__name__: 1})
            return row

    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(one, arms))
    finally:
        if fh is not None:
            fh.close()
