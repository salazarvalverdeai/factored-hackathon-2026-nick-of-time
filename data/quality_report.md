# Reporte de calidad — pipeline LATAM Bank

> Generado por `python -m data.pipeline report` desde `data/gold/run_results.json` y `data/_fixture_run/fixture_results.json`. **No editar a mano**: `make setup` lo regenera.
> Corrida: 2026-09-28T20:01:08+00:00 (49.0 s). Pipeline 0.1.0, contrato v1, **gold v1** (contenido desde 2026-09-28T20:01:08+00:00; `data/gold/manifest.json`).
> Fuente: `s3://factored-datathon-2026-s3-157725502942-us-east-2-an/data/` (s3), 1,482 archivos, 416.5 MB, cargados entre 2026-09-01T02:38:33+00:00 y 2026-09-01T02:51:35+00:00.
> Alcance: las 4 tablas de la idea W3 y las derivadas de `contracts/gold_contract.md`.

## 1. Resumen por tabla

| Tabla | Archivos | Filas bronze | Duplicados exactos | Versiones de PK | Cuarentena | Filas silver | Filas gold | sha256 gold |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `customers` | 1 | 150,000 | 0 | 0 | 0 | 150,000 | 150,000 | `a6ad9e0e3d01` |
| `products` | 1 | 400,000 | 0 | 0 | 0 | 400,000 | 400,000 | `a05d6177c7b1` |
| `transactions` | 383 | 1,551,365 | 0 | 0 | 0 | 1,551,365 | 1,477,723 | `37296dbfec9b` |
| `complaints` | 1,097 | 67,095 | 0 | 0 | 0 | 67,095 | 67,095 | `6e4a5db4744f` |

`transactions` en gold cubre la ventana [2025-06-01, 2026-06-01) (contrato R1). Bronze lee sus particiones desde un día antes del inicio en adelante; 714 archivos fuera de ese alcance no se descargan ni se leen. Silver tiene todo lo leído; el check WIN-01 cuenta lo que no pasa a gold.

Bronze es la copia fiel del CSV (todo texto + linaje). Silver aplica el contrato: tipos, renombres declarados, normalización de etiquetas, dedup/upsert por PK y validación pandera. Gold agrega flags `qc_*` por fila y no borra nada. Una fila con problemas de calidad se marca, y la capa de servicio decide qué hacer con ella.

## 2. Contrato de gold

Contrato: `contracts/gold_contract.md` (v1). La solución lee solo `data/gold/`; `is_fraud` vive en `data/gold_eval/` y la evaluación la une por `transaction_id`. Las reglas se verifican antes de publicar: si una falla, gold no se reemplaza.

| Regla | Condición | Valor | Estado |
|---|---|---|---|
| G1 | ninguna tabla de data/gold/ tiene is_fraud | ninguna | cumple |
| G2 | transaction_date en [2025-06-01, 2026-06-01) | 2025-06-01 00:00:16 → 2026-05-31 23:57:20; fuera: 0 | cumple |
| G3 | transactions.customer_id = dueño del producto (join) | 0 filas distintas | cumple |
| G4 | transaction_labels 1:1 con gold.transactions | sin etiqueta: 0; etiqueta sin transacción: 0 | cumple |
| G5 | customer_profile 1 fila por cliente; transactions_enriched 1 por transacción | profile 150000 (únicos 150000) vs customers 150000; enriched 1477723 (únicos 1477723) vs transactions 1477723 | cumple |

| Tabla | Ruta (bajo data/) | Filas | Columnas | sha256 |
|---|---|---:|---:|---|
| `customers` | `gold/customers.parquet` | 150,000 | 32 | `a6ad9e0e3d01` |
| `products` | `gold/products.parquet` | 400,000 | 22 | `a05d6177c7b1` |
| `transactions` | `gold/transactions.parquet` | 1,477,723 | 33 | `37296dbfec9b` |
| `complaints` | `gold/complaints.parquet` | 67,095 | 36 | `6e4a5db4744f` |
| `transaction_labels` | `gold_eval/transaction_labels.parquet` | 1,477,723 | 2 | `96194cdaa295` |
| `transactions_enriched` | `gold/transactions_enriched.parquet` | 1,477,723 | 33 | `15d74f2f8efa` |
| `customer_profile` | `gold/customer_profile.parquet` | 150,000 | 14 | `39213080a40f` |

## 3. Checks con conteos

Violaciones = filas (o archivos, en SCH-01) que fallan el check; denominador = filas donde el check aplica. La última columna es la cifra del EDA para el mismo check (`outputs/tables/01_*.csv`, documentada en `docs/eda/data_quality.md` §B–C).

| ID | Tabla | Check | Descripción | Violaciones | Denominador | % | Acción | EDA (violaciones / denominador) |
|---|---|---|---|---:|---:|---:|---|---|
| DUP-01 | `customers` | duplicado exacto | filas idénticas en todas las columnas del contrato | 0 | 150,000 | 0% | se conserva una | — |
| DUP-02 | `customers` | versiones de PK | misma PK con contenido distinto (upsert) | 0 | 150,000 | 0% | gana process_date / carga más reciente | — |
| NUL-01 | `customers` | nulo en obligatoria | filas con alguna columna obligatoria nula | 0 | 150,000 | 0% | cuarentena (contrato) | — |
| CAST-01 | `customers` | cast fallido | valores no nulos que no castean al tipo del contrato | 0 | 150,000 | 0% | queda nulo; cuarentena si es obligatoria | — |
| CON-01 | `customers` | viola el contrato | filas que fallan algún check pandera | 0 | 150,000 | 0% | silver/_quarantine/ | — |
| LBL-01 | `customers` | etiqueta inconsistente | country: Mexico → México | 0 | 74,907 | 0% | se normaliza en silver | — |
| SCH-01 | `customers` | cambio de schema | archivos cuyo header difiere del contrato | 0 | 1 | 0% | alias declarado o columna solo en bronze | — |
| DUP-01 | `products` | duplicado exacto | filas idénticas en todas las columnas del contrato | 0 | 400,000 | 0% | se conserva una | — |
| DUP-02 | `products` | versiones de PK | misma PK con contenido distinto (upsert) | 0 | 400,000 | 0% | gana process_date / carga más reciente | — |
| NUL-01 | `products` | nulo en obligatoria | filas con alguna columna obligatoria nula | 0 | 400,000 | 0% | cuarentena (contrato) | — |
| CAST-01 | `products` | cast fallido | valores no nulos que no castean al tipo del contrato | 0 | 400,000 | 0% | queda nulo; cuarentena si es obligatoria | — |
| CON-01 | `products` | viola el contrato | filas que fallan algún check pandera | 0 | 400,000 | 0% | silver/_quarantine/ | — |
| SCH-01 | `products` | cambio de schema | archivos cuyo header difiere del contrato | 0 | 1 | 0% | alias declarado o columna solo en bronze | — |
| DUP-01 | `transactions` | duplicado exacto | filas idénticas en todas las columnas del contrato | 0 | 1,551,365 | 0% | se conserva una | — |
| DUP-02 | `transactions` | versiones de PK | misma PK con contenido distinto (upsert) | 0 | 1,551,365 | 0% | gana process_date / carga más reciente | — |
| NUL-01 | `transactions` | nulo en obligatoria | filas con alguna columna obligatoria nula | 0 | 1,551,365 | 0% | cuarentena (contrato) | — |
| CAST-01 | `transactions` | cast fallido | valores no nulos que no castean al tipo del contrato | 0 | 1,551,365 | 0% | queda nulo; cuarentena si es obligatoria | — |
| CON-01 | `transactions` | viola el contrato | filas que fallan algún check pandera | 0 | 1,551,365 | 0% | silver/_quarantine/ | — |
| LBL-01 | `transactions` | etiqueta inconsistente | transaction_country: Mexico → México | 14,070 | 752,633 | 1.869% | se normaliza en silver | — |
| SCH-01 | `transactions` | cambio de schema | archivos cuyo header difiere del contrato | 0 | 383 | 0% | alias declarado o columna solo en bronze | — |
| DUP-01 | `complaints` | duplicado exacto | filas idénticas en todas las columnas del contrato | 0 | 67,095 | 0% | se conserva una | — |
| DUP-02 | `complaints` | versiones de PK | misma PK con contenido distinto (upsert) | 0 | 67,095 | 0% | gana process_date / carga más reciente | — |
| NUL-01 | `complaints` | nulo en obligatoria | filas con alguna columna obligatoria nula | 0 | 67,095 | 0% | cuarentena (contrato) | — |
| CAST-01 | `complaints` | cast fallido | valores no nulos que no castean al tipo del contrato | 0 | 67,095 | 0% | queda nulo; cuarentena si es obligatoria | — |
| CON-01 | `complaints` | viola el contrato | filas que fallan algún check pandera | 0 | 67,095 | 0% | silver/_quarantine/ | — |
| SCH-01 | `complaints` | cambio de schema | archivos cuyo header difiere del contrato | 0 | 1,097 | 0% | alias declarado o columna solo en bronze | — |
| WIN-01 | `transactions` | fuera de la ventana | transaction_date fuera de [2025-06-01, 2026-06-01) en lo leído | 73,642 | 1,551,365 | 4.747% | queda en silver, no pasa a gold (R1) | — |
| FK-01 | `products` | FK huérfana | customer_id sin fila en customers | 0 | 400,000 | 0% | flag en gold | — |
| FK-02 | `transactions` | FK huérfana | customer_id resuelto (dueño del producto) sin fila en customers | 0 | 1,477,723 | 0% | flag en gold | — |
| FK-03 | `transactions` | FK huérfana | product_id sin fila en products | 0 | 1,477,723 | 0% | flag en gold | — |
| FK-04 | `complaints` | FK huérfana | customer_id sin fila en customers | 0 | 67,095 | 0% | flag en gold | — |
| FK-05 | `complaints` | FK huérfana | affected_product_id sin fila en products | 0 | 44,570 | 0% | flag en gold | — |
| OWN-01 | `transactions` | FK a producto de otro cliente | el customer_id del archivo no es el dueño del producto | 0 | 1,477,723 | 0% | gold usa el dueño (R2); flag para auditoría | — |
| OWN-02 | `complaints` | FK a producto de otro cliente | affected_product_id pertenece a otro cliente | 44,570 | 44,570 | 100% | flag en gold; la capa de servicio no lo muestra | — |
| FUT-01 | `customers` | fecha futura | last_updated posterior al día de carga del archivo | 5,957 | 150,000 | 3.971% | flag en gold | — |
| FUT-02 | `products` | fecha futura | last_updated posterior al día de carga del archivo | 15,939 | 400,000 | 3.985% | flag en gold | — |
| FUT-03 | `transactions` | fecha futura | transaction_date posterior al día de carga del archivo | 0 | 1,477,723 | 0% | flag en gold | — |
| FUT-04 | `complaints` | fecha futura | creation_date posterior al día de carga del archivo | 0 | 67,095 | 0% | flag en gold | — |
| ORD-01 | `transactions` | transacción antes de la apertura | transaction_date anterior a products.opening_date | 100,659 | 1,477,723 | 6.812% | flag en gold | — |
| LATE-01 | `transactions` | llegada tardía | process_date − transaction_date > 0 días | 0 | 1,477,723 | 0% | flag en gold; alerta de frescura | — |
| LATE-02 | `complaints` | llegada tardía | process_date − creation_date > 0 días | 0 | 67,095 | 0% | flag en gold; alerta de frescura | — |

Sin comparación con el EDA en este repo: `outputs/tables/` quedó en el repo del EDA, donde el mismo pipeline sobre el dataset completo reproduce las cifras de `data_quality.md`. Aquí `transactions` cubre solo la ventana de 12 meses, así que sus conteos no son comparables con el EDA.

## 4. Contratos de schema de silver (pandera)

Contratos en `data/pipeline/contracts.py` (versión v1): columnas, tipos, obligatorias, PK única y dominios (enums y rangos observados en el EDA). Una columna del archivo que no está en el contrato se conserva en bronze y no pasa a silver. Un renombre solo se acepta si está declarado como alias.

| Tabla | Columnas | Obligatorias | Reglas | Filas validadas | En cuarentena | Fallas (columna: check, filas) | Columnas fuera del contrato | Alias usados (filas) |
|---|---:|---:|---:|---:|---:|---|---|---|
| `customers` | 27 | 7 | 18 | 150,000 | 0 | ninguna | — | — |
| `products` | 17 | 6 | 14 | 400,000 | 0 | ninguna | — | — |
| `transactions` | 22 | 9 | 23 | 1,551,365 | 0 | ninguna | — | — |
| `complaints` | 27 | 8 | 20 | 67,095 | 0 | ninguna | — | — |


## 5. Llegadas tardías y rezago

Rezago = `process_date − fecha del evento` en días. Positivo = llegada tardía (flag `qc_late_arrival`). Un rezago de −1 no es un error: el día operativo del archivo corta a las 06:00 u 08:00 (`data_quality.md` §B4).

| Tabla | Filas | Tardías (> 0 d) | Rezago máx. | Distribución del rezago | Partición ≠ process_date |
|---|---:|---:|---:|---|---:|
| `transactions` | 1,551,365 | 0 | 0 | -1 d: 388,071, 0 d: 1,163,294 | 0 |
| `complaints` | 67,095 | 0 | 0 | -1 d: 22,585, 0 d: 44,510 | 0 |

## 6. Qué cambió respecto de la corrida anterior

Primera corrida en este directorio: no hay versión anterior con qué comparar.

## 7. Fixture `late_arrival`: llegadas tardías, cambio de schema y contrato de gold

> **FIXTURE, datos sintéticos de prueba (no salen del dataset).** El dataset real no tiene llegadas tardías ni evolución de schema (`data_quality.md` §B4, §B6), así que la frescura se demuestra con dos entregas etiquetadas en `data/fixtures/late_arrival/` (IDs `FX-`). El pipeline las procesa con el mismo código que la corrida real, en `data/_fixture_run/`.

- **delivery_1** (entregada 2026-05-17T23:00:00-05:00, gold v1, contrato 5/5 reglas): Carga inicial con problemas de calidad conocidos: 1 duplicado exacto, 2 etiquetas Mexico, 1 transacción antes de la apertura, 1 transacción con customer_id que no es el dueño del producto (gold lo resuelve al dueño), FK huérfanas (1 transacción, 1 complaint), 1 complaint con producto de otro cliente, fechas futuras (1 customer, 1 product), 1 complaint sin category y 1 evento de 2025-05-31 fuera de la ventana.
- **delivery_2** (entregada 2026-05-21T09:00:00-05:00, gold v2, contrato 5/5 reglas): Llegadas tardías y cambio de schema: re-entrega del snapshot de customers (1 update, 1 insert), re-entrega de la partición del 16 (sin el duplicado, +1 fila) y partición nueva del 20 con schema v2 (txn_country renombrada, merchant_mcc nueva), 3 eventos del 12–14 de mayo y la corrección de FX-TRX-0008 (Pending → Approved).

### Qué cambió de delivery_1 a delivery_2

**Archivos**

| Cambio | Archivo | Filas antes | Filas ahora |
|---|---|---:|---:|
| nuevo | `transactions/year=2026/month=05/day=20/transactions_20260520.csv` | — | 5 |
| re-entregado (md5 distinto) | `customers/customers.csv` | 5 | 6 |
| re-entregado (md5 distinto) | `transactions/year=2026/month=05/day=16/transactions_20260516.csv` | 5 | 5 |

**Cambio de schema** (header del archivo vs contrato)

| Archivo | Columnas nuevas | Columnas faltantes | Renombradas |
|---|---|---|---|
| `transactions/year=2026/month=05/day=20/transactions_20260520.csv` | `merchant_mcc` | — | `txn_country` → `transaction_country` |

Manejo: el alias declarado alimenta la columna canónica (`txn_country->transaction_country`: 5 filas); la columna nueva queda solo en bronze (`merchant_mcc`) hasta que el contrato suba de versión. Ninguna fila se pierde por el cambio.

**Llegadas tardías**

5 transacciones con rezago positivo (máximo 349 días). Distribución: 0 d: 10, 4 d: 1, 6 d: 1, 7 d: 1, 8 d: 1, 349 d: 1. Quedan en gold con `qc_late_arrival = true`, y la corrección de una transacción ya cargada entra como upsert (DUP-02: gana el `process_date` más reciente).

**Checks que cambiaron**

| ID | Tabla | Check | delivery_1 | delivery_2 |
|---|---|---|---:|---:|
| DUP-01 | `transactions` | duplicado exacto | 1 | 0 |
| DUP-02 | `transactions` | versiones de PK | 0 | 1 |
| LBL-01 | `transactions` | etiqueta inconsistente | 2 | 3 |
| SCH-01 | `transactions` | cambio de schema | 0 | 1 |
| LATE-01 | `transactions` | llegada tardía | 0 | 4 |

**Gold**

| Tabla | Insertadas | Actualizadas | Borradas | Sin cambio |
|---|---:|---:|---:|---:|
| `customers` | 1 | 1 | 0 | 4 |
| `products` | 0 | 0 | 0 | 6 |
| `transactions` | 5 | 1 | 0 | 8 |
| `complaints` | 0 | 0 | 0 | 4 |
| `transaction_labels` | 5 | 0 | 0 | 9 |
| `transactions_enriched` | 5 | 3 | 0 | 6 |
| `customer_profile` | 1 | 4 | 0 | 1 |

Versión v1 → v2; cambiaron: customers, transactions, transaction_labels, transactions_enriched, customer_profile.

**Contra lo esperado** (`fixture.json` → `expected`): 98 de 98 conteos coinciden.

## 8. Nulos por columna (silver)

Solo columnas con nulos. Obligatorias en negrita (deben ser 0). Nulos esperables y aleatorios según `data_quality.md` §B2.

- `customers` (150,000 filas): `email` 1.989%, `mobile_phone` 3.138%, `landline_phone` 50.035%, `address` 4.913%, `postal_code` 10.029%, `detected_accent` 29.878%, `credit_score` 14.995%, `estimated_monthly_income` 20.022%, `occupation` 10.026%, `marital_status` 7.97%, `education_level` 11.968%
- `products` (400,000 filas): `credit_limit` 68.671%, `interest_rate` 10.017%, `expiration_date` 66.71%, `days_past_due` 68.662%, `last_transaction_date` 23.569%
- `transactions` (1,551,365 filas): `transaction_category` 60.904%, `amount_usd` 57.358%, `branch_id` 68.606%, `merchant_name` 76.785%, `merchant_category` 76.776%, `transaction_city` 10%, `response_code` 4.99%, `fraud_score` 20.047%, `latitude` 80.641%, `longitude` 80.643%
- `complaints` (67,095 filas): `subcategory` 9.983%, `affected_product_id` 33.572%, `related_branch_id` 71.417%, `origin_interaction_id` 100%, `claimed_amount` 67.582%, `currency` 67.545%, `assigned_agent_id` 34.451%, `assignment_date` 34.471%, `first_response_date` 39.112%, `resolution_date` 77.123%, `closing_date` 96.302%, `resolution_days` 77.103%, `resolution` 77.182%, `compensation_granted` 93.083%, `resolution_satisfaction` 96.298%

## Cómo se reproduce

```bash
make setup     # venv + dependencias + pipeline desde S3 (.env) + fixture + este reporte
make pipeline  # solo la corrida real (SOURCE=local para usar un espejo local en data/, sin red)
make fixture   # solo el fixture late_arrival
make report    # solo este archivo
make test      # pytest, sin red
```
