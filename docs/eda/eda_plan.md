# Plan de EDA — evidencia para el pitch

Objetivo: salir con una tabla comparativa de los **4 workflows** del reto, respaldada por queries, que permita
elegir 1 a 3 ideas y llenar los 5 bloques del pitch (`docs/pitch/pitch_brief.md`). El EDA es **transversal**:
primero se miran los 4 workflows con la misma vara; recién después se profundiza en los que ganen.

Contexto: `docs/context/proyecto/01_reto_2026.md` (métricas del reto) y `02_dataset_latam_bank.md` (tablas).

Los 4 workflows (nombres cortos que se usan en todo el repo):
`W1_cuentas_pagos` · `W2_tarjetas` · `W3_disputas` · `W4_credito`

## Decisiones acordadas con Freddy (26 sep, tras el inventario S3)
1. **Cada métrica del scorecard con su propio n y denominador. Sin índice compuesto.** Interactions (todos los
   contactos) y complaints (casos que fallaron) son poblaciones distintas; W3 vive en complaints por definición.
2. **Intervalos de confianza en la fase 4.** Si el dolor no discrimina entre workflows (IC95 solapados en las
   métricas de dolor), el criterio alternativo para compararlos es **riqueza de labels y viabilidad**.
3. **Revisar el sesgo de `has_transcript` por workflow antes de usar `detected_intents`** (transcripts cubren como
   máximo ~25% de las interacciones).
4. **Nunca promediar `main_score` entre tipos de encuesta** (CSAT, NPS, CES tienen escalas distintas).
5. **Dimensiones como foto única** (hallazgo del inventario): `customers`, `products`, etc. son un solo CSV sin
   historia. Va a la fase 5 como riesgo de leakage para W2 y W4, y a "Vacíos".
6. **Sync:** dimensiones + núcleo + `transactions` completo. `digital_events` completo en segundo plano y **solo
   para el embudo de errores y logins previos a una llamada**. `campaign_sends` diferida.
7. **Documentos incrementales:** cada fase escribe su parte en el documento que le corresponde
   (`calidad_datos.md` en la fase 1, `mapeo_workflows.md` en la 3, secciones de los expedientes en la 2 y la 4–6);
   la fase 7 consolida. Un commit por fase.

## Decisiones acordadas con Freddy (26 sep, tras las fases 0 y 1)
8. **Caché Parquet aprobado** (`data/_cache/`, gitignored; ningún `.parquet` entra a git).
9. **Sección 8 de los expedientes = catálogo de plantillas** distintas (transcripts y complaints), deduplicado, con
   frecuencia y workflow asignado, sin identificadores ni datos personales. Sujeto a la pregunta 4 de Slack.
10. **Cambio de estrategia.** Motivo sin granularidad, intents con un solo valor, texto de plantilla y
    `sla_breached`/CSAT/NPS sin relación con nada implican que "el problema en números" no discriminará entre
    workflows y que un clasificador de intención sobre texto no es un componente aprendido defendible. Entonces:
    - Fase 4 sigue; su conclusión esperada es "los outcomes no discriminan", y se **demuestra** con intervalos.
    - **Fase 5 pasa a ser la fase central**, con un chequeo de señal aprendible por label candidato.
    - Fase 6 mantiene la fórmula, pero explicita que **el volumen es lo único medido** y el dolor es supuesto.
    - Los problemas reales de calidad van a `calidad_datos.md` como evidencia de data engineering para el pitch.
11. **Mapeo (fase 3) sin revisión conjunta**: reglas versionadas con confianza alta/media/baja; cobertura y % AMBIGUO
    por fuente. Freddy lo revisa al final sobre `mapeo_workflows.md`.
12. **Modo autónomo en fases 2–7**: sin checkpoints; un commit por fase; decisiones en `findings.md` como "Decisión
    tomada". Solo se para ante bloqueo técnico o hallazgo que invalide el plan.
13. **Prioridad: breadth sobre depth.** Primero los 4 expedientes completos. De las exploraciones opcionales, solo el
    embudo de errores/logins de `digital_events` previo a una llamada (W2), si toma menos de una hora. Fase 5 sin
    modelos elaborados.

---

## Fase 0 — Inventario y carga (`eda/inventory.py`)
**Preguntas**
- ¿Qué archivos hay en el bucket, en qué formato, con qué estructura de particiones y cuánto pesan?
- ¿Coinciden los conteos de filas con el diccionario (150k, 400k, 800k, 80k, …)?
- ¿Qué columnas tiene cada tabla en cada partición? ¿Dónde cambia el schema y cuándo?
- ¿Qué valores reales toman los enums (`product_type`, `reason_category`, `case_type`, `status`, …)? El diccionario
  trae uno truncado ("Investme…").

**Entregables**: `outputs/tables/00_inventory_files.csv`, `00_row_counts.csv`, `00_schema_by_partition.csv`,
`00_enum_values.csv`. Checkpoint con Freddy antes de la fase 1.

## Fase 1 — Calidad de datos (`eda/quality.py`)
**Preguntas por tabla**
- Duplicados exactos y por PK (`customer_id`, `interaction_id`, `case_id`, …). Tasa vs el ~2% anunciado.
- Nulos por columna; cuáles son "opcionales" y cuáles no deberían tener nulos.
- Huérfanos de FK (interacciones sin cliente, complaints sin interacción origen, transcripts sin interacción).
- Llegadas tardías: distribución de `process_date − fecha_del_evento` en días. La ruta S3 no trae `process_date`
  (solo `year/month/day`) y todo se subió el 31-ago-2026: el rezago está simulado **dentro de los archivos**. Se
  mide con la columna `process_date` si existe, o con la fecha de la partición vs la fecha del evento.
- Rangos imposibles: fechas fuera de 2023-06-17..2026-06-17, montos negativos, `resolution_days` < 0,
  `main_score` fuera de escala.
- Cobertura de transcripts y surveys sobre interacciones (`has_transcript` vs transcripts reales), insumo de la
  decisión 3.

**Entregables**: `01_quality_summary.csv` (una fila por tabla), `01_null_rates.csv`, `01_late_arrivals.csv`.
Documento: `docs/eda/calidad_datos.md` (fase 1 + hallazgos del inventario de la fase 0).
Esto alimenta el bloque "Riesgos y vacíos" y la parte de data engineering del pitch.

## Fase 2 — Demanda (`eda/demand.py`)
Base: `call_center_interactions` deduplicada. Complementos: `complaints` y `digital_events` **solo para el embudo
de errores y logins previos a una llamada** (decisión 6; los `event_type` reales se validan en la fase 0).
**Preguntas**
- Volumen mensual total y por `reason_category`, `contact_reason`, `channel`, `country`, `interaction_type`.
- Top 30 `contact_reason` por volumen. Estabilidad en el tiempo (¿hay estacionalidad o tendencias?).
- Volumen mensual de `complaints` por `case_type`, `category`, `subcategory`, `reception_channel`.
- ¿Qué proporción de interacciones tiene transcript (`has_transcript`) y survey asociada?

**Entregables**: `02_monthly_volume_by_reason.csv`, `02_top_contact_reasons.csv`, `02_complaints_by_category.csv`,
figuras de series mensuales.

## Fase 3 — Mapeo a workflows (`eda/workflows.py`)
Es la fase más delicada: **ningún campo dice "workflow"**. Se construye un mapeo explícito y auditable.
**Método**
1. Listar todos los valores distintos de `contact_reason`, `complaints.category/subcategory`,
   `call_transcripts.detected_intents` y `main_topics` con su frecuencia.
2. Proponer un diccionario de reglas `valor → workflow` (W1–W4, `OTRO`, `AMBIGUO`) en
   `docs/eda/queries/03_workflow_mapping.csv`. Reglas por keyword solo como primera pasada; la asignación final
   se revisa a mano con Freddy.
3. Medir cobertura: % de interacciones/complaints que caen en cada workflow, en `OTRO` y en `AMBIGUO`.
4. **Antes de usar `detected_intents`:** comparar la mezcla de workflows entre interacciones con y sin transcript
   (decisión 3). Si difiere, todo lo que salga de transcripts se reporta como válido solo para ese subconjunto.
5. Cruzar fuentes: ¿coinciden `contact_reason` y `detected_intents` para la misma interacción? Eso mide qué tan
   confiables son los labels derivados por modelo.

**Entregables**: `03_workflow_mapping.csv` (la tabla de reglas, versionada), `03_coverage_by_workflow.csv`,
`03_transcript_bias_by_workflow.csv`, `03_reason_vs_intent_agreement.csv`.
Documento: `docs/eda/mapeo_workflows.md` (reglas, justificación de cada asignación, acuerdo, OTRO/AMBIGUO) y la
sección (1) de cada expediente.

## Fase 4 — Outcomes por workflow (`eda/outcomes.py`)
Con el mapeo de la fase 3, calcular **la misma tabla para los 4 workflows**:

| Métrica | Fuente | Nota |
|---|---|---|
| Volumen mensual | interactions + complaints | meses completos |
| FCR (`was_resolved`) | interactions | |
| Escalamiento (`was_escalated`), `requires_followup` | interactions | proxy de "necesita humano" |
| Duración y espera (p50/p95) | interactions | proxy de costo |
| % SLA incumplido (`sla_breached`) | complaints | |
| Días de resolución (p50/p95) | complaints | |
| Compensación otorgada, monto reclamado | complaints | disputas |
| CSAT / NPS / CES y `resolution_satisfaction` | surveys, complaints | **cada tipo por separado**, nunca promediar `main_score` entre tipos |
| Sentimiento (`detected_sentiment`) | interactions | label derivado, tratar con cuidado |
| Repetición (`is_repeat_complainer`, re-contacto a 7/30 días) | complaints, interactions | señal de "no resuelto" |

**Reglas del scorecard** (decisiones 1, 2 y 4):
- Cada celda lleva valor, **n, denominador explícito** (p. ej. "interacciones W2 deduplicadas" vs "complaints W2
  con `sla_breached` no nulo") e **IC95**: Wilson para proporciones, bootstrap (semilla 42) para medianas/p95.
- **Sin índice compuesto** ni ranking agregado.
- Si los IC95 de las métricas de dolor se solapan entre workflows, se declara que el dolor no discrimina y la
  comparación pasa al criterio alternativo: riqueza de labels (fase 5) y viabilidad en 10 días.

Además, por workflow: distribución por país, canal y segmento (`customers.segment`), porque el reto pide
comparar outcomes por segmento y por idioma. Ojo: `segment` es el valor al corte (foto única), no al momento del
contacto.

**Conclusión esperada (decisión 10):** "los outcomes no discriminan entre workflows". Se demuestra, no se asume:
IC95 por celda y, además, una prueba de independencia (chi-cuadrado y V de Cramér) de cada outcome contra
`reason_category`, canal, país y segmento. Si alguna métrica sí discrimina, se reporta y cambia la conclusión.

**Entregables**: `04_workflow_scorecard.csv` (la tabla central del pitch, formato largo: workflow × métrica ×
{valor, n, denominador, ic_low, ic_high, query}), `04_scorecard_by_country.csv`, `04_scorecard_by_segment.csv`,
`04_recontact.csv`. Documento: sección (3) de cada expediente.

## Fase 5 — Labels, baseline y señal aprendible (`eda/labels.py`) — FASE CENTRAL
El reto exige evaluar **un componente aprendido contra un baseline** con labels válidos y sin leakage.

**Chequeo de señal aprendible (decisión 10).** Para cada label candidato — `was_escalated`, `was_resolved`,
`requires_followup` (interactions), `sla_breached` (complaints), `is_fraud`, `transaction_status = Declined`,
`transaction_status = Reversed` (transactions), `product_status = Blocked` (products de tarjeta), `days_past_due > 0`
(products de crédito):
- Features estructuradas **disponibles antes del evento** (nada que se conozca solo al cerrar: duración, sentimiento,
  resolución, `response_code`, estados posteriores). Las features de dimensiones son foto única: se marcan como riesgo.
- **Split temporal** (entrenamiento con el período más antiguo, prueba con el más reciente; para products, por
  `opening_date`).
- Baseline trivial (clase mayoritaria) vs regresión logística y árbol de profundidad ≤ 4. Semilla 42.
- Métricas en prueba: AUC con IC95 (Hanley-McNeil), average precision vs prevalencia, F1 con IC95 (bootstrap).
- Regla: si el IC95 del AUC incluye 0.5 (o el F1 no supera al baseline), **el label es ruido y se descarta**.
  Si no hay señal en ningún label, ese es el hallazgo y va al pitch.
**Preguntas**
- ¿Qué labels existen por workflow? Candidatos: `contact_reason` / `reason_category` (intención),
  `detected_intents` (multi-label derivado), `was_escalated` (necesita humano), `was_resolved` (resoluble),
  `complaints.status`/`sla_breached` (riesgo de incumplimiento), `is_fraud` (disputas), `product_status=Blocked`
  (tarjetas), `days_past_due`/`credit_score` (crédito).
- Calidad de los labels: distribución de clases, desbalance, consistencia entre fuentes (fase 3).
- **Campos con leakage** (conocidos solo después del cierre): `resolution`, `resolution_days`, `resolution_date`,
  `compensation_granted`, `resolution_satisfaction`, `was_resolved` si se predice antes de terminar la llamada,
  surveys posteriores. Listarlos explícitamente.
- **Dimensiones como foto única (decisión 5):** `customers` y `products` son un solo snapshot al corte. Todo campo
  de estado (`product_status`, `days_past_due`, `current_balance`, `credit_limit`, `credit_score`, `segment`,
  `customer_status`) refleja el estado final, no el del momento del contacto. Riesgo de leakage directo para
  **W2** (`product_status=Blocked` como label o feature) y **W4** (`credit_score`, `days_past_due`). Medir cuánto
  pesa: p. ej. productos con `last_transaction_date` posterior a la interacción.
- ¿Cuántos transcripts hay por workflow y cuál es la longitud típica? Eso decide si un clasificador de intención
  sobre texto es viable en 10 días.
- Splits posibles: por tiempo (fecha del evento; `process_date` si existe como columna) y por cliente
  (`customer_id`). Ver cuántos clientes tienen interacciones en más de un mes.

**Entregables**: `05_labels_inventory.csv`, `05_leakage_fields.csv`, `05_transcripts_by_workflow.csv`,
`05_split_feasibility.csv`, `05_learnable_signal.csv` (label × modelo × métricas con IC). Baseline sugerido por
workflow según dónde haya señal (no TF-IDF sobre texto de plantilla).
Documento: sección (4) de cada expediente.

## Fase 6 — Costo y business case (`eda/cost.py`)
**Preguntas**
- Minutos de agente por workflow (`duration_seconds` + `wait_time_seconds`) por mes: `[medido]`.
- Costo por contacto = minutos × costo por minuto de agente: `[supuesto]` con fuente (dejar el parámetro en el
  script, no hardcodear un número).
- % "automatizable seguro" por workflow: primera aproximación `[supuesto]` = interacciones no escaladas,
  resueltas en primer contacto, sin complaint posterior. Explicitar que es una cota, no una medición.
- Ahorro `[proyectado]` = volumen × % automatizable × diferencia de costo. Misma fórmula para los 4 workflows.
- **Explícito en cada tabla (decisión 10):** el volumen es lo único `[medido]`; el dolor (SLA, CSAT, FCR) no
  discrimina y el % automatizable y el costo son `[supuesto]`.

**Entregables**: `06_cost_by_workflow.csv`, `06_business_case_inputs.csv` con columnas `valor`, `etiqueta`
(medido/supuesto/proyectado), `fuente`. Documento: sección (5) de cada expediente.

## Fase 7 — Cierre: documentos para el Project de claude.ai
Los documentos se suben a un Project de claude.ai para cruzarlos con investigación externa. Cada uno debe
entenderse solo, con cada cifra etiquetada (`[medido]`/`[supuesto]`/`[proyectado]`) y con su archivo de query.

1. **Expedientes por workflow** `docs/eda/workflows/W1_cuentas_pagos.md`, `W2_tarjetas.md`, `W3_disputas.md`,
   `W4_credito.md`. Misma estructura en los cuatro:
   1. Definición del workflow y reglas de mapeo que lo alimentan, con cobertura y % ambiguo
   2. Demanda: volumen mensual, canales, países, segmentos, estacionalidad
   3. Outcomes: cada métrica con n, denominador, intervalo y query
   4. Labels disponibles, calidad, campos con leakage, baseline sugerido y split
   5. Proxies de costo e insumos del business case, etiquetados
   6. Vacíos específicos del workflow
   7. Exploraciones posibles con estimación de esfuerzo
   8. Catálogo de plantillas: todas las plantillas de texto distintas (transcripts y complaints) asignadas al
      workflow, con su frecuencia, sin identificadores (decisión 9)
2. **`docs/eda/calidad_datos.md`**: todo lo de la fase 1 más los hallazgos del inventario (foto única de
   dimensiones, sin `process_date` en ruta, llegadas tardías simuladas dentro de los archivos, cobertura de
   transcripts).
3. **`docs/eda/mapeo_workflows.md`**: tabla de reglas versionada, justificación de cada asignación, acuerdo motivo
   vs intent, sesgo de `has_transcript` y lo que quedó en OTRO/AMBIGUO.
4. **`docs/eda/findings.md` pasa a ser el índice**: resumen de 1 página por workflow que apunta a cada expediente,
   la comparación con la misma vara (scorecard con n, denominador e IC), "Vacíos", "Exploraciones posibles",
   "Decisiones tomadas" y las 1 a 3 ideas candidatas.
5. **`docs/eda/resumen_ejecutivo.md`** (1 página, se abre en el Project junto con los expedientes): qué tiene y qué
   no tiene el dataset, en qué workflow hay señal aprendible y con qué label, ranking por el criterio alternativo
   (labels, viabilidad, señales deterministas), 1 a 3 ideas candidatas con los 2–3 números que las sostienen, y las
   preguntas para Slack.
6. Copiar los números a `docs/pitch/pitch_brief.md`.
7. Lista de preguntas que salieron para Slack `#technical-help` (agregar a `04_brechas_y_preguntas.md`).
8. Reporte final a Freddy (máximo 20 líneas).

Los expedientes se generan con `python -m eda.report` a partir de `outputs/tables/` para que las cifras no se
desincronicen. La sección 8 es el catálogo de plantillas (decisión 9), sujeto a la pregunta 4 de Slack.

---

## Exploraciones opcionales (si sobra tiempo o si un workflow lo pide)
- Texto de transcripts: longitud, vocabulario por país/acento, cuántos mencionan montos o fechas (útil para
  extracción de entidades en disputas).
- `digital_events`: embudo de errores y logins fallidos antes de una llamada (¿la gente llama porque la app falló?).
- `products`: tarjetas bloqueadas y su relación con transacciones declinadas y llamadas posteriores.
- `service_agents.languages`: ¿algún agente habla portugués? Sirve para el bloque de idioma.
- Correlación entre `wait_time_seconds` y CSAT.
- Fraude (`is_fraud`, `fraud_score`) solo como señal para disputas; no es el reto.

## Lo que este EDA NO hace
- No entrena modelos. Solo deja labels, baseline sugerido y splits factibles.
- No construye el pipeline de producción. Deja la lista de checks de calidad que ese pipeline tendrá que hacer.
- No decide el workflow. Presenta los 4 con la misma vara; la decisión es del pitch y la votación.
