# Calidad de datos — dataset LATAM Bank

> Documento autocontenido para el Project de claude.ai. Cada cifra lleva etiqueta (`[medido]` / `[supuesto]` /
> `[proyectado]`) y el archivo que la produce. `[medido]` = sale del dataset con la query indicada.
> Fuentes: `python scripts/s3_inventory.py`, `python -m eda.inventory` (fase 0), `python -m eda.quality` (fase 1).
> Tablas de salida en `outputs/tables/`, queries en `docs/eda/queries/`.
> Última actualización: 26 sep 2026 (fases 0, 1 y cierre en fase 7).

## Contexto
Dataset sintético de un banco ficticio (LATAM Bank) con clientes de México, Colombia y Argentina, 13 tablas,
rango 2023-06-17 → 2026-06-17. El diccionario oficial anuncia problemas de calidad intencionales: ~2% duplicados,
~5% nulos en campos opcionales, llegadas tardías, evolución de schema y huérfanos de FK. Este documento mide
cuáles están de verdad y dónde.

## A. Inventario (fase 0)

### A1. Formato, particiones y carga
- **100% CSV**, UTF-8 con BOM, sin Parquet ni comprimidos. 7,671 objetos, 5.35 GB `[medido]`
  (`00_inventory_files.csv`, `queries/00_s3_partition_coverage.sql` bloque 1).
- **Hechos** (transactions, interactions, transcripts, surveys, digital_events, complaints, campaign_sends):
  `data/<tabla>/year=YYYY/month=MM/day=DD/<tabla>_YYYYMMDD.csv`, un archivo por día, 1,097 días sin huecos
  `[medido]`. Excepción: `campaign_sends` arranca 2023-07-01 (14 días sin partición; probablemente de diseño)
  (`00_s3_partition_coverage.sql` bloque 2).
- **Dimensiones** (customers, products, branches, service_agents, marketing_campaigns, daily_exchange_rates): **un
  solo CSV plano**. El diccionario habla de `monthly_snapshot` / `full_snapshot`, pero no hay historia: es **una
  foto única al corte** `[medido]`. Consecuencia: `segment`, `credit_score`, `customer_status`, `product_status`,
  `days_past_due`, `current_balance`, `credit_limit` reflejan el estado final, no el del momento de cada contacto.
  **Riesgo de leakage para W2 (tarjetas) y W4 (crédito)**, y vacío para cualquier análisis point-in-time.
- **Sin `process_date` en la ruta**: la partición es `year/month/day`. `process_date` existe como **columna** dentro
  de los archivos de hechos `[medido]` (`00_column_types.csv`).
- **Carga única**: todos los objetos se subieron el 2026-08-31 entre 21:36 y 21:51 (hora Lima) `[medido]`
  (`00_s3_partition_coverage.sql` bloque 1). No hay entrega incremental real: las "llegadas tardías" que anuncia el
  diccionario están **simuladas dentro de los archivos** (diferencia entre `process_date`, fecha del evento y fecha
  de la partición), no en tiempos de llegada. Para demostrar manejo de updates hará falta un test fixture etiquetado.
- **Patrón semanal** (proxy por tamaño de archivo, antes de descargar): en interactions, sábado y domingo pesan
  ~75 KB vs ~148–150 KB de lunes a viernes; mes a mes el tamaño es estable (120–135 KB/día) `[medido]`
  (`00_s3_partition_coverage.sql` bloques 3 y 4). Se confirma con filas en la fase 1.

### A2. Conteos vs diccionario
Fuente: `00_row_counts.csv` (`eda/inventory.py` + `queries/00_row_counts.sql`) `[medido]`.

| Tabla | Filas | Diccionario | Ratio | Duplicados de PK |
|---|---:|---:|---:|---:|
| customers | 150,000 | 150,000 | 1.000 | 0 |
| products | 400,000 | 400,000 | 1.000 | 0 |
| branches | 350 | 350 | 1.000 | 0 |
| service_agents | 1,200 | 1,200 | 1.000 | 0 |
| marketing_campaigns | 200 | 200 | 1.000 | 0 |
| transactions | 4,425,008 | 5,000,000 | 0.885 | 0 |
| call_center_interactions | 686,296 | 800,000 | 0.858 | 0 |
| call_transcripts | 171,321 | 200,000 | 0.857 | 0 |
| satisfaction_surveys | 212,759 | 250,000 | 0.851 | 0 |
| digital_events | 15,620,994 | 10,000,000 | 1.562 | 0 |
| complaints | 67,095 | 80,000 | 0.839 | 0 |
| daily_exchange_rates | 13,164 | 3,000 | 4.388 | 0 |
| campaign_sends | no sincronizada | 2,000,000 | — | — |

- Las dimensiones cuadran exacto. Las tablas de hechos de atención traen ~14–16% menos filas que lo anunciado.
  Hipótesis `[supuesto]`: el generador fijó el total nominal y luego redujo los fines de semana a la mitad
  (5 días × 1 + 2 días × 0.5 = 6/7 = 0.857). Coincide muy bien con interactions y transcripts; peor con complaints
  (0.839) y transactions (0.885). Se verifica en la fase 1.
- `digital_events` trae 56% más filas y `daily_exchange_rates` 4.4 veces lo anunciado. No bloquea nada.
- **Cero duplicados de PK en todas las tablas.** El ~2% de duplicados anunciado no está en la clave primaria; se
  busca como duplicado de contenido (misma fila con distinto ID) en la fase 1.

### A3. Evolución de schema
- **Una sola firma de header por tabla** en los 1,097 archivos: mismas columnas y mismo orden de principio a fin
  `[medido]` (`00_schema_by_partition.csv`). No hay columnas que aparezcan o desaparezcan.
- La evolución anunciada, si existe, tendría que estar en los valores (formatos, escalas, etiquetas). Candidatos
  vistos en el inventario: `fraud_score` en escalas distintas (0.89 vs 25.02 en filas del mismo día), `México` vs
  `Mexico` en `transaction_country` (0.9% `Mexico`) e `ip_country` (6.6% `Mexico`) `[medido]`
  (`00_enum_values.csv`). Se cuantifican en la fase 1.

### A4. Enums reales vs diccionario
Fuente: `00_enum_vs_dictionary.csv` y `00_enum_values.csv` (`queries/00_enum_values.sql`) `[medido]`.

| Columna | Diccionario | Real | Nota |
|---|---|---|---|
| `products.product_type` | Checking, Savings, Credit Card, Debit Card, Personal Loan, Mortgage, Investme… | Cuenta Ahorro 30.1%, Tarjeta Crédito 25.0%, Cuenta Corriente 25.0%, Tarjeta Débito 10.0%, Préstamo Personal 5.0%, Préstamo Hipotecario 3.0%, Inversión 1.5%, **Seguro** 0.5% | en español; `Seguro` no documentado |
| `call_center_interactions.reason_category` | Transactional, Product, Technical, Commercial, Complaint | Transaccional 35.0%, Producto 22.0%, Queja 17.1%, Técnico 15.0%, Comercial 8.0%, **Retención** 3.0% | en español; `Retención` no documentado |
| `call_center_interactions.channel` | Phone, Web Chat, WhatsApp, Email, App | + **Web** 0.5% | Phone = 85.0% |
| `customers.document_type` | DNI, CURP, CC, CE, Pasaporte | sin **CURP** (DNI 69.8%) | clientes de México sin CURP |
| `products.currency`, `transactions.currency` | MXN, COP, ARS, USD | USD 55.1%, COP 27.0%, ARS 17.9%; **sin MXN** | complaints sí trae MXN (8.2%) |

Coinciden con el diccionario: `country`, `segment`, `product_status`, `agent_type`, `transaction_type`,
`transaction_status`, `survey_type`, `event_type`, `case_type`.

### A5. Campos derivados y de texto: menos información de la esperada
Fuente: `00_enum_values.csv`, `00_multivalue_values.csv` (`queries/00_multivalue_values.sql`) `[medido]`.

| Campo | Lo que se esperaba | Lo que hay |
|---|---|---|
| `contact_reason` | motivo granular | **idéntico a `reason_category`** (6 valores) |
| `call_transcripts.detected_intents` | intents multi-label | **un solo valor**: `consulta_general` (95.1%), resto nulo |
| `call_transcripts.detected_keywords` | keywords | 3 palabras (banco, cuenta, servicio) en distinto orden |
| `call_transcripts.main_topics` | temas | las mismas 6 categorías de `reason_category` |
| `call_transcripts.customer_text` | texto libre del cliente | **42 valores distintos**; 2 plantillas ("consultar el saldo de mi tarjeta de crédito" 30.1%, "saldo actual en mi cuenta de ahorros" 29.9%) |
| `call_transcripts.agent_text` | respuesta del agente | plantillas con placeholders **sin rellenar** (`{monto} {moneda}`, `{limite}`) |
| `call_transcripts.detected_language` | es | 100% `es` |
| `complaints.description` | relato del cliente | **5 plantillas** ("Queja relacionada con transactions/fees/technical/branch/service") |
| `complaints.resolution` | texto de resolución | 5 plantillas; 77.2% nulo |
| `complaints.origin_interaction_id` | FK a la interacción origen | **100% nulo** |
| `satisfaction_surveys.open_comments` | comentario libre | 13 frases fijas; 52.4% nulo |
| `satisfaction_surveys.nps_category` | Promoter/Passive/Detractor | **sin Promoter**: Detractor 21.2%, Passive 7.2%, nulo 71.6% |

Consecuencias:
- No hay texto real de cliente para entrenar ni para evaluar un clasificador de intención: el texto es de plantilla.
  Cualquier set de evaluación de lenguaje (incluido el portugués) tendrá que ser generado por el equipo y etiquetado
  como tal.
- La cadena "interaction → transcript → survey → complaint" del diccionario se corta en complaints: solo se pueden
  vincular por `customer_id` + ventana de tiempo, con la ambigüedad que eso implica.
- El mapeo a workflows (fase 3) no puede apoyarse en `contact_reason` ni en `detected_intents`. Señales disponibles:
  `reason_category`, `complaints.category/subcategory`, productos mencionados (`mentioned_products`,
  `affected_product_id`, `mentioned_entities.products`) cruzados con `product_type`.

### A6. Distribuciones uniformes (firma del generador)
`complaints.category` 5 × ~20%, `complaints.subcategory` 5 × ~18% (+10% nulo), `customers.gender` F/M/O 3 × ~33%,
`transcription_model` 4 × ~25%, `accepts_marketing` y `has_linked_app` 50/50 `[medido]` (`00_enum_values.csv`).
Señal de un generador con distribuciones uniformes e independientes: las métricas por workflow podrían no
diferenciarse (ver decisión 2 del plan: intervalos de confianza y criterio alternativo).

### A7. Lo que sí sirve para el reto
- **Portugués en agentes:** 129 de 1,200 agentes (10.75%) declaran portugués `[medido]`
  (`00_multivalue_values.csv`). El texto de clientes es 100% español.
- **`response_code`** con códigos ISO 8583 reales: 00 (87.4%), 14, 51, 05, 54 (~1.9% c/u), nulo 5.0% `[medido]`.
  Útil para W2 (declinaciones de tarjeta).
- **`digital_events`**: `Login` 15.6%, `Error` 2.3% de los eventos; `event_category=Authentication` 31.2% `[medido]`.
  Base del embudo "errores y logins antes de llamar".
- **`transactions.transaction_status`**: `Reversed` 1.0%, `Declined` 5.0%; `is_fraud` 0.098% `[medido]`.

## B. Calidad por tabla (fase 1)
Fuente: `python -m eda.quality` → `outputs/tables/01_*.csv`, queries `docs/eda/queries/01_*.sql`. Lectura sobre el
caché Parquet (`data/_cache/`), copia fiel del CSV con conteos verificados (`scripts/build_cache.py`).

### Resumen: lo anunciado vs lo medido
| Problema anunciado por el diccionario | Lo medido | Dónde |
|---|---|---|
| ~2% duplicados | **0 duplicados** en las 12 tablas: ni por PK, ni de contenido (misma fila con otro ID), ni re-entregados otro día. Tampoco con claves de negocio laxas | §B1 |
| ~5% nulos en campos opcionales | **Sí**: muchas columnas opcionales con ~5% (o ~10%, ~15%, ~20%) de nulos aleatorios, más nulos estructurales | §B2 |
| Huérfanos de FK "pequeño %" | **No es pequeño en tres FK**: 99.997% en `customers.registration_branch_id`, 99.8% en `service_agents.assigned_branch_id`, 99.4% en `mentioned_products`. Además, FK válidas que apuntan al producto **de otro cliente** (100% en complaints) | §B3 |
| Llegadas tardías | **No hay**: el rezago `process_date − fecha del evento` es 0 o −1 día (nunca positivo) | §B4 |
| Evolución de schema | **No hay** en headers (fase 0) ni deriva material en valores | §B6 |

Lo que **no** anunciaba y sí está: fechas futuras imposibles, textos de plantilla, escalas de encuesta truncadas,
`sla_breached` independiente de todo, moneda aleatoria en complaints, eventos antes de la apertura del producto,
coordenadas inválidas, etiquetas inconsistentes (`México`/`Mexico`).

### B1. Duplicados
- `dup_exact`, `dup_content_excl_pk` y `dup_content_excl_pk_process_date` = **0 en las 12 tablas** `[medido]`
  (`01_quality_summary.csv`, `queries/01_duplicates.sql`). Método: `count(*) − count(DISTINCT hash(columnas))`;
  validado inyectando 1,000 filas duplicadas en interactions (las detecta todas).
- Claves de negocio laxas `[medido]` (`01_business_key_checks.csv`, `queries/01_business_key_checks.sql`):
  0 repetidos en interactions (cliente, fecha-hora), transactions (producto, fecha-hora, monto) y (cliente, día, monto,
  tipo), complaints (cliente, fecha), customers (documento) y (nombre, apellido, nacimiento). 263 interacciones
  repiten (cliente, día, motivo, canal): clientes que contactan dos veces el mismo día, no duplicados.
- **Emails no únicos**: 79,930 clientes (54.4% de los 147,016 con email) comparten su email con al menos otro
  cliente; hay 91,289 emails distintos `[medido]` (`01_business_key_checks.csv`). El email no sirve como
  identificador de cliente ni como factor de identidad (relevante para el mock de autenticación del reto).
- Implicación: el pipeline debe tener el check de duplicados (lo evalúan), pero hoy no hay nada que deduplicar.

### B2. Nulos
Fuente: `01_null_rates.csv` (`queries/01_null_rates.sql`) y `01_null_patterns.csv` (`queries/01_null_patterns.sql`)
`[medido]`.
- **Columnas obligatorias sin nulos** en 11 de 12 tablas. Excepción: `digital_events.customer_id` 24.0% nulo,
  uniforme en todos los `event_type` (23.96–24.08%): nulos aleatorios, no sesiones anónimas previas al login. Esos
  eventos no se pueden vincular a una llamada.
- **Nulos aleatorios "de diseño"**: bloques de columnas con ~5% (`response_code`, `audio_quality`, `ip_address`,
  `amount_usd` en COP/ARS, `credit_limit` y `days_past_due` en productos de crédito), ~10% (`postal_code`,
  `occupation`, `mentioned_entities`), 15% (`credit_score`), 20% (`estimated_monthly_income`, `fraud_score`),
  ~30% (`customer_detected_accent`). Uniformes entre segmentos, canales y categorías.
- **Nulos estructurales** (esperables, no son defecto):
  - `wait_time_seconds` existe **solo para `Inbound Call`** (0% nulo); es 100% nulo en Outbound Call, Chat, Email y
    Video. El proxy de espera de la fase 6 solo vale para llamadas entrantes (70.0% de las interacciones,
    `00_enum_values.csv`).
  - `credit_limit` / `days_past_due`: 100% nulos fuera de Tarjeta Crédito y préstamos.
  - Campos de resolución de complaints (`resolution_date`, `resolution_days`, `resolution`): 77% nulos, porque el
    70% de los casos está abierto (Open, In Process).
  - `amount_usd`: 100% nulo cuando `currency = USD` (ver §B5).
- **Relevante para W4:** `credit_score` 15.0% nulo y `estimated_monthly_income` 20.0% nulo, aleatorios por segmento.
  Un flujo de elegibilidad tendrá que manejar datos faltantes (el reto lo pide explícitamente).

### B3. Huérfanos de FK y pertenencia al cliente
Fuente: `01_fk_orphans.csv` (`queries/01_fk_orphans.sql`, `01_fk_orphans_mentioned_products.sql`) y
`01_consistency_checks.csv` (`queries/01_consistency_checks.sql`) `[medido]`.

| Relación | Resultado |
|---|---|
| interactions, transcripts, surveys, complaints, transactions, digital_events → `customers` | 0 huérfanos |
| transactions → `products` | 0 huérfanos; el `customer_id` de la transacción es **siempre** el dueño del producto (C12 = 0) |
| transcripts / surveys → `call_center_interactions` | 0 huérfanos; mismo cliente, mismo agente, encuesta posterior a la interacción, 1 transcript y 1 encuesta como máximo por interacción (C01–C11 = 0) |
| `customers.registration_branch_id` → `branches` | **99.997% huérfanos**: 150,000 IDs distintos, uno por cliente, casi ninguno existe |
| `service_agents.assigned_branch_id` → `branches` | **99.76% huérfanos** (831 de 833 no nulos) |
| `call_center_interactions.mentioned_products` → `products` | **99.35% huérfanos** (545,118 de 548,680 IDs mencionados); los 3,562 que existen pertenecen a **otro cliente** (C16 = 100%) |
| `complaints.affected_product_id` → `products` | 0 huérfanos, pero el producto pertenece a **otro cliente** en el 100% de los casos (C15) |
| `digital_events.product_id` → `products` | 0 huérfanos, pero de **otro cliente** en el 99.999% (C20) |
| `complaints.origin_interaction_id` | 100% nulo |

Consecuencias:
- **La cadena interaction → transcript → survey es sólida y se puede usar para el scorecard.** Complaints queda
  aislada: no se vincula ni a la interacción ni a un producto del propio cliente. Solo por `customer_id` + tiempo.
- **No hay forma confiable de saber el producto de una interacción o de un complaint** (los IDs de producto
  mencionados no existen o son de otro cliente). El mapeo a workflows por producto (fase 3) queda limitado a
  transactions → products, que sí es consistente.
- `branches` solo se une bien desde products, transactions y complaints.
- Para el reto ("aislamiento de registros por cliente"): un tool que confíe en `affected_product_id` o en
  `mentioned_products` mostraría datos de otro cliente. El check de pertenencia debe estar en la capa de servicio.

### B4. Llegadas tardías
Fuente: `01_late_arrivals.csv`, `01_late_arrivals_hist.csv` (`queries/01_late_arrivals.sql`,
`01_late_arrivals_hist.sql`) `[medido]`.
- `partition_date = process_date` en el 100% de las filas de las 6 tablas de hechos.
- `lag_days = process_date − fecha del evento` toma **solo 0 o −1** (encuestas: 0, −1, −2). p50 = p95 = p99 = 0
  (encuestas p50 = −1). **Ningún registro llega tarde.**
- El −1 (25% en transactions y digital_events, 33% en interactions, transcripts y complaints) aparece porque el
  evento cae en la madrugada del día siguiente al `process_date`: los eventos de un archivo van de las 08:00 a las
  08:00 del día siguiente en interactions y complaints, y de 06:00 a 06:00 en transactions y digital_events `[medido]`
  (`01_day_boundary.csv`, `queries/01_day_boundary.sql`). Hipótesis `[supuesto]`: el "día" del generador está corrido
  de la medianoche (zona horaria o día operativo). En encuestas, el −1/−2 es porque la encuesta se responde después de la interacción y se
  archiva con la fecha de la interacción.
- Eventos con fecha posterior al fin de la ventana (2026-06-18 00:00): 0.01–0.07% por tabla (R01, R16, R20, R41,
  R80), por el mismo corrimiento.
- Implicación: la política de frescura y el manejo de late arrivals no se pueden demostrar con estos datos. Hace falta
  un test fixture etiquetado (lo prevé el reto).

### B5. Rangos imposibles y reglas de negocio
Fuente: `01_range_checks.csv` (`queries/01_range_checks.sql`) y consultas complementarias `[medido]`.

| Tabla | Hallazgo | Violaciones / denominador |
|---|---|---|
| customers | `last_updated` posterior a la carga a S3 (2026-08-31): **fecha futura imposible** (hasta 2027-06-15) | 5,957 / 150,000 (3.97%) |
| customers | `last_updated` posterior al fin del dataset | 9,316 / 150,000 (6.21%) |
| customers | menor de 18 años al registrarse | 3,106 / 150,000 (2.07%) |
| customers | prefijo del celular no coincide con el país | 72,548 / 145,293 (49.9%) |
| products | `last_updated` posterior a la carga a S3 (fecha futura imposible) | 15,939 / 400,000 (3.99%) |
| products | producto abierto antes del registro del cliente (C17) | 199,596 / 400,000 (49.9%) |
| products | Tarjeta Crédito sin `credit_limit` | 5,059 / 100,102 (5.05%) |
| transactions | transacción anterior a la apertura del producto (C13) | 827,610 / 4,425,008 (18.7%) |
| transactions | `amount_usd` nulo cuando `currency = USD` | 2,437,979 / 2,437,979 (100%) |
| transactions | `amount_usd` nulo en COP/ARS | 99,477 / 1,987,029 (5.0%) |
| transactions | `transaction_country = 'Mexico'` en vez de `'México'` | 40,515 / 2,146,309 (1.9%) |
| digital_events | `ip_country = 'Mexico'` en vez de `'México'` | 1,038,174 / 7,281,067 (14.3%) |
| complaints | Resolved/Closed sin `resolution_date` | 772 / 16,121 (4.8%) |
| complaints | `compensation_granted` > `claimed_amount` | 62 / 1,453 (4.3%) |
| complaints | `claimed_amount` sin `currency` | 1,040 / 21,751 (4.8%) |
| branches | coordenadas cerca de (0, 0) | 167 / 350 (47.7%) |
| branches | longitud ≥ 0 (imposible en MX/CO/AR) | 83 / 350 (23.7%) |
| call_transcripts | `agent_text` / `full_text` con placeholders sin rellenar (`{monto}`, `{moneda}`, …) | 171,321 / 171,321 (100%) |

Sin violaciones: montos ≤ 0, `resolution_days` negativos o incoherentes con las fechas (R28 = 0), orden de fechas en
complaints, `credit_score` fuera de 300–850, `sentiment_score` fuera de [−1, 1] o con signo opuesto a la etiqueta,
`fraud_score` fuera de 0–100, `accent_confidence` fuera de [0, 1].

**Consistencia de `amount_usd`**: donde existe, coincide con el tipo de cambio del día (desvío p50 ≈ 1%, p95 ≈ 2%,
0 casos > 5%) `[medido]` (`01_fx_consistency.csv`, `queries/01_fx_consistency.sql`).

**Moneda por país** `[medido]` (`01_currency_by_country.csv`, `queries/01_currency_by_country.sql`):
- products y transactions: México 100% USD (nunca MXN); Colombia 90% COP / 10% USD; Argentina 90% ARS / 10% USD.
- complaints: `currency` **independiente del país** (un cliente argentino reclama en MXN, COP, USD o ARS con ~8% cada
  una; 67.5% nulo). `claimed_amount` no es comparable entre casos sin normalizar la moneda, y la moneda no es creíble.

**Escalas de encuesta** `[medido]` (`01_survey_scale_usage.csv`, `queries/01_survey_scale_usage.sql`):

| Tipo | Valores observados | Distribución |
|---|---|---|
| CSAT | 1–4 (nunca 5) | 1: 3.5% · 2: 27.9% · 3: 57.3% · 4: 11.3% |
| CES | 1–4 | 1: 3.5% · 2: 27.8% · 3: 57.2% · 4: 11.6% (**la misma distribución que CSAT**) |
| NPS | 2–7 (nunca 0, 1, 8, 9, 10) | 2–4: ~7.7% c/u · 5–7: ~25.7% c/u |

- NPS sin promotores: con la definición estándar (Detractor 0–6, Passive 7–8, Promoter 9–10), el 74.5% de las
  respuestas NPS son detractores y el 25.5% pasivos, así que el NPS de todo el banco sería **−74.5** `[medido]`
  (`01_survey_scale_usage.csv`). Nadie responde 8–10.
- CSAT y CES generados con la misma distribución: no se pueden interpretar como constructos distintos.
- Refuerza la decisión 4 del plan (no promediar entre tipos) y agrega otra: **los valores absolutos de las encuestas no
  son interpretables como satisfacción real**; solo sirven comparaciones relativas entre grupos, con IC.

**SLA de complaints** `[medido]` (`01_complaints_sla_consistency.csv`, `queries/01_complaints_sla_consistency.sql`):
`sla_breached` ≈ 20% **en todos los cortes**: por días de resolución (1–5 días: 19.95%; 26–30 días: 19.13%), por estado
(Open 19.6%, Resolved 19.7%, Rejected 21.4%), por prioridad (Critical 19.2%, Low 20.1%) y por tipo de caso. **No depende
del tiempo de resolución.** "% SLA incumplido" no mide desempeño del proceso en este dataset.

### B6. Evolución de schema en valores
Fuente: `01_null_drift.csv` (`queries/01_null_rates.sql` agrupado por mes) `[medido]`.
- Criterio: un mes es anómalo si su tasa de nulos se aparta de la global más de 4 desviaciones binomiales.
- 5 de 134 columnas superan el umbral: 4 en digital_events (`app_version`, `browser`, `customer_id`, `ip_city`) con
  rango mensual ≤ 1.6 pp (detectable solo por el volumen: 15.6M eventos / 37 meses ≈ 420k/mes, `00_row_counts.csv`) y `complaints.subcategory` (z = 4.2, en el
  límite). Ninguna muestra un escalón que indique un cambio de schema. `[supuesto]`: las variaciones de digital_events
  vienen de la mezcla mensual de canales (web vs app).
- Conclusión: **no hay evolución de schema material**, ni en headers (fase 0) ni en valores. Candidatos de "schema
  drift" de etiquetas: `México`/`Mexico` (§B5), presente todo el período.

### B7. Volumen por día de la semana
Fuente: `01_rows_by_weekday.csv` (`queries/01_rows_by_weekday.sql`) `[medido]`.
- Sábado y domingo tienen **la mitad** del volumen de un día hábil en interactions (0.50), transcripts (0.50), surveys
  (0.50) y complaints (0.50); transactions 0.60; digital_events 0.66.
- Esto explica la diferencia con el diccionario de la fase 0: con fines de semana a 0.5035, el volumen esperado es
  (5 + 2 × 0.5035) / 7 = 0.858 del nominal, y interactions tiene 0.858; transactions predice 0.886 y tiene 0.885.
  Complaints (0.839 vs 0.858 predicho) queda ~2% por debajo sin explicación. `[proyectado]` sobre el `[supuesto]` de que
  el diccionario reporta el volumen nominal sin la reducción de fin de semana.

### B8. Cobertura de transcripts y encuestas
Fuente: `01_coverage.csv` (`queries/01_coverage_transcripts_surveys.sql`) `[medido]`.
- **24.96%** de las interacciones tiene transcript; el flag `has_transcript` coincide exactamente con la existencia de
  la fila (C01 = C02 = 0). **31.0%** tiene encuesta.
- La cobertura es **plana** por `reason_category` (24.9–25.2%), canal (24.7–26.3%) y tipo de interacción
  (24.7–25.2%); la de encuestas también (30.6–31.8%). No hay sesgo de cobertura en esas dimensiones. El sesgo por
  workflow se mide en la fase 3 (decisión 3 del plan), pero con esta uniformidad es poco probable.
- Recordatorio (§A5): aunque la cobertura es buena, el contenido de los transcripts es de plantilla (546 `full_text`,
  42 `customer_text` y 42 `agent_text` distintos en 171,321 filas; `01_business_key_checks.csv`) y `detected_intents`
  tiene un solo valor.

### B9. Checks que el pipeline de la solución debería tener
Derivados de lo anterior, para el bloque de data engineering del pitch:
1. Unicidad de PK y duplicados de contenido (hoy 0; el check debe existir igual).
2. Pertenencia al cliente en toda FK a producto (`affected_product_id`, `mentioned_products`, `digital_events.product_id`).
3. Fechas futuras (`last_updated` > fecha de carga) y orden temporal (transacción ≥ apertura del producto).
4. Normalización de etiquetas (`México`/`Mexico`) y de moneda (`amount_usd` para USD = `amount`).
5. Escalas de encuesta por tipo, sin promediar entre tipos.
6. Rezago `process_date` vs fecha del evento, con alerta si aparece rezago positivo (hoy no hay).
7. Placeholders sin rellenar en texto (`{…}`) antes de usar transcripts como contexto de un LLM.

## C. Evidencia de data engineering para el pitch
Los problemas reales del dataset (distintos de los que anuncia el diccionario) son exactamente los checks que un
pipeline de producción tendría que hacer. Cada uno con su cifra y su query `[medido]`:

| # | Problema real | Cifra | Query | Check de producción que lo detecta |
|---|---|---|---|---|
| 1 | FK válida que apunta al producto **de otro cliente** | `complaints.affected_product_id` 100% (44,570/44,570); `digital_events.product_id` 99.999% | `01_consistency_checks.sql` (C15, C20) | Pertenencia al cliente en cada FK antes de mostrar o actuar (aislamiento por cliente) |
| 2 | FK huérfana en listas | `mentioned_products` 99.35% (545,118/548,680 IDs) | `01_fk_orphans_mentioned_products.sql` | Integridad referencial sobre campos multivalor |
| 3 | FK falsa a sucursales | `customers.registration_branch_id` 99.997%, `service_agents.assigned_branch_id` 99.76% | `01_fk_orphans.sql` | Integridad referencial en dimensiones |
| 4 | Fechas futuras imposibles | `last_updated` > fecha de carga: 3.97% de customers, 3.99% de products | `01_range_checks.sql` (R52, R61) | `fecha ≤ fecha de ingesta` |
| 5 | Orden temporal violado | 18.7% de transacciones antes de la apertura del producto; 49.9% de productos antes del registro del cliente | `01_consistency_checks.sql` (C13, C17) | Orden de eventos por entidad |
| 6 | Día operativo corrido | los archivos diarios van de 08:00 a 08:00 (interactions, complaints) y de 06:00 a 06:00 (transactions, digital_events); 25–33% de eventos con fecha del día siguiente a `process_date` | `01_day_boundary.sql`, `01_late_arrivals.sql` | Definir el corte de día explícito en el contrato; no asumir medianoche |
| 7 | Etiquetas inconsistentes | `Mexico` vs `México`: 1.9% en transactions, 14.3% en digital_events | `01_range_checks.sql` (R47, R82) | Normalización de dominios (enums) |
| 8 | Campo derivado incompleto | `amount_usd` nulo en el 100% de las transacciones USD | `01_range_checks.sql` (R43) | Regla de derivación (`currency = USD ⇒ amount_usd = amount`) |
| 9 | Texto con placeholders sin rellenar | `{monto}`, `{moneda}` en el 100% de `agent_text` | `01_range_checks.sql` (R91) | Validación de texto antes de usarlo como contexto de un LLM |
| 10 | Identificadores no únicos | 54.4% de los clientes comparte email con otro cliente | `01_business_key_checks.sql` | Unicidad de atributos usados para identificar o autenticar |
| 11 | Enums distintos al diccionario | `product_type` y `reason_category` en español, `Seguro` y `Retención` no documentados, sin `CURP` ni `MXN` | `00_enum_values.sql` | Contrato de schema con dominios explícitos |
| 12 | Nulos estructurales vs aleatorios | `wait_time_seconds` solo existe en Inbound Call; ~5/10/15/20% de nulos aleatorios en campos opcionales | `01_null_patterns.sql`, `01_null_rates.sql` | Tasa de nulos por columna con umbral por tipo de nulo |

Lo que el diccionario anuncia y **no** está (0 duplicados, 0 llegadas tardías, sin evolución de schema) también es
evidencia: el pipeline debe tener esos checks, y la demostración de frescura/late arrivals requiere un **fixture
etiquetado** (lo prevé el reto). La cadena interaction → transcript → survey y transactions → products es 100%
consistente (C01–C12 = 0): son los joins seguros para una solución.
