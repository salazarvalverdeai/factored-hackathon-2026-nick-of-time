# Hallazgos del EDA — índice

> Índice del EDA del dataset sintético LATAM Bank (Factored AI & Data Hackathon 2026) para el pitch de Freddy.
> Cada cifra lleva etiqueta (`[medido]` = sale del dataset con la query indicada; `[supuesto]`; `[proyectado]`) y su
> archivo en `docs/eda/queries/` u `outputs/tables/`. Última actualización: 26 sep 2026 (fases 0–7).
> Regenerar todo: ver `README.md` (`python -m eda.<modulo>` en orden y `python -m eda.report`).

## Documentos
| Documento | Contenido |
|---|---|
| `docs/eda/resumen_ejecutivo.md` | Una página: qué tiene y qué no el dataset, dónde hay señal, ranking, ideas, preguntas |
| `docs/eda/workflows/W1_cuentas_pagos.md` … `W4_credito.md` | Expedientes con la misma estructura de 8 secciones |
| `docs/eda/calidad_datos.md` | Inventario, calidad por tabla y evidencia de data engineering para el pitch (§C) |
| `docs/eda/mapeo_workflows.md` | Reglas de mapeo v1 con confianza, cobertura por fuente, confiabilidad motivo vs texto |
| Este archivo | Resumen por workflow, comparación con la misma vara, ranking, ideas, vacíos, decisiones; anexo por fase |

## A. Lo que cambia el pitch
1. **No hay motivo granular ni intents ni texto real**: `contact_reason` = `reason_category` (6 valores),
   `detected_intents` tiene un solo valor, los transcripts son 2 plantillas de consulta de saldo independientes del
   motivo (kappa 0.0003) y de los productos del cliente. Un clasificador de intención sobre este texto no es defendible
   (`calidad_datos.md` §A5, `mapeo_workflows.md` §5).
2. **Solo W1 tiene una regla de contacto de confianza media** (`Transaccional`, 35.0% de los contactos); W3 y W4 entran
   con confianza baja (`Queja` 17.1%, `Comercial` 8.0%) y **W2 no tiene contactos propios** (§3).
3. **Los outcomes de contacto sí discriminan, pero solo por motivo**: FCR 91.5% (W1) vs 43.6% (W3), duración 3.4 vs
   7.2 min, NPS −69.9 vs −85.3. Nada depende de canal, país, segmento, acento ni agente (V ≤ 0.008). **SLA, escalamiento,
   re-contacto y resolución de complaints son planos** (§4).
4. **Señal aprendible en dos lugares**: FCR/seguimiento (AUC 0.763 / 0.676, 100% explicada por el motivo) y fraude vía
   el `fraud_score` existente (≥ 50 → precisión 100%, recall 48.8%). **Escalado, SLA, declinación, reverso, tarjeta
   bloqueada y mora son ruido** (AUC ≈ 0.50) (§5).
5. **El ahorro por contacto es marginal o negativo con costos laborales LATAM** (USD 10–20/h vs IA USD 0.50–1.84): el
   business case depende del supuesto de costo, no de los datos (§6).
6. **Los problemas de calidad anunciados no están** (0 duplicados, 0 llegadas tardías, sin evolución de schema); **los
   reales son otros** (FK a productos de otro cliente 100%, fechas futuras, orden temporal violado): son la evidencia de
   data engineering (`calidad_datos.md` §C).

## B. Resumen por workflow
### W1 — Cuentas y pagos → `workflows/W1_cuentas_pagos.md`
- **Volumen**: 6,661 contactos/mes (`Transaccional`, confianza media; 35.0%); 3,365 pagos rechazados y 1,348
  pendientes por mes desde cuentas `[medido]` (`04_workflow_scorecard.csv`, `04_trigger_events_summary.csv`).
- **Outcomes**: FCR 91.5% [91.4, 91.6], AHT 3.7 min, 0.0% sentimiento negativo, NPS −69.9: el workflow más "fácil".
  Cota automatizable 69.3% `[supuesto sobre medido]` (`06_cost_by_workflow.csv`).
- **Señal**: no resuelto AUC 0.763 solo por el motivo (baseline = regla por motivo). **Señales deterministas ricas**:
  saldos, movimientos consistentes con el dueño del producto (100%), estado de pagos, tipo de cambio coherente (1–2%).
- **Riesgo**: poco dolor y ahorro por contacto negativo en el escenario base LATAM (−51k USD/año); puede verse como
  "chatbot de saldo".

### W2 — Tarjetas → `workflows/W2_tarjetas.md`
- **Volumen**: sin contactos atribuibles; 2,383/mes solo vía plantilla de transcript (no confiable). Eventos: 2,156
  declinaciones de tarjeta/mes y 7,044 tarjetas bloqueadas al corte `[medido]` (`04_trigger_events_summary.csv`,
  `04_products_by_status.csv`).
- **Señal**: ninguna (declinada AUC 0.503, bloqueada 0.505). **Señales deterministas**: `response_code` ISO 8583
  (05, 14, 51, 54) explica cada declinación; `product_status` el bloqueo.
- **Riesgo**: el dataset no muestra demanda de contacto para W2; el componente aprendido tendría que salir de datos
  generados por el equipo. Sin embudo "error de app → llamada" (0.154% vs 0.149% de control).

### W3 — Disputas → `workflows/W3_disputas.md`
- **Volumen**: 679 complaints/mes de cargos no reconocidos y cobros indebidos (36.4% de complaints, confianza
  alta/media); 3,241 contactos `Queja`/mes (confianza baja); 120 fraudes y 1,241 reversos por mes `[medido]`.
- **Outcomes**: el peor en contacto: FCR 43.6%, 63.0% requiere seguimiento, 7.2 min, CSAT top 6.4%, NPS −85.3. SLA
  20.0% igual que el resto (no informativo).
- **Señal**: **`fraud_score` ≥ 50 → 100% de precisión, 48.8% de recall (45/mes); ≥ 30 → 79.6% / 69.3%**
  (`05_fraud_score_thresholds.csv`). Features + score AUC 0.79 vs score solo 0.75 (sin mejora significativa).
- **Riesgo**: complaints no se vincula a la interacción ni a un producto del propio cliente (`affected_product_id` de
  otro cliente en el 100%); 20.6% de los fraudes sin score.

### W4 — Crédito → `workflows/W4_credito.md`
- **Volumen**: 1,524 contactos `Comercial`/mes (confianza baja); sin complaints ni texto; 31,870 préstamos en cartera
  `[medido]`.
- **Outcomes**: FCR 65.2%, AHT 9.0 min (el más largo).
- **Señal**: **ninguna**: la mora no se predice (AUC 0.497). La elegibilidad solo puede ser una política de reglas
  sintética; `credit_score` 15.0% y `income` 20.0% nulos obligan a manejar faltantes.
- **Riesgo**: foto única al corte (leakage si se usa el estado actual), sin solicitudes ni decisiones de crédito,
  requisitos del reto más estrictos (el LLM no puede aprobar).

## C. Comparación con la misma vara y ranking
El scorecard completo, con n, denominador e IC95 por celda, está en §4 (anexo) y en `04_workflow_scorecard.csv`.
Como "el problema en números" solo discrimina por motivo y dos workflows no tienen población de contacto confiable,
la comparación usa el **criterio alternativo acordado: riqueza de labels, viabilidad en 10 días y señales
deterministas** (más la confianza del mapeo y el dolor medido como desempate).

| Criterio | W1 cuentas/pagos | W2 tarjetas | W3 disputas | W4 crédito |
|---|---|---|---|---|
| Label con señal (fase 5) | media: FCR vía motivo (trivial) | baja: ninguno | **alta: fraude vía `fraud_score`** | baja: ninguno |
| Señales deterministas para tools y verificación | **alta**: saldos, movimientos, pagos, FX | **alta**: `response_code`, bloqueo | **alta**: `fraud_score`, reversos, casos | media: score/ingreso con nulos |
| Viabilidad en 10 días | **alta** | media-alta | media | baja-media (política + compliance) |
| Confianza del mapeo de contactos | **media (35.0%)** | ninguna | baja (contactos) / alta-media (casos) | baja |
| Dolor medido (FCR, AHT, NPS) | bajo | n/d | **alto** | medio |
| Evaluación "saber cuándo no actuar" | media | media | **alta**: 3 zonas medibles | media (faltantes) |
| **Ranking** | **2°** | **3°** | **1°** | **4°** |

W3 queda primero porque es el único workflow con una señal medible que define cuándo actuar y cuándo escalar
(`fraud_score`) y con el peor dolor de contacto, aunque su mapeo de contactos sea de confianza baja. W1 es el más
viable y el mejor mapeado, pero sin dolor ni componente aprendido propio. W2 tiene buenas señales deterministas y cero
demanda medible. W4 no tiene señal y concentra los requisitos más duros del reto.

## 8. Para el pitch: ideas candidatas
**Idea 1 (recomendada) — W3: intake de disputas con triage verificable en 3 zonas.**
El agente recibe la disputa (ES/PT), identifica la transacción entre las del propio cliente (verificando pertenencia),
y decide con una regla fuera del modelo: `fraud_score` ≥ 50 → acción automática verificada (bloqueo + caso);
30–50 → confirma con el cliente y deriva; < 30 o sin score → handoff estructurado con hechos verificados.
- Números: **679 casos/mes** de cargos no reconocidos y cobros indebidos (`04_workflow_scorecard.csv`); **`fraud_score`
  ≥ 50: precisión 100%, recall 48.8%** (`05_fraud_score_thresholds.csv`); contactos `Queja` con **FCR 43.6% vs 76.6%** del
  banco (confianza baja).
- Label + baseline: `is_fraud` held-out; baseline = umbral fijo de `fraud_score`; componente a evaluar = calibración del
  triage y del handoff (el modelo features + score no mejora de forma significativa: decirlo).
- Riesgo principal: complaints desvinculados de interacciones y productos; convertirlo en demo de aislamiento por
  cliente (100% de `affected_product_id` es de otro cliente).

**Idea 2 — W1: consultas de cuenta y pagos con respuestas verificadas contra el ledger.**
- Números: **6,661 contactos/mes (35.0%)**, única regla de confianza media; **FCR 91.5%, AHT 3.7 min, cota automatizable
  69.3%**; 4,713 pagos rechazados o pendientes por mes (`04_trigger_events_summary.csv`).
- Label + baseline: no resuelto (AUC 0.763, todo del motivo) → baseline por regla; evaluación del agente contra ground
  truth determinista (saldo, movimientos, estado del pago) sobre casos held-out + set ES/PT generado.
- Riesgo principal: poco dolor y ahorro negativo en el escenario base LATAM; difícil diferenciarse de un chatbot.

**Idea 3 — W2: diagnóstico determinista de declinaciones y bloqueos de tarjeta.**
- Números: **2,156 declinaciones de tarjeta/mes** con `response_code` ISO (05, 14, 51, 54); **7,044 tarjetas bloqueadas**.
- Label + baseline: en el dataset no hay label aprendible (AUC ≈ 0.50); componente aprendido = clasificador de intención
  sobre set ES/PT generado por el equipo vs baseline de reglas.
- Riesgo principal: sin demanda de contacto medible para W2 en el dataset.

Transversal a las tres: `was_escalated` es ruido (AUC 0.501), así que **la política de handoff tiene que ser de reglas**,
fuera del modelo, que es justo lo que pide el reto.

## 7. Vacíos
- **Dimensiones como foto única** (customers, products): sin historia, el estado es el del corte. No hay forma de saber
  `product_status`, `credit_score`, `days_past_due` o `segment` al momento de un contacto. Riesgo de leakage para W2 y
  W4 (fase 5). (`00_row_counts.csv`: 1 archivo por dimensión)
- **Sin motivo de contacto granular**: `contact_reason` = `reason_category` (6 valores). (`00_enum_values.csv`)
- **Sin intents ni texto real de cliente**: `detected_intents` tiene un valor; transcripts con 42 textos de cliente
  distintos; complaints con 5 descripciones. (`00_multivalue_values.csv`, `01_business_key_checks.csv`)
- **Sin vínculo complaint → interacción ni complaint → producto del cliente**. (`01_fk_orphans.csv`, C15)
- **Sin producto confiable por interacción**: `mentioned_products` 99.35% huérfano. (`01_fk_orphans.csv`)
- **Sin llegadas tardías ni evolución de schema** para demostrar frescura: hará falta un fixture etiquetado.
  (`01_late_arrivals.csv`)
- **Sin SLA informativo**: `sla_breached` no depende del tiempo de resolución. (`01_complaints_sla_consistency.csv`)
- **Encuestas sin escala completa**: CSAT/CES 1–4, NPS 2–7. (`01_survey_scale_usage.csv`)
- **Sin MXN** en products/transactions (México opera 100% en USD). (`01_currency_by_country.csv`)
- **W2 sin contactos propios y W2/W4 sin complaints asignables** (`03_coverage_summary.csv`).
- **Escalamiento no aprendible** (AUC 0.501) y **mora no predecible** (AUC 0.497): no hay "cuándo escalar" ni "riesgo de
  crédito" que aprender del dataset (`05_learnable_signal.csv`).
- **Navegación digital independiente de los contactos**: sin embudo error → llamada (`06_digital_funnel.csv`).
- **Sin costos del banco**: el business case depende de benchmarks externos (`06_business_case_inputs.csv`).

## 9. Exploraciones posibles
| Exploración | Workflow | Esfuerzo |
|---|---|---|
| Vincular complaints W3 con reversos/fraudes del mismo cliente en ±30 días | W3 | medio día |
| Curva precisión/recall de `fraud_score` por país, canal y producto (fairness del triage) | W3 | 2–3 horas |
| Política de triage en 3 zonas con costo de falsos positivos/negativos | W3 | 1 día |
| Reconstrucción de saldo histórico desde `transactions` vs `current_balance` | W1 | medio día |
| Catálogo `response_code` × tipo de tarjeta × canal para el agente | W2 | 2 horas |
| Política sintética de pre-elegibilidad y casos de borde por datos faltantes | W4 | medio día |
| Set de evaluación ES/PT generado por el equipo (intenciones + respuestas esperadas desde el dataset) | todos | 1 día |
| Fixture etiquetado de llegadas tardías y cambio de schema para demostrar frescura | todos | medio día |
| Embudo errores/logins → llamada (**hecho**: sin efecto, `06_digital_funnel.csv`) | W2 | — |

## 10. Preguntas para Slack
1. ¿`contact_reason` idéntico a `reason_category` y `detected_intents` con un solo valor son intencionales, o habrá
   una versión del dataset con motivo e intents granulares?
2. ¿`complaints.origin_interaction_id` 100% nulo y `affected_product_id` apuntando a productos de otros clientes son
   intencionales (test de aislamiento) o un defecto del generador?
3. ¿Cuál es la definición de `sla_breached`? No depende de `resolution_days` ni del estado.
4. ¿Las escalas de encuesta son CSAT 1–5, NPS 0–10, CES 1–7? En los datos solo aparecen 1–4 y 2–7.
5. ¿Los placeholders `{monto}`, `{moneda}` en `agent_text` son intencionales?
6. El diccionario anuncia ~2% duplicados, llegadas tardías y evolución de schema; no los encontramos. ¿Está pensado
   que cada equipo los simule, o el dataset publicado no es la versión final?
7. ¿`fraud_score` puede tratarse como un dato del banco disponible en tiempo real (input de la solución) o es una
   variable de evaluación?
8. ¿`reason_category` se captura al inicio del contacto (IVR/menú) o lo registra el agente al cierre? Define si la
   señal de FCR es usable o es leakage.
9. ¿Los archivos diarios con corte a las 06:00/08:00 reflejan una zona horaria o un día operativo intencional?
10. ¿Hay un costo por contacto o por minuto de referencia que Factored espere en el business case?

## Decisiones tomadas
Decisiones de análisis tomadas en modo autónomo (fases 2–7), con su motivo. Freddy las revisa al final.

| Fase | Decisión | Motivo |
|---|---|---|
| 2 | Sin figuras en esta pasada; las series quedan en CSV | Breadth sobre depth; los documentos del Project son markdown |
| 2 | Estacionalidad y tendencia se prueban contra un modelo nulo (volumen ∝ días hábiles equivalentes) | Distinguir patrón real de ruido en vez de mirar la serie |
| 2 | `scikit-learn` agregado a `requirements.txt` | Baselines y modelos simples de la fase 5 |
| 3 | Mapeo por fuente (6 fuentes), cada una con su denominador; poblaciones por workflow pueden solaparse | No hay un campo que asigne workflow a todas las filas; mezclar fuentes ocultaría que W2 y W4 no tienen contactos propios |
| 3 | `Queja` → W3 y `Comercial` → W4 con confianza baja; `Producto` → AMBIGUO | Única forma de dar población de contacto a W3 y W4; se reporta cobertura estricta y amplia |
| 3 | Plantilla de saldo de tarjeta → W2 (media) y de cuenta → W1 (alta) | Única señal de W2 a nivel de contacto; se marca como no confiable (independiente de todo) |
| 3 | El acuerdo motivo vs `detected_intents` se reemplaza por motivo vs plantilla del transcript | `detected_intents` tiene un solo valor |
| 3 | `mapeo_workflows.md` se genera con `python -m eda.report` desde los CSV | Evitar cifras desincronizadas |
| 4 | "Discrimina" = IC95 separados **y** diferencia ≥ 2 pp (proporciones) o ≥ 10% relativo (resto) | Con n > 50k los IC son tan angostos que cualquier ruido del generador los separa |
| 4 | Además de IC, chi-cuadrado / Kruskal-Wallis con V de Cramér / ε² contra 8 agrupaciones | Mostrar de qué depende (y de qué no) cada outcome |
| 4 | Re-contacto = siguiente contacto del mismo cliente por cualquier motivo, con ventana completa de seguimiento | No hay forma de saber si el re-contacto es por el mismo tema |
| 4 | NPS reportado como −% detractores | No hay respuestas 8–10 (fase 1) |
| 4 | La conclusión esperada ("no discriminan") no se confirmó para contactos: se reporta tal cual | Regla del plan: demostrar, no asumir |
| 5 | Preprocesamiento con Polars/numpy (one-hot de niveles con ≥ 50 filas, imputación por mediana de train + indicador) | No hay pandas en el entorno; evita leakage de estadísticas de test |
| 5 | Veredicto: ruido si el IC95 del AUC incluye 0.5 o F1 ≤ F1 de "todo positivo"; señal débil si AUC < 0.60 | Operacionaliza "no supera al baseline" |
| 5 | Transacciones: muestra determinista de ~1.2M por `hash(transaction_id) % 1000 < 271` para modelar; umbrales de `fraud_score` sobre las 4.4M | Tiempo de cómputo; el reservoir de DuckDB no era repetible con varios hilos |
| 5 | `fraud_score` se evalúa como "score existente" y no como feature propia; se agregó un modelo features + score | Es la salida de otro modelo; hay que ver si algo le suma |
| 5 | Modelo "solo motivo" para los labels de contacto | Mostrar que toda la señal viene de `reason_category` |
| 6 | Costo por minuto = tarifa por hora / 60, sin ajuste por ocupación | Evitar un supuesto sin fuente; es cota inferior del costo humano |
| 6 | Escenarios conservador/base/optimista + referencia global (Gartner USD 13.50 por contacto) | Mostrar que el resultado depende del supuesto de costo |
| 6 | "Automatizable" = resuelto + no escalado + sin seguimiento + sin complaint del cliente en 30 días | Plan de la fase 6; se etiqueta como supuesto aunque las tasas sean medidas |
| 6 | Búsqueda web solo de benchmarks públicos de costo (ningún dato del dataset sale del repo) | Los supuestos requieren fuente |
| 6 | Embudo de digital_events (opcional, W2) hecho con ventana de control de 7 días antes | Distinguir causa de actividad normal; tomó < 1 hora |
| 7 | Expedientes generados con `python -m eda.report` desde `outputs/tables/` | Cifras sincronizadas con las queries |
| 7 | `findings.md` como índice; el detalle por fase queda como anexo con la numeración §0–§6 original | Mantener válidas las referencias desde queries y documentos |
| 7 | Ranking por criterio alternativo: W3 > W1 > W2 > W4 | Señal medible + dolor (W3) vs viabilidad y mapeo (W1); ver §C |
| 7 | `ORDER BY` por clave única en las bases de fases 4–5 y orden estable de niveles categóricos | Dos corridas completas dan CSV y documentos idénticos byte a byte |

---
# Anexo — detalle por fase

## 0. Estado del dataset (inventario)
Generado con `python scripts/s3_inventory.py` y `python -m eda.inventory`. Sincronizadas 12 de 13 tablas;
`campaign_sends` diferida (fuera de alcance).

- **Formato y particiones** `[medido]`: 100% CSV (UTF-8 con BOM), 7,671 objetos, 5.35 GB. Hechos en
  `data/<tabla>/year=YYYY/month=MM/day=DD/<tabla>_YYYYMMDD.csv`, 1 archivo/día, 1,097 días (2023-06-17 → 2026-06-17)
  sin huecos, salvo `campaign_sends` (arranca 2023-07-01). Dimensiones: un CSV plano cada una. Todo subido el
  2026-08-31 en ~15 min. `process_date` no está en la ruta pero sí como columna. (`00_inventory_files.csv`,
  `queries/00_s3_partition_coverage.sql`)
- **Conteos vs diccionario** `[medido]` (`00_row_counts.csv`, `queries/00_row_counts.sql`):
  dimensiones exactas (150k, 400k, 350, 1,200, 200). Hechos **por debajo**: interactions 686,296 (0.858),
  transcripts 171,321 (0.857), surveys 212,759 (0.851), complaints 67,095 (0.839), transactions 4,425,008 (0.885).
  **Por encima**: digital_events 15,620,994 (1.56) y daily_exchange_rates 13,164 (4.39).
  Hipótesis `[supuesto]`: 6/7 = 0.857 coincide con fines de semana a la mitad de volumen (ver
  `00_s3_partition_coverage.sql` bloque 3); se verifica en la fase 1 con filas por día de la semana.
- **Duplicados de PK: 0 en las 12 tablas** `[medido]` (`00_row_counts.csv`). El ~2% anunciado no está en la PK;
  se busca como duplicado de contenido en la fase 1.
- **Cambios de schema: ninguno a nivel de header** `[medido]`: 1 firma de columnas por tabla en los 1,097 archivos
  (`00_schema_by_partition.csv`). La "evolución de schema" anunciada, si existe, está en los valores (fase 1).
- **Enums que difieren del diccionario** `[medido]` (`00_enum_vs_dictionary.csv`, `queries/00_enum_values.sql`):
  `product_type` y `reason_category` vienen **en español** (8 tipos de producto, incl. `Seguro` no documentado; 6
  categorías, incl. `Retención`); `document_type` sin `CURP`; `currency` de products/transactions **sin MXN**
  (México opera en USD) aunque complaints sí trae MXN; interactions tiene canal `Web` extra (0.5%).
- **Campos que no sirven como se esperaba** `[medido]` (`00_enum_values.csv`, `00_multivalue_values.csv`):
  - `contact_reason` es **idéntico** a `reason_category` (6 valores). No hay motivo granular.
  - `detected_intents` tiene **un solo valor** (`consulta_general`, 95.1%; resto nulo). `detected_keywords`: 3
    palabras genéricas. `main_topics`: las mismas 6 categorías.
  - `complaints.origin_interaction_id` **100% nulo**: no existe la cadena interaction → complaint.
  - `complaints.description`: 5 plantillas ("Queja relacionada con {category}"). `resolution`: 5 plantillas.
  - `call_transcripts.customer_text`: 42 valores distintos; 2 plantillas de consulta de saldo = 60%. `agent_text`
    trae placeholders sin rellenar (`{monto} {moneda}`).
  - `nps_category` sin `Promoter` (solo Detractor 21.2% y Passive 7.2%, resto nulo).
- **Distribuciones uniformes** `[medido]`: `complaints.category` 5 × ~20%, `gender` F/M/O 3 × ~33%,
  `transcription_model` 4 × ~25%. Señal de generador sintético uniforme (relevante para la decisión 2 del plan).
- **Útil para el reto** `[medido]`: 129 agentes (10.75%) hablan portugués (`service_agents.languages`);
  `response_code` con códigos ISO 8583 reales (00, 05, 14, 51, 54) para W2; `digital_events` tiene `Login`, `Error`
  y `event_category=Authentication` para el embudo previo a llamada.

## 1. Calidad de datos
Detalle completo, con denominadores y consecuencias, en `docs/eda/calidad_datos.md` §B. Módulo `python -m eda.quality`.
Todas las cifras `[medido]` salvo que se indique.

| Tabla | Duplicados | Nulos relevantes | Huérfanos / pertenencia FK | Rezago p50/p95 (días) | Query |
|---|---|---|---|---|---|
| customers | 0 | `credit_score` 15.0%, `income` 20.0% (aleatorios) | `registration_branch_id` 99.997% huérfano | — | `01_duplicates`, `01_null_rates`, `01_fk_orphans` |
| products | 0 | `credit_limit` 5.1% en Tarjeta Crédito | 0 huérfanos; 49.9% abierto antes del registro del cliente | — | `01_fk_orphans`, `01_consistency_checks` (C17) |
| call_center_interactions | 0 | `wait_time_seconds` solo existe en Inbound Call (estructural) | `mentioned_products` 99.35% huérfano; el resto, de otro cliente | 0 / 0 | `01_null_patterns`, `01_fk_orphans_mentioned_products`, `01_late_arrivals` |
| call_transcripts | 0 | ~5–14% en campos opcionales | 0; consistencia perfecta con interactions (C01–C07) | 0 / 0 | `01_consistency_checks` |
| satisfaction_surveys | 0 | preguntas 1–3 43–81% (estructural) | 0; consistencia perfecta (C08–C11) | −1 / 0 | `01_consistency_checks`, `01_late_arrivals` |
| complaints | 0 | resolución 77% (casos abiertos) | `origin_interaction_id` 100% nulo; `affected_product_id` 100% de otro cliente | 0 / 0 | `01_fk_orphans`, `01_consistency_checks` (C15) |
| transactions | 0 | `amount_usd` 100% nulo en USD, 5.0% en COP/ARS | 0; siempre del dueño del producto; 18.7% antes de la apertura | 0 / 0 | `01_range_checks` (R43, R44), `01_consistency_checks` (C12, C13) |
| digital_events | 0 | `customer_id` 24.0% (aleatorio) | `product_id` 99.999% de otro cliente | 0 / 0 | `01_null_patterns`, `01_consistency_checks` (C20) |

Lo que sorprendió:
- **Los problemas que anuncia el diccionario casi no están**: 0 duplicados (tampoco con claves de negocio laxas), 0
  llegadas tardías (el rezago es 0 o −1 día por un corte de día a las 06:00/08:00), sin evolución de schema. Sí están
  los ~5% de nulos aleatorios. (`01_quality_summary.csv`, `01_business_key_checks.csv`, `01_day_boundary.csv`)
- **Los problemas reales son otros**: FK que apuntan a productos de otro cliente (100% en complaints), fechas futuras
  imposibles (~4% de customers y products con `last_updated` posterior a la carga), 18.7% de transacciones antes de la
  apertura del producto, etiquetas `México`/`Mexico`, coordenadas inválidas en 47.7% de las sucursales.
- **`sla_breached` ≈ 20% en todos los cortes** (días de resolución, estado, prioridad, tipo): no mide desempeño.
  (`01_complaints_sla_consistency.csv`)
- **Encuestas truncadas**: CSAT y CES 1–4 con distribución idéntica, NPS 2–7 (sin promotores; NPS global −74.5).
  Solo sirven comparaciones relativas. (`01_survey_scale_usage.csv`)
- **Fines de semana a la mitad** en las tablas de atención (0.50): explica el 0.858 de la fase 0.
  (`01_rows_by_weekday.csv`)
- **Cobertura de transcripts (25.0%) y encuestas (31.0%) plana** por motivo, canal y tipo de interacción.
  (`01_coverage.csv`)
- 54.4% de los clientes comparte email con otro: no sirve como identidad. (`01_business_key_checks.csv`)

## 2. Demanda
Módulo `python -m eda.demand`; queries `docs/eda/queries/02_*.sql`. Meses completos: jul 2023 – may 2026 (35).
Todas las cifras `[medido]`.

- **Volumen mensual**: 19,033 interacciones/mes (666,141 en 35 meses completos), 1,864 complaints/mes, 122,779
  transacciones/mes (`02_seasonality_tests.csv`).
- **Motivos** (`contact_reason` = `reason_category`, solo 6 valores; `02_reason_summary.csv`):

  | Motivo | % | Por mes | CV mensual |
  |---|---:|---:|---:|
  | Transaccional | 35.0 | 6,661 | 0.039 |
  | Producto | 22.0 | 4,184 | 0.034 |
  | Queja | 17.0 | 3,241 | 0.038 |
  | Técnico | 15.0 | 2,854 | 0.040 |
  | Comercial | 8.0 | 1,524 | 0.040 |
  | Retención | 3.0 | 569 | 0.060 |

- **Canal** (`02_monthly_volume.csv`): Phone 16,175/mes (85.0%), Email 764, App 731, WhatsApp 636, Web Chat 633,
  Web 95. **Tipo**: Inbound Call 13,332/mes, Outbound 2,842, Chat 1,905, Email 764, Video 189. **País**: México 9,517,
  Colombia 5,734, Argentina 3,781. **Segmento**: Basic 11,398, Plus 4,773, Premium 1,915, Student 947.
- **Demanda plana en todas las dimensiones**:
  - Sin tendencia: +0.31%/año, IC95 [−0.65, +1.27] (`02_seasonality_tests.csv`).
  - Sin estacionalidad material: índice mes del año entre 0.975 y 1.028. El mes a mes tiene más varianza que Poisson
    (D = 10.3) pero de magnitud ±3% (`02_seasonality_tests.csv`, modelo nulo en `eda/demand.py`).
  - Fines de semana a la mitad (0.50, fase 1). **Perfil horario uniforme en 24 h**: 4.12–4.24% por hora, sin pico
    (`02_hourly_profile.csv`).
  - Mezcla de motivos constante en el tiempo: V de Cramér = 0.007, p = 0.76 (`02_reason_share_stability.csv`).
  - **Misma intensidad de contacto por segmento y país**: 4.54–4.59 interacciones por cliente en la ventana; 99.0% de
    los clientes contactó al menos una vez (`02_contact_rate.csv`).
- **Complaints** (`02_complaints_monthly.csv`, `02_complaints_crosstab.csv`): Complaint 1,124/mes (60.3%), Claim 461
  (24.7%), Request 188 (10.1%), Suggestion 91 (4.9%). Recepción: Call Center 50.3%, Email 19.9%, Web 14.7%, App 10.0%,
  Branch 4.0%, **Regulator 20/mes (1.1%)**. `subcategory` es 1:1 con `category` (+10% nulo); **`case_type` es
  independiente de `category`** (la misma mezcla ~54/22/9/4% en las 5 categorías). Serie mensual compatible con ruido
  de Poisson (D = 1.3), sin tendencia.
- **Eventos transaccionales que pueden originar contactos** (`02_transactions_monthly.csv`): 6,139 declinadas/mes
  (5.0%), 1,242 reversadas/mes (1.0%), 2,450 pendientes/mes, 120 fraudes/mes (0.098%). Las declinaciones se reparten
  entre todos los tipos de producto, incluidos préstamos y seguros (texto de generador, no de negocio).
- **Lectura para el pitch**: el volumen es el único número de demanda defendible, y es plano. No hay pico horario,
  estacional ni segmento más demandante que justifique un workflow sobre otro.

## 3. Mapeo a workflows
Detalle, tabla de reglas y justificación en `docs/eda/mapeo_workflows.md`. Reglas en
`docs/eda/queries/03_workflow_mapping.csv` (versión **v1**, 35 reglas con confianza alta/media/baja). Módulo
`python -m eda.workflows`. Cifras `[medido]` (`03_coverage_summary.csv`).

| Workflow | % contactos (interactions) | % complaints | % transcripts | Eventos disparadores (transactions/products) | Comentario |
|---|---|---|---|---|---|
| W1_cuentas_pagos | 35.0 (media) | 2.0 (baja) | 49.9 | 121,242 pagos rechazados + 48,599 pendientes desde cuenta | Único con regla de contacto de confianza media |
| W2_tarjetas | 0.0 | 0.0 | 50.1 | 77,641 declinaciones de tarjeta; 7,044 tarjetas bloqueadas | Sin regla de contacto; solo texto (no confiable) y eventos |
| W3_disputas | 17.1 (baja) | 36.4 (alta/media) | 0.0 | 4,316 fraudes + 44,714 reversos | El único con casos (complaints) asignables |
| W4_credito | 8.0 (baja) | 0.0 | 0.0 | 31,870 préstamos en cartera | Sin casos ni texto |
| OTRO / AMBIGUO | 18.0 / 22.0 | 61.5 / 0.0 | 0.0 / 0.0 | — | `Técnico` (15.0%) es un quinto workflow de facto |

- **Cobertura estricta de contactos: 35.0%** (alta + media); amplia 60.0% con las reglas de confianza baja.
- **Motivo vs texto: kappa = 0.0003**; la plantilla del transcript es independiente del motivo (V = 0.008, p = 0.07)
  y de los productos del cliente (48.8–48.9% tiene tarjeta de crédito con cualquier plantilla, igual que el total)
  (`03_reason_vs_text_agreement.csv`, `03_template_vs_ownership.csv`). Ninguno de los dos es un label de intención.
- **Sin sesgo de `has_transcript` por workflow** (24.9–25.2%, p = 0.84; `03_transcript_bias_by_workflow.csv`).
- Catálogo de plantillas: 42 textos de cliente, 42 de agente, 5 descripciones y 5 resoluciones de complaints, 13
  comentarios de encuesta (`03_template_catalog.csv`). Las resoluciones se reparten igual en todas las categorías.

## 4. Scorecard por workflow (tabla central)
Módulo `python -m eda.outcomes`; queries `04_interactions_base.sql`, `04_complaints_base.sql`. Todas las cifras
`[medido]`. Valor [IC95] (n = denominador). IC Wilson para proporciones, bootstrap (500, semilla 42) para medianas,
p95 y medias. **Sin índice compuesto; cada fila tiene su propio denominador.** Poblaciones (fase 3): W1 = contactos
`Transaccional`, W2 = contactos con transcript de saldo de tarjeta (texto no confiable), W3 = contactos `Queja`,
W4 = contactos `Comercial`; en complaints W1 = CMP-04, W3 = CMP-01..03. W3 y W4 en contactos son de confianza baja.
"¿Discrimina?" = IC de W1–W4 que no se solapan **y** diferencia práctica (≥ 2 pp o ≥ 10% relativo;
`04_ci_overlap.csv`).

| Métrica | W1 cuentas/pagos | W2 tarjetas | W3 disputas | W4 crédito | ¿Discrimina? |
|---|---|---|---|---|---|
| Volumen mensual de contactos | 6,661 [6,576–6,746] (n=35) | 2,383 [2,351–2,415] (n=35) | 3,241 [3,201–3,282] (n=35) | 1,524 [1,503–1,544] (n=35) | sí |
| FCR (%) | 91.5 [91.4–91.6] (n=240,056) | 76.6 [76.3–76.8] (n=85,910) | 43.6 [43.3–43.9] (n=117,021) | 65.2 [64.8–65.6] (n=54,879) | sí |
| % escalado | 9.9 [9.8–10.1] (n=240,056) | 9.9 [9.7–10.1] (n=85,910) | 10.0 [9.9–10.2] (n=117,021) | 9.8 [9.6–10.1] (n=54,879) | no |
| % requiere seguimiento | 22.1 [22.0–22.3] (n=240,056) | 34.9 [34.6–35.2] (n=85,910) | 63.0 [62.7–63.2] (n=117,021) | 44.5 [44.1–45.0] (n=54,879) | sí |
| % sentimiento negativo (derivado) | 0.0 [-0.0–0.0] (n=240,056) | 19.5 [19.3–19.8] (n=85,910) | 34.9 [34.6–35.2] (n=117,021) | 34.9 [34.5–35.3] (n=54,879) | sí |
| Duración p50 (min) | 3.42 [3.38–3.42] (n=206,465) | 4.85 [4.80–4.88] (n=73,812) | 7.18 [7.15–7.23] (n=100,727) | 9.00 [8.98–9.08] (n=47,082) | sí |
| Duración p95 (min) | 6.80 [6.65–6.92] (n=206,465) | 10.27 [10.20–10.45] (n=73,812) | 11.05 [11.02–11.15] (n=100,727) | 13.47 [13.42–13.58] (n=47,082) | sí |
| Espera p50 (min, solo Inbound) | 1.98 [1.97–2.00] (n=168,074) | 1.98 [1.97–2.00] (n=60,211) | 2.00 [1.98–2.02] (n=82,261) | 2.00 [1.97–2.00] (n=38,338) | no |
| Espera p95 (min, solo Inbound) | 3.62 [3.58–3.63] (n=168,074) | 3.63 [3.60–3.66] (n=60,211) | 3.65 [3.63–3.68] (n=82,261) | 3.63 [3.62–3.68] (n=38,338) | no |
| CSAT top = 4 (%) | 13.5 [13.2–13.8] (n=44,837) | 11.3 [10.9–11.8] (n=16,173) | 6.4 [6.0–6.7] (n=21,843) | 9.7 [9.2–10.3] (n=10,243) | sí |
| CSAT media (1–4) | 2.91 [2.90–2.92] (n=44,837) | 2.77 [2.76–2.78] (n=16,173) | 2.43 [2.43–2.45] (n=21,843) | 2.66 [2.65–2.67] (n=10,243) | sí |
| NPS (sin promotores) | -69.9 [-70.5–-69.3] (n=22,341) | -73.9 [-74.8–-72.9] (n=7,860) | -85.3 [-86.0–-84.6] (n=10,821) | -78.4 [-79.5–-77.2] (n=5,144) | sí |
| CES media (1–4) | 2.91 [2.90–2.93] (n=7,354) | 2.75 [2.72–2.78] (n=2,729) | 2.44 [2.41–2.46] (n=3,693) | 2.67 [2.63–2.70] (n=1,760) | sí |
| Re-contacto 7 días (%) | 2.88 [2.81–2.95] (n=238,253) | 2.81 [2.70–2.92] (n=85,222) | 2.88 [2.79–2.98] (n=116,055) | 2.89 [2.75–3.03] (n=54,464) | no |
| Re-contacto 30 días (%) | 11.86 [11.73–11.99] (n=233,193) | 11.70 [11.49–11.92] (n=83,441) | 11.64 [11.45–11.82] (n=113,616) | 11.71 [11.44–11.99] (n=53,325) | no |
| Volumen mensual de complaints | 37.7 [35.4–39.9] (n=35) | n/d (n=0) | 678.9 [669.6–688.2] (n=35) | n/d (n=0) | sí |
| % SLA incumplido (complaints) | 20.4 [18.4–22.6] (n=1,367) | n/d (n=0) | 20.0 [19.5–20.5] (n=24,431) | n/d (n=0) | no |
| Días de resolución p50 | 15 [13–15] (n=342) | n/d (n=0) | 16 [15–16] (n=5,622) | n/d (n=0) | no |
| Días de resolución p95 | 28 [28–29] (n=342) | n/d (n=0) | 29 [29–29] (n=5,622) | n/d (n=0) | no |
| % resueltos/cerrados | 25.7 [23.4–28.1] (n=1,367) | n/d (n=0) | 24.2 [23.6–24.7] (n=24,431) | n/d (n=0) | no |

**Conclusión de la fase 4 (cambia la esperada):**
- **Los outcomes de contacto SÍ discriminan, pero solo por motivo** (`reason_category`): FCR V de Cramér = 0.43,
  seguimiento 0.32, sentimiento negativo 0.39, duración ε² = 0.48, NPS detractor 0.14, CSAT top 0.08
  (`04_discrimination_tests.csv`). W3 (`Queja`) es el peor en todo: FCR 43.6%, 63.0% requiere seguimiento,
  7.2 min, CSAT top 6.4%, NPS −85.3. W1 (`Transaccional`) es el mejor: FCR 91.5%, 3.4 min, 0.0% sentimiento negativo.
- **No discriminan por nada más**: canal, tipo de interacción, país, segmento, acento del cliente, experiencia o tipo
  de agente tienen V ≤ 0.008 en todos los outcomes. Dentro de cada workflow, FCR, escalamiento y CSAT varían ≤ 0.8 pp
  entre países y ≤ 2.3 pp entre segmentos (`04_scorecard_by_country.csv`, `04_scorecard_by_segment.csv`): sin
  disparidades que investigar (y sin señal de fairness que demostrar).
- **Escalamiento (~10%), espera, re-contacto (2.9% a 7 días, 11.8% a 30 días) y todas las métricas de complaints (SLA
  ~20%, resolución p50 15–16 días, 24% resueltos) son planos** en todos los cortes. `sla_breached` y los tiempos de
  resolución no sirven para priorizar.
- Lectura: el generador asignó los outcomes de contacto como función del motivo más ruido. "El problema en números"
  sí distingue a W3 (dolor) de W1 (volumen resoluble), pero solo en la medida en que el motivo `Queja` represente
  disputas (confianza baja) y la señal viene de una sola variable.
- **W2 no tiene población de contacto propia**: su columna es una mezcla aleatoria de motivos (texto independiente) y
  por eso queda en el promedio general. Sus números reales son eventos: 2,156 declinaciones de tarjeta/mes y 7,044
  tarjetas bloqueadas al corte (`04_trigger_events_summary.csv`, `04_products_by_status.csv`).

## 5. Labels, leakage, baseline y señal aprendible (fase central)
Módulo `python -m eda.labels`; datasets `05_ds_*.sql`. Todas las cifras `[medido]`. Split temporal (test = período
más reciente: desde 2025-07-01; products por apertura desde 2024-01-01). Baseline = clase mayoritaria (AUC 0.5).
Modelos: regresión logística y árbol de profundidad 4, features disponibles antes del evento (`05_leakage_fields.csv`).
AUC con IC95 Hanley-McNeil; AP = average precision (baseline = prevalencia). Fuente: `05_learnable_signal.csv`.

| Label | Workflow | Prevalencia test | Mejor modelo | AUC [IC95] | AP (vs prevalencia) | Veredicto |
|---|---|---:|---|---|---|---|
| Contacto NO resuelto (1 − FCR) | transversal / W1 vs W3 | 23.4% | LR solo motivo | **0.763 [0.760, 0.766]** | 0.46 (0.23) | **señal (100% del motivo)** |
| Requiere seguimiento | transversal | 34.8% | LR solo motivo | **0.676 [0.674, 0.679]** | 0.51 (0.35) | **señal (100% del motivo)** |
| Escalado | transversal (handoff) | 10.0% | LR | 0.501 [0.497, 0.505] | 0.10 (0.10) | ruido |
| SLA incumplido | W3 | 19.9% | LR | 0.500 [0.491, 0.510] | 0.20 (0.20) | ruido |
| Fraude — features estructuradas | W3 | 0.09% | árbol | 0.508 [0.477, 0.539] | 0.001 (0.001) | ruido |
| Fraude — `fraud_score` existente | W3 | 0.09% | score | **0.752 [0.722, 0.782]** | **0.52 (0.0009)** | **señal (score dado)** |
| Fraude — features + `fraud_score` | W3 | 0.09% | LR | 0.792 [0.763, 0.820] | 0.50 (0.0009) | señal, sin mejora significativa sobre el score |
| Transacción declinada | W2 / W1 | 5.0% | LR + score | 0.503 [0.499, 0.507] | 0.05 (0.05) | ruido |
| Transacción reversada | W3 | 1.0% | score | 0.503 [0.494, 0.513] | 0.01 (0.01) | ruido |
| Tarjeta bloqueada | W2 | 5.0% | árbol | 0.505 [0.493, 0.518] | 0.05 (0.05) | ruido |
| Crédito en mora (`days_past_due` > 0) | W4 | 15.0% | árbol | 0.497 [0.489, 0.505] | 0.15 (0.15) | ruido |

- **Hay señal aprendible en dos lugares, y ninguna es un componente aprendido "propio"**:
  1. FCR y seguimiento dependen **solo del motivo**: el modelo con `reason_category` como única feature iguala al
     completo, y las 4 features más pesadas de ambos modelos son niveles de `reason_category`
     (`05_feature_importance.csv`). El "modelo" es una tabla de 6 filas.
  2. Fraude: **`fraud_score` es casi determinista**. Con umbral ≥ 50 marca 1,670 transacciones (45/mes) con
     **100% de precisión** y 48.8% de recall; con ≥ 30, 79.6% de precisión y 69.3% de recall. Las transacciones
     legítimas tienen p95 = 28.5 y ninguna llega a 80; el 20.6% de los fraudes no tiene score
     (`05_fraud_score_thresholds.csv`, `05_fraud_score_profile.csv`).
- **Todo lo demás es ruido**: no se puede aprender cuándo escalar, qué caso incumplirá el SLA, qué transacción se
  declinará o reversará, qué tarjeta se bloqueará ni qué crédito caerá en mora con las features disponibles. Para W4
  esto significa que **no hay estimación de riesgo que demostrar**: la elegibilidad tiene que ser una política de reglas
  sintética (lo que el reto ya exige separar).
- **Texto**: 21 plantillas de cliente por workflow (W1/W2), 11–15 palabras, la misma distribución en todos los motivos
  (`05_transcripts_by_workflow.csv`). Un clasificador de intención sobre este texto no es defendible.
- **Splits** (`05_split_feasibility.csv`): 464,791 contactos en train y 221,505 en test; el 95.5% de los contactos de
  test son de clientes que ya aparecen en train y el 94.9% de los clientes contacta en más de un mes. Para aislar
  clientes (lo pide el reto), usar split temporal **más** agrupación por `customer_id`.
- **Leakage** (`05_leakage_fields.csv`): 16 campos marcados. Los críticos: duración, sentimiento, acento y transcript
  (se conocen al cerrar el contacto); campos de resolución de complaints; `response_code` para declinaciones; y la
  **foto única de customers/products** (estado al corte) para W2 (`product_status`) y W4 (`credit_score`,
  `days_past_due`). `reason_category` se asume conocido al inicio del contacto `[supuesto]`; si lo registra el agente
  al cierre, la señal de FCR también sería leakage.
- **Labels descartados sin entrenar**: `detected_intents` (1 valor), intención desde texto (plantilla independiente),
  encuestas (posteriores, escala truncada), `detected_sentiment` (regla del generador por motivo)
  (`05_labels_inventory.csv`).

| Workflow | Labels con señal | Baseline sugerido | Componente aprendido posible | Split |
|---|---|---|---|---|
| W1 | no resuelto / seguimiento (vía motivo) | regla por `reason_category` | ninguno que supere a la regla; evaluar el agente contra ground truth determinista (saldos, movimientos) | temporal + cliente |
| W2 | ninguno (declinada, bloqueada = ruido) | reglas por `response_code` y `product_status` | ninguno en el dataset; clasificador de intención sobre set ES/PT generado por el equipo | temporal + cliente |
| W3 | fraude vía `fraud_score` | umbral de `fraud_score` (≥ 50: precisión 100%) | calibración del umbral de triage (automatizar / confirmar / escalar) contra `is_fraud` held-out | temporal + cliente |
| W4 | ninguno (mora = ruido) | política de reglas sintética | ninguno: no hay riesgo predecible; solo política + manejo de datos faltantes | por apertura |

## 6. Costo y business case (insumos)
Módulo `python -m eda.cost`; tablas `06_cost_by_workflow.csv` y `06_business_case_inputs.csv` (cada insumo con
etiqueta y fuente). Fórmula común: **ahorro = contactos/mes × % automatizable (cota) × (costo humano − costo IA)**.
Meses completos (35). Poblaciones de la fase 3 (W2 sale de texto no confiable; W3 y W4 de reglas de confianza baja).

| Insumo | W1 | W2 | W3 | W4 | Etiqueta | Fuente |
|---|---|---|---|---|---|---|
| Contactos por mes | 6,661 | 2,383 | 3,241 | 1,524 | medido | `06_cost_base.sql` |
| AHT medio (min) | 3.68 | 5.37 | 7.24 | 9.00 | medido | `06_cost_base.sql` |
| Minutos de atención por mes | 24,515 | 12,789 | 23,477 | 13,711 | medido | `06_cost_base.sql` |
| % automatizable seguro (cota superior) | 69.3 | 57.8 | 32.8 | 49.4 | supuesto (definición sobre tasas medidas) | `06_cost_base.sql` |
| Costo por minuto de agente (USD, base) | 0.250 | 0.250 | 0.250 | 0.250 | supuesto | SkyCom 2026: USD 10–20/h LATAM |
| Costo por contacto humano (USD, base) | 0.92 | 1.34 | 1.81 | 2.25 | proyectado | AHT × costo/min |
| Costo por contacto con IA (USD, base) | 1.84 | 1.84 | 1.84 | 1.84 | supuesto | Gartner vía Kustomer 2026 |
| Ahorro anual — conservador (USD) | -67,941 | -15,637 | -8,079 | -3,070 | proyectado | agente USD 10/h, IA USD 1.84 |
| Ahorro anual — base (USD) | -50,952 | -8,239 | -373 | 3,697 | proyectado | agente USD 15/h, IA USD 1.84 |
| Ahorro anual — optimista (USD) | 40,260 | 21,322 | 24,440 | 22,556 | proyectado | agente USD 20/h, IA USD 0.50 |
| Ahorro anual — referencia global (USD) | 645,853 | 192,851 | 148,855 | 105,217 | proyectado | USD 13.50 por contacto asistido (Gartner, global) vs IA USD 1.84 |

- **Medido**: volumen y tiempo de atención (AHT W1 3.7 min, W2 5.4, W3 7.2, W4 9.0; `06_cost_by_workflow.csv`). El
  "dolor" medible (FCR, seguimiento, duración) sí difiere entre workflows por motivo (fase 4), pero SLA, escalado y
  re-contacto no. **Supuesto**: qué fracción es automatizable y los costos unitarios.
- **Con costos laborales LATAM el ahorro es marginal o negativo** (−68k a +40k USD/año en W1): un contacto humano de
  3.7 min cuesta USD 0.61–1.23, del mismo orden que un contacto con IA (USD 0.50–1.84). El ahorro solo es grande con el
  costo asistido global de Gartner (USD 13.50 por contacto: +646k USD/año en W1), que no es LATAM ni está verificado en
  fuente primaria. **El business case depende del supuesto de costo, no de los datos**, y la escala del banco sintético
  es chica (19,033 contactos/mes, 150k clientes). El argumento de negocio más sólido no es ahorro por contacto sino
  capacidad 24/7, consistencia y control de riesgo (fraude, cumplimiento).
- Espera (solo Inbound Call): 2.0 min de media, igual en todos los workflows; 9,299 minutos/mes de espera del cliente
  en W1 (`06_cost_by_workflow.csv`).
- Complaint del mismo cliente en los 30 días siguientes a un contacto: 1.2% en todos los workflows (plano).
