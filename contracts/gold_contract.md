# Contrato de gold — LATAM Bank (v1)

> Redactado el 28 sep 2026 a partir de los 4 requisitos del equipo (R1–R4). Lo que no sale de esos 4 puntos está
> marcado **[propuesta]** y se puede cambiar subiendo la versión del contrato. Lo aplica `data/pipeline/gold.py`; las
> reglas G1–G5 se verifican en cada corrida (si una falla, gold no se publica) y en `tests/`.

## Requisitos
| # | Requisito | Cómo se cumple |
|---|---|---|
| R1 | 12 meses de transactions | Ventana = últimos 12 meses completos: `2025-06-01 00:00 ≤ transaction_date < 2026-06-01 00:00` (misma convención de meses completos que el EDA) |
| R2 | `customer_id` resuelto por join | En gold, `transactions.customer_id` = `products.customer_id` del `product_id` (dueño del producto), no el `customer_id` del archivo |
| R3 | `is_fraud` solo en `gold_eval/` | Ninguna tabla de `data/gold/` tiene `is_fraud` ni columnas derivadas de él; la etiqueta vive en `data/gold_eval/transaction_labels` |
| R4 | Tablas derivadas | `customer_profile` y `transactions_enriched` en `data/gold/` |

## Ubicación y acceso
- `data/gold/`: `customers`, `products`, `transactions`, `complaints`, `customer_profile`, `transactions_enriched`
  (Parquet) y `manifest.json`. Es lo único que lee la solución (agente, tools, servicio).
- `data/gold_eval/`: `transaction_labels` (Parquet). Solo lo lee la evaluación, uniendo por `transaction_id`.
- El manifest (`data/gold/manifest.json`) lista las dos carpetas con filas y sha256.

## Tablas

### `transactions` (R1, R2, R3)
- Filas: transacciones de silver con `transaction_date` en la ventana de R1.
- `customer_id`: dueño del producto por join con `products`. **[propuesta]** Si el `product_id` no existe en
  `products`, `customer_id` queda nulo y `qc_product_orphan = true`: la fila se conserva pero nunca se atribuye al
  `customer_id` del archivo.
- `_customer_id_source`: el `customer_id` que venía en el archivo (linaje, para auditar `qc_product_other_customer`).
- Sin `is_fraud`. `fraud_score` sí se queda **[propuesta]**: es la señal de triage de la idea W3 (preguntas 5 y 7 de
  Slack pendientes: si es input en tiempo real o variable de evaluación).
- Flags `qc_*` como en el resto de gold.

### `transactions_enriched` (R4) **[propuesta de columnas]**
Una fila por transacción de `gold.transactions`: sus columnas de contenido (sin linaje `_*`, sin `is_fraud`) más
`product_type`, `product_status`, `product_opening_date` (de `products`) y `customer_country`, `customer_segment` (del
`customer_id` resuelto). Limitación conocida: customers y products son una foto única al corte, así que un cambio de
segmento reescribe las filas históricas de ese cliente (`data_quality.md` §A1, riesgo de leakage).

### `customer_profile` (R4) **[propuesta de columnas]**
Una fila por cliente de `gold.customers`:
`customer_id`, `country`, `segment`, `customer_status`, `registration_date`, `n_products`, `n_active_products`,
`n_transactions_12m`, `n_declined_12m`, `n_reversed_12m`, `first_transaction_at_12m`, `last_transaction_at_12m`,
`n_complaints_12m` (complaints con `creation_date` en la ventana de R1) y `qc_future_last_updated`.
Sin datos personales (nombre, documento, email, teléfonos y dirección quedan solo en `gold.customers`) y sin `is_fraud`
ni agregados de él.

### `customers`, `products`, `complaints`
Silver + flags `qc_*`, completas (sin ventana) **[propuesta]**. En `complaints`, `customer_id` es el del caso: no se
resuelve por producto porque `affected_product_id` pertenece a otro cliente en el 100% de los casos
(`data_quality.md` §B3).

### `gold_eval/transaction_labels` (R3)
`transaction_id`, `is_fraud` para exactamente las transacciones de `gold.transactions`.

## Reglas verificables (cada corrida)
| Regla | Condición |
|---|---|
| G1 | Ninguna tabla de `data/gold/` tiene la columna `is_fraud` |
| G2 | `min` y `max` de `gold.transactions.transaction_date` dentro de la ventana de R1 |
| G3 | 0 filas de `gold.transactions` con producto existente y `customer_id` ≠ `products.customer_id` |
| G4 | `transaction_labels` y `gold.transactions` tienen el mismo conjunto de `transaction_id` (1:1) |
| G5 | `customer_profile` tiene una fila por cliente de `gold.customers` y `transactions_enriched` una por transacción de `gold.transactions` |

## Versionado
Contrato v1. Un cambio de columnas o de ventana es v2: se actualiza este archivo, `CONTRACT_VERSION` en
`data/pipeline/contracts.py` y el manifest registra la nueva versión.
