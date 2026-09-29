# Contrato del gold — qué lee el agente y qué no

> Para David (pipeline). El agente no lee bronze ni silver: solo `gold/`. Todo lo que está aquí lo consumen las
> tools por `customer_id` de sesión con DuckDB sobre Parquet. Lo "masticado" son las tablas derivadas de la
> sección 3 y las fixtures de la sección 4. Versionar con `manifest.json`.

## 0. Reglas generales
- Formato: Parquet, una carpeta por tabla en `data/gold/<tabla>/`, particionado solo donde se indica.
- Claves: `customer_id`, `product_id`, `transaction_id`, `case_id` son strings; nunca se reescriben.
- Fechas en UTC como `TIMESTAMP`; el "día operativo" se resuelve en el agente, no en gold.
- Países normalizados: `MX`, `CO`, `AR` (el `México`/`Mexico` se arregla en silver).
- **`is_fraud` no va a ninguna tabla que lean las tools.** Vive solo en `gold_eval/` (sección 5). Si el agente
  pudiera leerla, la evaluación sería leakage y el bloqueo "adivinaría" la etiqueta.
- Ningún dato de credenciales, ni columnas del diccionario que no se usen (menos es más).
- `manifest.json`: versión, fecha, filas por tabla, hash por archivo, rango de fechas, checks aplicados con conteos.

## 0b. Particiones (una sola vez, en gold; todo lo demás cuelga de aquí)
- `customers.split` = `hash(customer_id) mod 10` → `train` (0–6), `dev` (7), `heldout` (8–9). Se propaga a
  `products`, `transactions`, `demo_customers`, `demo_transactions` y `demo_index.csv`.
- `transactions.periodo` = `fit` (2025-06-01 a 2026-02-28) o `measure` (2026-03-01 a 2026-05-31).
- Reglas: los casos de desarrollo usan solo clientes `dev`; el held-out del agente usa solo `heldout`; el modelo de
  fraude y la calibración de zonas se ajustan con `train` × `fit` y se miden en `heldout` × `measure`.
- Regla G6 (además de G1–G5): `gold_eval/` lo lee únicamente el harness; ninguna tool ni el agente tienen ruta a él.

## 1. Tablas base que leen las tools

| Tabla | Grano | Columnas | Quién la usa |
|---|---|---|---|
| `customers` | 1 fila por cliente | `customer_id`, `country`, `segment`, `customer_status`, `document_type`, `document_last4` (solo últimos 4, para el OTP mock), `preferred_language` (derivada: `es`; `pt` solo en fixtures) | identidad mock; reloj regulatorio (país) |
| `products` | 1 fila por producto | `product_id`, `customer_id`, `product_type` (Débito, Crédito, …), `product_status` (Active/Blocked/Closed/Suspended), `opening_date`, `currency`, `credit_limit` | `search_transaction` (pertenencia), `block_card`, `get_product_status` |
| `transactions` | 1 fila por transacción; partición `year/month` | `transaction_id`, `product_id`, `customer_id` (**resuelto por join**, no confiar en el crudo), `ts`, `amount`, `currency`, `amount_usd`, `merchant`, `channel`, `transaction_type`, `transaction_status` (Approved/Declined/Pending/Reversed), `response_code`, `fraud_score` (0–100 o NULL) | `search_transaction`, `get_fraud_score` (proveedor `dataset`) |
| `exchange_rates` | 1 fila por día y par | `date`, `source_currency`, `target_currency`, `rate` | mostrar montos en USD si hace falta; opcional |

Checks que deben haber pasado antes de escribir gold (los conteos van al manifest): duplicados eliminados;
`transactions.product_id` existe en `products`; `products.customer_id` existe en `customers`; `ts` no futura;
`ts >= products.opening_date` (las que no cumplen se marcan `flag_before_opening=true`, no se borran);
`fraud_score` entre 0 y 100 o NULL.

## 2. Estado mutable (NO va en gold)
`product_status` cambia cuando el agente bloquea. Gold es solo lectura: el bloqueo se escribe en la tabla de
estado del agente (`case_events` / `product_state` en DynamoDB o SQLite), y `get_product_status()` lee **primero**
el estado mutable y **después** el gold. David no tiene que hacer nada aquí; es para que quede claro.

## 3. Tablas derivadas ("lo masticado") que sí van en gold

| Tabla | Grano | Columnas | Para qué |
|---|---|---|---|
| `customer_profile` | 1 fila por cliente | `customer_id`, `country`, `segment`, `n_products_active`, `n_tx_90d`, `avg_amount_usd_90d`, `p95_amount_usd_90d`, `top_merchants_90d` (lista de 5), `usual_channels` (lista), `n_reversed_90d`, `n_declined_90d`, `last_tx_ts` | proveedor de score `reglas` (monto vs habitual, comercio conocido); contexto para el copiloto; segmento para métricas |
| `transactions_enriched` | 1 fila por transacción de los **últimos 12 meses** (no hace falta 3 años) | todo `transactions` + `amount_vs_p95` (ratio), `is_known_merchant` (bool), `hour_local`, `is_weekend`, `country_mismatch` (bool, si el comercio/canal sugiere otro país), `days_since_opening`, `same_merchant_count_7d`, `flag_before_opening` | `search_transaction` devuelve esto; features para el proveedor `reglas` y para el plan B `modelo` |
| `product_state_snapshot` | 1 fila por producto | `product_id`, `product_status`, `snapshot_ts` | punto de partida del estado mutable; el agente lo copia al arrancar |

## 4. Fixtures para demo y evaluación (curadas, van en gold)

| Tabla | Qué es | Cómo se arma |
|---|---|---|
| `demo_customers` | 30–50 clientes reales del dataset elegidos a mano: 3 países × 4 segmentos, con al menos 3 productos y actividad reciente; columna `demo_language` (`es` o `pt` asignado por nosotros, etiquetado como team-generated) | filtro + muestreo con semilla fija |
| `demo_transactions` | Para cada cliente demo, sus transacciones de los últimos 90 días **más** un conjunto marcado por zona: `expected_zone` (`alta` ≥ 50, `media` 30–49, `humano` < 30 o NULL), `escenario` (normal, ambiguo con 3 candidatas, monto alto, sin score, reversada) | selección con semilla fija; nada inventado: son transacciones reales del dataset |
| `demo_index.csv` | Tabla legible: `customer_id`, país, segmento, idioma, `split` (dev o heldout), `transaction_id`, monto, fecha, score, zona esperada, escenario | Datos 2 escribe los mensajes de los casos de eval a partir de esta tabla |

## 5. Solo para evaluación y analytics (fuera del alcance de las tools)

| Carpeta | Contenido | Quién lee |
|---|---|---|
| `gold_eval/transaction_labels` | `transaction_id`, `is_fraud`, `fraud_score` | solo el harness (calibración de zonas, plan B) |
| `gold_analytics/` | `complaints` (con categoría y reglas CMP-01/02/03 aplicadas), `interactions` (motivo, FCR, seguimiento, duración), `surveys` (unidas por `interaction_id`), `kpis_pitch.csv` (los números del pitch ya calculados) | `/analytics`, `/data`, slides |

## 6. Frescura y fixture de actualizaciones
- `data/fixtures/late_arrival/`: dos particiones de `transactions` que "llegan tarde" y un archivo con una
  columna nueva (`merchant_category`). El pipeline las procesa en una segunda corrida; el manifest v2 muestra el
  delta (filas nuevas, columna nueva, checks re-ejecutados). Etiquetado como fixture en el README.
- El agente declara en `/data` la versión del manifest que está usando.

## 7. Entregas mínimas por día
- **Mar 29:** `customers`, `products`, `transactions` (12 meses) en gold con `split` y `period` + manifest v1 + `make setup`. Con esto
  el agente ya corre EV-0001.
- **Mié 30:** `customer_profile`, `transactions_enriched`, `product_state_snapshot`, `demo_*`.
- **Jue 1:** `gold_eval/`, `gold_analytics/`, fixture de late arrival, manifest v2.
