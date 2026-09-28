"""Fuentes de archivos crudos: S3 (con credenciales de .env), espejo local o fixture.

Todas devuelven la misma lista de `SourceFile`: clave relativa (`<tabla>/year=…/<tabla>_YYYYMMDD.csv`, igual que en
S3), ruta local, tamaño, md5, fecha de carga y header. La fecha de carga es el LastModified de S3 (modo s3), el mtime
del archivo (modo local; `aws s3 sync` lo iguala al LastModified) o la fecha de entrega declarada en el fixture.

Modo s3: lista el bucket con boto3 y descarga al espejo local (`data/<tabla>/…`, el mismo que usa el EDA) solo los
objetos nuevos o distintos (tamaño o md5 ≠ ETag). Nunca borra archivos locales. En el bucket las dimensiones son
archivos planos (`data/customers.csv`); en el espejo, como en `scripts/s3_sync.sh`, van a `data/customers/customers.csv`,
y esa es la clave canónica en los tres modos (`origin` guarda la URI de S3).
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from data.pipeline.config import in_scope, load_env

log = logging.getLogger("pipeline.sources")


@dataclass
class SourceFile:
    table: str
    key: str                 # ruta relativa a la raíz de la fuente, estilo S3
    local_path: str
    size: int
    md5: str
    loaded_at: str           # ISO 8601 con zona
    header: list[str]
    delivery: str            # "s3", "local" o el nombre de la entrega del fixture
    etag: str | None = None
    origin: str | None = None  # URI de S3 del objeto (modo s3)

    def as_dict(self) -> dict:
        return asdict(self)


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_header(path: Path) -> list[str]:
    """Primera línea del CSV, sin BOM ni fin de línea."""
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return next(csv.reader(io.StringIO(f.readline())))


def table_files(root: Path, table: str) -> list[Path]:
    """CSV de una tabla bajo root: particionados (<tabla>/year=…/…csv) o plano (<tabla>/<tabla>.csv)."""
    base = root / table
    return sorted(base.rglob("*.csv")) if base.is_dir() else []


def _local_file(root: Path, path: Path, table: str, delivery: str, loaded_at: datetime) -> SourceFile:
    return SourceFile(table=table, key=path.relative_to(root).as_posix(), local_path=str(path),
                      size=path.stat().st_size, md5=md5_of(path), loaded_at=loaded_at.isoformat(),
                      header=read_header(path), delivery=delivery)


def list_local(root: Path, tables: tuple[str, ...]) -> tuple[list[SourceFile], int]:
    """Devuelve (archivos en alcance, archivos omitidos por config.in_scope)."""
    out, skipped = [], 0
    for t in tables:
        for p in table_files(root, t):
            if not in_scope(t, p.relative_to(root).as_posix()):
                skipped += 1
                continue
            mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
            out.append(_local_file(root, p, t, "local", mtime))
    return out, skipped


def list_fixture(fixture_dir: Path, tables: tuple[str, ...], upto: int) -> tuple[list[SourceFile], int]:
    """Superpone las entregas 1..upto del fixture: una clave repetida en una entrega posterior reemplaza a la anterior
    (como una re-entrega que sobrescribe el objeto en S3)."""
    spec = json.loads((fixture_dir / "fixture.json").read_text())
    by_key: dict[str, SourceFile] = {}
    skipped: set[str] = set()
    for d in spec["deliveries"][:upto]:
        root = fixture_dir / d["name"]
        loaded_at = datetime.fromisoformat(d["delivered_at"])
        for t in tables:
            for p in table_files(root, t):
                if not in_scope(t, p.relative_to(root).as_posix()):
                    skipped.add(p.relative_to(root).as_posix())
                    continue
                f = _local_file(root, p, t, d["name"], loaded_at)
                by_key[f.key] = f
    return sorted(by_key.values(), key=lambda f: f.key), len(skipped)


def _s3_client(env: dict[str, str]):
    import boto3
    return boto3.client("s3", region_name=env["AWS_DEFAULT_REGION"] or None,
                        aws_access_key_id=env["AWS_ACCESS_KEY_ID"] or None,
                        aws_secret_access_key=env["AWS_SECRET_ACCESS_KEY"] or None)


def _needs_download(local: Path, size: int, etag: str) -> bool:
    if not local.exists() or local.stat().st_size != size:
        return True
    if "-" in etag:              # ETag multipart: no es el md5 del contenido; basta con el tamaño
        return False
    return md5_of(local) != etag


def list_s3(tables: tuple[str, ...], mirror: Path, workers: int = 16) -> tuple[list[SourceFile], int]:
    """Lista el bucket, sincroniza al espejo local lo que falte o cambió (solo archivos en alcance, config.in_scope)
    y devuelve (inventario, objetos omitidos por alcance)."""
    env = load_env()
    if not (env["AWS_ACCESS_KEY_ID"] and env["S3_BUCKET"]):
        raise RuntimeError("Faltan credenciales o bucket en .env (ver .env.example)")
    s3 = _s3_client(env)
    bucket, prefix = env["S3_BUCKET"], env["S3_PREFIX"] or "data/"
    objects, skipped = [], 0
    for t in tables:
        for sub in (f"{prefix}{t}/", f"{prefix}{t}.csv"):   # particionada o plana
            for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=sub):
                for o in page.get("Contents", []):
                    if o["Key"].endswith(".csv") and (o["Key"].startswith(f"{prefix}{t}/") or o["Key"] == sub):
                        if in_scope(t, o["Key"][len(prefix):]):
                            objects.append((t, o))
                        else:
                            skipped += 1
    log.info("S3: %d objetos en alcance en %d tablas (%d omitidos fuera de la ventana)", len(objects), len(tables),
             skipped)

    def fetch(item) -> tuple[SourceFile, bool]:
        t, o = item
        rel = o["Key"][len(prefix):]
        key = f"{t}/{rel}" if "/" not in rel else rel
        local, etag = mirror / key, o["ETag"].strip('"')
        downloaded = _needs_download(local, o["Size"], etag)
        if downloaded:
            local.parent.mkdir(parents=True, exist_ok=True)
            tmp = local.with_suffix(".csv.part")
            s3.download_file(bucket, o["Key"], str(tmp))
            tmp.replace(local)
        return SourceFile(table=t, key=key, local_path=str(local), size=o["Size"], md5=md5_of(local),
                          loaded_at=o["LastModified"].isoformat(), header=read_header(local), delivery="s3",
                          etag=etag, origin=f"s3://{bucket}/{o['Key']}"), downloaded

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(fetch, objects))
    n_new = sum(d for _, d in results)
    log.info("S3: %d descargados (nuevos o distintos), %d ya estaban en el espejo local", n_new, len(results) - n_new)
    return sorted((f for f, _ in results), key=lambda f: f.key), skipped
