"""Blocks against the fraud label (spec 10 AC-04). This is the only module of the harness that reads the label
(FR-05, constitution 7): the runtime, the cases and the rest of the harness never do."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import duckdb

LABELS = Path(__file__).resolve().parents[2] / "data/gold_eval/transaction_labels.parquet"   # `make labels-pull`


def load_labels(transaction_ids: set[str], path: Path = LABELS) -> Optional[dict[str, bool]]:
    """The label of each given transaction, or None when the label file is not on this machine."""
    if not path.exists():
        return None
    con = duckdb.connect()
    try:
        rows = con.execute(f"SELECT transaction_id, is_fraud FROM read_parquet('{path.as_posix()}') "
                           "WHERE transaction_id IN (SELECT unnest(?))", [sorted(transaction_ids)]).fetchall()
    finally:
        con.close()
    return {transaction_id: bool(is_fraud) for transaction_id, is_fraud in rows}


def blocks_vs_label(records: list[dict[str, Any]], labels: dict[str, bool]) -> dict[str, Any]:
    """Precision and recall of the agent's blocks, counted per run (§4.1): a block is a run that ends with the card
    Blocked on a labeled transaction; a fraud case is a run whose case transaction is labeled fraud."""
    blocked = [(record.get("final_state") or {}).get("transaction_id") for record in records
               if (record.get("final_state") or {}).get("product_status") == "Blocked"]
    blocked = [transaction_id for transaction_id in blocked if transaction_id in labels]
    fraud_runs = [record for record in records if labels.get(record.get("expected_transaction_id")) is True]
    caught = sum(1 for record in fraud_runs
                 if (record.get("final_state") or {}).get("product_status") == "Blocked"
                 and (record.get("final_state") or {}).get("transaction_id") == record["expected_transaction_id"])
    blocked_fraud = sum(1 for transaction_id in blocked if labels[transaction_id])
    return {"blocked": len(blocked), "blocked_fraud": blocked_fraud, "fraud_cases": len(fraud_runs),
            "fraud_blocked": caught,
            "precision": round(blocked_fraud / len(blocked), 4) if blocked else None,
            "recall": round(caught / len(fraud_runs), 4) if fraud_runs else None}
