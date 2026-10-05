"""One guard for the one-time runs after the seal of eval/PROTOCOL.md (spec 10 AC-07, spec 15, spec 17; ADR 0021).

The spec 15 benchmark on the test split, the spec 10 held-out run and the spec 17 test-window report each call
`check_seal(...)` and then `claim_run(...)` before any model call or label read:

    guard = seal_guard.check_seal(inputs={"agent_heldout": None})        # None: the guard hashes the file itself
    seal_guard.claim_run("heldout", out_dir, guard)                      # refuses a second run, writes the marker
    ... run, and embed `guard` in the result file ...

The guard only hashes the sealed inputs; it never parses them.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = "eval/PROTOCOL.md"
BEGIN = "<!-- SEAL:BEGIN -->"
END = "<!-- SEAL:END -->"
SEAL_TAG = "protocol-v1"
# The commit the seal of eval/PROTOCOL.md was made on (tag protocol-v1, "Sealed on: 2026-10-05", PR #166). The seal
# block cannot record its own commit, so it is pinned here; the guard also checks that the tag resolves to it.
SEAL_COMMIT = "7b18f72f4f7c427e51f54dadf9435b0896af476a"
TEST_REVIEW = "rules-v1"                                     # ADR 0028: the classifier test split was decided by rules
HEX64 = re.compile(r"[0-9a-f]{64}")
# Sealed inputs a caller can name: the seal field that holds its hash and, when the guard can hash it from files,
# how (eval/PROTOCOL.md "What is hashed"). The fraud split hash needs the gold data: the caller computes it with
# scripts.ml.fraud_split.split_hash and passes the value.
INPUTS = {
    "classifier_splits": "Classifier split manifest sha256",       # seal (b)
    "agent_heldout": "Agent held-out sha256 (eval/heldout.sha256, ADR 0007)",  # seal (c), sha256 of the case file
    "fraud_split": "Fraud split hash (spec 17 T1)",                 # seal (c)
}
HELDOUT_CASES = "eval/cases/heldout.jsonl"
# eval/ paths whose bytes the seal covers; any uncommitted change to them refuses the run.
SEALED_PATHS = (PROTOCOL_PATH, "eval/heldout.sha256", HELDOUT_CASES, ":(glob)eval/classifier/*.jsonl")
RESULTS_DIR = "eval/results"


class SealError(RuntimeError):
    """A one-time run is refused: the seal does not hold or the run was already started."""


def seal_fields(text: str) -> dict[str, str]:
    """Fields of the seal block: the lines between a line that is exactly the begin marker and a line that is exactly
    the end marker (anchored, so the markers quoted in the `sed` command of the protocol do not count)."""
    block = re.search(rf"^{re.escape(BEGIN)}$(.*?)^{re.escape(END)}$", text, re.M | re.S)
    return {k.strip(): v.strip() for k, v in re.findall(r"^- ([^:\n]+): (.+)$", block.group(1) if block else "", re.M)}


def protocol_body(data: bytes) -> bytes:
    """Seal (a): the protocol bytes without the seal block, the same lines that the documented `sed` removes."""
    keep, inside = [], False
    for line in data.splitlines(keepends=True):
        bare = line.rstrip(b"\n")
        if not inside and bare == BEGIN.encode():
            inside = True
            continue
        if inside:
            inside = bare != END.encode()
            continue
        keep.append(line)
    return b"".join(keep)


def protocol_sha256(data: bytes) -> str:
    return hashlib.sha256(protocol_body(data)).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def classifier_manifest_sha256(root: Path = ROOT) -> str:
    """Seal (b): sha256 of '<sha256>  <path>' lines for eval/classifier/*.jsonl (top level), C-locale path order."""
    files = sorted((root / "eval/classifier").glob("*.jsonl"), key=lambda p: p.relative_to(root).as_posix().encode())
    if not files:
        raise SealError("no eval/classifier/*.jsonl file to hash")
    lines = "".join(f"{file_sha256(f)}  {f.relative_to(root).as_posix()}\n" for f in files)
    return hashlib.sha256(lines.encode()).hexdigest()


def _git(root: Path, *args: str, check: bool = True, timeout: Optional[float] = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", *args], cwd=root, capture_output=True, check=check, timeout=timeout)
    except subprocess.CalledProcessError as exc:
        raise SealError(f"git {' '.join(args)} failed: {exc.stderr.decode(errors='replace').strip()}") from exc


def _rev(root: Path, ref: str) -> Optional[str]:
    out = _git(root, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}", check=False)
    return out.stdout.decode().strip() if out.returncode == 0 else None


def _computed(root: Path, name: str, given: Optional[str]) -> str:
    if given is not None:
        return given
    if name == "classifier_splits":
        return classifier_manifest_sha256(root)
    if name == "agent_heldout":
        path = root / HELDOUT_CASES
        if not path.is_file():
            raise SealError(f"{HELDOUT_CASES} is missing")
        return file_sha256(path)
    raise SealError(f"the guard cannot hash {name} itself: pass the value computed by its sealed method")


def check_seal(inputs: Optional[Mapping[str, Optional[str]]] = None, root: Path = ROOT, tag: str = SEAL_TAG,
               commit: str = SEAL_COMMIT) -> dict:
    """Refuse (SealError) unless the seal holds at HEAD and in the working tree, and each named sealed input still
    hashes to its sealed field. `inputs` maps a name of INPUTS to its computed hash, or to None for the guard to hash
    the files itself (classifier_splits, agent_heldout). Returns the dict the caller embeds in its result file."""
    root = Path(root)
    tag_sha = _rev(root, f"refs/tags/{tag}")
    if tag_sha is None:
        raise SealError(f"tag {tag} does not exist")
    if tag_sha != commit:
        raise SealError(f"tag {tag} resolves to {tag_sha}, not the sealing commit {commit}")
    head = _rev(root, "HEAD")
    if head is None or _git(root, "merge-base", "--is-ancestor", tag_sha, head, check=False).returncode != 0:
        raise SealError(f"tag {tag} is not an ancestor of HEAD")
    sealed = _git(root, "show", f"{tag_sha}:{PROTOCOL_PATH}").stdout
    if _git(root, "show", f"{head}:{PROTOCOL_PATH}").stdout != sealed:
        raise SealError(f"{PROTOCOL_PATH} at HEAD differs from {tag}")
    working = root / PROTOCOL_PATH
    if not working.is_file() or working.read_bytes() != sealed:
        raise SealError(f"{PROTOCOL_PATH} in the working tree differs from {tag}")
    fields = seal_fields(sealed.decode("utf-8"))
    if fields.get("Status") != "SEALED":
        raise SealError(f"{PROTOCOL_PATH} is {fields.get('Status', 'UNSEALED')}, not SEALED")
    protocol_sha = fields.get("Protocol sha256", "")
    if not HEX64.fullmatch(protocol_sha) or protocol_sha256(sealed) != protocol_sha:
        raise SealError(f"the protocol sha256 recomputed by the sealed method differs from the seal ({protocol_sha})")
    dirty = _git(root, "status", "--porcelain", "--untracked-files=all", "--", *SEALED_PATHS).stdout.decode().strip()
    if dirty:
        raise SealError(f"uncommitted changes to sealed inputs: {dirty.splitlines()[:5]}")
    checked = {}
    for name, given in (inputs or {}).items():
        if name not in INPUTS:
            raise SealError(f"unknown sealed input {name!r}; known: {sorted(INPUTS)}")
        expected = fields.get(INPUTS[name], "")
        if not HEX64.fullmatch(expected):
            raise SealError(f"the seal has no hash for {name} ({INPUTS[name]})")
        if _computed(root, name, given) != expected:
            raise SealError(f"{name} differs from the sealed {INPUTS[name]} ({expected[:8]}…)")
        checked[name] = expected
    return {"status": "SEALED", "sha256": protocol_sha, "tag": tag, "commit": tag_sha, "head": head,
            "test_review": TEST_REVIEW, "inputs": checked}


def _marker_name(name: str) -> str:
    return f"{name}.start.json"


def _is_output_of(path: str, name: str) -> bool:
    """A path of `name`'s outputs: its start marker, or under a folder named `name` or `<prefix>-name`
    (spec 10 §7.1 writes the held-out to eval/results/<date>-heldout/)."""
    parts = Path(path).parts
    return parts[-1] == _marker_name(name) or any(p == name or p.endswith(f"-{name}") for p in parts[:-1])


def _tree_outputs(root: Path, ref: str, name: str) -> list[str]:
    listed = _git(root, "ls-tree", "-r", "--name-only", ref, "--", RESULTS_DIR, check=False)
    rel = [p[len(RESULTS_DIR) + 1:] for p in listed.stdout.decode().splitlines()]
    return [f"{ref}:{RESULTS_DIR}/{p}" for p in rel if _is_output_of(p, name)]


def _origin_main(root: Path, fetch: bool) -> Optional[str]:
    if fetch:
        try:
            _git(root, "fetch", "--quiet", "origin", "main", check=False, timeout=60)
        except (subprocess.TimeoutExpired, OSError):
            pass
    return _rev(root, "refs/remotes/origin/main")


def claim_run(name: str, out_dir: Path, guard: Optional[dict] = None, root: Path = ROOT,
              argv: Optional[Sequence[str]] = None, fetch: bool = True) -> Path:
    """Run-once: `out_dir` must be under eval/results/. Refuse when a start marker or an output of `name` already
    exists in `out_dir`, in eval/results/ of the working tree, of HEAD, or of origin/main (fetched when reachable);
    else write `<out_dir>/<name>.start.json` (HEAD, tag, protocol sha256, UTC time, argv) and return its path. Call it
    before the first model call or label read."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", name):
        raise SealError(f"run name {name!r} must be lowercase letters, digits, '-' or '_'")
    root, out_dir = Path(root), Path(out_dir)
    results = root / RESULTS_DIR
    if not out_dir.resolve().is_relative_to(results.resolve()):
        raise SealError(f"the out dir of a one-time run must be under {RESULTS_DIR}/, where every later claim sees it")
    guard = guard or check_seal(root=root)
    found = [str(p) for p in sorted(out_dir.rglob("*")) if p.is_file()] if out_dir.exists() else []
    if results.exists():
        found += [str(p) for p in sorted(results.rglob("*"))
                  if p.is_file() and _is_output_of(p.relative_to(results).as_posix(), name)]
    found += _tree_outputs(root, "HEAD", name)
    origin = _origin_main(root, fetch)
    if origin:
        found += _tree_outputs(root, origin, name)
    if found:
        raise SealError(f"run {name!r} was already started or has outputs: {found[:5]}")
    marker = out_dir / _marker_name(name)
    out_dir.mkdir(parents=True, exist_ok=True)
    record = {"run": name, "head": _rev(root, "HEAD"), "tag": guard["tag"], "tag_commit": guard["commit"],
              "protocol_sha256": guard["sha256"], "origin_main": origin,
              "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "argv": list(sys.argv if argv is None else argv)}
    with marker.open("x", encoding="utf-8", newline="\n") as fh:      # "x": a concurrent second claim fails here
        fh.write(json.dumps(record, indent=2) + "\n")
    return marker
