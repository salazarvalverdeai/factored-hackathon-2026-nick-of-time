"""Decisions graph: why the problem was chosen, which decisions followed, what implements them, and the evidence.

Parses the headers of docs/adr/NNNN-*.md and specs/NN-*.md and reads docs/decisions/graph_extra.yaml for the few edges
the headers do not carry (problem -> ADR, evidence, components, layout themes). Emits docs/decisions/graph.md (a
Mermaid flowchart GitHub renders, a legend and a "Decision -> why -> evidence" table) and docs/decisions/graph.json.

Usage:
    python scripts/docs/decision_graph.py           # rewrite graph.md and graph.json
    python scripts/docs/decision_graph.py --check   # exit 1 when either file is stale (CI and tests use this)

Output is a pure function of the headers and the extra file: no clock, no network, sorted everywhere.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ADR_DIR = "docs/adr"
SPEC_DIR = "specs"
OUT_DIR = "docs/decisions"
EXTRA = "docs/decisions/graph_extra.yaml"
REPO_URL = "https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time"

SPEC_STATUSES = ("Superseded", "Implemented", "In progress", "Approved", "Draft")


# --------------------------------------------------------------------------------------------- parsing helpers
def _strip_parens(text: str) -> str:
    """Drop parenthesised asides (link targets, notes) so only the leading references remain."""
    prev = None
    while prev != text:
        prev, text = text, re.sub(r"\([^()]*\)", " ", text)
    return text


def _header(text: str) -> str:
    """The header block: everything before the first level-2 heading or horizontal rule."""
    lines = []
    for i, line in enumerate(text.splitlines()):
        if i > 0 and (line.startswith("## ") or line.strip() == "---"):
            break
        lines.append(line)
    return "\n".join(lines)


def _fields(header: str) -> dict[str, str]:
    """Map `**Name:** value` fields (bullets and inline `· **Name:**` alike) to their text, wraps joined."""
    out: dict[str, str] = {}
    pat = re.compile(
        r"\*\*([A-Z][\w ]*?):\*\*\s*(.*?)(?=\s*(?:·\s*)?\*\*[A-Z][\w ]*?:\*\*|\Z)", re.S
    )
    for m in pat.finditer(header):
        out.setdefault(
            m.group(1).strip(), " ".join(m.group(2).split()).rstrip("· ").strip()
        )
    return out


def _section(text: str, name: str) -> str:
    m = re.search(rf"^## {name}\s*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    return m.group(1).strip() if m else ""


def _first_sentence(text: str, limit: int = 230) -> str:
    text = re.sub(r"^\s*(?:\d+\.|[-*])\s+", "", text.strip())
    text = " ".join(text.split())
    text = re.sub(r"\*\*|`", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    m = re.search(r"(?<=[.!?])\s+(?=[A-Z(])", text)
    sentence = text[: m.start()] if m else text
    if len(sentence) > limit:
        sentence = sentence[:limit].rsplit(" ", 1)[0] + " ..."
    return sentence


def _adr_numbers(text: str, known: set[str]) -> list[str]:
    return sorted(
        {n for n in re.findall(r"\b(\d{4})\b", _strip_parens(text)) if n in known}
    )


def _spec_numbers(text: str) -> list[str]:
    text = re.sub(r"#\d+", " ", _strip_parens(text))
    return sorted(set(re.findall(r"\b(\d{2})\b", text)))


# ------------------------------------------------------------------------------------------------------ loading
def load_adrs(root: Path) -> dict[str, dict]:
    files = sorted((root / ADR_DIR).glob("[0-9][0-9][0-9][0-9]-*.md"))
    known = {f.name[:4] for f in files}
    adrs: dict[str, dict] = {}
    for f in files:
        text = f.read_text(encoding="utf-8")
        head = _header(text)
        fields = _fields(head)
        num = f.name[:4]
        title = re.sub(r"^#\s*\d+\.\s*", "", head.splitlines()[0]).strip()
        status_raw = fields.get("Status", "")
        status = next(
            (
                s
                for s in ("Superseded", "Accepted", "Proposed", "Deprecated")
                if status_raw.startswith(s)
            ),
            status_raw,
        )
        sup_by = re.search(r"Superseded by\s*\[?(?:ADR\s*)?(\d{4})", status_raw)
        supersedes = re.search(r"supersedes\s*\[?(?:ADR\s*)?(\d{4})", status_raw)
        amended = fields.get("Amended by", "")
        related = fields.get("Related", "")
        rel_specs = sorted(
            {
                n
                for seg in related.split("·")
                if re.match(r"\s*specs?\b", seg)
                for n in _spec_numbers(seg)
            }
        )
        # "ADRs 0019 and 0020" and "ADR 0018" both count; the record's own number does not.
        rel_adrs = [n for n in _adr_numbers(related, known) if n != num]
        adrs[num] = {
            "id": f"adr-{num}",
            "num": num,
            "file": f"{ADR_DIR}/{f.name}",
            "title": title,
            "status": status,
            "status_raw": status_raw,
            "superseded_by": sup_by.group(1) if sup_by else None,
            "supersedes": supersedes.group(1) if supersedes else None,
            "amended_by": _adr_numbers(amended, known),
            "related_adrs": rel_adrs,
            "related_specs": rel_specs,
            "decision": _first_sentence(_section(text, "Decision")),
            "context": _first_sentence(_section(text, "Context")),
        }
    return adrs


def load_specs(root: Path, adr_nums: set[str]) -> dict[str, dict]:
    specs: dict[str, dict] = {}
    for f in sorted((root / SPEC_DIR).glob("[0-9][0-9]-*.md")):
        text = f.read_text(encoding="utf-8")
        head = _header(text)
        fields = _fields(head)
        num = f.name[:2]
        title = re.sub(r"^#\s*Spec\s*\d+\s*[—-]\s*", "", head.splitlines()[0]).strip()
        status_raw = fields.get("Status", "")
        status = next(
            (s for s in SPEC_STATUSES if status_raw.startswith(s)),
            status_raw.split(" ")[0],
        )
        specs[num] = {
            "id": f"spec-{num}",
            "num": num,
            "file": f"{SPEC_DIR}/{f.name}",
            "title": title,
            "status": status,
            "adrs": _adr_numbers(fields.get("ADRs", ""), adr_nums),
            "depends_on": [
                n for n in _spec_numbers(fields.get("Depends on", "")) if n != num
            ],
        }
    return specs


def load_extra(root: Path) -> dict:
    return yaml.safe_load((root / EXTRA).read_text(encoding="utf-8"))


def read_problem(root: Path, extra: dict) -> list[dict]:
    out = []
    for p in extra["problem"]:
        for key in ("csv", "query"):
            if not (root / p[key]).exists():
                raise SystemExit(
                    f"graph_extra.yaml: problem {p['id']}: {key} {p[key]} does not exist"
                )
        with (root / p["csv"]).open(newline="", encoding="utf-8") as fh:
            rows = []
            for r in csv.DictReader(fh):
                rows.append({k: _num(v) for k, v in r.items()})
        out.append({**p, "text": p["template"].format(r=rows)})
    return out


def _num(v: str):
    try:
        return int(v)
    except ValueError:
        try:
            return float(v)
        except ValueError:
            return v


# ------------------------------------------------------------------------------------------------- graph model
def build_graph(root: Path = ROOT) -> dict:
    adrs = load_adrs(root)
    specs = load_specs(root, set(adrs))
    extra = load_extra(root)
    problems = read_problem(root, extra)

    # validate the extra file against the repository so it cannot rot
    themes = [
        {"name": th["name"], "adrs": [n for n in th["adrs"] if n in adrs]}
        for th in extra["themes"]
    ]
    themed = {n for th in themes for n in th["adrs"]}
    other = sorted(set(adrs) - themed)
    if other:
        print(
            f"note: ADRs {', '.join(other)} are not in graph_extra.yaml themes; drawn in the 'Other' group",
            file=sys.stderr,
        )
        themes.append({"name": "Other", "adrs": other})
    extra = {**extra, "themes": themes}
    for num, paths in extra["components"].items():
        if num not in specs:
            raise SystemExit(f"graph_extra.yaml: components for unknown spec {num}")
        for p in paths:
            if not (root / p).exists():
                raise SystemExit(
                    f"graph_extra.yaml: component {p} (spec {num}) does not exist"
                )
    targets = {a["id"] for a in adrs.values()} | {s["id"] for s in specs.values()}
    for e in extra["evidence"]:
        if e["kind"] != "pr" and not (root / e["path"]).exists():
            raise SystemExit(
                f"graph_extra.yaml: evidence {e['id']}: {e['path']} does not exist"
            )
        for t in e["supports"]:
            if t not in targets:
                raise SystemExit(
                    f"graph_extra.yaml: evidence {e['id']} supports unknown {t}"
                )
    for p in problems:
        for n in p["adrs"]:
            if n not in adrs:
                raise SystemExit(
                    f"graph_extra.yaml: problem {p['id']} points at unknown ADR {n}"
                )

    nodes: list[dict] = []
    edges: list[dict] = []

    for p in problems:
        nodes.append(
            {
                "id": p["id"],
                "layer": "problem",
                "label": f"{p['label']} {p['text']}",
                "evidence_label": p["label"],
                "query": p["query"],
                "csv": p["csv"],
            }
        )
        for n in p["adrs"]:
            edges.append(
                {
                    "from": p["id"],
                    "to": f"adr-{n}",
                    "kind": "motivates",
                    "source": "extra",
                }
            )

    for a in adrs.values():
        nodes.append(
            {
                "id": a["id"],
                "layer": "decision",
                "label": f"{a['num']} {a['title']}",
                "status": a["status"],
                "file": a["file"],
                "theme": next(
                    t["name"] for t in extra["themes"] if a["num"] in t["adrs"]
                ),
            }
        )
        for t in a["amended_by"]:
            edges.append(
                {
                    "from": f"adr-{t}",
                    "to": a["id"],
                    "kind": "amends",
                    "source": "adr-header",
                }
            )
        if a["supersedes"]:
            edges.append(
                {
                    "from": a["id"],
                    "to": f"adr-{a['supersedes']}",
                    "kind": "supersedes",
                    "source": "adr-header",
                }
            )
        if a["superseded_by"]:
            edges.append(
                {
                    "from": f"adr-{a['superseded_by']}",
                    "to": a["id"],
                    "kind": "supersedes",
                    "source": "adr-header",
                }
            )
        for r in a["related_adrs"]:
            edges.append(
                {
                    "from": a["id"],
                    "to": f"adr-{r}",
                    "kind": "related",
                    "source": "adr-header",
                }
            )

    for s in specs.values():
        nodes.append(
            {
                "id": s["id"],
                "layer": "spec",
                "label": f"Spec {s['num']} {s['title']}",
                "status": s["status"],
                "file": s["file"],
                "components": extra["components"].get(s["num"], []),
            }
        )
        for n in s["depends_on"]:
            if n in specs:
                edges.append(
                    {
                        "from": s["id"],
                        "to": f"spec-{n}",
                        "kind": "depends_on",
                        "source": "spec-header",
                    }
                )
    for a in adrs.values():
        implementers = {n for n in a["related_specs"] if n in specs} | {
            s["num"] for s in specs.values() if a["num"] in s["adrs"]
        }
        for n in sorted(implementers):
            in_spec, in_adr = a["num"] in specs[n]["adrs"], n in a["related_specs"]
            src = (
                "both-headers"
                if in_spec and in_adr
                else "spec-header"
                if in_spec
                else "adr-header"
            )
            edges.append(
                {
                    "from": a["id"],
                    "to": f"spec-{n}",
                    "kind": "implemented_by",
                    "source": src,
                }
            )

    for e in extra["evidence"]:
        node = {
            "id": e["id"],
            "layer": "evidence",
            "label": e["label"],
            "kind": e["kind"],
        }
        node["path" if e["kind"] != "pr" else "url"] = (
            e["path"] if e["kind"] != "pr" else f"{REPO_URL}/pull/{e['pr']}"
        )
        nodes.append(node)
        for t in e["supports"]:
            edges.append(
                {"from": t, "to": e["id"], "kind": "evidenced_by", "source": "extra"}
            )

    layer_order = {"problem": 0, "decision": 1, "spec": 2, "evidence": 3}
    nodes.sort(key=lambda n: (layer_order[n["layer"]], n["id"]))
    edges = sorted({json.dumps(e, sort_keys=True) for e in edges})
    edges = [json.loads(e) for e in edges]
    edges.sort(key=lambda e: (e["kind"], e["from"], e["to"]))

    return {
        "nodes": nodes,
        "edges": edges,
        "_adrs": adrs,
        "_specs": specs,
        "_extra": extra,
        "_problems": problems,
    }


def inconsistencies(root: Path = ROOT) -> list[str]:
    """Header mismatches: an amend or supersede stated on one side only, or a README status that disagrees."""
    adrs = load_adrs(root)
    out: list[str] = []
    for a in adrs.values():
        for t in a["amended_by"]:
            amender = adrs[t]
            if not re.search(
                rf"\b{a['num']}\b",
                amender["status_raw"] + " " + _raw_related(root, amender),
            ):
                out.append(
                    f"ADR {a['num']} is amended by {t}, but ADR {t}'s header never mentions {a['num']}"
                )
        if a["supersedes"] and adrs[a["supersedes"]]["superseded_by"] != a["num"]:
            out.append(
                f"ADR {a['num']} supersedes {a['supersedes']}, but ADR {a['supersedes']} is not marked 'Superseded by {a['num']}'"
            )
        if a["superseded_by"]:
            sup = adrs[a["superseded_by"]]
            if sup["supersedes"] != a["num"]:
                out.append(
                    f"ADR {a['num']} is superseded by {sup['num']}, but ADR {sup['num']} does not say 'supersedes {a['num']}'"
                )
        if a["status"] == "Superseded" and not a["superseded_by"]:
            out.append(
                f"ADR {a['num']} is Superseded without naming the ADR that supersedes it"
            )
    # README table: status column
    readme = (root / ADR_DIR / "README.md").read_text(encoding="utf-8")
    rows = {
        m.group(1): m.group(2)
        for m in re.finditer(
            r"^\| \[(\d{4})\]\([^)]*\) \|.*?\| (.*?) \| [\d-]+ \|$", readme, re.M
        )
    }
    for a in adrs.values():
        row = rows.get(a["num"])
        if row is None:
            out.append(
                f"ADR {a['num']} is missing from the table in docs/adr/README.md"
            )
            continue
        if a["superseded_by"] and f"Superseded by [{a['superseded_by']}]" not in row:
            out.append(
                f"README row for ADR {a['num']} does not say 'Superseded by {a['superseded_by']}'"
            )
        for t in a["amended_by"]:
            if f"[{t}]" not in row:
                out.append(
                    f"README row for ADR {a['num']} does not say 'amended by {t}'"
                )
        if not a["amended_by"] and not a["superseded_by"] and "amended" in row.lower():
            out.append(
                f"README row for ADR {a['num']} says amended, its header does not"
            )
    return out


def _raw_related(root: Path, adr: dict) -> str:
    head = _header((root / adr["file"]).read_text(encoding="utf-8"))
    return _fields(head).get("Related", "")


# --------------------------------------------------------------------------------------------------- rendering
def _q(text: str) -> str:
    """Quote a Mermaid label: double quotes become single, and nothing else needs escaping inside quotes."""
    return '"' + text.replace('"', "'").replace("\n", " ") + '"'


def _short(text: str, n: int = 44) -> str:
    text = text.replace("`", "")
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + "..."


def _mid(node_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", node_id)


def render_mermaid(g: dict) -> tuple[str, dict]:
    adrs, specs, extra = g["_adrs"], g["_specs"], g["_extra"]
    collapse = {n: c for c in extra["collapse"] for n in c["adrs"]}

    def adr_node(num_id: str) -> str:
        num = num_id.split("-")[1]
        return (
            _mid(f"collapsed-{collapse[num]['id']}")
            if num in collapse
            else _mid(num_id)
        )

    def node_ref(i: str) -> str:
        return adr_node(i) if i.startswith("adr-") else _mid(i)

    L: list[str] = []
    counts = {"problem": 0, "decision": 0, "spec": 0, "evidence": 0}

    L.append("flowchart LR")
    L.append('  subgraph LP["1. Problem [data]"]')
    for n in g["nodes"]:
        if n["layer"] == "problem":
            counts["problem"] += 1
            L.append(
                f"    {_mid(n['id'])}[{_q(n['id'] + ' ' + n['label'] + '<br/>' + n['query'])}]"
            )
    L.append("  end")

    L.append('  subgraph LD["2. Decisions (ADRs)"]')
    done_collapse: set[str] = set()
    for t in extra["themes"]:
        L.append(f"    subgraph T{_mid(t['name'])}[{_q(t['name'])}]")
        for num in t["adrs"]:
            if num in collapse:
                c = collapse[num]
                if c["id"] in done_collapse:
                    continue
                done_collapse.add(c["id"])
                counts["decision"] += 1
                L.append(f"      {_mid('collapsed-' + c['id'])}[{_q(c['label'])}]")
                continue
            counts["decision"] += 1
            a = adrs[num]
            L.append(f"      {_mid(a['id'])}[{_q(num + ' ' + _short(a['title']))}]")
        L.append("    end")
    L.append("  end")

    L.append('  subgraph LS["3. Specs and components"]')
    for s in specs.values():
        counts["spec"] += 1
        comp = " ".join(extra["components"].get(s["num"], [])[:1])
        L.append(
            f"    {_mid(s['id'])}[{_q(s['num'] + ' ' + _short(s['title'], 36) + '<br/>' + s['status'] + (' | ' + comp if comp else ''))}]"
        )
    L.append("  end")

    L.append('  subgraph LE["4. Evidence"]')
    for n in g["nodes"]:
        if n["layer"] == "evidence":
            counts["evidence"] += 1
            L.append(f"    {_mid(n['id'])}[{_q(n['label'])}]")
    L.append("  end")

    seen: set[str] = set()
    n_edges = {"problem": 0, "decision": 0, "spec": 0, "evidence": 0}
    for e in g["edges"]:
        a, b = node_ref(e["from"]), node_ref(e["to"])
        if a == b:
            continue
        k = e["kind"]
        if k in ("related", "depends_on"):
            continue  # kept in graph.json (and the specs table) only: too dense to draw
        if k == "implemented_by" and e["source"] != "both-headers":
            continue  # drawn only when the ADR's `Related` and the spec's `ADRs` agree; the rest stay in graph.json
        if k == "evidenced_by" and e["from"].startswith("spec-"):
            continue  # evidence is drawn against the decision it backs; spec evidence is in the specs table
        if k == "amends":
            line = f"  {a} -. amends .-> {b}"
        elif k == "supersedes":
            line = f"  {a} == supersedes ==> {b}"
        else:
            line = f"  {a} --> {b}"
        if line in seen:
            continue
        seen.add(line)
        L.append(line)
        layer = {
            "motivates": "problem",
            "amends": "decision",
            "supersedes": "decision",
            "implemented_by": "spec",
            "evidenced_by": "evidence",
        }[k]
        n_edges[layer] += 1

    # colors from docs/brand/BRAND.md: violet (system), teal (verification), amber (urgency/problem)
    L.append("  classDef problem fill:#FEF3C7,stroke:#D97706,color:#1F2937")
    L.append("  classDef decision fill:#EDE9FE,stroke:#7C3AED,color:#1F2937")
    L.append("  classDef spec fill:#F1F5F9,stroke:#94A3B8,color:#1F2937")
    L.append("  classDef evidence fill:#CCFBF1,stroke:#0F766E,color:#1F2937")
    for layer, cls in (
        ("problem", "problem"),
        ("decision", "decision"),
        ("spec", "spec"),
        ("evidence", "evidence"),
    ):
        ids = []
        for n in g["nodes"]:
            if n["layer"] == layer:
                ids.append(node_ref(n["id"]) if layer == "decision" else _mid(n["id"]))
        if layer == "decision":
            ids = sorted(set(ids))
        L.append(f"  class {','.join(ids)} {cls}")
    return "\n".join(L), {"nodes": counts, "edges": n_edges}


def _link(path: str, rel_to: str = OUT_DIR) -> str:
    depth = len(Path(rel_to).parts)
    return "../" * depth + path


def render_md(g: dict) -> str:
    adrs, specs, extra, problems = g["_adrs"], g["_specs"], g["_extra"], g["_problems"]
    mermaid, counts = render_mermaid(g)
    n_nodes = sum(counts["nodes"].values())
    n_edges = sum(counts["edges"].values())
    ev_by_target: dict[str, list[dict]] = {}
    nodes_by_id = {n["id"]: n for n in g["nodes"]}
    for e in g["edges"]:
        if e["kind"] == "evidenced_by":
            ev_by_target.setdefault(e["from"], []).append(nodes_by_id[e["to"]])
    prob_by_adr: dict[str, list[str]] = {}
    for e in g["edges"]:
        if e["kind"] == "motivates":
            prob_by_adr.setdefault(e["to"], []).append(e["from"])
    impl_by_adr: dict[str, list[str]] = {}
    for e in g["edges"]:
        if e["kind"] == "implemented_by":
            impl_by_adr.setdefault(e["from"], []).append(e["to"].split("-")[1])

    def ev_link(n: dict) -> str:
        if n["kind"] == "pr":
            return f"[{n['label'].split(':')[0]}]({n['url']})"
        return f"[`{Path(n['path']).name}`]({_link(n['path'])})"

    out: list[str] = []
    out.append("# Decisions graph")
    out.append("")
    out.append(
        "<!-- Generated by scripts/docs/decision_graph.py from the ADR and spec headers and docs/decisions/graph_extra.yaml. "
        "Do not edit by hand: run `python scripts/docs/decision_graph.py`. `--check` fails when this file is stale. -->"
    )
    out.append("")
    out.append(
        "One picture of the project's reasoning: the problem the data showed, the decisions that answered it, the specs and "
        "components that implement them, and the evidence behind each. Every ADR and spec is a node; every edge comes from a "
        "header (`Status`, `Amended by`, `Related`, `ADRs`, `Depends on`) or from the small mapping in "
        "[`graph_extra.yaml`](graph_extra.yaml). The same graph, with every edge, is in [`graph.json`](graph.json)."
    )
    out.append("")
    out.append(
        f"**Size:** {counts['nodes']['problem']} problem nodes, {counts['nodes']['decision']} decision nodes "
        f"({len(adrs)} ADRs, ADRs 0001 and 0002 drawn as one), {counts['nodes']['spec']} specs, "
        f"{counts['nodes']['evidence']} evidence nodes: {n_nodes} nodes and {n_edges} edges drawn."
    )
    out.append("")
    out.append("```mermaid")
    out.append(mermaid)
    out.append("```")
    out.append("")
    out.append("## Legend")
    out.append("")
    out.append("| Shape or line | Meaning |")
    out.append("|---|---|")
    out.append(
        "| Amber box | A finding from the data. Every figure carries its label and the query that produced it (`[data]`, constitution rule 8). |"
    )
    out.append(
        "| Violet box | An ADR (decision). Boxes are grouped by theme only for layout. |"
    )
    out.append("| Grey box | A spec, with its status and its main component. |")
    out.append(
        "| Teal box | Evidence: a test, a committed result file, a metric file or a merged PR. |"
    )
    out.append(
        "| `-->` | A problem motivates a decision; a decision is implemented by a spec (drawn when the ADR's `Related` and the spec's `ADRs` agree); a decision is backed by evidence. |"
    )
    out.append(
        "| `-. amends .->` | The ADR amends an earlier ADR (from the target's `Amended by` header). |"
    )
    out.append(
        "| `== supersedes ==>` | The ADR replaces an earlier one (from `Status`). |"
    )
    out.append("")
    out.append(
        "Not drawn, to keep the picture readable, but present in `graph.json`: `Related` links between ADRs "
        "(`kind: related`), spec dependencies (`kind: depends_on`, also in the specs table) and ADR-side `Related` "
        "links to specs that the spec's own `ADRs` header does not repeat, or the reverse (`kind: implemented_by`, `source: adr-header` or "
        "`spec-header`; the drawn edges are `both-headers`), and evidence for specs."
    )
    out.append("")
    out.append("## The problem, with its numbers")
    out.append("")
    out.append("| Id | Finding | Label | Query | Decisions it drove |")
    out.append("|---|---|---|---|---|")
    for p in problems:
        drove = ", ".join(
            f"[{n}](../adr/{adrs[n]['file'].split('/')[-1]})" for n in p["adrs"]
        )
        out.append(
            f"| {p['id']} | {p['text']} | `{p['label']}` | [`{Path(p['query']).name}`]({_link(p['query'])}) "
            f"(output [`{Path(p['csv']).name}`]({_link(p['csv'])})) | {drove} |"
        )
    out.append("")
    out.append(
        "The dataset is synthetic; these figures describe the problem, not our system (see "
        "[`problem_in_numbers.md`](../problem_in_numbers.md))."
    )
    out.append("")
    out.append("## Decision, why, evidence")
    out.append("")
    out.append("| ADR | Decision | Why | Specs | Evidence |")
    out.append("|---|---|---|---|---|")
    for a in adrs.values():
        status = a["status"]
        if a["superseded_by"]:
            status += f" by {a['superseded_by']}"
        notes = []
        if a["amended_by"]:
            notes.append("amended by " + ", ".join(a["amended_by"]))
        if a["supersedes"]:
            notes.append(f"supersedes {a['supersedes']}")
        tag = f" ({'; '.join(notes)})" if notes else ""
        probs = prob_by_adr.get(a["id"], [])
        why = (" ".join(f"**{p}**" for p in probs) + ": " if probs else "") + a[
            "context"
        ]
        specs_cell = (
            ", ".join(
                f"[{n}](../../{specs[n]['file']})"
                for n in sorted(set(impl_by_adr.get(a["id"], [])))
            )
            or "-"
        )
        ev_cell = ", ".join(ev_link(n) for n in ev_by_target.get(a["id"], [])) or "-"
        title = f"[{a['num']} {a['title']}](../adr/{a['file'].split('/')[-1]}) · {status}{tag}"
        out.append(
            f"| {_cell(title)} | {_cell(a['decision'])} | {_cell(why)} | {specs_cell} | {ev_cell} |"
        )
    out.append("")
    out.append("## Specs and components")
    out.append("")
    out.append("| Spec | Status | Components | Depends on | Evidence |")
    out.append("|---|---|---|---|---|")
    for s in specs.values():
        comps = (
            ", ".join(
                f"[`{c}`]({_link(c)})" for c in extra["components"].get(s["num"], [])
            )
            or "-"
        )
        deps = ", ".join(s["depends_on"]) or "-"
        ev_cell = ", ".join(ev_link(n) for n in ev_by_target.get(s["id"], [])) or "-"
        out.append(
            f"| [{s['num']} {_cell(s['title'])}](../../{s['file']}) | {s['status']} | {comps} | {deps} | {ev_cell} |"
        )
    out.append("")
    out.append("## How this file stays true")
    out.append("")
    out.append(
        "`python scripts/docs/decision_graph.py --check` regenerates the graph in memory and fails when `graph.md` or "
        "`graph.json` differ from it; `tests/test_docs_decision_graph.py` runs the same check in CI. Add an ADR or change a "
        "header, run the script without `--check`, commit the result. A path named in `graph_extra.yaml` that no longer "
        "exists fails the run."
    )
    out.append("")
    return "\n".join(out)


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def render_json(g: dict) -> str:
    return (
        json.dumps(
            {"nodes": g["nodes"], "edges": g["edges"]}, indent=2, ensure_ascii=False
        )
        + "\n"
    )


def generate(root: Path = ROOT) -> tuple[str, str]:
    g = build_graph(root)
    return render_md(g), render_json(g)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--check",
        action="store_true",
        help="exit 1 when graph.md or graph.json is stale",
    )
    ap.add_argument(
        "--root", default=str(ROOT), help="repository root (tests use a fixture)"
    )
    args = ap.parse_args(argv)
    root = Path(args.root)
    md, js = generate(root)
    bad = inconsistencies(root)
    for msg in bad:
        print(f"header inconsistency: {msg}", file=sys.stderr)
    md_path, js_path = root / OUT_DIR / "graph.md", root / OUT_DIR / "graph.json"
    if args.check:
        stale = [
            p.name
            for p, want in ((md_path, md), (js_path, js))
            if not p.exists() or p.read_text(encoding="utf-8") != want
        ]
        if stale:
            print(
                f"{', '.join(stale)} stale: run `python scripts/docs/decision_graph.py` and commit the result",
                file=sys.stderr,
            )
            return 1
        print("decisions graph is up to date")
        return 1 if bad else 0
    md_path.write_text(md, encoding="utf-8")
    js_path.write_text(js, encoding="utf-8")
    print(f"wrote {md_path.relative_to(root)} and {js_path.relative_to(root)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
