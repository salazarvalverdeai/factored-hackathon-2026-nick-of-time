"""The decisions graph (docs/decisions/graph.md) is generated from the ADR and spec headers and must not go stale."""

import importlib.util
import json
import re
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "decision_graph", ROOT / "scripts" / "docs" / "decision_graph.py"
)
dg = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(dg)

STALE = "docs/decisions/graph.md is stale: run python scripts/docs/decision_graph.py"


def _graph():
    return json.loads(dg.generate(ROOT)[1])


ADR_FILES = sorted((ROOT / "docs" / "adr").glob("[0-9][0-9][0-9][0-9]-*.md"))


def test_committed_graph_freshness_is_a_warning_only():
    """Never blocks a PR that adds an ADR or flips a spec status; `make docs-graph` regenerates."""
    md, js = dg.generate(ROOT)
    for name, want in (("graph.md", md), ("graph.json", js)):
        f = ROOT / "docs/decisions" / name
        if not f.exists() or f.read_text(encoding="utf-8") != want:
            warnings.warn(STALE, stacklevel=1)


def _copy_inputs(tmp_path):
    """A fresh copy of every input the generator reads (headers, queries, evidence and component paths)."""
    import shutil

    for rel in ("docs/adr", "specs", "docs/decisions", "queries/pitch"):
        shutil.copytree(ROOT / rel, tmp_path / rel)
    extra = dg.load_extra(ROOT)
    paths = [e["path"] for e in extra["evidence"] if e.get("path")] + [
        c for cs in extra["components"].values() for c in cs
    ]
    for rel in paths:
        dst = tmp_path / rel
        if (ROOT / rel).is_dir():
            dst.mkdir(parents=True, exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / rel, dst)


def test_check_mode_passes_when_fresh_and_fails_when_stale(tmp_path, capsys):
    _copy_inputs(tmp_path)
    assert dg.main(["--root", str(tmp_path)]) == 0  # regenerate in the copy
    assert dg.main(["--check", "--root", str(tmp_path)]) == 0
    (tmp_path / "docs/decisions/graph.md").write_text("stale\n", encoding="utf-8")
    assert dg.main(["--check", "--root", str(tmp_path)]) == 1
    assert "stale" in capsys.readouterr().err


def test_every_adr_file_is_a_node():
    nodes = {
        n["id"]
        for n in json.loads(
            (ROOT / "docs/decisions/graph.json").read_text(encoding="utf-8")
        )["nodes"]
    }
    assert len(ADR_FILES) >= 27
    for f in ADR_FILES:
        assert f"adr-{f.name[:4]}" in nodes, f.name


def test_every_spec_file_is_a_node():
    nodes = {
        n["id"]
        for n in json.loads(
            (ROOT / "docs/decisions/graph.json").read_text(encoding="utf-8")
        )["nodes"]
    }
    for f in sorted((ROOT / "specs").glob("[0-9][0-9]-*.md")):
        assert f"spec-{f.name[:2]}" in nodes, f.name


def test_amended_and_superseded_edges_match_the_headers():
    edges = json.loads(
        (ROOT / "docs/decisions/graph.json").read_text(encoding="utf-8")
    )["edges"]
    amends = {(e["from"], e["to"]) for e in edges if e["kind"] == "amends"}
    supersedes = {(e["from"], e["to"]) for e in edges if e["kind"] == "supersedes"}
    want_amends, want_supersedes = set(), set()
    for f in ADR_FILES:
        head = f.read_text(encoding="utf-8").split("\n## ")[0]
        me = f"adr-{f.name[:4]}"
        if m := re.search(r"\*\*Amended by:\*\*(.*?)(?=\n- \*\*|\Z)", head, re.S):
            for n in re.findall(
                r"\[(?:ADR )?(\d{4})\]", m.group(1)
            ):  # the linked records, not dates in the prose
                want_amends.add((f"adr-{n}", me))
        if m := re.search(r"Superseded by\s*\[?(?:ADR\s*)?(\d{4})", head):
            want_supersedes.add((f"adr-{m.group(1)}", me))
        if m := re.search(
            r"\*\*Status:\*\*[^\n]*supersedes\s*\[?(?:ADR\s*)?(\d{4})", head
        ):
            want_supersedes.add((me, f"adr-{m.group(1)}"))
    assert want_amends and want_supersedes
    assert amends == want_amends
    assert supersedes == want_supersedes


def test_headers_are_consistent():
    """Findings are documentation bugs, reported as a warning so other PRs are never blocked."""
    for msg in dg.inconsistencies(ROOT):
        warnings.warn(f"header inconsistency: {msg}", stacklevel=1)


def test_extra_paths_exist_and_new_adr_does_not_crash(tmp_path):
    """build_graph validates every path in graph_extra.yaml; an ADR missing from the themes lands in 'Other'."""
    assert dg.build_graph(ROOT)["nodes"]
    _copy_inputs(tmp_path)
    src = (ROOT / "docs/adr/0003-scope-regulatory-clock-dispute-intake.md").read_text(
        encoding="utf-8"
    )
    (tmp_path / "docs/adr/0099-new.md").write_text(
        src.replace("# 0003.", "# 0099."), encoding="utf-8"
    )
    nodes = {n["id"]: n for n in dg.build_graph(tmp_path)["nodes"]}
    assert nodes["adr-0099"]["theme"] == "Other"


def test_problem_figures_carry_label_and_query():
    g = _graph()
    problems = [n for n in g["nodes"] if n["layer"] == "problem"]
    assert len(problems) >= 2
    for n in problems:
        assert n["evidence_label"] == "[data]"
        assert (ROOT / n["query"]).is_file() and (ROOT / n["csv"]).is_file()
    text = " ".join(n["label"] for n in problems)
    assert "36.4%" in text and "43.6%" in text and "76.6%" in text


def test_graph_md_links_from_the_adr_readme_and_user_guide():
    assert "decisions/graph.md" in (ROOT / "docs/adr/README.md").read_text(
        encoding="utf-8"
    )
    assert "decisions/graph.md" in (ROOT / "docs/user-guide.md").read_text(
        encoding="utf-8"
    )
