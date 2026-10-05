"""Verify local gold (and labels, if present) against the sha256 in data/gold/manifest.json.

    make gold-pull     # downloads and then runs this check

Exit code 1 if any table is missing or does not match the manifest.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT / "data/gold/manifest.json").read_text())
problems = 0
for name, table in manifest["tables"].items():
    folder = "data/gold_eval" if name == "transaction_labels" else "data/gold"
    path = ROOT / folder / f"{name}.parquet"
    if not path.exists():
        if name == "transaction_labels":
            print(f"skip  {name}: labels are only for the harness owner and the lead (make labels-pull)")
            continue
        print(f"FAIL  {name}: missing {path.relative_to(ROOT)}")
        problems += 1
        continue
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    status = "OK  " if digest == table["sha256"] else "FAIL"
    problems += status == "FAIL"
    print(f"{status}  {name:24s} {table['rows']:>10,} rows")
print(f"gold version {manifest['version']} · {'all tables match the manifest' if not problems else f'{problems} problem(s)'}")
sys.exit(1 if problems else 0)
