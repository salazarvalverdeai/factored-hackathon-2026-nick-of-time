"""Genera data/quality_report.md desde los resultados de las corridas (nunca a mano).

Entradas: data/gold/run_results.json (corrida real) y data/_fixture_run/fixture_results.json (fixture). Si falta
alguna, la sección correspondiente lo dice y explica cómo producirla.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from data.pipeline.config import DATA_DIR, FIXTURE_WORKDIR, REPORT_PATH, Layout
from data.pipeline.run import expected_vs_actual

log = logging.getLogger("pipeline.report")


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
    mark = "igual" if (e["n"], e["denominator"]) == (c["n"], c["denominator"]) else "**distinto**"
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
    return ["## 1. Resumen por tabla", "",
            *table(["Tabla", "Archivos", "Filas bronze", "Duplicados exactos", "Versiones de PK", "Cuarentena",
                    "Filas silver", "Filas gold", "sha256 gold"], rows, "---|---:|---:|---:|---:|---:|---:|---:|---"),
            f"`transactions` en gold cubre la ventana [{w[0]}, {w[1]}) (contrato R1). Bronze lee sus particiones desde "
            f"un día antes del inicio en adelante; {n(src['files_out_of_scope'])} archivos fuera de ese alcance no se "
            "descargan ni se leen. Silver tiene todo lo leído; el check WIN-01 cuenta lo que no pasa a gold.", "", ""
            "Bronze es la copia fiel del CSV (todo texto + linaje). Silver aplica el contrato: tipos, renombres "
            "declarados, normalización de etiquetas, dedup/upsert por PK y validación pandera. Gold agrega flags "
            "`qc_*` por fila y no borra nada. Una fila con problemas de calidad se marca, y la capa de servicio decide "
            "qué hacer con ella.", ""]


def section_contract(r: dict) -> list[str]:
    m = r["gold"]["manifest"]
    rules = [[x["id"], x["rule"], x["value"], "cumple" if x["ok"] else "**no cumple**"] for x in r["gold"]["contract_rules"]]
    tabs = [[f"`{t}`", f"`{meta['path']}`", n(meta["rows"]), n(len(meta["columns"])), f"`{meta['sha256'][:12]}`"]
            for t, meta in m["tables"].items()]
    return ["## 2. Contrato de gold", "",
            f"Contrato: `{m['contract']['file']}` ({m['contract']['version']}). La solución lee solo `data/gold/`; "
            "`is_fraud` vive en `data/gold_eval/` y la evaluación la une por `transaction_id`. Las reglas se "
            "verifican antes de publicar: si una falla, gold no se reemplaza.", "",
            *table(["Regla", "Condición", "Valor", "Estado"], rules),
            *table(["Tabla", "Ruta (bajo data/)", "Filas", "Columnas", "sha256"], tabs, "---|---|---:|---:|---")]


def section_checks(r: dict) -> list[str]:
    rows = [[c["id"], f"`{c['table']}`", c["check"], c["description"], n(c["n"]), n(c["denominator"]), pct(c["pct"]),
             c["action"], eda_cell(c)] for c in r["checks"]]
    with_eda = [c for c in r["checks"] if c["eda"]]
    same = sum((c["eda"]["n"], c["eda"]["denominator"]) == (c["n"], c["denominator"]) for c in with_eda)
    eda_note = (f"**{same} de {len(with_eda)} checks con referencia en el EDA dan exactamente la misma cifra** "
                "(numerador y denominador)." if with_eda else
                "Sin comparación con el EDA en este repo: `outputs/tables/` quedó en el repo del EDA, donde el mismo "
                "pipeline sobre el dataset completo reproduce las cifras de `calidad_datos.md`. Aquí `transactions` "
                "cubre solo la ventana de 12 meses, así que sus conteos no son comparables con el EDA.")
    return ["## 3. Checks con conteos", "",
            "Violaciones = filas (o archivos, en SCH-01) que fallan el check; denominador = filas donde el check "
            "aplica. La última columna es la cifra del EDA para el mismo check (`outputs/tables/01_*.csv`, "
            "documentada en `docs/eda/calidad_datos.md` §B–C).", "",
            *table(["ID", "Tabla", "Check", "Descripción", "Violaciones", "Denominador", "%", "Acción",
                    "EDA (violaciones / denominador)"], rows, "---|---|---|---|---:|---:|---:|---|---"),
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
                     or "ninguna", ", ".join(f"`{c}`" for c in s["extra_columns"]) or "—",
                     ", ".join(f"`{k}` ({n(v)})" for k, v in s["renamed"].items()) or "—"])
        if failing:
            details.append(f"- `{t}`: {n(s['quarantined'])} filas en `silver/_quarantine/{t}.parquet` con el motivo "
                           "en `_quarantine_reason`.")
    return ["## 4. Contratos de schema de silver (pandera)", "",
            "Contratos en `data/pipeline/contracts.py` (versión " + r["contract_version"] + "): columnas, tipos, "
            "obligatorias, PK única y dominios (enums y rangos observados en el EDA). Una columna del archivo que no "
            "está en el contrato se conserva en bronze y no pasa a silver. Un renombre solo se acepta si está "
            "declarado como alias.", "",
            *table(["Tabla", "Columnas", "Obligatorias", "Reglas", "Filas validadas", "En cuarentena",
                    "Fallas (columna: check, filas)", "Columnas fuera del contrato", "Alias usados (filas)"], rows,
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
    return ["## 5. Llegadas tardías y rezago", "",
            "Rezago = `process_date − fecha del evento` en días. Positivo = llegada tardía (flag `qc_late_arrival`). "
            "Un rezago de −1 no es un error: el día operativo del archivo corta a las 06:00 u 08:00 "
            "(`calidad_datos.md` §B4).", "",
            *table(["Tabla", "Filas", "Tardías (> 0 d)", "Rezago máx.", "Distribución del rezago",
                    "Partición ≠ process_date"], rows, "---|---:|---:|---:|---|---:")]


def section_changes(r: dict) -> list[str]:
    m = r["gold"]["manifest"]
    out = ["## 6. Qué cambió respecto de la corrida anterior", ""]
    fc = r["file_changes"]
    if fc is None:
        return out + ["Primera corrida en este directorio: no hay versión anterior con qué comparar.", ""]
    out += [f"Corrida anterior: {r['previous_run_at']}. Archivos: {n(len(fc['new']))} nuevos, "
            f"{n(len(fc['changed']))} cambiados (md5 distinto), {n(len(fc['removed']))} retirados, "
            f"{n(fc['unchanged'])} sin cambio.", ""]
    listed = [f"- {kind}: `{f['key']}` ({n(f.get('n_rows'))} filas)"
              for kind in ("new", "changed", "removed") for f in fc[kind][:20]]
    out += [*listed, ""] if listed else []
    rows = [[f"`{t}`", n(d["inserted"]), n(d["updated"]), n(d["deleted"]), n(d["unchanged"])]
            for t, d in r["gold"]["diff"].items()]
    prev = m["previous"]["version"] if m["previous"] else "—"
    out += [*table(["Tabla gold", "Insertadas", "Actualizadas", "Borradas", "Sin cambio"], rows,
                       "---|---:|---:|---:|---:"),
            f"Versión gold: v{prev} → v{m['version']} "
            f"({'sin cambios de contenido: mismo sha256 en todas las tablas' if not m['changed_tables'] else 'cambiaron ' + ', '.join(m['changed_tables'])}).",
            ""]
    return out


def section_fixture(fx: dict | None) -> list[str]:
    out = ["## 7. Fixture `late_arrival`: llegadas tardías, cambio de schema y contrato de gold", ""]
    if fx is None:
        return out + ["Sin resultados: correr `python -m data.pipeline fixture`.", ""]
    spec, runs = fx["spec"], fx["runs"]
    out += ["> **FIXTURE, datos sintéticos de prueba (no salen del dataset).** El dataset real no tiene llegadas "
            "tardías ni evolución de schema (`calidad_datos.md` §B4, §B6), así que la frescura se demuestra con dos "
            "entregas etiquetadas en `data/fixtures/late_arrival/` (IDs `FX-`). El pipeline las procesa con el "
            "mismo código que la corrida real, en `data/_fixture_run/`.", ""]
    for d, r in zip(spec["deliveries"], runs):
        m = r["gold"]["manifest"]
        ok = sum(x["ok"] for x in r["gold"]["contract_rules"])
        out.append(f"- **{d['name']}** (entregada {d['delivered_at']}, gold v{m['version']}, contrato "
                   f"{ok}/{len(r['gold']['contract_rules'])} reglas): {d['purpose']}")
    last = runs[-1]
    fc = last["file_changes"]
    out += ["", f"### Qué cambió de {spec['deliveries'][0]['name']} a {spec['deliveries'][-1]['name']}", "",
            "**Archivos**", ""]
    rows = [["nuevo", f"`{f['key']}`", "—", n(f["n_rows"])] for f in fc["new"]] + \
           [["re-entregado (md5 distinto)", f"`{f['key']}`", n(f["n_rows_before"]), n(f["n_rows"])]
            for f in fc["changed"]]
    out += table(["Cambio", "Archivo", "Filas antes", "Filas ahora"], rows, "---|---|---:|---:")
    drift = [f for f in last["files"] if f["schema_drift"]]
    out += ["**Cambio de schema** (header del archivo vs contrato)", ""]
    rows = [[f"`{f['key']}`", ", ".join(f"`{c}`" for c in f["header_added"]) or "—",
             ", ".join(f"`{c}`" for c in f["header_missing"]) or "—",
             ", ".join(f"`{a}` → `{c}`" for a, c in f["header_renamed"].items()) or "—"] for f in drift]
    out += table(["Archivo", "Columnas nuevas", "Columnas faltantes", "Renombradas"], rows)
    s = last["silver"]["transactions"]
    out += [f"Manejo: el alias declarado alimenta la columna canónica "
            f"({', '.join(f'`{k}`: {n(v)} filas' for k, v in s['renamed'].items()) or 'sin alias'}); la columna "
            f"nueva queda solo en bronze ({', '.join(f'`{c}`' for c in s['extra_columns']) or '—'}) hasta que el "
            "contrato suba de versión. Ninguna fila se pierde por el cambio.", ""]
    late = s["late"]
    out += ["**Llegadas tardías**", "",
            f"{n(late['n_late'])} transacciones con rezago positivo (máximo {n(late['max_lag_days'])} días). "
            f"Distribución: {', '.join(f'{k} d: {n(v)}' for k, v in late['lag_hist'].items())}. Quedan en gold con "
            "`qc_late_arrival = true`, y la corrección de una transacción ya cargada entra como upsert "
            "(DUP-02: gana el `process_date` más reciente).", "",
            "**Checks que cambiaron**", ""]
    first = {(c["id"], c["table"]): c["n"] for c in runs[0]["checks"]}
    rows = [[c["id"], f"`{c['table']}`", c["check"], n(first.get((c["id"], c["table"]))), n(c["n"])]
            for c in last["checks"] if first.get((c["id"], c["table"])) != c["n"]]
    out += table(["ID", "Tabla", "Check", spec["deliveries"][0]["name"], spec["deliveries"][-1]["name"]], rows,
                 "---|---|---|---:|---:")
    rows = [[f"`{t}`", n(d["inserted"]), n(d["updated"]), n(d["deleted"]), n(d["unchanged"])]
            for t, d in last["gold"]["diff"].items()]
    m0, m1 = runs[0]["gold"]["manifest"], last["gold"]["manifest"]
    out += ["**Gold**", "", *table(["Tabla", "Insertadas", "Actualizadas", "Borradas", "Sin cambio"], rows,
                                   "---|---:|---:|---:|---:"),
            f"Versión v{m0['version']} → v{m1['version']}; cambiaron: {', '.join(m1['changed_tables']) or 'ninguna'}.",
            ""]
    checks_all = [x for d, r in zip(spec["deliveries"], runs) for x in expected_vs_actual(r, spec["expected"][d["name"]])]
    bad = [x for x in checks_all if not x["ok"]]
    out += [f"**Contra lo esperado** (`fixture.json` → `expected`): {n(len(checks_all) - len(bad))} de "
            f"{n(len(checks_all))} conteos coinciden."]
    out += [f"- NO coincide: {x['item']}: esperado {x['expected']}, obtenido {x['actual']}" for x in bad]
    return out + [""]


def section_nulls(r: dict) -> list[str]:
    out = ["## 8. Nulos por columna (silver)", "",
           "Solo columnas con nulos. Obligatorias en negrita (deben ser 0). Nulos esperables y aleatorios según "
           "`calidad_datos.md` §B2.", ""]
    from data.pipeline import contracts
    for t in r["tables"]:
        nulls = r["silver"][t]["nulls"]
        rows_ = r["silver"][t]["rows_silver"]
        req = set(contracts.required_columns(t))
        items = [f"{'**' if c in req else ''}`{c}`{'**' if c in req else ''} {pct(round(100 * v / rows_, 3))}"
                 for c, v in nulls.items() if v]
        out.append(f"- `{t}` ({n(rows_)} filas): " + (", ".join(items) or "sin nulos"))
    return out + [""]


def write_report() -> None:
    real = Layout(DATA_DIR).results
    fx_path = FIXTURE_WORKDIR / "fixture_results.json"
    r = json.loads(real.read_text()) if real.exists() else None
    fx = json.loads(fx_path.read_text()) if fx_path.exists() else None
    lines = ["# Reporte de calidad — pipeline LATAM Bank", ""]
    if r is None:
        lines += ["Sin corrida real: correr `make setup` o `python -m data.pipeline run --source s3`.", ""]
    else:
        m, src = r["gold"]["manifest"], r["source"]
        lines += [f"> Generado por `python -m data.pipeline report` desde `data/gold/run_results.json` y "
                  "`data/_fixture_run/fixture_results.json`. **No editar a mano**: `make setup` lo regenera.",
                  f"> Corrida: {r['run_at']} ({r['seconds']} s). Pipeline {r['pipeline_version']}, contrato "
                  f"{r['contract_version']}, **gold v{m['version']}** (contenido desde {m['version_created_at']}; "
                  "`data/gold/manifest.json`).",
                  f"> Fuente: `{src['location']}` ({src['mode']}), {n(src['files'])} archivos, "
                  f"{src['bytes'] / 1e6:,.1f} MB, cargados entre {src['loaded_at_min']} y {src['loaded_at_max']}.",
                  "> Alcance: las 4 tablas de la idea W3 y las derivadas de `contracts/gold_contract.md`.", ""]
        lines += (section_summary(r) + section_contract(r) + section_checks(r) + section_contracts(r) + section_lag(r)
                  + section_changes(r))
    lines += section_fixture(fx)
    if r is not None:
        lines += section_nulls(r)
    lines += ["## Cómo se reproduce", "", "```bash",
              "make setup     # venv + dependencias + pipeline desde S3 (.env) + fixture + este reporte",
              "make pipeline  # solo la corrida real (SOURCE=local para usar un espejo local en data/, sin red)",
              "make fixture   # solo el fixture late_arrival", "make report    # solo este archivo",
              "make test      # pytest, sin red", "```", ""]
    REPORT_PATH.write_text("\n".join(lines))
    log.info("reporte: %s", REPORT_PATH)
