# Expediente W1 — Consultas de cuenta y pagos

> Documento autocontenido para el Project de claude.ai (EDA del dataset sintético LATAM Bank, Factored AI & Data
> Hackathon 2026). Generado con `python -m eda.report` desde `outputs/tables/`. Cada cifra lleva etiqueta
> (`[medido]` = sale del dataset con la query indicada; `[supuesto]`; `[proyectado]`) y su archivo de query en
> `docs/eda/queries/`. Contexto general: `data_quality.md`, `workflow_mapping.md`, `findings.md`,
> `executive_summary.md`.

## 1. Definición y reglas de mapeo
Consultas sobre saldos, movimientos, pagos y transferencias de cuentas (ahorro y corriente), incluidos pagos rechazados o pendientes y conversión de moneda. Es el workflow con la regla de contacto más confiable del dataset (`Transaccional`, confianza media).

Reglas que alimentan este workflow (`queries/03_workflow_mapping.csv` v1; cobertura `03_coverage_by_rule.csv`)
`[medido]`:

| Regla | Fuente | Condición | Confianza | n | Cobertura |
|---|---|---|---|---|---|
| INT-01 | interactions | `reason_category = 'Transaccional'` | media | 240,056 | 35.0% de interactions |
| TRS-01 | transcripts | `customer_text LIKE '%cuenta de ahorros%'` | alta | 85,411 | 49.9% de transcripts |
| CMP-04 | complaints | `category = 'Fees' AND case_type = 'Request'` | baja | 1,367 | 2.0% de complaints |
| TRX-04 | transactions | `transaction_status = 'Declined' AND product_type IN ('Cuenta Ahorro', 'Cuenta Corriente')` | media | 121,242 | 2.7% de transactions |
| TRX-05 | transactions | `transaction_status = 'Pending' AND product_type IN ('Cuenta Ahorro', 'Cuenta Corriente')` | media | 48,599 | 1.1% de transactions |
| TRX-07 | transactions | `product_type IN ('Cuenta Ahorro', 'Cuenta Corriente')` | baja | 2,240,623 | 50.6% de transactions |
| PRD-04 | products | `product_type IN ('Cuenta Ahorro', 'Cuenta Corriente')` | alta | 220,182 | 55.0% de products |
| DEV-01 | digital_events | `page_url IN ('/payments', '/transfer', '/accounts', '/transactions')` | alta | 3,797,081 | 24.3% de digital_events |

Cobertura del workflow y % AMBIGUO/OTRO por fuente (`03_coverage_summary.csv`) `[medido]`:

| Fuente | % W1_cuentas_pagos | % AMBIGUO | % OTRO |
|---|---|---|---|
| interactions | 35.0 | 22.0 | 18.0 |
| transcripts | 49.9 | 0.0 | 0.0 |
| complaints | 2.0 | 0.0 | 61.5 |
| transactions | 54.5 | 0.0 | 2.0 |
| products | 55.0 | 0.0 | 2.0 |
| digital_events | 24.3 | 5.0 | 55.3 |

Confiabilidad: la plantilla de transcript es independiente del motivo (kappa 0.0003) y de los productos del cliente;
la cobertura de transcripts no tiene sesgo por workflow (p = 0.84). Detalle en `workflow_mapping.md` §5.

## 2. Demanda
Población de contacto: contactos Transaccional (INT-01, confianza media).

- Volumen: **6,661 contactos/mes** (meses completos jul 2023 – may 2026) `[medido]`
  (`04_workflow_scorecard.csv`, `06_cost_by_workflow.csv`).
- Serie mensual: media=6660.9; sd=257.0; cv=0.0386; min=6040; max=7172 `[medido]` (`04_workflow_demand.csv`). Sin tendencia ni estacionalidad material en el
  total del banco (+0.31%/año, IC95 [−0.65, 1.27]; índice mes del año 0.975–1.028), fines de semana a la mitad y
  perfil horario plano 24 h (`02_seasonality_tests.csv`, `01_rows_by_weekday.csv`, `02_hourly_profile.csv`).

| Dimensión | Mezcla (% de la población) |
|---|---|
| channel | Phone 85.0%; Email 4.0%; App 3.9%; Web Chat 3.3%; WhatsApp 3.3%; Web 0.5% |
| interaction_type | Inbound Call 70.0%; Outbound Call 15.0%; Chat 10.0%; Email 4.0%; Video 1.0% |
| country | México 49.9%; Colombia 30.2%; Argentina 19.9% |
| segment | Basic 59.8%; Plus 25.1%; Premium 10.1%; Student 4.9% |

Eventos disparadores asignados a este workflow (`04_trigger_events_summary.csv`, `queries/04_trigger_events_monthly.sql`)
`[medido]`:

| Regla | Condición | Confianza | Media mensual | CV mensual |
|---|---|---|---|---|
| TRX-04 | `transaction_status = 'Declined' AND product_type IN ('Cuenta Ahorro', 'Cuenta Corriente')` | media | 3,364.6 | 0.0316 |
| TRX-05 | `transaction_status = 'Pending' AND product_type IN ('Cuenta Ahorro', 'Cuenta Corriente')` | media | 1,348.1 | 0.0407 |
| TRX-07 | `product_type IN ('Cuenta Ahorro', 'Cuenta Corriente')` | baja | 62,166.2 | 0.0348 |

## 3. Outcomes
Cada métrica con su propio n y denominador; IC95 Wilson (proporciones) o bootstrap 500 réplicas, semilla 42
(medianas, p95, medias). Query: `04_interactions_base.sql` / `04_complaints_base.sql`, módulo `eda/outcomes.py`.
"Total banco" = misma métrica sobre todos los contactos o complaints. "¿Discrimina?" = IC de W1–W4 separados y
diferencia ≥ 2 pp o ≥ 10% relativo (`04_ci_overlap.csv`).

| Métrica | Valor | IC95 | n | Denominador | Total banco | ¿Discrimina? | Etiqueta |
|---|---|---|---|---|---|---|---|
| Volumen mensual de contactos | 6,660.9 | [6,575.70, 6,746.00] | 35 | interacciones con reason_category = Transaccional (INT-01); meses completos jul 2023 – may 2026 | 19,032.60 | sí | medido |
| FCR (%) | 91.5 | [91.40, 91.62] | 240,056 | interacciones con reason_category = Transaccional (INT-01) con was_resolved no nulo | 76.65 | sí | medido |
| % escalado | 9.9 | [9.81, 10.05] | 240,056 | interacciones con reason_category = Transaccional (INT-01) con was_escalated no nulo | 9.96 | no | medido |
| % requiere seguimiento | 22.1 | [21.97, 22.30] | 240,056 | interacciones con reason_category = Transaccional (INT-01) con requires_followup no nulo | 34.83 | sí | medido |
| % sentimiento negativo (derivado) | 0.0 | [-0.00, 0.00] | 240,056 | interacciones con reason_category = Transaccional (INT-01) con detected_sentiment no nulo (label derivado) | 19.24 | sí | medido |
| Duración p50 (min) | 3.42 | [3.38, 3.42] | 206,465 | interacciones con reason_category = Transaccional (INT-01) con duración | 4.85 | sí | medido |
| Duración p95 (min) | 6.80 | [6.65, 6.92] | 206,465 | interacciones con reason_category = Transaccional (INT-01) con duración | 10.23 | sí | medido |
| Espera p50 (min) | 1.98 | [1.97, 2.00] | 168,074 | interacciones con reason_category = Transaccional (INT-01), solo Inbound Call (única con espera) | 1.98 | no | medido |
| Espera p95 (min) | 3.62 | [3.58, 3.63] | 168,074 | interacciones con reason_category = Transaccional (INT-01), solo Inbound Call (única con espera) | 3.63 | no | medido |
| CSAT top = 4 (%) | 13.5 | [13.16, 13.79] | 44,837 | encuestas CSAT de interacciones con reason_category = Transaccional (INT-01); top = 4 (máximo observado) | 11.32 | sí | medido |
| CSAT media (1–4) | 2.91 | [2.90, 2.92] | 44,837 | encuestas CSAT de interacciones con reason_category = Transaccional (INT-01) (escala observada 1–4) | 2.77 | sí | medido |
| NPS | -69.9 | [-70.47, -69.26] | 22,341 | encuestas NPS de interacciones con reason_category = Transaccional (INT-01); sin promotores observados, NPS = −% detractores | -74.51 | sí | medido |
| CES media (1–4) | 2.91 | [2.90, 2.93] | 7,354 | encuestas CES de interacciones con reason_category = Transaccional (INT-01) (escala observada 1–4) | 2.77 | sí | medido |
| Re-contacto 7 días (%) | 2.9 | [2.81, 2.95] | 238,253 | interacciones con reason_category = Transaccional (INT-01) con 7 días de seguimiento completos (antes de 2026-06-10) | 2.88 | no | medido |
| Re-contacto 30 días (%) | 11.9 | [11.73, 11.99] | 233,193 | interacciones con reason_category = Transaccional (INT-01) con 30 días de seguimiento completos (antes de 2026-05-18) | 11.79 | no | medido |
| Volumen mensual de complaints | 37.7 | [35.40, 39.90] | 35 | complaints Fees + Request (CMP-04); meses completos jul 2023 – may 2026 | 1,863.90 | sí | medido |
| % SLA incumplido | 20.4 | [18.36, 22.63] | 1,367 | complaints Fees + Request (CMP-04) con sla_breached no nulo | 20.11 | no | medido |
| Días de resolución p50 | 15.0 | [13.00, 15.00] | 342 | complaints Fees + Request (CMP-04) con resolution_days (resueltos/cerrados) | 16.00 | no | medido |
| Días de resolución p95 | 28.0 | [27.95, 29.00] | 342 | complaints Fees + Request (CMP-04) con resolution_days (resueltos/cerrados) | 29.00 | no | medido |
| % resueltos/cerrados | 25.7 | [23.43, 28.06] | 1,367 | complaints Fees + Request (CMP-04); status Resolved o Closed | 24.03 | no | medido |
| % repetidor | 13.9 | [12.17, 15.83] | 1,367 | complaints Fees + Request (CMP-04) con is_repeat_complainer no nulo | 15.03 | no | medido |
| % con compensación | 29.6 | [25.09, 34.61] | 351 | complaints Fees + Request (CMP-04) resueltos/cerrados; con compensation_granted | 28.79 | no | medido |
| Compensación / reclamado (p50) | n/d | — | 0 | complaints Fees + Request (CMP-04) con compensación y monto reclamado (misma fila, misma moneda) | 0.10 | no evaluable (menos de 2 workflows con dato) | medido |
| Satisfacción con la resolución (media) | 3.22 | [2.88, 3.60] | 63 | complaints Fees + Request (CMP-04) con resolution_satisfaction (96% nulo) | 3.02 | no | medido |

Lectura transversal (`04_discrimination_tests.csv`) `[medido]`: los outcomes de contacto dependen **solo del motivo**
(FCR V de Cramér 0.43, duración ε² 0.48); canal, país, segmento, acento y agente no los mueven (V ≤ 0.008).
Escalamiento, espera, re-contacto y todas las métricas de complaints son planos en todos los cortes.

## 4. Labels, calidad, leakage, baseline y split
Chequeo de señal aprendible (`05_learnable_signal.csv`, módulo `eda/labels.py`, datasets `05_ds_*.sql`) `[medido]`.
Baseline = clase mayoritaria (AUC 0.5). AUC con IC95 Hanley-McNeil; AP vs prevalencia; F1 vs "todo positivo".

| Label | Modelo | AUC [IC95] | AP (prevalencia) | F1 (todo positivo) | Prevalencia test % | Veredicto |
|---|---|---|---|---|---|---|
| interactions.not_resolved | baseline_mayoria | 0.5 [0.5, 0.5] | 0.2335 (0.2335) | 0.0 (todo+ 0.3786) | 23.353 | referencia |
| interactions.not_resolved | regresion_logistica | 0.7626 [0.76, 0.7652] | 0.4754 (0.2335) | 0.5466 (todo+ 0.3786) | 23.353 | señal |
| interactions.not_resolved | arbol_prof4 | 0.7626 [0.76, 0.7651] | 0.4602 (0.2335) | 0.5467 (todo+ 0.3786) | 23.353 | señal |
| interactions.not_resolved | regresion_logistica_solo_motivo | 0.763 [0.7604, 0.7655] | 0.4602 (0.2335) | 0.5467 (todo+ 0.3786) | 23.353 | señal |
| interactions.requires_followup | baseline_mayoria | 0.5 [0.5, 0.5] | 0.348 (0.348) | 0.0 (todo+ 0.5163) | 34.801 | referencia |
| interactions.requires_followup | regresion_logistica | 0.6763 [0.6739, 0.6787] | 0.524 (0.348) | 0.5617 (todo+ 0.5163) | 34.801 | señal |
| interactions.requires_followup | arbol_prof4 | 0.6759 [0.6734, 0.6783] | 0.5089 (0.348) | 0.5618 (todo+ 0.5163) | 34.801 | señal |
| interactions.requires_followup | regresion_logistica_solo_motivo | 0.6763 [0.6739, 0.6788] | 0.5059 (0.348) | 0.5618 (todo+ 0.5163) | 34.801 | señal |
| interactions.was_escalated | baseline_mayoria | 0.5 [0.5, 0.5] | 0.1 (0.1) | 0.0 (todo+ 0.1819) | 10.002 | referencia |
| interactions.was_escalated | regresion_logistica | 0.5013 [0.4973, 0.5053] | 0.1005 (0.1) | 0.1815 (todo+ 0.1819) | 10.002 | ruido |
| interactions.was_escalated | arbol_prof4 | 0.4996 [0.4956, 0.5037] | 0.0999 (0.1) | 0.1819 (todo+ 0.1819) | 10.002 | ruido |
| interactions.was_escalated | regresion_logistica_solo_motivo | 0.5012 [0.4972, 0.5052] | 0.0999 (0.1) | 0.1819 (todo+ 0.1819) | 10.002 | ruido |
| transactions.declined | baseline_mayoria | 0.5 [0.5, 0.5] | 0.0504 (0.0504) | 0.0 (todo+ 0.0961) | 5.045 | referencia |
| transactions.declined | regresion_logistica | 0.5028 [0.4986, 0.5069] | 0.0512 (0.0504) | 0.0959 (todo+ 0.0961) | 5.045 | ruido |
| transactions.declined | arbol_prof4 | 0.5029 [0.4987, 0.507] | 0.0508 (0.0504) | 0.0959 (todo+ 0.0961) | 5.045 | ruido |
| transactions.declined | score_existente_fraud_score | 0.5011 [0.497, 0.5053] | 0.0506 (0.0504) | 0.096 (todo+ 0.0961) | 5.045 | ruido |
| transactions.declined | regresion_logistica_features_mas_fraud_score | 0.5033 [0.4991, 0.5074] | 0.0512 (0.0504) | 0.0952 (todo+ 0.0961) | 5.045 | ruido |

- **Baseline sugerido**: Regla por `reason_category` para FCR/seguimiento (el modelo no la supera). Para el agente: evaluación contra ground truth determinista (saldo, movimientos y estado del pago salen de `transactions`/`products`, consistentes con el dueño del producto al 100%).
- **Split**: Temporal (test desde 2025-07-01) + agrupación por `customer_id` (95.5% de los contactos de test son de clientes vistos en train).

Campos con riesgo de leakage en las tablas de este workflow (`05_leakage_fields.csv`):

| Tabla | Campo | Por qué | Riesgo |
|---|---|---|---|
| call_center_interactions | duration_seconds | Se conoce al terminar el contacto | alto |
| call_center_interactions | detected_sentiment / sentiment_score | Derivado de la llamada completa | alto |
| call_center_interactions | customer_detected_accent / agent_used_accent | Derivado del audio de la llamada | medio |
| call_center_interactions | has_transcript / has_recording | Se decide después del contacto | medio |
| call_center_interactions | reason_category | Se asume conocido al inicio (IVR). Si lo registra el agente al cierre, es leakage | medio (supuesto) |
| transactions | response_code | Resultado de la autorización (explica la declinación) | alto |
| transactions | transaction_status | Resultado; Declined/Reversed son labels | alto |
| transactions | fraud_score | Score de otro modelo; válido en tiempo de autorización pero no es feature propia | medio |
| customers | segment / credit_score / customer_status / estimated_monthly_income | Foto única al corte: estado final, no al momento del evento | alto (W4) / medio |
| products | product_status / days_past_due / current_balance / credit_limit | Foto única al corte; product_status y days_past_due son labels | alto (W2, W4) |
| service_agents | avg_csat / total_monthly_interactions | Agregan outcomes, incluidos futuros | alto |

## 5. Proxies de costo e insumos del business case
Fórmula común a los 4 workflows: ahorro = contactos/mes × % automatizable (cota) × (costo humano − costo IA).
Lo medido es el volumen y el tiempo de atención; el % automatizable es una definición (supuesto) y los costos
unitarios son supuestos con fuente externa (`06_business_case_inputs.csv`, módulo `eda/cost.py`).

- AHT medio: **3.68 min** (duración conocida en 86.0% de los contactos);
  24,515 minutos de atención/mes; espera media (solo Inbound Call)
  1.99 min; 85.0% por teléfono `[medido]`.
- Cota de automatizable seguro: **69.3%** (resuelto, no escalado, sin seguimiento y sin
  complaint del cliente en 30 días) `[supuesto sobre tasas medidas]`.

| Insumo | Escenario | Valor | Etiqueta | Fuente |
|---|---|---|---|---|
| contactos por mes | — | 6,661 | medido | 06_cost_base.sql (eda/cost.py); población: contactos Transaccional (INT-01, confianza media) |
| AHT medio (min) | — | 3.7 | medido | 06_cost_base.sql (eda/cost.py); duration_seconds no nulo (85.992%) |
| minutos de atención por mes | — | 24,515 | medido | 06_cost_base.sql (eda/cost.py); duración media × contactos (imputa el 14.0% sin duración) |
| % automatizable seguro (cota superior) | — | 69.3 | supuesto | 06_cost_base.sql (eda/cost.py); definición: resuelto + no escalado + sin seguimiento + sin complaint en 30 días (la tasa es medida; que eso sea automatizable es supuesto) |
| costo por minuto de agente (USD) | conservador | 0.167 | supuesto | [1] |
| costo por contacto humano (USD) | conservador | 0.61 | proyectado | AHT medio [medido] × costo por minuto [supuesto] |
| costo por contacto con IA (USD) | conservador | 1.84 | supuesto | [2] |
| ahorro mensual (USD) | conservador | -5,662 | proyectado | contactos/mes × % automatizable (cota) × (costo humano − costo IA); negativo = la IA cuesta más |
| ahorro anual (USD) | conservador | -67,941 | proyectado | 12 × ahorro mensual |
| costo por minuto de agente (USD) | base | 0.250 | supuesto | [1] |
| costo por contacto humano (USD) | base | 0.92 | proyectado | AHT medio [medido] × costo por minuto [supuesto] |
| costo por contacto con IA (USD) | base | 1.84 | supuesto | [2] |
| ahorro mensual (USD) | base | -4,246 | proyectado | contactos/mes × % automatizable (cota) × (costo humano − costo IA); negativo = la IA cuesta más |
| ahorro anual (USD) | base | -50,952 | proyectado | 12 × ahorro mensual |
| costo por minuto de agente (USD) | optimista | 0.333 | supuesto | [1] |
| costo por contacto humano (USD) | optimista | 1.23 | proyectado | AHT medio [medido] × costo por minuto [supuesto] |
| costo por contacto con IA (USD) | optimista | 0.50 | supuesto | [2] |
| ahorro mensual (USD) | optimista | 3,355 | proyectado | contactos/mes × % automatizable (cota) × (costo humano − costo IA); negativo = la IA cuesta más |
| ahorro anual (USD) | optimista | 40,260 | proyectado | 12 × ahorro mensual |
| costo por contacto humano (USD) | referencia_global | 13.50 | supuesto | [2] costo asistido global |
| costo por contacto con IA (USD) | referencia_global | 1.84 | supuesto | [2] |
| ahorro mensual (USD) | referencia_global | 53,821 | proyectado | contactos/mes × % automatizable (cota) × (costo humano − costo IA); negativo = la IA cuesta más |
| ahorro anual (USD) | referencia_global | 645,853 | proyectado | 12 × ahorro mensual |

Fuentes de los supuestos:
[1] SkyCom, 'Nearshore Call Center Pricing 2026' (29 jul 2026): contact center en LATAM USD 10–20 por hora de agente (base = punto medio); costo por minuto = tarifa/60, sin ajuste por ocupación. https://www.skycomcallcenter.com/blog/customer-experience-cx/nearshore-call-center-pricing/

[2] Kustomer, glosario 'Cost per contact' (2026): autoservicio USD 1.84 mediana (Gartner), asistido USD 13.50 (Gartner, global), chatbot/IA ~USD 0.50. Fuente secundaria: verificar en la Fase B3 del análisis estratégico. https://www.kustomer.com/glossary/cost-per-contact/

## 6. Vacíos específicos del workflow
- No hay texto real de cliente: los transcripts de W1 son 21 variantes de una sola frase ('saldo actual en mi cuenta de ahorros'), independientes del motivo y de los productos del cliente.
- `products.current_balance` es foto única al corte: no permite responder el saldo a una fecha pasada; el saldo histórico habría que reconstruirlo desde `transactions` (18.7% son anteriores a la apertura del producto: inconsistencia a manejar).
- `amount_usd` es nulo en el 100% de las transacciones en USD y México opera 100% en USD (sin MXN): la conversión de moneda en W1 solo aplica a COP y ARS.
- Sin políticas de comisiones ni de límites de transferencia: hay que crear una base de políticas sintética.
- El motivo `Transaccional` puede incluir movimientos de tarjeta o cargos a disputar; no hay campo que lo distinga (confianza media).

## 7. Exploraciones posibles
| Exploración | Esfuerzo estimado |
|---|---|
| Reconstruir saldo histórico por producto desde `transactions` y medir la inconsistencia con `current_balance` (tool de 'saldo a una fecha'). | medio día |
| Tabla de pagos rechazados/pendientes por cliente y mes como fuente de casos de prueba (normal, ambiguo, requiere humano). | 2–3 horas |
| Set de evaluación ES/PT generado por el equipo sobre consultas de saldo/movimientos, con respuesta esperada calculada desde el dataset. | 1 día |

## 8. Catálogo de plantillas de texto
Plantillas distintas asignadas a este workflow, deduplicadas, sin identificadores (sin `customer_id`,
`interaction_id`, nombres, documentos, emails ni teléfonos), con su frecuencia (`03_template_catalog.csv`,
`queries/03_template_catalog.sql`) `[medido]`. El dataset es 100% sintético y el texto es de plantilla; su uso fuera
del repo queda sujeto a la pregunta 4 de Slack (`04_brechas_y_preguntas.md`).

| Campo | Plantilla | n | % del campo | Distribución por workflow |
|---|---|---|---|---|
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. | 51,189 | 29.9 | W1_cuentas_pagos=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. Claro, estoy para servirle. | 4,282 | 2.5 | W1_cuentas_pagos=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. Perfecto, ¿necesita algo más? | 4,278 | 2.5 | W1_cuentas_pagos=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. Con gusto. ¿Hay algo más en lo que pueda ayudarle? | 4,276 | 2.5 | W1_cuentas_pagos=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. No hay problema, que tenga buen día. | 4,274 | 2.5 | W1_cuentas_pagos=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. Con gusto. ¿Hay algo más en lo que pueda ayudarle? Claro, estoy para servirle. | 1,120 | 0.7 | W1_cuentas_pagos=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. Con gusto. ¿Hay algo más en lo que pueda ayudarle? No hay problema, que tenga buen día. | 1,106 | 0.6 | W1_cuentas_pagos=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. No hay problema, que tenga buen día. Perfecto, ¿necesita algo más? | 1,103 | 0.6 | W1_cuentas_pagos=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. Perfecto, ¿necesita algo más? No hay problema, que tenga buen día. | 1,103 | 0.6 | W1_cuentas_pagos=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. No hay problema, que tenga buen día. Claro, estoy para servirle. | 1,094 | 0.6 | W1_cuentas_pagos=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. Perfecto, ¿necesita algo más? Con gusto. ¿Hay algo más en lo que pueda ayudarle? | 1,089 | 0.6 | W1_cuentas_pagos=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. Claro, estoy para servirle. No hay problema, que tenga buen día. | 1,085 | 0.6 | W1_cuentas_pagos=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. Con gusto. ¿Hay algo más en lo que pueda ayudarle? Perfecto, ¿necesita algo más? | 1,084 | 0.6 | W1_cuentas_pagos=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. Claro, estoy para servirle. Con gusto. ¿Hay algo más en lo que pueda ayudarle? | 1,079 | 0.6 | W1_cuentas_pagos=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. Claro, estoy para servirle. Claro, estoy para servirle. | 1,063 | 0.6 | W1_cuentas_pagos=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. Perfecto, ¿necesita algo más? Claro, estoy para servirle. | 1,053 | 0.6 | W1_cuentas_pagos=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. Con gusto. ¿Hay algo más en lo que pueda ayudarle? Con gusto. ¿Hay algo más en lo que pueda ayudarle? | 1,047 | 0.6 | W1_cuentas_pagos=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. Perfecto, ¿necesita algo más? Perfecto, ¿necesita algo más? | 1,036 | 0.6 | W1_cuentas_pagos=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. No hay problema, que tenga buen día. Con gusto. ¿Hay algo más en lo que pueda ayudarle? | 1,030 | 0.6 | W1_cuentas_pagos=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. No hay problema, que tenga buen día. No hay problema, que tenga buen día. | 1,016 | 0.6 | W1_cuentas_pagos=100.0% |
| call_transcripts.agent_text | Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}. Claro, estoy para servirle. Perfecto, ¿necesita algo más? | 1,004 | 0.6 | W1_cuentas_pagos=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. | 51,189 | 29.9 | W1_cuentas_pagos=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. ¿Y eso cuánto tiempo tarda? | 4,365 | 2.5 | W1_cuentas_pagos=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. Muy bien, ¿hay algo más que deba saber? | 4,315 | 2.5 | W1_cuentas_pagos=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. Perfecto, eso es lo que necesitaba. | 4,258 | 2.5 | W1_cuentas_pagos=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. Entiendo, muchas gracias. | 4,172 | 2.4 | W1_cuentas_pagos=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. Muy bien, ¿hay algo más que deba saber? ¿Y eso cuánto tiempo tarda? | 1,112 | 0.6 | W1_cuentas_pagos=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. Muy bien, ¿hay algo más que deba saber? Entiendo, muchas gracias. | 1,106 | 0.6 | W1_cuentas_pagos=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. ¿Y eso cuánto tiempo tarda? Muy bien, ¿hay algo más que deba saber? | 1,105 | 0.6 | W1_cuentas_pagos=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. Perfecto, eso es lo que necesitaba. Entiendo, muchas gracias. | 1,084 | 0.6 | W1_cuentas_pagos=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. ¿Y eso cuánto tiempo tarda? ¿Y eso cuánto tiempo tarda? | 1,081 | 0.6 | W1_cuentas_pagos=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. Muy bien, ¿hay algo más que deba saber? Perfecto, eso es lo que necesitaba. | 1,080 | 0.6 | W1_cuentas_pagos=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. Entiendo, muchas gracias. Entiendo, muchas gracias. | 1,074 | 0.6 | W1_cuentas_pagos=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. Perfecto, eso es lo que necesitaba. Muy bien, ¿hay algo más que deba saber? | 1,071 | 0.6 | W1_cuentas_pagos=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. Muy bien, ¿hay algo más que deba saber? Muy bien, ¿hay algo más que deba saber? | 1,067 | 0.6 | W1_cuentas_pagos=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. Perfecto, eso es lo que necesitaba. Perfecto, eso es lo que necesitaba. | 1,062 | 0.6 | W1_cuentas_pagos=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. Entiendo, muchas gracias. Muy bien, ¿hay algo más que deba saber? | 1,059 | 0.6 | W1_cuentas_pagos=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. Perfecto, eso es lo que necesitaba. ¿Y eso cuánto tiempo tarda? | 1,059 | 0.6 | W1_cuentas_pagos=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. ¿Y eso cuánto tiempo tarda? Perfecto, eso es lo que necesitaba. | 1,051 | 0.6 | W1_cuentas_pagos=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. ¿Y eso cuánto tiempo tarda? Entiendo, muchas gracias. | 1,042 | 0.6 | W1_cuentas_pagos=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. Entiendo, muchas gracias. ¿Y eso cuánto tiempo tarda? | 1,031 | 0.6 | W1_cuentas_pagos=100.0% |
| call_transcripts.customer_text | Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. Entiendo, muchas gracias. Perfecto, eso es lo que necesitaba. | 1,028 | 0.6 | W1_cuentas_pagos=100.0% |

Comentarios de encuesta (transversales a todos los workflows; `satisfaction_surveys.open_comments`):

| Comentario | n | % de comentarios |
|---|---|---|
| Tardaron mucho en atenderme. | 13,620 | 13.5 |
| No resolvieron mi problema completamente. | 13,546 | 13.4 |
| Tuve que esperar demasiado tiempo. | 13,501 | 13.3 |
| No estoy satisfecho con la solución. | 13,472 | 13.3 |
| El agente no fue muy claro en sus explicaciones. | 13,338 | 13.2 |
| Normal, sin problemas mayores. | 8,975 | 8.9 |
| El servicio estuvo bien. | 8,964 | 8.9 |
| Aceptable. | 8,799 | 8.7 |
| Resolvieron mi problema rápidamente. | 1,442 | 1.4 |
| Muy satisfecho con el servicio. | 1,406 | 1.4 |
| Excelente atención, muy amable el agente. | 1,395 | 1.4 |
| El agente fue muy profesional y eficiente. | 1,394 | 1.4 |
| Buena experiencia, gracias. | 1,344 | 1.3 |
