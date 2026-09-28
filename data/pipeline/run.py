"""Orquestación: fuente → bronze → silver → gold → checks, y resultados en gold/run_results.json."""
from __future__ import annotations

import json
import logging
import shutil
import time
from datetime import datetime, timezone

import duckdb

from data.pipeline import bronze, checks, contracts, gold, silver, sources
from data.pipeline.config import (DATA_DIR, FIXTURE_DIR, FIXTURE_WORKDIR, PIPELINE_VERSION, TABLES, TX_WINDOW,
                                  Layout, load_env)

log = logging.getLogger("pipeline.run")


def file_changes(previous: list[dict], current: list[dict]) -> dict:
    """Archivos nuevos, cambiados (md5 distinto) y retirados respecto de la corrida anterior."""
    old = {f["key"]: f for f in previous}
    new = {f["key"]: f for f in current}
    pick = ("table", "key", "n_rows", "delivery", "schema_drift", "header_added", "header_missing", "header_renamed")
    return {
        "new": [{k: new[x][k] for k in pick} for x in sorted(set(new) - set(old))],
        "changed": [{**{k: new[x][k] for k in pick}, "n_rows_before": old[x].get("n_rows")}
                    for x in sorted(set(new) & set(old)) if new[x]["md5"] != old[x]["md5"]],
        "removed": [{k: old[x].get(k) for k in pick} for x in sorted(set(old) - set(new))],
        "unchanged": sum(new[x]["md5"] == old[x]["md5"] for x in set(new) & set(old)),
    }


def run(source: str, layout: Layout, tables: tuple[str, ...] = TABLES, delivery: int | None = None,
        with_eda: bool = True) -> dict:
    t0 = time.time()
    layout.mkdirs()
    previous = json.loads(layout.results.read_text()) if layout.results.exists() else None

    if source == "s3":
        files, skipped = sources.list_s3(tables, mirror=DATA_DIR)
        env = load_env()
        location = f"s3://{env['S3_BUCKET']}/{env['S3_PREFIX'] or 'data/'}"
    elif source == "local":
        (files, skipped), location = sources.list_local(DATA_DIR, tables), str(DATA_DIR.relative_to(DATA_DIR.parent))
    elif source == "fixture":
        files, skipped = sources.list_fixture(FIXTURE_DIR, tables, upto=delivery or 1)
        location = f"{FIXTURE_DIR.relative_to(DATA_DIR.parent)} (hasta delivery_{delivery or 1})"
    else:
        raise ValueError(f"fuente desconocida: {source}")

    con = duckdb.connect()
    con.execute("SET threads TO 8")
    bronze_stats, registry = bronze.build(con, files, layout, tables)
    silver_stats = {t: silver.build_table(con, t, layout) for t in tables}
    loaded = sorted(f.loaded_at for f in files)
    source_meta = {"mode": source, "location": location, "fixture": source == "fixture", "files": len(files),
                   "bytes": sum(f.size for f in files), "loaded_at_min": loaded[0], "loaded_at_max": loaded[-1],
                   "transactions_window": list(TX_WINDOW), "files_out_of_scope": skipped}
    gold_res = gold.build(con, layout, tables, source_meta)
    check_rows = checks.run(con, layout, tables, silver_stats, registry, with_eda=with_eda)

    results = {
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seconds": round(time.time() - t0, 1),
        "pipeline_version": PIPELINE_VERSION, "contract_version": contracts.CONTRACT_VERSION,
        "source": source_meta, "tables": list(tables),
        "bronze": bronze_stats, "silver": silver_stats, "checks": check_rows,
        "gold": {"manifest": gold_res["manifest"], "diff": gold_res["diff"], "contract_rules": gold_res["contract_rules"]},
        "files": [{k: v for k, v in r.items() if k not in ("header", "local_path")} for r in registry],
        "file_changes": file_changes(previous["files"], registry) if previous else None,
        "previous_run_at": previous["run_at"] if previous else None,
    }
    layout.results.write_text(json.dumps(results, indent=1, ensure_ascii=False, default=str) + "\n")
    log.info("corrida %s terminada en %.1fs → %s", source, results["seconds"], layout.results)
    return results


def run_fixture(workdir=FIXTURE_WORKDIR) -> dict:
    """Corre el fixture desde cero: delivery_1 y luego delivery_1 + delivery_2 sobre el mismo directorio."""
    if workdir.name != "_fixture_run":   # se borra entero: solo se acepta un directorio con este nombre
        raise RuntimeError(f"directorio de trabajo inesperado: {workdir}")
    shutil.rmtree(workdir, ignore_errors=True)
    spec = json.loads((FIXTURE_DIR / "fixture.json").read_text())
    layout = Layout(workdir)
    runs = [run("fixture", layout, delivery=i, with_eda=False) for i in range(1, len(spec["deliveries"]) + 1)]
    out = {"spec": spec, "runs": runs}
    (workdir / "fixture_results.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False, default=str) + "\n")
    return out


def expected_vs_actual(result: dict, expected: dict) -> list[dict]:
    """Compara una corrida del fixture con fixture.json → expected[delivery]. Una fila por conteo esperado."""
    out = []

    def add(item: str, exp, act) -> None:
        out.append({"item": item, "expected": exp, "actual": act, "ok": exp == act})

    for t, n in expected.get("rows_bronze", {}).items():
        add(f"filas bronze {t}", n, result["bronze"][t]["rows"])
    for t, n in expected.get("rows_silver", {}).items():
        add(f"filas silver {t}", n, result["silver"][t]["rows_silver"])
    for t, n in expected.get("rows_gold", {}).items():
        add(f"filas gold {t}", n, result["gold"]["manifest"]["tables"][t]["rows"])
    for rule in result["gold"]["contract_rules"]:
        add(f"contrato {rule['id']}", True, rule["ok"])
    got = {f"{c['id']}/{c['table']}": c["n"] for c in result["checks"]}
    for k, n in expected.get("checks", {}).items():
        add(f"check {k}", n, got.get(k))
    for t, d in expected.get("gold_diff", {}).items():
        for k, n in d.items():
            add(f"gold {t} {k}", n, result["gold"]["diff"][t][k])
    for k, n in expected.get("files", {}).items():
        add(f"archivos {k}", n, len((result["file_changes"] or {}).get(k, [])))
    files = {f["key"]: f for f in result["files"]}
    for key, sc in expected.get("schema_changes", {}).items():
        f = files.get(key, {})
        add(f"schema {key}", sc, {"added": f.get("header_added"), "missing": f.get("header_missing"),
                                  "renamed": f.get("header_renamed")})
    return out
