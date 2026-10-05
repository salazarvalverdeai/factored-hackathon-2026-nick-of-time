"""Spec 10 T7 — the held-out runs once (AC-03, AC-07, AC-09, AC-11; ADR 0007).

Every test runs in a throwaway git repository sealed like the real one (tag protocol-v1, PROTOCOL with the sha256 of a
synthetic held-out made of the five example cases) against an in-memory api. The real eval/cases/heldout.jsonl is
never opened.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from eval.harness import Api, heldout, labels, report, seal_guard
from eval.harness.__main__ import main
from nick_of_time.config import HAIKU, SONNET
from tests.test_spec10_harness import EXAMPLES, final_for

GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false",
       "-c", "tag.gpgsign=false", "-c", "init.defaultBranch=main"]
BODY = "# Evaluation protocol\n\nSynthetic, for the spec 10 T7 tests.\n\n"
META = {"S0": {"provider": "none", "model_fast": None, "model_graph": None},
        "S1": {"provider": "bedrock", "model_fast": HAIKU, "model_graph": None},
        "S2": {"provider": "bedrock", "model_fast": None, "model_graph": SONNET}}
ARGS = ["run", "--set", "heldout", "--arms", "S0,S1,S2", "--runs", "4", "--workers", "1"]


def git(repo: Path, *args: str) -> str:
    return subprocess.run([*GIT, *args], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()


def write_cases(path: Path, set_name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps({**c, "set": set_name}, ensure_ascii=False) + "\n" for c in EXAMPLES),
                    encoding="utf-8", newline="\n")


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Path:
    """Sealed repository; the harness's root, its sealed paths and the web summary point into it."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    cases = repo / seal_guard.HELDOUT_CASES
    write_cases(cases, "heldout")
    write_cases(repo / heldout.DEV_CASES, "dev")
    sha = seal_guard.file_sha256(cases)
    (repo / "eval/heldout.sha256").write_text(sha + "\n")
    block = (f"{seal_guard.BEGIN}\n- Status: SEALED\n- Protocol sha256: {hashlib.sha256(BODY.encode()).hexdigest()}\n"
             f"- Agent held-out sha256 (eval/heldout.sha256, ADR 0007): {sha}\n- Sealed on: 2026-10-05\n"
             f"{seal_guard.END}\n")
    (repo / seal_guard.PROTOCOL_PATH).write_text(BODY + block, encoding="utf-8", newline="\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "seal")
    git(repo, "tag", seal_guard.SEAL_TAG)
    commit = git(repo, "rev-parse", "HEAD")
    monkeypatch.setattr(heldout, "ROOT", repo)
    monkeypatch.setattr(seal_guard.check_seal, "__defaults__", (None, seal_guard.ROOT, seal_guard.SEAL_TAG, commit))
    for name, path in (("PROTOCOL", repo / seal_guard.PROTOCOL_PATH), ("HELDOUT_HASH", repo / "eval/heldout.sha256"),
                       ("HELDOUT_CASES", cases), ("WEB_SUMMARY", repo / "apps/web/public/data/evaluation_summary.json")):
        monkeypatch.setattr(report, name, path)
    monkeypatch.setattr(labels, "LABELS", tmp_path / "no-labels.parquet")
    return repo


def stack(seen: list | None = None, health: dict | None = None, meta=None, fail_heldout: bool = False,
          stop_after: int | None = None, live: bool = False) -> Api:
    """An in-memory stack: health, seed, turns and final state, with each arm's run_meta (`meta(arm)`)."""
    sessions: dict[str, dict] = {}
    meta = meta or (lambda arm: META[arm])
    health = {"status": "ok", "today": {"replay": "2026-06-01", "live": "2026-10-05"}} if health is None else health

    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/health":
            return httpx.Response(200, json=health) if health else httpx.Response(503, json={})
        if path == "/api/eval/seed":
            body = json.loads(request.content)
            if seen is not None:
                seen.append(body["run_id"])
            sid = f"S-{len(sessions) + 1:016d}"
            sessions[sid] = body
            held = not body["run_id"].endswith(":preflight")
            stopped = held and stop_after is not None and len(sessions) > stop_after + 3
            mode = "live" if live or stopped else "replay"
            return httpx.Response(200, json={"session_id": sid, "thread_id": f"t-{sid}", "run_id": body["run_id"],
                                             "arm": body["arm"], "mode": mode})
        if path.endswith("/runs/stream"):
            sid = path.split("/")[-3][2:]
            held = not sessions[sid]["run_id"].endswith(":preflight")
            return httpx.Response(500 if fail_heldout and held else 200, text="event: turn\ndata: {}\n\n")
        body = sessions[path.rsplit("/", 1)[-1]]
        case = next(c for c in EXAMPLES if c["id"] == body["run_id"].split(":")[0])
        return httpx.Response(200, json=final_for(case, arm=body["arm"], run_meta={
            "git_sha": "abc", "policies_version": 2, "prompt_hash": None, **meta(body["arm"])}))

    return Api(httpx.Client(transport=httpx.MockTransport(handle), base_url="http://eval.test"))


def out_dir(repo: Path) -> Path:
    return repo / "eval/results" / f"{datetime.now(timezone.utc):%Y-%m-%d}-heldout"


def test_ac_07_heldout_runs_once_with_the_guard_in_every_result(repo, capsys):
    """AC-07, T7: the seal holds, the preflight passes on dev cases, the run is claimed, every run is recorded, and
    meta.json and both evaluation_summary.json carry the guard; a second run is refused before the system is called."""
    seen: list = []
    assert main(ARGS, api=stack(seen)) == 0
    printed = capsys.readouterr().out
    assert "[projected] projected cost" in printed and "S1 ~0.15 USD, S2 ~0.45 USD" in printed
    assert seen[:3] == ["EV-0001:S0:preflight", "EV-0001:S1:preflight", "EV-0001:S2:preflight"]
    assert len(seen) == 3 + 5 * 3 * 4
    out = out_dir(repo)
    assert (out / "heldout.start.json").is_file()
    assert len((out / "runs.jsonl").read_text().splitlines()) == 60
    meta = json.loads((out / "meta.json").read_text())
    assert meta["run_status"] == "complete" and meta["arms_pinned"] == ["S0", "S1", "S2"] and meta["runs_per_case"] == 4
    guard = meta["protocol"]
    assert (guard["status"], guard["tag"], guard["commit"]) == ("SEALED", "protocol-v1", git(repo, "rev-parse", "HEAD"))
    assert guard["inputs"] == {"agent_heldout": seal_guard.file_sha256(repo / seal_guard.HELDOUT_CASES)}
    assert meta["model_map"]["label"] == "[assumption]" and "D-080" in meta["model_map"]["source"]
    assert meta["projected_cost"] == heldout.projected_cost() and meta["projected_cost"]["label"] == "[projected]"
    assert meta["preflight"]["arms"]["S1"]["run_meta"]["model_fast"] == HAIKU
    web = json.loads(report.WEB_SUMMARY.read_text())
    assert web == json.loads((out / "evaluation_summary.json").read_text()) and web["data"]["protocol"] == guard
    seen.clear()
    assert main(ARGS, api=stack(seen)) == 2 and not seen
    assert "not empty" in capsys.readouterr().err


def test_ac_07_a_claim_in_another_out_folder_also_refuses(repo, capsys):
    """AC-07: the run-once marker anywhere under eval/results/ refuses a new run, whatever the date folder."""
    guard = seal_guard.check_seal(inputs={"agent_heldout": None}, root=repo)
    seal_guard.claim_run("heldout", repo / "eval/results/2026-10-04-heldout", guard, root=repo, fetch=False)
    seen: list = []
    assert main(ARGS, api=stack(seen)) == 2
    assert "already started" in capsys.readouterr().err
    assert seen == ["EV-0001:S0:preflight", "EV-0001:S1:preflight", "EV-0001:S2:preflight"]   # dev cases only


@pytest.mark.parametrize("argv, message", [
    (["--arms", "S0", "--runs", "1"], "only as pre-registered"),
    (["--arms", "S0,S1", "--runs", "4"], "only as pre-registered"),
    (["--arms", "S0,S1,S2", "--runs", "3"], "only as pre-registered"),
    (["--arms", "S0,S1,S2", "--runs", "4", "--out", "x"], "no --cases, --out or --web"),
    (["--arms", "S0,S1,S2", "--runs", "4", "--cases", "x.jsonl"], "no --cases, --out or --web"),
])
def test_ac_03_heldout_arms_and_runs_are_pinned_to_the_protocol(repo, capsys, argv, message):
    """AC-03 (S0, S1 and S2 on the same held-out, 4 runs, ADR 0007): any other arms, runs or paths are refused before
    the seal check, the preflight or the claim."""
    seen: list = []
    assert main(["run", "--set", "heldout", *argv], api=stack(seen)) == 2
    assert message in capsys.readouterr().err and not seen and not (repo / "eval/results").exists()


@pytest.mark.parametrize("problem, message", [
    ("dead", "health check failed"),
    ("today", "not DEMO_TODAY 2026-06-01"),
    ("fake", "fake provider"),
    ("model", "model_fast is"),
    ("live", "not 'replay'"),
])
def test_ac_07_preflight_refuses_a_wrong_stack_without_consuming_the_run(repo, capsys, problem, message):
    """AC-07, T7: a dead api, a replay date other than DEMO_TODAY, the fake provider, a wrong model or a live session
    stop the command on a dev case, before the claim; nothing held-out is seeded and the run is still available."""
    seen: list = []
    api = {"dead": lambda: stack(seen, health={}),
           "today": lambda: stack(seen, health={"status": "ok", "today": {"replay": "2026-10-05"}}),
           "fake": lambda: stack(seen, meta=lambda arm: {**META[arm], "provider": "fake"} if arm == "S1" else META[arm]),
           "model": lambda: stack(seen, meta=lambda arm: {**META[arm], "model_fast": SONNET} if arm == "S1" else META[arm]),
           "live": lambda: stack(seen, live=True)}[problem]()
    assert main(ARGS, api=api) == 2
    assert message in capsys.readouterr().err
    assert all(run_id.endswith(":preflight") for run_id in seen) and not (repo / "eval/results").exists()
    assert main(ARGS, api=stack()) == 0                                # the one run was not consumed


def test_ac_03_the_s1_map_comes_from_the_spec_15_file_when_it_exists(repo, capsys):
    """AC-03, spec 15 §4.2: S1 is the chosen map of eval/results/model_map.json when spec 15 wrote it; the preflight
    then expects that model, so a stack still on the default refuses."""
    path = repo / heldout.MODEL_MAP
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"label": "[data]", "source": "spec 15 B2", "arms": {
        "S1": {"provider": "bedrock", "model_fast": "us.example.chosen-v1:0"},
        "S2": {"provider": "bedrock", "model_graph": SONNET}}}))
    assert main(ARGS, api=stack()) == 2
    assert "expected 'us.example.chosen-v1:0'" in capsys.readouterr().err
    chosen = {**META, "S1": {**META["S1"], "model_fast": "us.example.chosen-v1:0"}}
    assert main(ARGS, api=stack(meta=lambda arm: chosen[arm])) == 0
    meta = json.loads((out_dir(repo) / "meta.json").read_text())
    assert meta["model_map"]["label"] == "[data]" and meta["model_map"]["arms"]["S1"]["model_fast"].endswith("chosen-v1:0")


def test_ac_09_a_set_that_stops_after_the_claim_keeps_its_runs_and_is_marked_aborted(repo, capsys):
    """AC-09, T7 (D-079 default): the runs seen before a stop stay in runs.jsonl, meta.json says aborted, the web
    summary is not written, the exit is non-zero, and the marker keeps the run from starting again."""
    assert main(ARGS, api=stack(stop_after=7)) == 3
    assert "run_status aborted" in capsys.readouterr().err
    out = out_dir(repo)
    kept = [json.loads(line) for line in (out / "runs.jsonl").read_text().splitlines()]
    assert len(kept) == 7 and [r["run_id"] for r in kept][:2] == ["EV-0001:S0:1", "EV-0001:S0:2"]
    meta = json.loads((out / "meta.json").read_text())
    assert meta["run_status"] == "aborted" and "not 'replay'" in meta["error"] and meta["runs"] == 7
    assert not report.WEB_SUMMARY.exists()
    assert main(ARGS, api=stack()) == 2


def test_ac_09_runs_are_appended_as_they_finish(repo, monkeypatch):
    """AC-09: each run reaches runs.jsonl when it finishes, before the set ends, so a crash keeps what was seen."""
    sizes: list[int] = []
    real = heldout.run_set

    def spy(*args, on_record, **kwargs):
        def keep(record):
            on_record(record)
            sizes.append(len((out_dir(repo) / "runs.jsonl").read_text().splitlines()))
        return real(*args, on_record=keep, **kwargs)
    monkeypatch.setattr(heldout, "run_set", spy)
    assert main(ARGS, api=stack()) == 0
    assert sizes == list(range(1, 61))


def test_ac_11_every_run_failed_exits_non_zero_without_the_web_summary(repo, capsys):
    """AC-11, T7: when every held-out run failed (a stack that broke after the preflight), the results stay in the run
    folder, the web summary is not written and the command exits 1."""
    assert main(ARGS, api=stack(fail_heldout=True)) == 1
    assert "every held-out run failed" in capsys.readouterr().err
    meta = json.loads((out_dir(repo) / "meta.json").read_text())
    assert (meta["runs"], meta["failed_runs"], meta["run_status"]) == (60, 60, "complete")
    assert not report.WEB_SUMMARY.exists()
