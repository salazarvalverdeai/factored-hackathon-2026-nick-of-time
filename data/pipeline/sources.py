"""Raw file sources: S3 (with credentials from .env), local mirror or fixture.

All of them return the same list of `SourceFile`: relative key (`<table>/year=…/<table>_YYYYMMDD.csv`, same as in
S3), local path, size, md5, load date and header. The load date is the S3 LastModified (s3 mode), the file's mtime
(local mode; `aws s3 sync` sets it to LastModified) or the delivery date declared in the fixture.

s3 mode: lists the bucket with boto3 and downloads to the local mirror (`data/<table>/…`, the same one the EDA uses)
only new or different objects (size or md5 ≠ ETag). It never deletes local files. In the bucket the dimensions are
flat files (`data/customers.csv`); in the mirror, as in `scripts/s3_sync.sh`, they go to `data/customers/customers.csv`,
and that is the canonical key in all three modes (`origin` keeps the S3 URI).
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
    key: str                 # path relative to the source root, S3 style
    local_path: str
    size: int
    md5: str
    loaded_at: str           # ISO 8601 with time zone
    header: list[str]
    delivery: str            # "s3", "local" or the name of the fixture delivery
    etag: str | None = None
    origin: str | None = None  # S3 URI of the object (s3 mode)

    def as_dict(self) -> dict:
        return asdict(self)


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_header(path: Path) -> list[str]:
    """First line of the CSV, without BOM or line ending."""
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return next(csv.reader(io.StringIO(f.readline())))


def table_files(root: Path, table: str) -> list[Path]:
    """CSVs of a table under root: partitioned (<table>/year=…/…csv) or flat (<table>/<table>.csv)."""
    base = root / table
    return sorted(base.rglob("*.csv")) if base.is_dir() else []


def _local_file(root: Path, path: Path, table: str, delivery: str, loaded_at: datetime) -> SourceFile:
    return SourceFile(table=table, key=path.relative_to(root).as_posix(), local_path=str(path),
                      size=path.stat().st_size, md5=md5_of(path), loaded_at=loaded_at.isoformat(),
                      header=read_header(path), delivery=delivery)


def list_local(root: Path, tables: tuple[str, ...]) -> tuple[list[SourceFile], int]:
    """Returns (files in scope, files skipped by config.in_scope)."""
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
    """Overlays fixture deliveries 1..upto: a key repeated in a later delivery replaces the earlier one
    (like a re-delivery that overwrites the object in S3)."""
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
    if "-" in etag:              # multipart ETag: not the md5 of the content; the size is enough
        return False
    return md5_of(local) != etag


def list_s3(tables: tuple[str, ...], mirror: Path, workers: int = 16) -> tuple[list[SourceFile], int]:
    """Lists the bucket, syncs to the local mirror whatever is missing or changed (only files in scope, config.in_scope)
    and returns (inventory, objects skipped by scope)."""
    env = load_env()
    if not (env["AWS_ACCESS_KEY_ID"] and env["S3_BUCKET"]):
        raise RuntimeError("Missing credentials or bucket in .env (see .env.example)")
    s3 = _s3_client(env)
    bucket, prefix = env["S3_BUCKET"], env["S3_PREFIX"] or "data/"
    objects, skipped = [], 0
    for t in tables:
        for sub in (f"{prefix}{t}/", f"{prefix}{t}.csv"):   # partitioned or flat
            for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=sub):
                for o in page.get("Contents", []):
                    if o["Key"].endswith(".csv") and (o["Key"].startswith(f"{prefix}{t}/") or o["Key"] == sub):
                        if in_scope(t, o["Key"][len(prefix):]):
                            objects.append((t, o))
                        else:
                            skipped += 1
    log.info("S3: %d objects in scope in %d tables (%d skipped outside the window)", len(objects), len(tables),
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
    log.info("S3: %d downloaded (new or different), %d already in the local mirror", n_new, len(results) - n_new)
    return sorted((f for f, _ in results), key=lambda f: f.key), skipped
