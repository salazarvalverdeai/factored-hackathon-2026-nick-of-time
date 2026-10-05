"""Spec 15 AC-01, AC-03, AC-07 — `make bench` on the test split is the one-time run of PROTOCOL §0.2: it calls the
shared seal guard (`check_seal` with the classifier split manifest, then `claim_run("bench")`) before the first model
call, embeds the guard in benchmark.json, carries the `rules-v1` label (PROTOCOL §1.1, ADR 0028) and never overwrites
an official output.

Every test builds a throwaway repository in tmp_path with synthetic split files, as tests/test_spec10_seal_guard.py
does; the real repository, its seal and its test split are never touched. Fake provider only (CLAUDE.md).
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from eval.bench import __main__ as cli
from eval.bench import b1, core
from eval.harness import seal_guard

GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false",
       "-c", "tag.gpgsign=false", "-c", "init.defaultBranch=main", "-c", "core.hooksPath=/dev/null"]
BODY = "# Evaluation protocol\n\nSynthetic protocol for the spec 15 guard tests.\n\n"
ROWS = [{"id": f"T{i}", "language": lang, "intent": intent, "text": text, "slots": {"amount": "45", "date": None}}
        for i, (lang, intent, text) in enumerate([
            ("es", "unrecognized_charge", "No reconozco un cargo de 45 dólares en mi tarjeta."),
            ("es", "human_request", "Quiero hablar con una persona."),
            ("pt", "unrecognized_charge", "Não reconheço uma cobrança de 45 reais no meu cartão."),
            ("pt", "status_inquiry", "Como está o meu caso?")])]
MARKER = "eval/results/bench/bench.start.json"


def run_git(repo: Path, *args: str) -> str:
    return subprocess.run([*GIT, *args], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()


def commit(repo: Path, message: str) -> str:
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-q", "-m", message)
    return run_git(repo, "rev-parse", "HEAD")


def write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


@pytest.fixture
def calls() -> list:
    """One entry per model call: whether the claim marker existed at that moment."""
    return []


@pytest.fixture
def repo(tmp_path: Path, monkeypatch, calls: list) -> Path:
    """A throwaway repository sealed like the real one (synthetic splits, protocol, tag protocol-v1), with the bench
    command pointed at it, a synthetic split loader and the fake provider standing in for Bedrock."""
    repo = tmp_path / "repo"
    repo.mkdir()
    run_git(repo, "init", "-q")
    write(repo, "eval/classifier/train.jsonl", '{"text": "a"}\n')
    write(repo, "eval/classifier/test.jsonl", '{"text": "synthetic"}\n')
    block = (f"{seal_guard.BEGIN}\n- Status: SEALED\n- Protocol sha256: {hashlib.sha256(BODY.encode()).hexdigest()}\n"
             f"- Classifier split manifest sha256: {seal_guard.classifier_manifest_sha256(repo)}\n"
             f"- Sealed on: 2026-10-05\n{seal_guard.END}\n")
    write(repo, seal_guard.PROTOCOL_PATH, BODY + block)
    sealed = commit(repo, "seal")
    run_git(repo, "tag", seal_guard.SEAL_TAG)
    write(repo, "code.py", "print(1)\n")
    commit(repo, "after the seal")
    monkeypatch.setattr(cli, "ROOT", repo)
    monkeypatch.setattr(cli, "SEAL_COMMIT", sealed)
    monkeypatch.setattr(cli, "generator", lambda split: "deepseek.v3-v1:0")
    monkeypatch.setattr(b1, "load_split", lambda split: ROWS)
    arms = [a for a in core.load_arms() if a["id"] in ("b0_rules", "nova-micro")]
    monkeypatch.setattr(core, "load_arms", lambda: arms)

    def provider(*args, **kwargs):
        calls.append((repo / MARKER).exists())            # the claim marker must exist before any model call
        return b1.fake_provider(*args, **kwargs)
    monkeypatch.setattr(b1.smoke, "bedrock_provider", lambda: provider)
    return repo


def official(repo: Path, key: str) -> Path:
    return repo / cli.OFFICIAL[key]


def test_ac_07_test_run_claims_before_the_first_model_call_and_embeds_the_guard(repo, calls):
    """AC-01, AC-07: the guard passes, the run is claimed (marker written) before the first model call, and
    benchmark.json embeds the guard dict as `protocol`, with the classifier split manifest checked."""
    assert cli.main(["--split", "test"]) == 0
    assert calls and all(calls)
    marker = json.loads((repo / MARKER).read_text(encoding="utf-8"))
    data = json.loads(official(repo, "json").read_text(encoding="utf-8"))["data"]
    guard = data["protocol"]
    assert guard["status"] == "SEALED" and guard["tag"] == "protocol-v1" and guard["commit"] == cli.SEAL_COMMIT
    assert guard["inputs"] == {"classifier_splits": seal_guard.classifier_manifest_sha256(repo)}
    assert guard["head"] == marker["head"] and guard["sha256"] == marker["protocol_sha256"]
    assert data["run_kind"] == "pre-registered test run" and data["split"] == "test"
    items = official(repo, "items").read_text(encoding="utf-8").splitlines()
    assert len(items) == len(ROWS) * 2                    # streamed by b1.run, not rewritten at the end


def test_ac_03_test_results_carry_the_rules_v1_label(repo):
    """AC-03, PROTOCOL §1.1, ADR 0028: benchmark.json, bench_b1.md and bench_b1.csv say the test split was decided
    by fixed rules, without independent human review."""
    assert cli.main(["--split", "test"]) == 0
    data = json.loads(official(repo, "json").read_text(encoding="utf-8"))["data"]
    assert (data["test_review"], data["test_review_label"]) == ("rules-v1", cli.TEST_REVIEW_LABEL)
    assert data["protocol"]["test_review"] == "rules-v1"
    assert cli.TEST_REVIEW_LABEL == "test split decided by fixed rules, without independent human review"
    table = official(repo, "table").read_text(encoding="utf-8")
    assert cli.TEST_REVIEW_LABEL in table.splitlines()[0] and "rules-v1" in table.splitlines()[0]
    assert "## Model map" in table and "[assumption] D-077 pending" in table
    with official(repo, "csv").open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert rows and all(r["test_review"] == "rules-v1" and r["test_review_label"] == cli.TEST_REVIEW_LABEL
                        for r in rows)


def test_ac_07_a_second_test_run_is_refused(repo, calls, capsys):
    """AC-07: once claimed, the test run is refused again, even with the outputs removed; no model is called."""
    assert cli.main(["--split", "test"]) == 0
    first = len(calls)
    assert cli.main(["--split", "test"]) == 2 and "never overwritten" in capsys.readouterr().err
    for key in cli.OFFICIAL:
        official(repo, key).unlink()
    assert cli.main(["--split", "test"]) == 2 and "already started" in capsys.readouterr().err
    assert len(calls) == first


def test_ac_07_an_existing_official_output_is_never_overwritten(repo, calls, capsys):
    """AC-07: an official output already present (working tree or committed) refuses the run before the claim."""
    write(repo, cli.OFFICIAL["svg"], "<svg/>\n")
    assert cli.main(["--split", "test"]) == 2 and "never overwritten" in capsys.readouterr().err
    assert not (repo / MARKER).exists() and not calls
    commit(repo, "an svg on HEAD")
    (repo / cli.OFFICIAL["svg"]).unlink()
    assert cli.existing_outputs(repo) == [f"HEAD:{cli.OFFICIAL['svg']}"]
    assert cli.main(["--split", "test"]) == 2 and not (repo / MARKER).exists()


@pytest.mark.parametrize("breakage", ["no tag", "split edited", "split uncommitted"])
def test_ac_07_a_broken_seal_refuses_before_any_claim_or_call(repo, calls, capsys, breakage):
    """AC-01, AC-07: no tag, a committed split edit (manifest differs) or an uncommitted one is refused by the guard,
    with no marker written and no model called."""
    if breakage == "no tag":
        run_git(repo, "tag", "-d", seal_guard.SEAL_TAG)
    else:
        write(repo, "eval/classifier/test.jsonl", '{"text": "edited"}\n')
        if breakage == "split edited":
            commit(repo, "edit the split")
    assert cli.main(["--split", "test"]) == 2 and "the seal does not hold" in capsys.readouterr().err
    assert not (repo / MARKER).exists() and not calls


def test_ac_07_dry_run_checks_the_seal_but_never_claims(repo, calls):
    """AC-08 with AC-07: a test dry run prints the projected spend under the guard and leaves the run unclaimed."""
    assert cli.main(["--split", "test", "--dry-run"]) == 0
    assert not (repo / MARKER).exists() and not calls
