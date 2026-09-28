"""Check de pertenencia (OWN-02, `calidad_datos.md` §C #1): `affected_product_id` de un producto de otro cliente."""
from __future__ import annotations

import duckdb

from data.pipeline import gold
from tests.conftest import contract_frame


def test_affected_product_of_other_customer_is_flagged():
    con = duckdb.connect()
    customers = contract_frame("customers", [{"customer_id": "C1"}, {"customer_id": "C2"}], lineage=True)
    products = contract_frame("products", [{"product_id": "P1", "customer_id": "C1"},
                                           {"product_id": "P2", "customer_id": "C2"}], lineage=True)
    complaints = contract_frame("complaints", [
        {"complaint_id": "K1", "customer_id": "C1", "affected_product_id": "P1"},   # producto propio
        {"complaint_id": "K2", "customer_id": "C1", "affected_product_id": "P2"},   # producto de otro cliente
        {"complaint_id": "K3", "customer_id": "C2", "affected_product_id": None},   # sin producto: no aplica
        {"complaint_id": "K4", "customer_id": "C2", "affected_product_id": "P9"},   # huérfano: no aplica aquí
    ], lineage=True)
    for name, df in [("s_customers", customers), ("s_products", products), ("s_complaints", complaints)]:
        con.register(name, df)

    out = con.sql(gold.gold_select("complaints")).pl()
    flags = dict(zip(out["complaint_id"], out["qc_affected_product_other_customer"]))
    assert flags == {"K1": False, "K2": True, "K3": None, "K4": None}
    orphans = dict(zip(out["complaint_id"], out["qc_affected_product_orphan"]))
    assert orphans == {"K1": False, "K2": False, "K3": None, "K4": True}

    # El conteo del check = flags en true sobre flags no nulos (denominador = complaints con producto existente)
    n, den = con.sql("SELECT count(*) FILTER (WHERE f), count(f) FROM (SELECT qc_affected_product_other_customer f "
                     f"FROM ({gold.gold_select('complaints')}))").fetchone()
    assert (n, den) == (1, 2)
