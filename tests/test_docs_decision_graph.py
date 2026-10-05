"""The decisions graph (docs/decisions/graph.md) is generated from the ADR and spec headers and must not go stale."""

import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "decision_graph", ROOT / "scripts" / "docs" / "decision_graph.py"
)
dg = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(dg)

ADR_FILES = sorted((ROOT / "docs" / "adr").glob("[0-9][0-9][0-9][0-9]-*.md"))


def test_committed_graph_equals_generated():
    md, js = dg.generate(ROOT)
    assert (ROOT / "docs/decisions/graph.md").read_text(encoding="utf-8") == md, (
        "run scripts/docs/decision_graph.py"
    )
    assert (ROOT / "docs/decisions/graph.json").read_text(encoding="utf-8") == js, (
        "run scripts/docs/decision_graph.py"
    )


def test_check_mode_passes_on_the_repo_and_fails_when_stale(tmp_path, capsys):
    assert dg.main(["--check"]) == 0
    # a copy of the inputs with a stale graph.md must fail
    for rel in ("docs/adr", "specs", "docs/decisions", "queries/pitch"):
        for f in (ROOT / rel).glob("*"):
            if f.is_file():
                (tmp_path / rel).mkdir(parents=True, exist_ok=True)
                (tmp_path / rel / f.name).write_bytes(f.read_bytes())
    extra = dg.load_extra(ROOT)
    for paths in [e.get("path") for e in extra["evidence"]] + [
        c for cs in extra["components"].values() for c in cs
    ]:
        if paths:
            target = tmp_path / paths
            if (ROOT / paths).is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / paths).read_bytes())
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
    """A supersede or amend stated on one side only, or contradicted by docs/adr/README.md, is a documentation bug."""
    assert dg.inconsistencies(ROOT) == []


def test_problem_figures_carry_label_and_query():
    g = json.loads((ROOT / "docs/decisions/graph.json").read_text(encoding="utf-8"))
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
