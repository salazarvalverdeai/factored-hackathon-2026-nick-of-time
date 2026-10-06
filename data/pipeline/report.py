"""Generates data/quality_report.md from the run results (never by hand).

Inputs: data/gold/run_results.json (real run) and data/_fixture_run/fixture_results.json (fixture). If either is
missing, the corresponding section says so and explains how to produce it.
"""
from __future__ import annotations

import csv
import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from data.pipeline.config import DATA_DIR, FIXTURE_WORKDIR, REPORT_PATH, ROOT, Layout
from data.pipeline.run import expected_vs_actual

log = logging.getLogger("pipeline.report")
WEB_JSON = ROOT / "apps" / "web" / "public" / "data" / "data_quality.json"   # read by /data (spec 12 §7.2)
LINK_QUERY = "queries/data/d01_complaint_transaction_link.sql"               # dataset limitations on /data
PROFILE_QUERIES = {                                                          # the data profile of /data (spec 12 §7.2)
    "d02": "queries/data/d02_transactions_per_month.sql",
    "d03": "queries/data/d03_customers_transactions_by_country_segment.sql",
    "d04": "queries/data/d04_fraud_score_distribution.sql",
    "d05": "queries/data/d05_complaints_per_month.sql",
    "d06": "queries/data/d06_data_quality_per_table.sql"}


def n(x) -> str:
    return "—" if x is None else f"{x:,}" if isinstance(x, int) else str(x)


def pct(x) -> str:
    return "—" if x is None else f"{x:.3f}".rstrip("0").rstrip(".") + "%"


def table(header: list[str], rows: list[list], align: str | None = None) -> list[str]:
    align = align or "|".join("---" for _ in header)
    return ["| " + " | ".join(header) + " |", "|" + align + "|"] + \
           ["| " + " | ".join(str(c) for c in r) + " |" for r in rows] + [""]


def eda_cell(c: dict) -> str:
    e = c["eda"]
    if not e:
        return "—"
    mark = "same" if (e["n"], e["denominator"]) == (c["n"], c["denominator"]) else "**different**"
    return f"{n(e['n'])} / {n(e['denominator'])} ({mark}; `{e['source']}`)"


def section_summary(r: dict) -> list[str]:
    m = r["gold"]["manifest"]
    rows = []
    for t in r["tables"]:
        b, s, g = r["bronze"][t], r["silver"][t], m["tables"][t]
        rows.append([f"`{t}`", n(b["files"]), n(b["rows"]), n(s["exact_duplicates"]), n(s["superseded_versions"]),
                     n(s["quarantined"]), n(s["rows_silver"]), n(g["rows"]), f"`{g['sha256'][:12]}`"])
    src = r["source"]
    w = src["transactions_window"]
    return ["## 1. Summary by table", "",
            *table(["Table", "Files", "Bronze rows", "Exact duplicates", "PK versions", "Quarantine",
                    "Silver rows", "Gold rows", "Gold sha256"], rows, "---|---:|---:|---:|---:|---:|---:|---:|---"),
            f"`transactions` in gold covers the window [{w[0]}, {w[1]}) (contract R1). Bronze reads its partitions "
            f"from one day before the start onward; {n(src['files_out_of_scope'])} files outside that scope are not "
            "downloaded or read. Silver has everything that was read; check WIN-01 counts what does not go to gold.", "", ""
            "Bronze is the faithful copy of the CSV (all text + lineage). Silver applies the contract: types, declared "
            "renames, label normalization, dedup/upsert by PK and pandera validation. Gold adds per-row `qc_*` flags "
            "and deletes nothing. A row with quality problems is flagged, and the serving layer decides what to do "
            "with it.", ""]


def section_contract(r: dict) -> list[str]:
    m = r["gold"]["manifest"]
    rules = [[x["id"], x["rule"], x["value"], "pass" if x["ok"] else "**fail**"] for x in r["gold"]["contract_rules"]]
    tabs = [[f"`{t}`", f"`{meta['path']}`", n(meta["rows"]), n(len(meta["columns"])), f"`{meta['sha256'][:12]}`"]
            for t, meta in m["tables"].items()]
    return ["## 2. Gold contract", "",
            f"Contract: `{m['contract']['file']}` ({m['contract']['version']}). The solution reads only `data/gold/`; "
            "`is_fraud` lives in `data/gold_eval/` and the evaluation joins it by `transaction_id`. The rules are "
            "verified before publishing: if one fails, gold is not replaced.", "",
            *table(["Rule", "Condition", "Value", "Status"], rules),
            *table(["Table", "Path (under data/)", "Rows", "Columns", "sha256"], tabs, "---|---|---:|---:|---")]


def section_checks(r: dict) -> list[str]:
    rows = [[c["id"], f"`{c['table']}`", c["check"], c["description"], n(c["n"]), n(c["denominator"]), pct(c["pct"]),
             c["action"], eda_cell(c)] for c in r["checks"]]
    with_eda = [c for c in r["checks"] if c["eda"]]
    same = sum((c["eda"]["n"], c["eda"]["denominator"]) == (c["n"], c["denominator"]) for c in with_eda)
    eda_note = (f"**{same} of {len(with_eda)} checks with an EDA reference give exactly the same figure** "
                "(numerator and denominator)." if with_eda else
                "No comparison with the EDA in this repo: `outputs/tables/` stayed in the EDA repo, where the same "
                "pipeline over the full dataset reproduces the figures in `data_quality.md`. Here `transactions` "
                "covers only the 12-month window, so its counts are not comparable with the EDA.")
    return ["## 3. Checks with counts", "",
            "Violations = rows (or files, in SCH-01) that fail the check; denominator = rows where the check "
            "applies. The last column is the EDA figure for the same check (`outputs/tables/01_*.csv`, "
            "documented in `docs/eda/data_quality.md` §B–C).", "",
            *table(["ID", "Table", "Check", "Description", "Violations", "Denominator", "%", "Action",
                    "EDA (violations / denominator)"], rows, "---|---|---|---|---:|---:|---:|---|---"),
            eda_note, ""]


def section_contracts(r: dict) -> list[str]:
    from data.pipeline import contracts
    rows, details = [], []
    for t in r["tables"]:
        s = r["silver"][t]
        failing = sum(f["rows"] for f in s["contract_failures"])
        rows.append([f"`{t}`", n(len(contracts.columns(t))), n(len(contracts.required_columns(t))),
                     n(s["contract_checks"]), n(s["rows_after_dedup"]), n(s["quarantined"]),
                     ", ".join(f"`{f['column']}`: {f['check']} ({n(f['rows'])})" for f in s["contract_failures"])
                     or "none", ", ".join(f"`{c}`" for c in s["extra_columns"]) or "—",
                     ", ".join(f"`{k}` ({n(v)})" for k, v in s["renamed"].items()) or "—"])
        if failing:
            details.append(f"- `{t}`: {n(s['quarantined'])} rows in `silver/_quarantine/{t}.parquet` with the reason "
                           "in `_quarantine_reason`.")
    return ["## 4. Silver schema contracts (pandera)", "",
            "Contracts in `data/pipeline/contracts.py` (version " + r["contract_version"] + "): columns, types, "
            "required columns, unique PK and domains (enums and ranges observed in the EDA). A file column that is "
            "not in the contract is kept in bronze and does not go to silver. A rename is accepted only if it is "
            "declared as an alias.", "",
            *table(["Table", "Columns", "Required", "Rules", "Validated rows", "Quarantined",
                    "Failures (column: check, rows)", "Columns outside the contract", "Aliases used (rows)"], rows,
                   "---|---:|---:|---:|---:|---:|---|---|---"),
            *details, ""]


def section_lag(r: dict) -> list[str]:
    rows = []
    for t in r["tables"]:
        late = r["silver"][t]["late"]
        if not late:
            continue
        hist = ", ".join(f"{k} d: {n(v)}" for k, v in late["lag_hist"].items())
        rows.append([f"`{t}`", n(late["denominator"]), n(late["n_late"]), n(late["max_lag_days"]), hist,
                     n(late["partition_mismatch"])])
    return ["## 5. Late arrivals and lag", "",
            "Lag = `process_date − event date` in days. Positive = late arrival (flag `qc_late_arrival`). "
            "A lag of −1 is not an error: the file's operating day cuts off at 06:00 or 08:00 "
            "(`data_quality.md` §B4).", "",
            *table(["Table", "Rows", "Late (> 0 d)", "Max lag", "Lag distribution",
                    "Partition ≠ process_date"], rows, "---|---:|---:|---:|---|---:")]


def section_changes(r: dict) -> list[str]:
    m = r["gold"]["manifest"]
    out = ["## 6. What changed since the previous run", ""]
    fc = r["file_changes"]
    if fc is None:
        return out + ["First run in this directory: there is no previous version to compare with.", ""]
    out += [f"Previous run: {r['previous_run_at']}. Files: {n(len(fc['new']))} new, "
            f"{n(len(fc['changed']))} changed (different md5), {n(len(fc['removed']))} removed, "
            f"{n(fc['unchanged'])} unchanged.", ""]
    listed = [f"- {kind}: `{f['key']}` ({n(f.get('n_rows'))} rows)"
              for kind in ("new", "changed", "removed") for f in fc[kind][:20]]
    out += [*listed, ""] if listed else []
    rows = [[f"`{t}`", n(d["inserted"]), n(d["updated"]), n(d["deleted"]), n(d["unchanged"])]
            for t, d in r["gold"]["diff"].items()]
    prev = m["previous"]["version"] if m["previous"] else "—"
    out += [*table(["Gold table", "Inserted", "Updated", "Deleted", "Unchanged"], rows,
                       "---|---:|---:|---:|---:"),
            f"Gold version: v{prev} → v{m['version']} "
            f"({'no content changes: same sha256 in all tables' if not m['changed_tables'] else 'changed: ' + ', '.join(m['changed_tables'])}).",
            ""]
    return out


def section_fixture(fx: dict | None) -> list[str]:
    out = ["## 7. `late_arrival` fixture: late arrivals, schema change and gold contract", ""]
    if fx is None:
        return out + ["No results: run `python -m data.pipeline fixture`.", ""]
    spec, runs = fx["spec"], fx["runs"]
    out += ["> **FIXTURE, synthetic test data (not from the dataset).** The real dataset has no late arrivals "
            "or schema evolution (`data_quality.md` §B4, §B6), so freshness is demonstrated with two labeled "
            "deliveries in `data/fixtures/late_arrival/` (IDs `FX-`). The pipeline processes them with the "
            "same code as the real run, in `data/_fixture_run/`.", ""]
    for d, r in zip(spec["deliveries"], runs):
        m = r["gold"]["manifest"]
        ok = sum(x["ok"] for x in r["gold"]["contract_rules"])
        out.append(f"- **{d['name']}** (delivered {d['delivered_at']}, gold v{m['version']}, contract "
                   f"{ok}/{len(r['gold']['contract_rules'])} rules): {d['purpose']}")
    last = runs[-1]
    fc = last["file_changes"]
    out += ["", f"### What changed from {spec['deliveries'][0]['name']} to {spec['deliveries'][-1]['name']}", "",
            "**Files**", ""]
    rows = [["new", f"`{f['key']}`", "—", n(f["n_rows"])] for f in fc["new"]] + \
           [["re-delivered (different md5)", f"`{f['key']}`", n(f["n_rows_before"]), n(f["n_rows"])]
            for f in fc["changed"]]
    out += table(["Change", "File", "Rows before", "Rows now"], rows, "---|---|---:|---:")
    drift = [f for f in last["files"] if f["schema_drift"]]
    out += ["**Schema change** (file header vs contract)", ""]
    rows = [[f"`{f['key']}`", ", ".join(f"`{c}`" for c in f["header_added"]) or "—",
             ", ".join(f"`{c}`" for c in f["header_missing"]) or "—",
             ", ".join(f"`{a}` → `{c}`" for a, c in f["header_renamed"].items()) or "—"] for f in drift]
    out += table(["File", "New columns", "Missing columns", "Renamed"], rows)
    s = last["silver"]["transactions"]
    out += [f"Handling: the declared alias feeds the canonical column "
            f"({', '.join(f'`{k}`: {n(v)} rows' for k, v in s['renamed'].items()) or 'no alias'}); the new "
            f"column stays only in bronze ({', '.join(f'`{c}`' for c in s['extra_columns']) or '—'}) until the "
            "contract version goes up. No row is lost because of the change.", ""]
    late = s["late"]
    out += ["**Late arrivals**", "",
            f"{n(late['n_late'])} transactions with positive lag (max {n(late['max_lag_days'])} days). "
            f"Distribution: {', '.join(f'{k} d: {n(v)}' for k, v in late['lag_hist'].items())}. They stay in gold with "
            "`qc_late_arrival = true`, and the correction of an already loaded transaction comes in as an upsert "
            "(DUP-02: the latest `process_date` wins).", "",
            "**Checks that changed**", ""]
    first = {(c["id"], c["table"]): c["n"] for c in runs[0]["checks"]}
    rows = [[c["id"], f"`{c['table']}`", c["check"], n(first.get((c["id"], c["table"]))), n(c["n"])]
            for c in last["checks"] if first.get((c["id"], c["table"])) != c["n"]]
    out += table(["ID", "Table", "Check", spec["deliveries"][0]["name"], spec["deliveries"][-1]["name"]], rows,
                 "---|---|---|---:|---:")
    rows = [[f"`{t}`", n(d["inserted"]), n(d["updated"]), n(d["deleted"]), n(d["unchanged"])]
            for t, d in last["gold"]["diff"].items()]
    m0, m1 = runs[0]["gold"]["manifest"], last["gold"]["manifest"]
    out += ["**Gold**", "", *table(["Table", "Inserted", "Updated", "Deleted", "Unchanged"], rows,
                                   "---|---:|---:|---:|---:"),
            f"Version v{m0['version']} → v{m1['version']}; changed: {', '.join(m1['changed_tables']) or 'none'}.",
            ""]
    checks_all = [x for d, r in zip(spec["deliveries"], runs) for x in expected_vs_actual(r, spec["expected"][d["name"]])]
    bad = [x for x in checks_all if not x["ok"]]
    out += [f"**Against expected** (`fixture.json` → `expected`): {n(len(checks_all) - len(bad))} of "
            f"{n(len(checks_all))} counts match."]
    out += [f"- MISMATCH: {x['item']}: expected {x['expected']}, got {x['actual']}" for x in bad]
    return out + [""]


def section_nulls(r: dict) -> list[str]:
    out = ["## 8. Nulls by column (silver)", "",
           "Only columns with nulls. Required columns in bold (must be 0). Expected, random nulls per "
           "`data_quality.md` §B2.", ""]
    from data.pipeline import contracts
    for t in r["tables"]:
        nulls = r["silver"][t]["nulls"]
        rows_ = r["silver"][t]["rows_silver"]
        req = set(contracts.required_columns(t))
        items = [f"{'**' if c in req else ''}`{c}`{'**' if c in req else ''} {pct(round(100 * v / rows_, 3))}"
                 for c, v in nulls.items() if v]
        out.append(f"- `{t}` ({n(rows_)} rows): " + (", ".join(items) or "no nulls"))
    return out + [""]


def write_report() -> None:
    real = Layout(DATA_DIR).results
    fx_path = FIXTURE_WORKDIR / "fixture_results.json"
    r = json.loads(real.read_text()) if real.exists() else None
    fx = json.loads(fx_path.read_text()) if fx_path.exists() else None
    lines = ["# Quality report — LATAM Bank pipeline", ""]
    if r is None:
        lines += ["No real run: run `make setup` or `python -m data.pipeline run --source s3`.", ""]
    else:
        m, src = r["gold"]["manifest"], r["source"]
        lines += [f"> Generated by `python -m data.pipeline report` from `data/gold/run_results.json` and "
                  "`data/_fixture_run/fixture_results.json`. **Do not edit by hand**: `make setup` regenerates it.",
                  f"> Run: {r['run_at']} ({r['seconds']} s). Pipeline {r['pipeline_version']}, contract "
                  f"{r['contract_version']}, **gold v{m['version']}** (content since {m['version_created_at']}; "
                  "`data/gold/manifest.json`).",
                  f"> Source: `{src['location']}` ({src['mode']}), {n(src['files'])} files, "
                  f"{src['bytes'] / 1e6:,.1f} MB, loaded between {src['loaded_at_min']} and {src['loaded_at_max']}.",
                  "> Scope: the 4 tables of the W3 idea and the derived tables from `contracts/gold_contract.md`.", ""]
        lines += (section_summary(r) + section_contract(r) + section_checks(r) + section_contracts(r) + section_lag(r)
                  + section_changes(r))
    lines += section_fixture(fx)
    if r is not None:
        lines += section_nulls(r)
    lines += ["## How to reproduce", "", "```bash",
              "make setup     # venv + dependencies + pipeline from S3 (.env) + fixture + this report",
              "make pipeline  # only the real run (SOURCE=local to use a local mirror in data/, no network)",
              "make fixture   # only the late_arrival fixture", "make report    # only this file",
              "make test      # pytest, no network", "```", ""]
    REPORT_PATH.write_text("\n".join(lines))
    log.info("report: %s", REPORT_PATH)


def late_arrival(fx: dict) -> dict:
    """What changed between the first and the last delivery of the late_arrival fixture (spec 12 §7.2)."""
    spec, first, last = fx["spec"], fx["runs"][0], fx["runs"][-1]
    silver, before = last["silver"]["transactions"], {(c["id"], c["table"]): c["n"] for c in first["checks"]}
    compared = [x for d, r in zip(spec["deliveries"], fx["runs"]) for x in expected_vs_actual(r, spec["expected"][d["name"]])]
    return {
        "label": "fixture: synthetic test data, not from the dataset",
        "deliveries": [{"name": d["name"], "delivered_at": d["delivered_at"], "gold_version": r["gold"]["manifest"]["version"]}
                       for d, r in zip(spec["deliveries"], fx["runs"])],
        "rows_added": {t: d["inserted"] for t, d in last["gold"]["diff"].items() if d["inserted"]},
        "rows_updated": {t: d["updated"] for t, d in last["gold"]["diff"].items() if d["updated"]},
        "columns_added": silver["extra_columns"], "columns_renamed": list(silver["renamed"]),
        "late_rows": silver["late"]["n_late"], "max_lag_days": silver["late"]["max_lag_days"],
        "checks_changed": [{"id": c["id"], "table": c["table"], "check": c["check"],
                            "before": before.get((c["id"], c["table"])), "after": c["n"]}
                           for c in last["checks"] if before.get((c["id"], c["table"])) != c["n"]],
        "expected_counts": {"matched": sum(1 for x in compared if x["ok"]), "total": len(compared)}}


def complaint_link(csv_path: Path = ROOT / LINK_QUERY.replace(".sql", ".csv")) -> dict | None:
    """The committed output of the complaint-to-transaction query (queries/data/run.py), or None if it is missing."""
    if not csv_path.exists():
        return None
    rows = list(csv.DictReader(csv_path.read_text(encoding="utf-8").splitlines()))
    return {"query": LINK_QUERY, "rows": [{"metric": x["metric"], "numerator": int(x["numerator"]),
                                           "denominator": int(x["denominator"])} for x in rows]}


def _typed(value: str) -> int | float | str:
    """A CSV cell as the number it is (int, then float) or the text it is."""
    for kind in (int, float):
        try:
            return kind(value)
        except ValueError:
            pass
    return value


def profile(root: Path = ROOT) -> dict | None:
    """The committed outputs of queries/data d02..d06 (run.py) as `{dNN: {query, label, rows}}`; None if any is missing."""
    out = {}
    for key, query in PROFILE_QUERIES.items():
        csv_path = root / query.replace(".sql", ".csv")
        if not csv_path.exists():
            return None
        rows = csv.DictReader(csv_path.read_text(encoding="utf-8").splitlines())
        out[key] = {"query": query, "label": "[data]", "rows": [{k: _typed(v) for k, v in row.items()} for row in rows]}
    return out


def data_quality(r: dict, fx: dict | None, link: dict | None = None, prof: dict | None = None) -> dict:
    """The `data` of data_quality.json (spec 12 §7.2), from the same results as the Markdown report."""
    m = r["gold"]["manifest"]
    layers = [
        {"layer": "bronze", "note": "faithful copy of the CSV files, all text, with lineage",
         "tables": [{"table": t, "rows": r["bronze"][t]["rows"], "bytes": r["bronze"][t]["bytes"],
                     "files": r["bronze"][t]["files"]} for t in r["tables"]]},
        {"layer": "silver", "note": "typed, deduplicated and validated against the contract",
         "tables": [{"table": t, "rows": r["silver"][t]["rows_silver"], "bytes": None,
                     "quarantined": r["silver"][t]["quarantined"]} for t in r["tables"]]},
        {"layer": "gold", "note": "what the solution reads; quality flags per row, nothing deleted",
         "tables": [{"table": t, "rows": v["rows"], "bytes": v["bytes"], "sha256": v["sha256"][:12]}
                    for t, v in m["tables"].items()]}]
    return {
        "label": "[data]", "layers": layers,
        "gold_rules": [{"id": x["id"], "rule": x["rule"], "value": x["value"], "ok": x["ok"]} for x in m["contract"]["rules"]],
        "checks": [{"id": c["id"], "table": c["table"], "check": c["check"], "rows_affected": c["n"],
                    "denominator": c["denominator"], "action": c["action"]} for c in r["checks"]],
        "manifest": {"gold_version": m["version"], "version_created_at": m["version_created_at"],
                     "pipeline_version": r["pipeline_version"], "contract_version": r["contract_version"],
                     "run_at": r["run_at"], "transactions_window": m["contract"]["transactions_window"],
                     "source_files": r["source"]["files"], "source_bytes": r["source"]["bytes"]},
        "late_arrival": late_arrival(fx) if fx else None, "complaint_link": link, "profile": prof}


def write_json(path: Path = WEB_JSON, data_dir: Path = DATA_DIR) -> None:
    """`python -m data.pipeline report --json [--data-dir D]`: writes `{generated_at, git_sha, source, data}` (spec 01
    §6.2). `data_dir` (read only) holds the run results and `_fixture_run/`; it defaults to this repo's data/."""
    real, fx_path = Layout(data_dir).results, data_dir / FIXTURE_WORKDIR.name / "fixture_results.json"
    if not real.exists():
        raise SystemExit("no real run: run `make setup` or `python -m data.pipeline run` first")
    fx = json.loads(fx_path.read_text(encoding="utf-8")) if fx_path.exists() else None
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                             check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        sha = "unknown"
    payload = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "git_sha": sha,
               "source": "data/pipeline report [data] — data/gold/run_results.json and the late_arrival fixture",
               "data": data_quality(json.loads(real.read_text(encoding="utf-8")), fx, complaint_link(), profile())}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    log.info("report: %s", path)
