"""Spec 10 AC-07 — the seal is read correctly, and the shared guard for the one-time runs (held-out, spec 15 test
split, spec 17 test window) refuses unless the seal holds and the run was never started.

The guard tests build a throwaway git repository in tmp_path with synthetic files; the real-file test only reads
eval/PROTOCOL.md.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

import pytest

from eval.harness import report, seal_guard
from eval.harness.seal_guard import SealError

ROOT = Path(__file__).resolve().parents[1]
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false",
       "-c", "tag.gpgsign=false", "-c", "init.defaultBranch=main"]
FRAUD = hashlib.sha256(b"synthetic fraud split").hexdigest()
BODY = """# Evaluation protocol

From the repository root:

```
sed '/^<!-- SEAL:BEGIN -->$/,/^<!-- SEAL:END -->$/d' eval/PROTOCOL.md | shasum -a 256
```

"""


def git(repo: Path, *args: str) -> str:
    return subprocess.run([*GIT, *args], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()


def commit(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def sealed_protocol(repo: Path, status: str = "SEALED", protocol_sha: str | None = None) -> str:
    """BODY plus a seal block with the hashes of the synthetic inputs, computed by the sealed methods."""
    heldout = seal_guard.file_sha256(repo / seal_guard.HELDOUT_CASES)
    block = (f"{seal_guard.BEGIN}\n- Status: {status}\n"
             f"- Protocol sha256: {protocol_sha or hashlib.sha256(BODY.encode()).hexdigest()}\n"
             f"- Classifier split manifest sha256: {seal_guard.classifier_manifest_sha256(repo)}\n"
             f"- Agent held-out sha256 (eval/heldout.sha256, ADR 0007): {heldout}\n"
             f"- Fraud split hash (spec 17 T1): {FRAUD}\n- Sealed on: 2026-10-05\n{seal_guard.END}\n")
    return BODY + block


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, str]:
    """A repository sealed like the real one: protocol, split files, held-out cases, tag protocol-v1."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    write(repo, "README.md", "x\n")
    commit(repo, "init")
    write(repo, "eval/classifier/train.jsonl", '{"text": "a"}\n')
    write(repo, "eval/classifier/test.jsonl", '{"text": "b"}\n')
    write(repo, "eval/classifier/draft/test.jsonl", '{"text": "draft"}\n')
    write(repo, seal_guard.HELDOUT_CASES, '{"id": "EV-0201"}\n')
    write(repo, "eval/heldout.sha256", seal_guard.file_sha256(repo / seal_guard.HELDOUT_CASES) + "\n")
    write(repo, seal_guard.PROTOCOL_PATH, sealed_protocol(repo))
    sha = commit(repo, "seal")
    git(repo, "tag", seal_guard.SEAL_TAG)
    write(repo, "code.py", "print(1)\n")                       # work after the seal, as on main
    commit(repo, "after the seal")
    return repo, sha


ALL_INPUTS = {"classifier_splits": None, "agent_heldout": None, "fraud_split": FRAUD}


def check(repo: tuple[Path, str], **inputs) -> dict:
    return seal_guard.check_seal(inputs or ALL_INPUTS, root=repo[0], commit=repo[1])


def test_ac_07_protocol_seal_reads_the_real_sealed_protocol():
    """AC-07: the seal block is found by its anchored markers, not by the markers quoted in the `sed` command, so the
    real eval/PROTOCOL.md reads SEALED with its sealed sha256, and that sha256 recomputes by the sealed method."""
    data = (ROOT / "eval/PROTOCOL.md").read_bytes()
    block = re.search(r"^<!-- SEAL:BEGIN -->$(.*?)^<!-- SEAL:END -->$", data.decode(), re.M | re.S).group(1)
    expected = re.search(r"^- Protocol sha256: ([0-9a-f]{64})$", block, re.M).group(1)
    seal = report.protocol_seal()
    assert seal == {"status": "SEALED", "sha256": expected} and expected.startswith("533fc516")
    assert seal_guard.protocol_sha256(data) == expected


def test_ac_07_protocol_seal_ignores_quoted_markers(tmp_path):
    """AC-07: the bug reproduced — a quoted marker before the block made the seal read UNSEALED."""
    protocol = tmp_path / "PROTOCOL.md"
    protocol.write_text(BODY + "<!-- SEAL:BEGIN -->\n- Status: SEALED\n- Protocol sha256: " + "a" * 64
                        + "\n<!-- SEAL:END -->\n", encoding="utf-8")
    assert report.protocol_seal(protocol) == {"status": "SEALED", "sha256": "a" * 64}


def test_ac_07_guard_happy_path_returns_what_the_result_embeds(repo):
    """AC-07: with the seal intact and every sealed input unchanged, the guard returns the seal for the result file
    and the claim writes the start marker before any model call."""
    guard = check(repo)
    assert guard == {"status": "SEALED", "sha256": hashlib.sha256(BODY.encode()).hexdigest(),
                     "tag": "protocol-v1", "commit": repo[1], "head": git(repo[0], "rev-parse", "HEAD"),
                     "test_review": "rules-v1",
                     "inputs": {"classifier_splits": seal_guard.classifier_manifest_sha256(repo[0]),
                                "agent_heldout": seal_guard.file_sha256(repo[0] / seal_guard.HELDOUT_CASES),
                                "fraud_split": FRAUD}}
    out = repo[0] / "eval/results/2026-10-06-heldout"
    marker = seal_guard.claim_run("heldout", out, guard, root=repo[0], argv=["make", "x"], fetch=False)
    record = json.loads(marker.read_text(encoding="utf-8"))
    assert marker.name == "heldout.start.json"
    assert (record["run"], record["head"], record["tag_commit"], record["protocol_sha256"], record["argv"]) == (
        "heldout", guard["head"], repo[1], guard["sha256"], ["make", "x"])
    assert record["started_at"].endswith("Z")


def test_ac_07_guard_refuses_without_the_tag(repo):
    """AC-07: no tag protocol-v1, no run."""
    git(repo[0], "tag", "-d", seal_guard.SEAL_TAG)
    with pytest.raises(SealError, match="does not exist"):
        check(repo)


def test_ac_07_guard_refuses_a_tag_on_another_commit(repo):
    """AC-07: the tag must resolve to the pinned sealing commit."""
    with pytest.raises(SealError, match="not the sealing commit"):
        seal_guard.check_seal(ALL_INPUTS, root=repo[0], commit="0" * 40)


def test_ac_07_guard_refuses_a_tag_that_is_not_an_ancestor_of_head(repo):
    """AC-07: a HEAD that does not descend from the sealing commit is refused, even with the same protocol bytes."""
    git(repo[0], "checkout", "-q", "--orphan", "other")
    commit(repo[0], "same files, other history")
    with pytest.raises(SealError, match="not an ancestor of HEAD"):
        check(repo)


def test_ac_07_guard_refuses_a_protocol_edited_after_the_tag(repo):
    """AC-07: a committed edit of eval/PROTOCOL.md after the tag is refused."""
    path = repo[0] / seal_guard.PROTOCOL_PATH
    path.write_text(path.read_text(encoding="utf-8").replace("# Evaluation protocol", "# Edited"), encoding="utf-8")
    commit(repo[0], "edit the protocol")
    with pytest.raises(SealError, match="at HEAD differs"):
        check(repo)


def test_ac_07_guard_refuses_an_uncommitted_protocol_edit(repo):
    """AC-07: an edit of eval/PROTOCOL.md in the working tree is refused."""
    with (repo[0] / seal_guard.PROTOCOL_PATH).open("a", encoding="utf-8") as fh:
        fh.write("\n")
    with pytest.raises(SealError, match="working tree differs"):
        check(repo)


def test_ac_07_guard_refuses_a_seal_that_does_not_hold(tmp_path):
    """AC-07: an UNSEALED protocol, or a protocol sha256 that does not recompute, is refused at the tag itself."""
    for status, sha, message in (("UNSEALED", None, "not SEALED"), ("SEALED", "b" * 64, "recomputed")):
        repo = tmp_path / status / (sha or "ok")
        repo.mkdir(parents=True)
        git(repo, "init", "-q")
        write(repo, "eval/classifier/train.jsonl", '{"text": "a"}\n')
        write(repo, seal_guard.HELDOUT_CASES, '{"id": "EV-0201"}\n')
        write(repo, seal_guard.PROTOCOL_PATH, sealed_protocol(repo, status, sha))
        sealed = commit(repo, "seal")
        git(repo, "tag", seal_guard.SEAL_TAG)
        with pytest.raises(SealError, match=message):
            seal_guard.check_seal({}, root=repo, commit=sealed)


def test_ac_07_guard_refuses_a_sealed_input_whose_hash_differs(repo):
    """AC-07: each named input is compared with its SEALED field: a committed split edit, a held-out edit even with
    eval/heldout.sha256 updated to match, and a wrong fraud split hash are refused."""
    write(repo[0], "eval/classifier/test.jsonl", '{"text": "changed"}\n')
    commit(repo[0], "edit a split")
    with pytest.raises(SealError, match="classifier_splits differs"):
        check(repo, classifier_splits=None)
    check(repo, agent_heldout=None)                              # an input not named is not checked
    write(repo[0], seal_guard.HELDOUT_CASES, '{"id": "EV-0201", "edited": true}\n')
    write(repo[0], "eval/heldout.sha256", seal_guard.file_sha256(repo[0] / seal_guard.HELDOUT_CASES) + "\n")
    commit(repo[0], "edit the held-out and its hash file")
    with pytest.raises(SealError, match="agent_heldout differs"):
        check(repo, agent_heldout=None)
    with pytest.raises(SealError, match="fraud_split differs"):
        check(repo, fraud_split="c" * 64)
    with pytest.raises(SealError, match="cannot hash fraud_split"):
        check(repo, fraud_split=None)


def test_ac_07_guard_refuses_uncommitted_changes_to_sealed_inputs(repo):
    """AC-07: an uncommitted or untracked file among the sealed eval/ inputs is refused; drafts are not sealed."""
    write(repo[0], "eval/classifier/draft/new.jsonl", "{}\n")
    check(repo)
    write(repo[0], "eval/classifier/extra.jsonl", "{}\n")
    with pytest.raises(SealError, match="uncommitted changes"):
        check(repo)


def test_ac_07_second_claim_is_refused(repo, tmp_path):
    """AC-07: a run is claimed once — its start marker anywhere in eval/results/ refuses a second claim, in the same
    out dir or another one; the out dir must be under eval/results/ so the marker is always seen."""
    guard = check(repo)
    results = repo[0] / "eval/results"
    with pytest.raises(SealError, match="must be under eval/results/"):
        seal_guard.claim_run("heldout", tmp_path / "outside", guard, root=repo[0], fetch=False)
    seal_guard.claim_run("heldout", results / "2026-10-06-heldout", guard, root=repo[0], fetch=False)
    for out in ("2026-10-06-heldout", "2026-10-07-retry"):
        with pytest.raises(SealError, match="already started"):
            seal_guard.claim_run("heldout", results / out, guard, root=repo[0], fetch=False)
    seal_guard.claim_run("bench-test", results / "bench-test", guard, root=repo[0], fetch=False)  # another run is free
    check(repo)                                                   # markers are not sealed inputs


def test_ac_07_claim_sees_outputs_committed_on_head_and_origin(repo):
    """AC-07: outputs of the run in the working tree, committed on HEAD, or only on origin/main refuse the claim."""
    guard = check(repo)
    results = repo[0] / "eval/results"
    write(repo[0], "eval/results/2026-10-06-heldout/meta.json", "{}\n")
    with pytest.raises(SealError, match="2026-10-06-heldout"):            # working tree
        seal_guard.claim_run("heldout", results / "a", guard, root=repo[0], fetch=False)
    commit(repo[0], "results")
    git(repo[0], "rm", "-q", "-r", "--cached", "eval/results")
    (results / "2026-10-06-heldout/meta.json").unlink()
    with pytest.raises(SealError, match="HEAD:eval/results/2026-10-06-heldout"):
        seal_guard.claim_run("heldout", results / "b", guard, root=repo[0], fetch=False)
    git(repo[0], "update-ref", "refs/remotes/origin/main", "HEAD")
    git(repo[0], "reset", "-q", "--hard", "HEAD~1")
    with pytest.raises(SealError, match="2026-10-06-heldout"):            # only on origin/main now
        seal_guard.claim_run("heldout", results / "c", guard, root=repo[0], fetch=False)
    seal_guard.claim_run("fraud-test", results / "fraud-test", guard, root=repo[0], fetch=False)
