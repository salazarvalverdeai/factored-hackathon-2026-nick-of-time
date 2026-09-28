# Expediente W4 — Información y elegibilidad de productos de crédito

> Documento autocontenido para el Project de claude.ai (EDA del dataset sintético LATAM Bank, Factored AI & Data
> Hackathon 2026). Generado con `python -m eda.report` desde `outputs/tables/`. Cada cifra lleva etiqueta
> (`[medido]` = sale del dataset con la query indicada; `[supuesto]`; `[proyectado]`) y su archivo de query en
> `docs/eda/queries/`. Contexto general: `calidad_datos.md`, `mapeo_workflows.md`, `findings.md`,
> `resumen_ejecutivo.md`.

## 1. Definición y reglas de mapeo
Información de productos de crédito y pre-elegibilidad (tarjeta de crédito, préstamo personal, hipotecario) con una política de reglas explícita; el reto prohíbe que el LLM invente reglas o apruebe crédito. A nivel de contacto se aproxima con el motivo `Comercial` (confianza baja); no tiene complaints ni texto propios.

Reglas que alimentan este workflow (`queries/03_workflow_mapping.csv` v1; cobertura `03_coverage_by_rule.csv`)
`[medido]`:

| Regla | Fuente | Condición | Confianza | n | Cobertura |
|---|---|---|---|---|---|
| INT-03 | interactions | `reason_category = 'Comercial'` | baja | 54,879 | 8.0% de interactions |
| TRX-08 | transactions | `product_type IN ('Préstamo Personal', 'Préstamo Hipotecario')` | baja | 348,631 | 7.9% de transactions |
| PRD-03 | products | `product_type IN ('Préstamo Personal', 'Préstamo Hipotecario')` | alta | 31,870 | 8.0% de products |
| DEV-03 | digital_events | `page_url = '/products/loans'` | alta | 1,199,796 | 7.7% de digital_events |

Cobertura del workflow y % AMBIGUO/OTRO por fuente (`03_coverage_summary.csv`) `[medido]`:

| Fuente | % W4_credito | % AMBIGUO | % OTRO |
|---|---|---|---|
| interactions | 8.0 | 22.0 | 18.0 |
| transcripts | 0.0 | 0.0 | 0.0 |
| complaints | 0.0 | 0.0 | 61.5 |
| transactions | 7.9 | 0.0 | 2.0 |
| products | 8.0 | 0.0 | 2.0 |
| digital_events | 7.7 | 5.0 | 55.3 |

Confiabilidad: la plantilla de transcript es independiente del motivo (kappa 0.0003) y de los productos del cliente;
la cobertura de transcripts no tiene sesgo por workflow (p = 0.84). Detalle en `mapeo_workflows.md` §5.

## 2. Demanda
Población de contacto: contactos Comercial (INT-03, confianza baja).

- Volumen: **1,524 contactos/mes** (meses completos jul 2023 – may 2026) `[medido]`
  (`04_workflow_scorecard.csv`, `06_cost_by_workflow.csv`).
- Serie mensual: media=1523.7; sd=61.1; cv=0.0401; min=1361; max=1623 `[medido]` (`04_workflow_demand.csv`). Sin tendencia ni estacionalidad material en el
  total del banco (+0.31%/año, IC95 [−0.65, 1.27]; índice mes del año 0.975–1.028), fines de semana a la mitad y
  perfil horario plano 24 h (`02_seasonality_tests.csv`, `01_rows_by_weekday.csv`, `02_hourly_profile.csv`).

| Dimensión | Mezcla (% de la población) |
|---|---|
| channel | Phone 84.8%; Email 4.0%; App 3.8%; Web Chat 3.5%; WhatsApp 3.4%; Web 0.5% |
| interaction_type | Inbound Call 69.9%; Outbound Call 15.0%; Chat 10.2%; Email 4.0%; Video 1.0% |
| country | México 50.4%; Colombia 30.1%; Argentina 19.6% |
| segment | Basic 60.0%; Plus 25.1%; Premium 9.9%; Student 5.0% |

Eventos disparadores asignados a este workflow (`04_trigger_events_summary.csv`, `queries/04_trigger_events_monthly.sql`)
`[medido]`:

| Regla | Condición | Confianza | Media mensual | CV mensual |
|---|---|---|---|---|
| TRX-08 | `product_type IN ('Préstamo Personal', 'Préstamo Hipotecario')` | baja | 9,670.5 | 0.035 |

Cartera de crédito al corte (`04_products_by_status.csv`, foto única):

| Tipo | Estado | n | con days_past_due > 0 | con days_past_due conocido |
|---|---|---|---|---|
| Préstamo Hipotecario | Active | 10,157 | 1,445 | 9,663 |
| Préstamo Hipotecario | Blocked | 612 | 112 | 577 |
| Préstamo Hipotecario | Closed | 912 | 130 | 868 |
| Préstamo Hipotecario | Suspended | 229 | 36 | 216 |
| Préstamo Personal | Active | 16,977 | 2,405 | 16,147 |
| Préstamo Personal | Blocked | 1,010 | 132 | 957 |
| Préstamo Personal | Closed | 1,585 | 234 | 1,517 |
| Préstamo Personal | Suspended | 388 | 69 | 372 |
| Tarjeta Crédito | Active | 85,090 | 12,039 | 80,786 |
| Tarjeta Crédito | Blocked | 4,932 | 718 | 4,689 |
| Tarjeta Crédito | Closed | 8,053 | 1,150 | 7,639 |
| Tarjeta Crédito | Suspended | 2,027 | 295 | 1,919 |

## 3. Outcomes
Cada métrica con su propio n y denominador; IC95 Wilson (proporciones) o bootstrap 500 réplicas, semilla 42
(medianas, p95, medias). Query: `04_interactions_base.sql` / `04_complaints_base.sql`, módulo `eda/outcomes.py`.
"Total banco" = misma métrica sobre todos los contactos o complaints. "¿Discrimina?" = IC de W1–W4 separados y
diferencia ≥ 2 pp o ≥ 10% relativo (`04_ci_overlap.csv`).

| Métrica | Valor | IC95 | n | Denominador | Total banco | ¿Discrimina? | Etiqueta |
|---|---|---|---|---|---|---|---|
| Volumen mensual de contactos | 1,523.7 | [1,503.40, 1,543.90] | 35 | interacciones con reason_category = Comercial (INT-03); meses completos jul 2023 – may 2026 | 19,032.60 | sí | medido |
| FCR (%) | 65.2 | [64.81, 65.61] | 54,879 | interacciones con reason_category = Comercial (INT-03) con was_resolved no nulo | 76.65 | sí | medido |
| % escalado | 9.8 | [9.59, 10.09] | 54,879 | interacciones con reason_category = Comercial (INT-03) con was_escalated no nulo | 9.96 | no | medido |
| % requiere seguimiento | 44.5 | [44.13, 44.96] | 54,879 | interacciones con reason_category = Comercial (INT-03) con requires_followup no nulo | 34.83 | sí | medido |
| % sentimiento negativo (derivado) | 34.9 | [34.47, 35.27] | 54,879 | interacciones con reason_category = Comercial (INT-03) con detected_sentiment no nulo (label derivado) | 19.24 | sí | medido |
| Duración p50 (min) | 9.00 | [8.98, 9.08] | 47,082 | interacciones con reason_category = Comercial (INT-03) con duración | 4.85 | sí | medido |
| Duración p95 (min) | 13.47 | [13.42, 13.58] | 47,082 | interacciones con reason_category = Comercial (INT-03) con duración | 10.23 | sí | medido |
| Espera p50 (min) | 2.00 | [1.97, 2.00] | 38,338 | interacciones con reason_category = Comercial (INT-03), solo Inbound Call (única con espera) | 1.98 | no | medido |
| Espera p95 (min) | 3.63 | [3.62, 3.68] | 38,338 | interacciones con reason_category = Comercial (INT-03), solo Inbound Call (única con espera) | 3.63 | no | medido |
| CSAT top = 4 (%) | 9.7 | [9.17, 10.32] | 10,243 | encuestas CSAT de interacciones con reason_category = Comercial (INT-03); top = 4 (máximo observado) | 11.32 | sí | medido |
| CSAT media (1–4) | 2.66 | [2.65, 2.67] | 10,243 | encuestas CSAT de interacciones con reason_category = Comercial (INT-03) (escala observada 1–4) | 2.77 | sí | medido |
| NPS | -78.4 | [-79.47, -77.22] | 5,144 | encuestas NPS de interacciones con reason_category = Comercial (INT-03); sin promotores observados, NPS = −% detractores | -74.51 | sí | medido |
| CES media (1–4) | 2.67 | [2.63, 2.70] | 1,760 | encuestas CES de interacciones con reason_category = Comercial (INT-03) (escala observada 1–4) | 2.77 | sí | medido |
| Re-contacto 7 días (%) | 2.9 | [2.75, 3.03] | 54,464 | interacciones con reason_category = Comercial (INT-03) con 7 días de seguimiento completos (antes de 2026-06-10) | 2.88 | no | medido |
| Re-contacto 30 días (%) | 11.7 | [11.44, 11.99] | 53,325 | interacciones con reason_category = Comercial (INT-03) con 30 días de seguimiento completos (antes de 2026-05-18) | 11.79 | no | medido |
| Volumen mensual de complaints | n/d | — | 0 | sin complaints asignables a este workflow (mapeo_workflows.md §3) | 1,863.90 | sí | vacío |
| % SLA incumplido | n/d | — | 0 | sin complaints asignables a este workflow (mapeo_workflows.md §3) | 20.11 | no | vacío |
| Días de resolución p50 | n/d | — | 0 | sin complaints asignables a este workflow (mapeo_workflows.md §3) | 16.00 | no | vacío |
| Días de resolución p95 | n/d | — | 0 | sin complaints asignables a este workflow (mapeo_workflows.md §3) | 29.00 | no | vacío |
| % resueltos/cerrados | n/d | — | 0 | sin complaints asignables a este workflow (mapeo_workflows.md §3) | 24.03 | no | vacío |

Lectura transversal (`04_discrimination_tests.csv`) `[medido]`: los outcomes de contacto dependen **solo del motivo**
(FCR V de Cramér 0.43, duración ε² 0.48); canal, país, segmento, acento y agente no los mueven (V ≤ 0.008).
Escalamiento, espera, re-contacto y todas las métricas de complaints son planos en todos los cortes.

## 4. Labels, calidad, leakage, baseline y split
Chequeo de señal aprendible (`05_learnable_signal.csv`, módulo `eda/labels.py`, datasets `05_ds_*.sql`) `[medido]`.
Baseline = clase mayoritaria (AUC 0.5). AUC con IC95 Hanley-McNeil; AP vs prevalencia; F1 vs "todo positivo".

| Label | Modelo | AUC [IC95] | AP (prevalencia) | F1 (todo positivo) | Prevalencia test % | Veredicto |
|---|---|---|---|---|---|---|
| products.past_due_credit | baseline_mayoria | 0.5 [0.5, 0.5] | 0.1502 (0.1502) | 0.0 (todo+ 0.2612) | 15.022 | referencia |
| products.past_due_credit | regresion_logistica | 0.4961 [0.4881, 0.5042] | 0.1491 (0.1502) | 0.2606 (todo+ 0.2612) | 15.022 | ruido |
| products.past_due_credit | arbol_prof4 | 0.4966 [0.4885, 0.5047] | 0.1494 (0.1502) | 0.2583 (todo+ 0.2612) | 15.022 | ruido |
| interactions.not_resolved | baseline_mayoria | 0.5 [0.5, 0.5] | 0.2335 (0.2335) | 0.0 (todo+ 0.3786) | 23.353 | referencia |
| interactions.not_resolved | regresion_logistica | 0.7626 [0.76, 0.7652] | 0.4754 (0.2335) | 0.5466 (todo+ 0.3786) | 23.353 | señal |
| interactions.not_resolved | arbol_prof4 | 0.7626 [0.76, 0.7651] | 0.4602 (0.2335) | 0.5467 (todo+ 0.3786) | 23.353 | señal |
| interactions.not_resolved | regresion_logistica_solo_motivo | 0.763 [0.7604, 0.7655] | 0.4602 (0.2335) | 0.5467 (todo+ 0.3786) | 23.353 | señal |
| interactions.was_escalated | baseline_mayoria | 0.5 [0.5, 0.5] | 0.1 (0.1) | 0.0 (todo+ 0.1819) | 10.002 | referencia |
| interactions.was_escalated | regresion_logistica | 0.5013 [0.4973, 0.5053] | 0.1005 (0.1) | 0.1815 (todo+ 0.1819) | 10.002 | ruido |
| interactions.was_escalated | arbol_prof4 | 0.4996 [0.4956, 0.5037] | 0.0999 (0.1) | 0.1819 (todo+ 0.1819) | 10.002 | ruido |
| interactions.was_escalated | regresion_logistica_solo_motivo | 0.5012 [0.4972, 0.5052] | 0.0999 (0.1) | 0.1819 (todo+ 0.1819) | 10.002 | ruido |

- **Baseline sugerido**: Política de reglas sintética y versionada (el reto la exige). No hay estimación de riesgo que demostrar: la mora (`days_past_due` > 0) no se puede predecir con las features disponibles (AUC 0.497). El componente aprendido, si lo hay, no está en el riesgo.
- **Split**: Por fecha de apertura del producto (test desde 2024-01-01); foto única de customers y products.

Campos con riesgo de leakage en las tablas de este workflow (`05_leakage_fields.csv`):

| Tabla | Campo | Por qué | Riesgo |
|---|---|---|---|
| customers | segment / credit_score / customer_status / estimated_monthly_income | Foto única al corte: estado final, no al momento del evento | alto (W4) / medio |
| products | product_status / days_past_due / current_balance / credit_limit | Foto única al corte; product_status y days_past_due son labels | alto (W2, W4) |

## 5. Proxies de costo e insumos del business case
Fórmula común a los 4 workflows: ahorro = contactos/mes × % automatizable (cota) × (costo humano − costo IA).
Lo medido es el volumen y el tiempo de atención; el % automatizable es una definición (supuesto) y los costos
unitarios son supuestos con fuente externa (`06_business_case_inputs.csv`, módulo `eda/cost.py`).

- AHT medio: **9.00 min** (duración conocida en 85.8% de los contactos);
  13,711 minutos de atención/mes; espera media (solo Inbound Call)
  2.00 min; 84.8% por teléfono `[medido]`.
- Cota de automatizable seguro: **49.4%** (resuelto, no escalado, sin seguimiento y sin
  complaint del cliente en 30 días) `[supuesto sobre tasas medidas]`.

| Insumo | Escenario | Valor | Etiqueta | Fuente |
|---|---|---|---|---|
| contactos por mes | — | 1,524 | medido | 06_cost_base.sql (eda/cost.py); población: contactos Comercial (INT-03, confianza baja) |
| AHT medio (min) | — | 9.0 | medido | 06_cost_base.sql (eda/cost.py); duration_seconds no nulo (85.784%) |
| minutos de atención por mes | — | 13,711 | medido | 06_cost_base.sql (eda/cost.py); duración media × contactos (imputa el 14.2% sin duración) |
| % automatizable seguro (cota superior) | — | 49.4 | supuesto | 06_cost_base.sql (eda/cost.py); definición: resuelto + no escalado + sin seguimiento + sin complaint en 30 días (la tasa es medida; que eso sea automatizable es supuesto) |
| costo por minuto de agente (USD) | conservador | 0.167 | supuesto | [1] |
| costo por contacto humano (USD) | conservador | 1.50 | proyectado | AHT medio [medido] × costo por minuto [supuesto] |
| costo por contacto con IA (USD) | conservador | 1.84 | supuesto | [2] |
| ahorro mensual (USD) | conservador | -256 | proyectado | contactos/mes × % automatizable (cota) × (costo humano − costo IA); negativo = la IA cuesta más |
| ahorro anual (USD) | conservador | -3,070 | proyectado | 12 × ahorro mensual |
| costo por minuto de agente (USD) | base | 0.250 | supuesto | [1] |
| costo por contacto humano (USD) | base | 2.25 | proyectado | AHT medio [medido] × costo por minuto [supuesto] |
| costo por contacto con IA (USD) | base | 1.84 | supuesto | [2] |
| ahorro mensual (USD) | base | 308 | proyectado | contactos/mes × % automatizable (cota) × (costo humano − costo IA); negativo = la IA cuesta más |
| ahorro anual (USD) | base | 3,697 | proyectado | 12 × ahorro mensual |
| costo por minuto de agente (USD) | optimista | 0.333 | supuesto | [1] |
| costo por contacto humano (USD) | optimista | 3.00 | proyectado | AHT medio [medido] × costo por minuto [supuesto] |
| costo por contacto con IA (USD) | optimista | 0.50 | supuesto | [2] |
| ahorro mensual (USD) | optimista | 1,880 | proyectado | contactos/mes × % automatizable (cota) × (costo humano − costo IA); negativo = la IA cuesta más |
| ahorro anual (USD) | optimista | 22,556 | proyectado | 12 × ahorro mensual |
| costo por contacto humano (USD) | referencia_global | 13.50 | supuesto | [2] costo asistido global |
| costo por contacto con IA (USD) | referencia_global | 1.84 | supuesto | [2] |
| ahorro mensual (USD) | referencia_global | 8,768 | proyectado | contactos/mes × % automatizable (cota) × (costo humano − costo IA); negativo = la IA cuesta más |
| ahorro anual (USD) | referencia_global | 105,217 | proyectado | 12 × ahorro mensual |

Fuentes de los supuestos:
[1] SkyCom, 'Nearshore Call Center Pricing 2026' (29 jul 2026): contact center en LATAM USD 10–20 por hora de agente (base = punto medio); costo por minuto = tarifa/60, sin ajuste por ocupación. https://www.skycomcallcenter.com/blog/customer-experience-cx/nearshore-call-center-pricing/

[2] Kustomer, glosario 'Cost per contact' (2026): autoservicio USD 1.84 mediana (Gartner), asistido USD 13.50 (Gartner, global), chatbot/IA ~USD 0.50. Fuente secundaria: verificar en la Fase B3 del análisis estratégico. https://www.kustomer.com/glossary/cost-per-contact/

## 6. Vacíos específicos del workflow
- Sin historia de `credit_score`, ingreso ni mora: la foto única al corte impide saber el estado al momento de una solicitud (leakage directo si se usa como feature o label).
- `credit_score` 15.0% nulo y `estimated_monthly_income` 20.0% nulo (aleatorios): el flujo debe manejar datos faltantes y derivar a revisión humana.
- Sin solicitudes de crédito, aprobaciones ni rechazos: no hay outcome de elegibilidad.
- Sin política de crédito: toda regla será sintética y debe etiquetarse como tal.
- Contactos `Comercial` incluyen ahorro e inversión; no hay producto por interacción.

## 7. Exploraciones posibles
| Exploración | Esfuerzo estimado |
|---|---|
| Diseñar la política sintética de pre-elegibilidad y medir cuántos clientes caen en 'aprobable', 'rechazable' y 'revisión por datos faltantes'. | medio día |
| Distribución de `credit_limit` e `interest_rate` por segmento y país como insumo de respuestas informativas. | 2 horas |
| Casos de prueba de borde (score nulo, ingreso nulo, mora) para demostrar abstención y handoff. | medio día |

## 8. Catálogo de plantillas de texto
Plantillas distintas asignadas a este workflow, deduplicadas, sin identificadores (sin `customer_id`,
`interaction_id`, nombres, documentos, emails ni teléfonos), con su frecuencia (`03_template_catalog.csv`,
`queries/03_template_catalog.sql`) `[medido]`. El dataset es 100% sintético y el texto es de plantilla; su uso fuera
del repo queda sujeto a la pregunta 4 de Slack (`04_brechas_y_preguntas.md`).

No hay plantillas de texto asignadas a este workflow: ni transcripts ni complaints caen en él.

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
