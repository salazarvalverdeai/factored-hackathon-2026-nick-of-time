"""Pipeline paths, scope and versions."""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
FIXTURE_DIR = DATA_DIR / "fixtures" / "late_arrival"
FIXTURE_WORKDIR = DATA_DIR / "_fixture_run"
REPORT_PATH = DATA_DIR / "quality_report.md"
EDA_TABLES_DIR = ROOT / "outputs" / "tables"

PIPELINE_VERSION = "0.1.0"
# Tables the W3 idea needs (pitch_brief.md, block 3). Order = build order (dimensions first).
TABLES = ("customers", "products", "transactions", "complaints")
# Time zone used to read the load date (S3 LastModified) for the future-dates check. It is the
# convention in data_quality.md (load "2026-08-31 Lima time").
LOAD_TZ = "America/Lima"
# contracts/gold_contract.md R1: last 12 full months of transactions, [start, end).
TX_WINDOW = ("2025-06-01", "2026-06-01")
GOLD_CONTRACT = ROOT / "contracts" / "gold_contract.md"

log = logging.getLogger("pipeline")


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def load_env() -> dict[str, str]:
    """Variables from .env (S3 credentials included). They are never logged."""
    load_dotenv(ROOT / ".env")
    return {k: os.environ.get(k, "") for k in
            ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_DEFAULT_REGION", "S3_BUCKET", "S3_PREFIX",
             "LOCAL_DATA_DIR")}


@dataclass(frozen=True)
class Layout:
    """Directories of a run. The real run uses data/; the fixture, data/_fixture_run/."""
    workdir: Path

    @property
    def bronze(self) -> Path:
        return self.workdir / "bronze"

    @property
    def silver(self) -> Path:
        return self.workdir / "silver"

    @property
    def quarantine(self) -> Path:
        return self.silver / "_quarantine"

    @property
    def gold(self) -> Path:
        return self.workdir / "gold"

    @property
    def gold_eval(self) -> Path:
        return self.workdir / "gold_eval"

    @property
    def manifest(self) -> Path:
        return self.gold / "manifest.json"

    @property
    def results(self) -> Path:
        return self.gold / "run_results.json"

    def mkdirs(self) -> None:
        for d in (self.bronze, self.silver, self.quarantine, self.gold, self.gold_eval):
            d.mkdir(parents=True, exist_ok=True)


def in_scope(table: str, key: str) -> bool:
    """Files that are read. transactions: partitions from one day before the window (the shifted operating day leaves
    next-day events in the previous partition) onward, including those after the end of the window
    (they may bring late arrivals). The rest of the tables are read in full."""
    m = re.search(r"_(\d{8})\.csv$", key)
    if table != "transactions" or not m:
        return True
    d = date(int(m.group(1)[:4]), int(m.group(1)[4:6]), int(m.group(1)[6:]))
    return d >= date.fromisoformat(TX_WINDOW[0]) - timedelta(days=1)
