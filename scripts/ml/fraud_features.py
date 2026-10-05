"""Spec 17 T2: features known at transaction time (AC-02, spec 17 §4.2).

History features aggregate ALL strictly earlier transactions of the same customer (timestamp < current; a same-time
transaction is never history), whatever their status: a Declined attempt is known at authorization and a later status
such as Reversed must not shape earlier features [assumption, D-009]. Feature rows are emitted only for
Approved/Pending transactions. Input: gold `transactions_enriched` rows of all statuses. No labels here.
"""
from __future__ import annotations

import math
from bisect import insort

import polars as pl

STATIC = ["amount_usd_f", "log_amount_usd", "currency", "channel", "transaction_type", "transaction_category",
          "merchant_category", "abroad", "hour", "weekday", "product_type"]
HISTORY = ["n_1h", "amt_1h", "n_24h", "amt_24h", "n_7d", "amt_7d", "amount_vs_median", "first_at_merchant",
           "km_from_prev", "secs_since_prev"]
FEATURES = STATIC + HISTORY
INPUT_COLUMNS = ["transaction_id", "transaction_date", "customer_id", "product_id", "amount", "amount_usd", "currency",
                 "channel", "transaction_type", "transaction_category", "merchant_name", "merchant_category",
                 "transaction_country", "latitude", "longitude", "product_type", "customer_country"]
STATUS_COL = "transaction_status"  # read only to choose which rows get a feature row, never as a feature
EMIT_STATUSES = ("Approved", "Pending")
# Never features: snapshots after the fact, quality flags, processing date, labels (spec 17 §4.2, AC-02).
# `fraud_score` is the bank's baseline arm, not a feature [assumption: it only enters the stacked arm].
FORBIDDEN_PREFIXES = ("qc_", "_")
FORBIDDEN = {"product_status", "process_date", "is_fraud", "fraud_score", "response_code", "transaction_status"}
_WINDOWS = {"1h": 3600, "24h": 86400, "7d": 7 * 86400}


def is_forbidden(col: str) -> bool:
    return col in FORBIDDEN or col.startswith(FORBIDDEN_PREFIXES)


def _haversine_km(lat1, lon1, lat2, lon2) -> pl.Expr:
    p = math.pi / 180
    a = ((lat2 - lat1) * p / 2).sin() ** 2 + (lat1 * p).cos() * (lat2 * p).cos() * ((lon2 - lon1) * p / 2).sin() ** 2
    return 12742 * a.sqrt().arcsin()


def build_features(tx: pl.DataFrame) -> pl.DataFrame:
    """One row per Approved/Pending input transaction (input order): `transaction_id` + FEATURES.

    Only INPUT_COLUMNS are ever read, so forbidden columns in `tx` (product_status, qc_*, labels...) are ignored."""
    df = tx.select([*INPUT_COLUMNS, STATUS_COL]).with_row_index("_row")
    # entity = customer; rows without one fall back to the product (the file never attributes them to a customer)
    df = df.with_columns(
        pl.coalesce("customer_id", "product_id").alias("_entity"),
        pl.col("transaction_date").dt.epoch("s").alias("_ts"),
        pl.coalesce("amount_usd", pl.when(pl.col("currency") == "USD").then(pl.col("amount"))).alias("amount_usd_f"),
    )
    df = df.sort(["_entity", "_ts", "_row"])
    n = df.height
    codes = df.select(pl.col("_entity").rank("dense").cast(pl.Int64)).to_series()
    key = (codes * (1 << 34) + df["_ts"]).alias("key")  # sorted by (entity, ts)
    amt = df["amount_usd_f"].fill_null(0.0)
    cs = pl.concat([pl.Series([0.0]), amt.cum_sum()])
    start = key.search_sorted((codes * (1 << 34)), side="left").to_list()
    hi = key.search_sorted(key, side="left").to_list()  # rows [start, hi) are strictly earlier (ts < own)
    cols: dict[str, pl.Series] = {}
    for name, w in _WINDOWS.items():
        lo = [max(a, b) for a, b in zip(key.search_sorted(key - w, side="left").to_list(), start)]
        cols[f"n_{name}"] = pl.Series(f"n_{name}", [h - l for h, l in zip(hi, lo)])
        cols[f"amt_{name}"] = pl.Series(f"amt_{name}", [cs[h] - cs[l] for h, l in zip(hi, lo)])
    # amount against the median of strictly earlier amounts (null when no history or amount unknown)
    vals, known = amt.to_list(), df["amount_usd_f"].is_not_null().to_list()
    ratio: list[float | None] = []
    seen: list[float] = []
    ptr = 0
    for i in range(n):
        if i == start[i]:
            seen, ptr = [], i
        while ptr < hi[i]:
            if known[ptr]:
                insort(seen, vals[ptr])
            ptr += 1
        k = len(seen)
        med = None if not k else (seen[k // 2] if k % 2 else (seen[k // 2 - 1] + seen[k // 2]) / 2)
        ratio.append(vals[i] / med if med and known[i] else None)
    # previous transaction = the closest strictly earlier one; for the distance, the closest one with a known location
    prev = pl.Series("prev", [h - 1 if h > s0 else None for h, s0 in zip(hi, start)], dtype=pl.Int64)
    ts, lat, lon = df["_ts"], df["latitude"].cast(pl.Float64), df["longitude"].cast(pl.Float64)
    located = (lat.is_not_null() & lon.is_not_null()).to_list()
    last_loc: list[int | None] = []
    for i in range(n):
        last_loc.append(i if located[i] else (last_loc[i - 1] if i > start[i] else None))
    prev_loc = pl.Series("prev_loc", [last_loc[h - 1] if h > s0 else None for h, s0 in zip(hi, start)], dtype=pl.Int64)
    pl_lat, pl_lon = lat.gather(prev_loc), lon.gather(prev_loc)
    km = pl.select(_haversine_km(pl.lit(lat), pl.lit(lon), pl.lit(pl_lat), pl.lit(pl_lon))).to_series()
    out = df.select("_row", "transaction_id", "amount_usd_f", "currency", "channel", "transaction_type",
                    "transaction_category", "merchant_category", "product_type", STATUS_COL).with_columns(
        pl.col("amount_usd_f").clip(lower_bound=0).log1p().alias("log_amount_usd"),
        (df["transaction_country"] != df["customer_country"]).alias("abroad"),
        df["transaction_date"].dt.hour().alias("hour"),
        df["transaction_date"].dt.weekday().alias("weekday"),
        pl.Series("amount_vs_median", ratio, dtype=pl.Float64),
        km.alias("km_from_prev"),
        (ts - ts.gather(prev)).alias("secs_since_prev"),
        *cols.values(),
    )
    # first time at this merchant: no strictly earlier transaction of the entity at the same merchant
    first = df.select(
        (pl.col("_ts") == pl.col("_ts").min().over(["_entity", "merchant_name"])).alias("first_at_merchant"),
        pl.col("merchant_name").is_null().alias("_nom"),
    )
    out = out.with_columns(
        pl.when(first["_nom"]).then(None).otherwise(first["first_at_merchant"]).alias("first_at_merchant"))
    return out.filter(pl.col(STATUS_COL).is_in(EMIT_STATUSES)).sort("_row").select(["transaction_id", *FEATURES])
