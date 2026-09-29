# Expediente W3 — Intake de disputas de transacciones

> Documento autocontenido para el Project de claude.ai (EDA del dataset sintético LATAM Bank, Factored AI & Data
> Hackathon 2026). Generado con `python -m eda.report` desde `outputs/tables/`. Cada cifra lleva etiqueta
> (`[medido]` = sale del dataset con la query indicada; `[supuesto]`; `[proyectado]`) y su archivo de query en
> `docs/eda/queries/`. Contexto general: `data_quality.md`, `workflow_mapping.md`, `findings.md`,
> `executive_summary.md`.

## 1. Definición y reglas de mapeo
Recepción de reclamos por cargos no reconocidos, cobros indebidos y fraude: identificar la transacción, verificar, decidir si se automatiza (bloqueo, crédito provisional, caso) o se escala. Tiene la mejor fuente de casos (complaints de 'Cargo no reconocido' y 'Cobro indebido', confianza alta/media) y la única señal casi determinista del dataset (`fraud_score`). A nivel de contacto se aproxima con el motivo `Queja` (confianza baja).

Reglas que alimentan este workflow (`queries/03_workflow_mapping.csv` v1; cobertura `03_coverage_by_rule.csv`)
`[medido]`:

| Regla | Fuente | Condición | Confianza | n | Cobertura |
|---|---|---|---|---|---|
| INT-02 | interactions | `reason_category = 'Queja'` | baja | 117,021 | 17.1% de interactions |
| CMP-01 | complaints | `category = 'Transactions' AND case_type = 'Claim'` | alta | 3,335 | 5.0% de complaints |
| CMP-02 | complaints | `category = 'Transactions' AND case_type IN ('Complaint', 'Request')` | media | 9,568 | 14.3% de complaints |
| CMP-03 | complaints | `category = 'Fees' AND case_type IN ('Claim', 'Complaint')` | media | 11,528 | 17.2% de complaints |
| TRX-01 | transactions | `is_fraud` | alta | 4,316 | 0.1% de transactions |
| TRX-02 | transactions | `transaction_status = 'Reversed'` | media | 44,714 | 1.0% de transactions |

Cobertura del workflow y % AMBIGUO/OTRO por fuente (`03_coverage_summary.csv`) `[medido]`:

| Fuente | % W3_disputas | % AMBIGUO | % OTRO |
|---|---|---|---|
| interactions | 17.1 | 22.0 | 18.0 |
| transcripts | 0.0 | 0.0 | 0.0 |
| complaints | 36.4 | 0.0 | 61.5 |
| transactions | 1.1 | 0.0 | 2.0 |
| products | 0.0 | 0.0 | 2.0 |
| digital_events | 0.0 | 5.0 | 55.3 |

Confiabilidad: la plantilla de transcript es independiente del motivo (kappa 0.0003) y de los productos del cliente;
la cobertura de transcripts no tiene sesgo por workflow (p = 0.84). Detalle en `workflow_mapping.md` §5.

## 2. Demanda
Población de contacto: contactos Queja (INT-02, confianza baja).

- Volumen: **3,241 contactos/mes** (meses completos jul 2023 – may 2026) `[medido]`
  (`04_workflow_scorecard.csv`, `06_cost_by_workflow.csv`).
- Serie mensual: media=3241.3; sd=122.3; cv=0.0377; min=2918; max=3437 `[medido]` (`04_workflow_demand.csv`). Sin tendencia ni estacionalidad material en el
  total del banco (+0.31%/año, IC95 [−0.65, 1.27]; índice mes del año 0.975–1.028), fines de semana a la mitad y
  perfil horario plano 24 h (`02_seasonality_tests.csv`, `01_rows_by_weekday.csv`, `02_hourly_profile.csv`).

| Dimensión | Mezcla (% de la población) |
|---|---|
| channel | Phone 85.1%; Email 4.0%; App 3.8%; Web Chat 3.4%; WhatsApp 3.3%; Web 0.5% |
| interaction_type | Inbound Call 70.3%; Outbound Call 14.8%; Chat 10.0%; Email 4.0%; Video 1.0% |
| country | México 49.9%; Colombia 30.1%; Argentina 20.0% |
| segment | Basic 60.0%; Plus 25.1%; Premium 10.0%; Student 4.9% |

Eventos disparadores asignados a este workflow (`04_trigger_events_summary.csv`, `queries/04_trigger_events_monthly.sql`)
`[medido]`:

| Regla | Condición | Confianza | Media mensual | CV mensual |
|---|---|---|---|---|
| TRX-01 | `is_fraud` | alta | 119.8 | 0.1088 |
| TRX-02 | `transaction_status = 'Reversed'` | media | 1,241.2 | 0.0478 |

## 3. Outcomes
Cada métrica con su propio n y denominador; IC95 Wilson (proporciones) o bootstrap 500 réplicas, semilla 42
(medianas, p95, medias). Query: `04_interactions_base.sql` / `04_complaints_base.sql`, módulo `eda/outcomes.py`.
"Total banco" = misma métrica sobre todos los contactos o complaints. "¿Discrimina?" = IC de W1–W4 separados y
diferencia ≥ 2 pp o ≥ 10% relativo (`04_ci_overlap.csv`).

| Métrica | Valor | IC95 | n | Denominador | Total banco | ¿Discrimina? | Etiqueta |
|---|---|---|---|---|---|---|---|
| Volumen mensual de contactos | 3,241.3 | [3,200.70, 3,281.80] | 35 | interacciones con reason_category = Queja (INT-02); meses completos jul 2023 – may 2026 | 19,032.60 | sí | medido |
| FCR (%) | 43.6 | [43.32, 43.88] | 117,021 | interacciones con reason_category = Queja (INT-02) con was_resolved no nulo | 76.65 | sí | medido |
| % escalado | 10.0 | [9.86, 10.20] | 117,021 | interacciones con reason_category = Queja (INT-02) con was_escalated no nulo | 9.96 | no | medido |
| % requiere seguimiento | 63.0 | [62.69, 63.24] | 117,021 | interacciones con reason_category = Queja (INT-02) con requires_followup no nulo | 34.83 | sí | medido |
| % sentimiento negativo (derivado) | 34.9 | [34.61, 35.16] | 117,021 | interacciones con reason_category = Queja (INT-02) con detected_sentiment no nulo (label derivado) | 19.24 | sí | medido |
| Duración p50 (min) | 7.18 | [7.15, 7.23] | 100,727 | interacciones con reason_category = Queja (INT-02) con duración | 4.85 | sí | medido |
| Duración p95 (min) | 11.05 | [11.02, 11.15] | 100,727 | interacciones con reason_category = Queja (INT-02) con duración | 10.23 | sí | medido |
| Espera p50 (min) | 2.00 | [1.98, 2.02] | 82,261 | interacciones con reason_category = Queja (INT-02), solo Inbound Call (única con espera) | 1.98 | no | medido |
| Espera p95 (min) | 3.65 | [3.63, 3.68] | 82,261 | interacciones con reason_category = Queja (INT-02), solo Inbound Call (única con espera) | 3.63 | no | medido |
| CSAT top = 4 (%) | 6.4 | [6.05, 6.70] | 21,843 | encuestas CSAT de interacciones con reason_category = Queja (INT-02); top = 4 (máximo observado) | 11.32 | sí | medido |
| CSAT media (1–4) | 2.43 | [2.43, 2.45] | 21,843 | encuestas CSAT de interacciones con reason_category = Queja (INT-02) (escala observada 1–4) | 2.77 | sí | medido |
| NPS | -85.3 | [-85.97, -84.64] | 10,821 | encuestas NPS de interacciones con reason_category = Queja (INT-02); sin promotores observados, NPS = −% detractores | -74.51 | sí | medido |
| CES media (1–4) | 2.44 | [2.41, 2.46] | 3,693 | encuestas CES de interacciones con reason_category = Queja (INT-02) (escala observada 1–4) | 2.77 | sí | medido |
| Re-contacto 7 días (%) | 2.9 | [2.79, 2.98] | 116,055 | interacciones con reason_category = Queja (INT-02) con 7 días de seguimiento completos (antes de 2026-06-10) | 2.88 | no | medido |
| Re-contacto 30 días (%) | 11.6 | [11.45, 11.82] | 113,616 | interacciones con reason_category = Queja (INT-02) con 30 días de seguimiento completos (antes de 2026-05-18) | 11.79 | no | medido |
| Volumen mensual de complaints | 678.9 | [669.60, 688.20] | 35 | complaints cargos no reconocidos y cobros indebidos (CMP-01..03); meses completos jul 2023 – may 2026 | 1,863.90 | sí | medido |
| % SLA incumplido | 20.0 | [19.48, 20.48] | 24,431 | complaints cargos no reconocidos y cobros indebidos (CMP-01..03) con sla_breached no nulo | 20.11 | no | medido |
| Días de resolución p50 | 16.0 | [15.00, 16.00] | 5,622 | complaints cargos no reconocidos y cobros indebidos (CMP-01..03) con resolution_days (resueltos/cerrados) | 16.00 | no | medido |
| Días de resolución p95 | 29.0 | [29.00, 29.00] | 5,622 | complaints cargos no reconocidos y cobros indebidos (CMP-01..03) con resolution_days (resueltos/cerrados) | 29.00 | no | medido |
| % resueltos/cerrados | 24.2 | [23.63, 24.70] | 24,431 | complaints cargos no reconocidos y cobros indebidos (CMP-01..03); status Resolved o Closed | 24.03 | no | medido |
| % repetidor | 15.0 | [14.59, 15.49] | 24,431 | complaints cargos no reconocidos y cobros indebidos (CMP-01..03) con is_repeat_complainer no nulo | 15.03 | no | medido |
| % con compensación | 29.5 | [28.38, 30.70] | 5,903 | complaints cargos no reconocidos y cobros indebidos (CMP-01..03) resueltos/cerrados; con compensation_granted | 28.79 | no | medido |
| Compensación / reclamado (p50) | 0.10 | [0.09, 0.11] | 610 | complaints cargos no reconocidos y cobros indebidos (CMP-01..03) con compensación y monto reclamado (misma fila, misma moneda) | 0.10 | no evaluable (menos de 2 workflows con dato) | medido |
| Satisfacción con la resolución (media) | 3.02 | [2.93, 3.12] | 880 | complaints cargos no reconocidos y cobros indebidos (CMP-01..03) con resolution_satisfaction (96% nulo) | 3.02 | no | medido |

Lectura transversal (`04_discrimination_tests.csv`) `[medido]`: los outcomes de contacto dependen **solo del motivo**
(FCR V de Cramér 0.43, duración ε² 0.48); canal, país, segmento, acento y agente no los mueven (V ≤ 0.008).
Escalamiento, espera, re-contacto y todas las métricas de complaints son planos en todos los cortes.

## 4. Labels, calidad, leakage, baseline y split
Chequeo de señal aprendible (`05_learnable_signal.csv`, módulo `eda/labels.py`, datasets `05_ds_*.sql`) `[medido]`.
Baseline = clase mayoritaria (AUC 0.5). AUC con IC95 Hanley-McNeil; AP vs prevalencia; F1 vs "todo positivo".

| Label | Modelo | AUC [IC95] | AP (prevalencia) | F1 (todo positivo) | Prevalencia test % | Veredicto |
|---|---|---|---|---|---|---|
| transactions.is_fraud | baseline_mayoria | 0.5 [0.5, 0.5] | 0.0009 (0.0009) | 0.0 (todo+ 0.0018) | 0.088 | referencia |
| transactions.is_fraud | regresion_logistica | 0.507 [0.4762, 0.5377] | 0.0009 (0.0009) | 0.0018 (todo+ 0.0018) | 0.088 | ruido |
| transactions.is_fraud | arbol_prof4 | 0.5078 [0.477, 0.5385] | 0.0009 (0.0009) | 0.0016 (todo+ 0.0018) | 0.088 | ruido |
| transactions.is_fraud | score_existente_fraud_score | 0.7521 [0.7221, 0.7821] | 0.5217 (0.0009) | 0.0837 (todo+ 0.0018) | 0.088 | señal |
| transactions.is_fraud | regresion_logistica_features_mas_fraud_score | 0.7918 [0.7632, 0.8204] | 0.5007 (0.0009) | 0.0802 (todo+ 0.0018) | 0.088 | señal |
| transactions.reversed | baseline_mayoria | 0.5 [0.5, 0.5] | 0.0099 (0.0099) | 0.0 (todo+ 0.0196) | 0.988 | referencia |
| transactions.reversed | regresion_logistica | 0.4977 [0.4885, 0.5068] | 0.0099 (0.0099) | 0.0193 (todo+ 0.0196) | 0.988 | ruido |
| transactions.reversed | arbol_prof4 | 0.4975 [0.4883, 0.5066] | 0.0099 (0.0099) | 0.0093 (todo+ 0.0196) | 0.988 | ruido |
| transactions.reversed | score_existente_fraud_score | 0.5033 [0.4941, 0.5125] | 0.0099 (0.0099) | 0.0196 (todo+ 0.0196) | 0.988 | ruido |
| transactions.reversed | regresion_logistica_features_mas_fraud_score | 0.4945 [0.4854, 0.5037] | 0.0097 (0.0099) | 0.0194 (todo+ 0.0196) | 0.988 | ruido |
| complaints.sla_breached | baseline_mayoria | 0.5 [0.5, 0.5] | 0.1992 (0.1992) | 0.0 (todo+ 0.3322) | 19.918 | referencia |
| complaints.sla_breached | regresion_logistica | 0.5004 [0.4908, 0.5101] | 0.2006 (0.1992) | 0.3321 (todo+ 0.3322) | 19.918 | ruido |
| complaints.sla_breached | arbol_prof4 | 0.4924 [0.4828, 0.5019] | 0.1966 (0.1992) | 0.3306 (todo+ 0.3322) | 19.918 | ruido |
| interactions.not_resolved | baseline_mayoria | 0.5 [0.5, 0.5] | 0.2335 (0.2335) | 0.0 (todo+ 0.3786) | 23.353 | referencia |
| interactions.not_resolved | regresion_logistica | 0.7626 [0.76, 0.7652] | 0.4754 (0.2335) | 0.5466 (todo+ 0.3786) | 23.353 | señal |
| interactions.not_resolved | arbol_prof4 | 0.7626 [0.76, 0.7651] | 0.4602 (0.2335) | 0.5467 (todo+ 0.3786) | 23.353 | señal |
| interactions.not_resolved | regresion_logistica_solo_motivo | 0.763 [0.7604, 0.7655] | 0.4602 (0.2335) | 0.5467 (todo+ 0.3786) | 23.353 | señal |
| interactions.requires_followup | baseline_mayoria | 0.5 [0.5, 0.5] | 0.348 (0.348) | 0.0 (todo+ 0.5163) | 34.801 | referencia |
| interactions.requires_followup | regresion_logistica | 0.6763 [0.6739, 0.6787] | 0.524 (0.348) | 0.5617 (todo+ 0.5163) | 34.801 | señal |
| interactions.requires_followup | arbol_prof4 | 0.6759 [0.6734, 0.6783] | 0.5089 (0.348) | 0.5618 (todo+ 0.5163) | 34.801 | señal |
| interactions.requires_followup | regresion_logistica_solo_motivo | 0.6763 [0.6739, 0.6788] | 0.5059 (0.348) | 0.5618 (todo+ 0.5163) | 34.801 | señal |

- **Baseline sugerido**: Umbral de `fraud_score`: ≥ 50 marca fraude con 100% de precisión (48.8% de recall); 30–50 es zona gris (79.6% de precisión con ≥ 30). Componente aprendido posible: calibración del triage (automatizar / confirmar / escalar) contra `is_fraud` held-out; el modelo con features + score (AUC 0.79) no mejora de forma significativa al score solo (0.75).
- **Split**: Temporal (transacciones y complaints desde 2025-07-01) + agrupación por `customer_id`.

Campos con riesgo de leakage en las tablas de este workflow (`05_leakage_fields.csv`):

| Tabla | Campo | Por qué | Riesgo |
|---|---|---|---|
| complaints | status / resolution / resolution_date / resolution_days / closing_date | Posteriores al cierre del caso | alto |
| complaints | compensation_granted / resolution_satisfaction | Posteriores al cierre | alto |
| complaints | assignment_date / first_response_date / assigned_agent_id | Posteriores a la creación | medio |
| transactions | response_code | Resultado de la autorización (explica la declinación) | alto |
| transactions | transaction_status | Resultado; Declined/Reversed son labels | alto |
| transactions | fraud_score | Score de otro modelo; válido en tiempo de autorización pero no es feature propia | medio |
| customers | segment / credit_score / customer_status / estimated_monthly_income | Foto única al corte: estado final, no al momento del evento | alto (W4) / medio |

## 5. Proxies de costo e insumos del business case
Fórmula común a los 4 workflows: ahorro = contactos/mes × % automatizable (cota) × (costo humano − costo IA).
Lo medido es el volumen y el tiempo de atención; el % automatizable es una definición (supuesto) y los costos
unitarios son supuestos con fuente externa (`06_business_case_inputs.csv`, módulo `eda/cost.py`).

- AHT medio: **7.24 min** (duración conocida en 86.1% de los contactos);
  23,477 minutos de atención/mes; espera media (solo Inbound Call)
  2.00 min; 85.1% por teléfono `[medido]`.
- Cota de automatizable seguro: **32.8%** (resuelto, no escalado, sin seguimiento y sin
  complaint del cliente en 30 días) `[supuesto sobre tasas medidas]`.

| Insumo | Escenario | Valor | Etiqueta | Fuente |
|---|---|---|---|---|
| contactos por mes | — | 3,241 | medido | 06_cost_base.sql (eda/cost.py); población: contactos Queja (INT-02, confianza baja) |
| AHT medio (min) | — | 7.2 | medido | 06_cost_base.sql (eda/cost.py); duration_seconds no nulo (86.086%) |
| minutos de atención por mes | — | 23,477 | medido | 06_cost_base.sql (eda/cost.py); duración media × contactos (imputa el 13.9% sin duración) |
| % automatizable seguro (cota superior) | — | 32.8 | supuesto | 06_cost_base.sql (eda/cost.py); definición: resuelto + no escalado + sin seguimiento + sin complaint en 30 días (la tasa es medida; que eso sea automatizable es supuesto) |
| costo por minuto de agente (USD) | conservador | 0.167 | supuesto | [1] |
| costo por contacto humano (USD) | conservador | 1.21 | proyectado | AHT medio [medido] × costo por minuto [supuesto] |
| costo por contacto con IA (USD) | conservador | 1.84 | supuesto | [2] |
| ahorro mensual (USD) | conservador | -673 | proyectado | contactos/mes × % automatizable (cota) × (costo humano − costo IA); negativo = la IA cuesta más |
| ahorro anual (USD) | conservador | -8,079 | proyectado | 12 × ahorro mensual |
| costo por minuto de agente (USD) | base | 0.250 | supuesto | [1] |
| costo por contacto humano (USD) | base | 1.81 | proyectado | AHT medio [medido] × costo por minuto [supuesto] |
| costo por contacto con IA (USD) | base | 1.84 | supuesto | [2] |
| ahorro mensual (USD) | base | -31 | proyectado | contactos/mes × % automatizable (cota) × (costo humano − costo IA); negativo = la IA cuesta más |
| ahorro anual (USD) | base | -373 | proyectado | 12 × ahorro mensual |
| costo por minuto de agente (USD) | optimista | 0.333 | supuesto | [1] |
| costo por contacto humano (USD) | optimista | 2.41 | proyectado | AHT medio [medido] × costo por minuto [supuesto] |
| costo por contacto con IA (USD) | optimista | 0.50 | supuesto | [2] |
| ahorro mensual (USD) | optimista | 2,037 | proyectado | contactos/mes × % automatizable (cota) × (costo humano − costo IA); negativo = la IA cuesta más |
| ahorro anual (USD) | optimista | 24,440 | proyectado | 12 × ahorro mensual |
| costo por contacto humano (USD) | referencia_global | 13.50 | supuesto | [2] costo asistido global |
| costo por contacto con IA (USD) | referencia_global | 1.84 | supuesto | [2] |
| ahorro mensual (USD) | referencia_global | 12,405 | proyectado | contactos/mes × % automatizable (cota) × (costo humano − costo IA); negativo = la IA cuesta más |
| ahorro anual (USD) | referencia_global | 148,855 | proyectado | 12 × ahorro mensual |

Fuentes de los supuestos:
[1] SkyCom, 'Nearshore Call Center Pricing 2026' (29 jul 2026): contact center en LATAM USD 10–20 por hora de agente (base = punto medio); costo por minuto = tarifa/60, sin ajuste por ocupación. https://www.skycomcallcenter.com/blog/customer-experience-cx/nearshore-call-center-pricing/

[2] Kustomer, glosario 'Cost per contact' (2026): autoservicio USD 1.84 mediana (Gartner), asistido USD 13.50 (Gartner, global), chatbot/IA ~USD 0.50. Fuente secundaria: verificar en la Fase B3 del análisis estratégico. https://www.kustomer.com/glossary/cost-per-contact/

## 6. Vacíos específicos del workflow
- Complaints no se vincula a la interacción (`origin_interaction_id` 100% nulo) ni a un producto del cliente (`affected_product_id` es de otro cliente en el 100%): la transacción disputada hay que buscarla en `transactions` del propio cliente.
- `description` son 5 plantillas ('Queja relacionada con transactions/fees/...'): no hay relato del cliente.
- `sla_breached` es ~20% en todos los cortes y no depende del tiempo de resolución: no sirve como métrica ni como label.
- `currency` de complaints es independiente del país del cliente y `claimed_amount` no es comparable entre casos; la compensación es ~10% del monto reclamado en todos los casos (regla del generador).
- El 20.6% de los fraudes no tiene `fraud_score`: esos casos no se pueden triagear con la regla.
- Sin marco regulatorio de plazos de disputa por país (define el SLA real): viene del análisis externo.

## 7. Exploraciones posibles
| Exploración | Esfuerzo estimado |
|---|---|
| Vincular cada complaint W3 con transacciones reversadas o fraudulentas del mismo cliente en ±30 días (cuántos casos tendrían transacción identificable). | medio día |
| Curva precisión/recall de `fraud_score` por país, canal y tipo de producto (fairness del triage). | 2–3 horas |
| Diseño y evaluación de la política de triage en 3 zonas con costo de errores (falso positivo = bloqueo innecesario; falso negativo = fraude no atendido). | 1 día |

## 8. Catálogo de plantillas de texto
Plantillas distintas asignadas a este workflow, deduplicadas, sin identificadores (sin `customer_id`,
`interaction_id`, nombres, documentos, emails ni teléfonos), con su frecuencia (`03_template_catalog.csv`,
`queries/03_template_catalog.sql`) `[medido]`. El dataset es 100% sintético y el texto es de plantilla; su uso fuera
del repo queda sujeto a la pregunta 4 de Slack (`04_brechas_y_preguntas.md`).

| Campo | Plantilla | n | % del campo | Distribución por workflow |
|---|---|---|---|---|
| complaints.description | Queja relacionada con transactions | 13,580 | 20.2 | W3_disputas=95.0%; OTRO=5.0% |
| complaints.description | Queja relacionada con fees | 13,553 | 20.2 | W3_disputas=85.1%; W1_cuentas_pagos=10.1%; OTRO=4.9% |

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
