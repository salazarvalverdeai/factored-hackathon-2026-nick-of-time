# Expediente W2 — Soporte de tarjetas

> Documento autocontenido para el Project de claude.ai (EDA del dataset sintético LATAM Bank, Factored AI & Data
> Hackathon 2026). Generado con `python -m eda.report` desde `outputs/tables/`. Cada cifra lleva etiqueta
> (`[medido]` = sale del dataset con la query indicada; `[supuesto]`; `[proyectado]`) y su archivo de query en
> `docs/eda/queries/`. Contexto general: `calidad_datos.md`, `mapeo_workflows.md`, `findings.md`,
> `resumen_ejecutivo.md`.

## 1. Definición y reglas de mapeo
Consultas y problemas con tarjetas de crédito y débito: declinaciones, bloqueos, saldo y límite disponible. **No tiene regla a nivel de contacto**: su población de contacto sale de la plantilla de transcript 'saldo de mi tarjeta de crédito' (confianza media, texto independiente de todo). Sus señales reales son eventos: declinaciones con `response_code` y tarjetas bloqueadas.

Reglas que alimentan este workflow (`queries/03_workflow_mapping.csv` v1; cobertura `03_coverage_by_rule.csv`)
`[medido]`:

| Regla | Fuente | Condición | Confianza | n | Cobertura |
|---|---|---|---|---|---|
| TRS-02 | transcripts | `customer_text LIKE '%tarjeta de crédito%'` | media | 85,910 | 50.1% de transcripts |
| TRX-03 | transactions | `transaction_status = 'Declined' AND product_type IN ('Tarjeta Crédito', 'Tarjeta Débito')` | alta | 77,641 | 1.8% de transactions |
| TRX-06 | transactions | `product_type IN ('Tarjeta Crédito', 'Tarjeta Débito')` | baja | 1,452,465 | 32.8% de transactions |
| PRD-01 | products | `product_type IN ('Tarjeta Crédito', 'Tarjeta Débito') AND product_status = 'Blocked'` | alta | 7,044 | 1.8% de products |
| PRD-02 | products | `product_type IN ('Tarjeta Crédito', 'Tarjeta Débito')` | alta | 132,996 | 33.2% de products |
| DEV-02 | digital_events | `page_url = '/products/credit-card'` | media | 1,198,674 | 7.7% de digital_events |

Cobertura del workflow y % AMBIGUO/OTRO por fuente (`03_coverage_summary.csv`) `[medido]`:

| Fuente | % W2_tarjetas | % AMBIGUO | % OTRO |
|---|---|---|---|
| interactions | 0.0 | 22.0 | 18.0 |
| transcripts | 50.1 | 0.0 | 0.0 |
| complaints | 0.0 | 0.0 | 61.5 |
| transactions | 34.6 | 0.0 | 2.0 |
| products | 35.0 | 0.0 | 2.0 |
| digital_events | 7.7 | 5.0 | 55.3 |

Confiabilidad: la plantilla de transcript es independiente del motivo (kappa 0.0003) y de los productos del cliente;
la cobertura de transcripts no tiene sesgo por workflow (p = 0.84). Detalle en `mapeo_workflows.md` §5.

## 2. Demanda
Población de contacto: contactos con transcript de saldo de tarjeta (TRS-02; texto no confiable, solo 25% tiene transcript).

- Volumen: **2,383 contactos/mes** (meses completos jul 2023 – may 2026) `[medido]`
  (`04_workflow_scorecard.csv`, `06_cost_by_workflow.csv`).
- Serie mensual: media=2382.7; sd=96.4; cv=0.0405; min=2094; max=2631 `[medido]` (`04_workflow_demand.csv`). Sin tendencia ni estacionalidad material en el
  total del banco (+0.31%/año, IC95 [−0.65, 1.27]; índice mes del año 0.975–1.028), fines de semana a la mitad y
  perfil horario plano 24 h (`02_seasonality_tests.csv`, `01_rows_by_weekday.csv`, `02_hourly_profile.csv`).

| Dimensión | Mezcla (% de la población) |
|---|---|
| channel | Phone 84.9%; Email 4.2%; App 3.8%; WhatsApp 3.4%; Web Chat 3.3%; Web 0.5% |
| interaction_type | Inbound Call 70.1%; Outbound Call 14.8%; Chat 9.9%; Email 4.2%; Video 1.0% |
| country | México 50.0%; Colombia 30.0%; Argentina 20.0% |
| segment | Basic 59.8%; Plus 24.9%; Premium 10.1%; Student 5.1% |

Eventos disparadores asignados a este workflow (`04_trigger_events_summary.csv`, `queries/04_trigger_events_monthly.sql`)
`[medido]`:

| Regla | Condición | Confianza | Media mensual | CV mensual |
|---|---|---|---|---|
| TRX-03 | `transaction_status = 'Declined' AND product_type IN ('Tarjeta Crédito', 'Tarjeta Débito')` | alta | 2,156.3 | 0.0397 |
| TRX-06 | `product_type IN ('Tarjeta Crédito', 'Tarjeta Débito')` | baja | 40,304.3 | 0.0333 |

Cartera de tarjetas al corte (`04_products_by_status.csv`, foto única):

| Tipo | Estado | n |
|---|---|---|
| Tarjeta Crédito | Active | 85,090 |
| Tarjeta Crédito | Blocked | 4,932 |
| Tarjeta Crédito | Closed | 8,053 |
| Tarjeta Crédito | Suspended | 2,027 |
| Tarjeta Débito | Active | 33,749 |
| Tarjeta Débito | Blocked | 2,112 |
| Tarjeta Débito | Closed | 3,244 |
| Tarjeta Débito | Suspended | 833 |

## 3. Outcomes
Cada métrica con su propio n y denominador; IC95 Wilson (proporciones) o bootstrap 500 réplicas, semilla 42
(medianas, p95, medias). Query: `04_interactions_base.sql` / `04_complaints_base.sql`, módulo `eda/outcomes.py`.
"Total banco" = misma métrica sobre todos los contactos o complaints. "¿Discrimina?" = IC de W1–W4 separados y
diferencia ≥ 2 pp o ≥ 10% relativo (`04_ci_overlap.csv`).

| Métrica | Valor | IC95 | n | Denominador | Total banco | ¿Discrimina? | Etiqueta |
|---|---|---|---|---|---|---|---|
| Volumen mensual de contactos | 2,382.7 | [2,350.80, 2,414.70] | 35 | interacciones con transcript de saldo de tarjeta (TRS-02); meses completos jul 2023 – may 2026 | 19,032.60 | sí | medido |
| FCR (%) | 76.6 | [76.28, 76.85] | 85,910 | interacciones con transcript de saldo de tarjeta (TRS-02) con was_resolved no nulo | 76.65 | sí | medido |
| % escalado | 9.9 | [9.75, 10.15] | 85,910 | interacciones con transcript de saldo de tarjeta (TRS-02) con was_escalated no nulo | 9.96 | no | medido |
| % requiere seguimiento | 34.9 | [34.58, 35.22] | 85,910 | interacciones con transcript de saldo de tarjeta (TRS-02) con requires_followup no nulo | 34.83 | sí | medido |
| % sentimiento negativo (derivado) | 19.5 | [19.27, 19.80] | 85,910 | interacciones con transcript de saldo de tarjeta (TRS-02) con detected_sentiment no nulo (label derivado) | 19.24 | sí | medido |
| Duración p50 (min) | 4.85 | [4.80, 4.88] | 73,812 | interacciones con transcript de saldo de tarjeta (TRS-02) con duración | 4.85 | sí | medido |
| Duración p95 (min) | 10.27 | [10.20, 10.45] | 73,812 | interacciones con transcript de saldo de tarjeta (TRS-02) con duración | 10.23 | sí | medido |
| Espera p50 (min) | 1.98 | [1.97, 2.00] | 60,211 | interacciones con transcript de saldo de tarjeta (TRS-02), solo Inbound Call (única con espera) | 1.98 | no | medido |
| Espera p95 (min) | 3.63 | [3.60, 3.66] | 60,211 | interacciones con transcript de saldo de tarjeta (TRS-02), solo Inbound Call (única con espera) | 3.63 | no | medido |
| CSAT top = 4 (%) | 11.3 | [10.85, 11.83] | 16,173 | encuestas CSAT de interacciones con transcript de saldo de tarjeta (TRS-02); top = 4 (máximo observado) | 11.32 | sí | medido |
| CSAT media (1–4) | 2.77 | [2.76, 2.78] | 16,173 | encuestas CSAT de interacciones con transcript de saldo de tarjeta (TRS-02) (escala observada 1–4) | 2.77 | sí | medido |
| NPS | -73.9 | [-74.81, -72.87] | 7,860 | encuestas NPS de interacciones con transcript de saldo de tarjeta (TRS-02); sin promotores observados, NPS = −% detractores | -74.51 | sí | medido |
| CES media (1–4) | 2.75 | [2.72, 2.78] | 2,729 | encuestas CES de interacciones con transcript de saldo de tarjeta (TRS-02) (escala observada 1–4) | 2.77 | sí | medido |
| Re-contacto 7 días (%) | 2.8 | [2.70, 2.92] | 85,222 | interacciones con transcript de saldo de tarjeta (TRS-02) con 7 días de seguimiento completos (antes de 2026-06-10) | 2.88 | no | medido |
| Re-contacto 30 días (%) | 11.7 | [11.49, 11.92] | 83,441 | interacciones con transcript de saldo de tarjeta (TRS-02) con 30 días de seguimiento completos (antes de 2026-05-18) | 11.79 | no | medido |
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
| transactions.declined | baseline_mayoria | 0.5 [0.5, 0.5] | 0.0504 (0.0504) | 0.0 (todo+ 0.0961) | 5.045 | referencia |
| transactions.declined | regresion_logistica | 0.5028 [0.4986, 0.5069] | 0.0512 (0.0504) | 0.0959 (todo+ 0.0961) | 5.045 | ruido |
| transactions.declined | arbol_prof4 | 0.5029 [0.4987, 0.507] | 0.0508 (0.0504) | 0.0959 (todo+ 0.0961) | 5.045 | ruido |
| transactions.declined | score_existente_fraud_score | 0.5011 [0.497, 0.5053] | 0.0506 (0.0504) | 0.096 (todo+ 0.0961) | 5.045 | ruido |
| transactions.declined | regresion_logistica_features_mas_fraud_score | 0.5033 [0.4991, 0.5074] | 0.0512 (0.0504) | 0.0952 (todo+ 0.0961) | 5.045 | ruido |
| products.blocked_card | baseline_mayoria | 0.5 [0.5, 0.5] | 0.05 (0.05) | 0.0 (todo+ 0.0952) | 4.997 | referencia |
| products.blocked_card | regresion_logistica | 0.505 [0.4924, 0.5176] | 0.0505 (0.05) | 0.0921 (todo+ 0.0952) | 4.997 | ruido |
| products.blocked_card | arbol_prof4 | 0.5052 [0.4926, 0.5178] | 0.051 (0.05) | 0.0843 (todo+ 0.0952) | 4.997 | ruido |
| interactions.not_resolved | baseline_mayoria | 0.5 [0.5, 0.5] | 0.2335 (0.2335) | 0.0 (todo+ 0.3786) | 23.353 | referencia |
| interactions.not_resolved | regresion_logistica | 0.7626 [0.76, 0.7652] | 0.4754 (0.2335) | 0.5466 (todo+ 0.3786) | 23.353 | señal |
| interactions.not_resolved | arbol_prof4 | 0.7626 [0.76, 0.7651] | 0.4602 (0.2335) | 0.5467 (todo+ 0.3786) | 23.353 | señal |
| interactions.not_resolved | regresion_logistica_solo_motivo | 0.763 [0.7604, 0.7655] | 0.4602 (0.2335) | 0.5467 (todo+ 0.3786) | 23.353 | señal |
| interactions.was_escalated | baseline_mayoria | 0.5 [0.5, 0.5] | 0.1 (0.1) | 0.0 (todo+ 0.1819) | 10.002 | referencia |
| interactions.was_escalated | regresion_logistica | 0.5013 [0.4973, 0.5053] | 0.1005 (0.1) | 0.1815 (todo+ 0.1819) | 10.002 | ruido |
| interactions.was_escalated | arbol_prof4 | 0.4996 [0.4956, 0.5037] | 0.0999 (0.1) | 0.1819 (todo+ 0.1819) | 10.002 | ruido |
| interactions.was_escalated | regresion_logistica_solo_motivo | 0.5012 [0.4972, 0.5052] | 0.0999 (0.1) | 0.1819 (todo+ 0.1819) | 10.002 | ruido |

- **Baseline sugerido**: Reglas deterministas: `response_code` explica la declinación (05 no autorizar, 14 tarjeta inválida, 51 fondos insuficientes, 54 tarjeta vencida) y `product_status` el bloqueo. No hay label aprendible en el dataset; un componente aprendido tendría que ser, por ejemplo, un clasificador de intención sobre un set ES/PT generado por el equipo.
- **Split**: Temporal (transacciones desde 2025-07-01; tarjetas por apertura desde 2024-01-01) + agrupación por `customer_id`.

Campos con riesgo de leakage en las tablas de este workflow (`05_leakage_fields.csv`):

| Tabla | Campo | Por qué | Riesgo |
|---|---|---|---|
| transactions | response_code | Resultado de la autorización (explica la declinación) | alto |
| transactions | transaction_status | Resultado; Declined/Reversed son labels | alto |
| transactions | fraud_score | Score de otro modelo; válido en tiempo de autorización pero no es feature propia | medio |
| customers | segment / credit_score / customer_status / estimated_monthly_income | Foto única al corte: estado final, no al momento del evento | alto (W4) / medio |
| products | product_status / days_past_due / current_balance / credit_limit | Foto única al corte; product_status y days_past_due son labels | alto (W2, W4) |

## 5. Proxies de costo e insumos del business case
Fórmula común a los 4 workflows: ahorro = contactos/mes × % automatizable (cota) × (costo humano − costo IA).
Lo medido es el volumen y el tiempo de atención; el % automatizable es una definición (supuesto) y los costos
unitarios son supuestos con fuente externa (`06_business_case_inputs.csv`, módulo `eda/cost.py`).

- AHT medio: **5.37 min** (duración conocida en 85.9% de los contactos);
  12,789 minutos de atención/mes; espera media (solo Inbound Call)
  2.00 min; 84.9% por teléfono `[medido]`.
- Cota de automatizable seguro: **57.8%** (resuelto, no escalado, sin seguimiento y sin
  complaint del cliente en 30 días) `[supuesto sobre tasas medidas]`.

| Insumo | Escenario | Valor | Etiqueta | Fuente |
|---|---|---|---|---|
| contactos por mes | — | 2,383 | medido | 06_cost_base.sql (eda/cost.py); población: contactos con transcript de saldo de tarjeta (TRS-02; texto no confiable, solo 25% tiene transcript) |
| AHT medio (min) | — | 5.4 | medido | 06_cost_base.sql (eda/cost.py); duration_seconds no nulo (85.933%) |
| minutos de atención por mes | — | 12,789 | medido | 06_cost_base.sql (eda/cost.py); duración media × contactos (imputa el 14.1% sin duración) |
| % automatizable seguro (cota superior) | — | 57.8 | supuesto | 06_cost_base.sql (eda/cost.py); definición: resuelto + no escalado + sin seguimiento + sin complaint en 30 días (la tasa es medida; que eso sea automatizable es supuesto) |
| costo por minuto de agente (USD) | conservador | 0.167 | supuesto | [1] |
| costo por contacto humano (USD) | conservador | 0.90 | proyectado | AHT medio [medido] × costo por minuto [supuesto] |
| costo por contacto con IA (USD) | conservador | 1.84 | supuesto | [2] |
| ahorro mensual (USD) | conservador | -1,303 | proyectado | contactos/mes × % automatizable (cota) × (costo humano − costo IA); negativo = la IA cuesta más |
| ahorro anual (USD) | conservador | -15,637 | proyectado | 12 × ahorro mensual |
| costo por minuto de agente (USD) | base | 0.250 | supuesto | [1] |
| costo por contacto humano (USD) | base | 1.34 | proyectado | AHT medio [medido] × costo por minuto [supuesto] |
| costo por contacto con IA (USD) | base | 1.84 | supuesto | [2] |
| ahorro mensual (USD) | base | -687 | proyectado | contactos/mes × % automatizable (cota) × (costo humano − costo IA); negativo = la IA cuesta más |
| ahorro anual (USD) | base | -8,239 | proyectado | 12 × ahorro mensual |
| costo por minuto de agente (USD) | optimista | 0.333 | supuesto | [1] |
| costo por contacto humano (USD) | optimista | 1.79 | proyectado | AHT medio [medido] × costo por minuto [supuesto] |
| costo por contacto con IA (USD) | optimista | 0.50 | supuesto | [2] |
| ahorro mensual (USD) | optimista | 1,777 | proyectado | contactos/mes × % automatizable (cota) × (costo humano − costo IA); negativo = la IA cuesta más |
| ahorro anual (USD) | optimista | 21,322 | proyectado | 12 × ahorro mensual |
| costo por contacto humano (USD) | referencia_global | 13.50 | supuesto | [2] costo asistido global |
| costo por contacto con IA (USD) | referencia_global | 1.84 | supuesto | [2] |
| ahorro mensual (USD) | referencia_global | 16,071 | proyectado | contactos/mes × % automatizable (cota) × (costo humano − costo IA); negativo = la IA cuesta más |
| ahorro anual (USD) | referencia_global | 192,851 | proyectado | 12 × ahorro mensual |

Fuentes de los supuestos:
[1] SkyCom, 'Nearshore Call Center Pricing 2026' (29 jul 2026): contact center en LATAM USD 10–20 por hora de agente (base = punto medio); costo por minuto = tarifa/60, sin ajuste por ocupación. https://www.skycomcallcenter.com/blog/customer-experience-cx/nearshore-call-center-pricing/

[2] Kustomer, glosario 'Cost per contact' (2026): autoservicio USD 1.84 mediana (Gartner), asistido USD 13.50 (Gartner, global), chatbot/IA ~USD 0.50. Fuente secundaria: verificar en la Fase B3 del análisis estratégico. https://www.kustomer.com/glossary/cost-per-contact/

## 6. Vacíos específicos del workflow
- Ningún contacto se puede atribuir a tarjetas con confianza: `mentioned_products` es 99.35% huérfano y el motivo no distingue producto.
- `product_status = Blocked` es foto única: no se sabe cuándo se bloqueó la tarjeta ni si el bloqueo fue antes o después de una llamada.
- Declinar una transacción y bloquear una tarjeta son ruido para los modelos (AUC ≈ 0.50): no se puede predecir qué tarjeta tendrá problemas.
- Sin políticas de reposición, desbloqueo o aumento de límite.
- El embudo 'error en la app → llamada' no existe en los datos (errores 24 h antes: 0.154% vs 0.149% de control).

## 7. Exploraciones posibles
| Exploración | Esfuerzo estimado |
|---|---|
| Mapa `response_code` × tipo de tarjeta × canal (POS/ATM/Web) como catálogo de explicaciones para el agente. | 2 horas |
| Secuencias de declinaciones repetidas por tarjeta en 24 h (candidatas a bloqueo preventivo o a escalamiento). | medio día |
| Set ES/PT de intenciones de tarjeta (bloqueo, declinación, límite, saldo) generado por el equipo para un clasificador con baseline de reglas. | 1 día |

## 8. Catálogo de plantillas de texto
Plantillas distintas asignadas a este workflow, deduplicadas, sin identificadores (sin `customer_id`,
`interaction_id`, nombres, documentos, emails ni teléfonos), con su frecuencia (`03_template_catalog.csv`,
`queries/03_template_catalog.sql`) `[medido]`. El dataset es 100% sintético y el texto es de plantilla; su uso fuera
del repo queda sujeto a la pregunta 4 de Slack (`04_brechas_y_preguntas.md`).

| Campo | Plantilla | n | % del campo | Distribución por workflow |
|---|---|---|---|---|
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. | 51,555 | 30.1 | W2_tarjetas=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. Claro, estoy para servirle. | 4,365 | 2.5 | W2_tarjetas=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. Con gusto. ¿Hay algo más en lo que pueda ayudarle? | 4,329 | 2.5 | W2_tarjetas=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. No hay problema, que tenga buen día. | 4,264 | 2.5 | W2_tarjetas=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. Perfecto, ¿necesita algo más? | 4,239 | 2.5 | W2_tarjetas=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. Claro, estoy para servirle. No hay problema, que tenga buen día. | 1,132 | 0.7 | W2_tarjetas=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. Perfecto, ¿necesita algo más? Con gusto. ¿Hay algo más en lo que pueda ayudarle? | 1,113 | 0.7 | W2_tarjetas=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. No hay problema, que tenga buen día. No hay problema, que tenga buen día. | 1,109 | 0.6 | W2_tarjetas=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. No hay problema, que tenga buen día. Claro, estoy para servirle. | 1,105 | 0.6 | W2_tarjetas=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. Con gusto. ¿Hay algo más en lo que pueda ayudarle? No hay problema, que tenga buen día. | 1,088 | 0.6 | W2_tarjetas=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. Perfecto, ¿necesita algo más? Perfecto, ¿necesita algo más? | 1,086 | 0.6 | W2_tarjetas=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. Claro, estoy para servirle. Claro, estoy para servirle. | 1,075 | 0.6 | W2_tarjetas=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. No hay problema, que tenga buen día. Con gusto. ¿Hay algo más en lo que pueda ayudarle? | 1,075 | 0.6 | W2_tarjetas=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. Con gusto. ¿Hay algo más en lo que pueda ayudarle? Claro, estoy para servirle. | 1,071 | 0.6 | W2_tarjetas=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. Perfecto, ¿necesita algo más? No hay problema, que tenga buen día. | 1,065 | 0.6 | W2_tarjetas=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. Con gusto. ¿Hay algo más en lo que pueda ayudarle? Con gusto. ¿Hay algo más en lo que pueda ayudarle? | 1,058 | 0.6 | W2_tarjetas=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. Claro, estoy para servirle. Con gusto. ¿Hay algo más en lo que pueda ayudarle? | 1,050 | 0.6 | W2_tarjetas=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. No hay problema, que tenga buen día. Perfecto, ¿necesita algo más? | 1,049 | 0.6 | W2_tarjetas=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. Con gusto. ¿Hay algo más en lo que pueda ayudarle? Perfecto, ¿necesita algo más? | 1,046 | 0.6 | W2_tarjetas=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. Claro, estoy para servirle. Perfecto, ¿necesita algo más? | 1,039 | 0.6 | W2_tarjetas=100.0% |
| call_transcripts.agent_text | Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}. Perfecto, ¿necesita algo más? Claro, estoy para servirle. | 997 | 0.6 | W2_tarjetas=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. | 51,555 | 30.1 | W2_tarjetas=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. Perfecto, eso es lo que necesitaba. | 4,393 | 2.6 | W2_tarjetas=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. Entiendo, muchas gracias. | 4,328 | 2.5 | W2_tarjetas=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. ¿Y eso cuánto tiempo tarda? | 4,269 | 2.5 | W2_tarjetas=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. Muy bien, ¿hay algo más que deba saber? | 4,207 | 2.5 | W2_tarjetas=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. Entiendo, muchas gracias. Entiendo, muchas gracias. | 1,130 | 0.7 | W2_tarjetas=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. ¿Y eso cuánto tiempo tarda? ¿Y eso cuánto tiempo tarda? | 1,130 | 0.7 | W2_tarjetas=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. Perfecto, eso es lo que necesitaba. Entiendo, muchas gracias. | 1,124 | 0.7 | W2_tarjetas=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. Entiendo, muchas gracias. ¿Y eso cuánto tiempo tarda? | 1,120 | 0.7 | W2_tarjetas=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. ¿Y eso cuánto tiempo tarda? Perfecto, eso es lo que necesitaba. | 1,114 | 0.7 | W2_tarjetas=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. Muy bien, ¿hay algo más que deba saber? ¿Y eso cuánto tiempo tarda? | 1,089 | 0.6 | W2_tarjetas=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. Entiendo, muchas gracias. Muy bien, ¿hay algo más que deba saber? | 1,085 | 0.6 | W2_tarjetas=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. ¿Y eso cuánto tiempo tarda? Entiendo, muchas gracias. | 1,079 | 0.6 | W2_tarjetas=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. Perfecto, eso es lo que necesitaba. ¿Y eso cuánto tiempo tarda? | 1,075 | 0.6 | W2_tarjetas=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. Entiendo, muchas gracias. Perfecto, eso es lo que necesitaba. | 1,061 | 0.6 | W2_tarjetas=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. Perfecto, eso es lo que necesitaba. Muy bien, ¿hay algo más que deba saber? | 1,058 | 0.6 | W2_tarjetas=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. Muy bien, ¿hay algo más que deba saber? Perfecto, eso es lo que necesitaba. | 1,053 | 0.6 | W2_tarjetas=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. Muy bien, ¿hay algo más que deba saber? Muy bien, ¿hay algo más que deba saber? | 1,037 | 0.6 | W2_tarjetas=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. Perfecto, eso es lo que necesitaba. Perfecto, eso es lo que necesitaba. | 1,020 | 0.6 | W2_tarjetas=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. Muy bien, ¿hay algo más que deba saber? Entiendo, muchas gracias. | 1,008 | 0.6 | W2_tarjetas=100.0% |
| call_transcripts.customer_text | Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. ¿Y eso cuánto tiempo tarda? Muy bien, ¿hay algo más que deba saber? | 975 | 0.6 | W2_tarjetas=100.0% |

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
