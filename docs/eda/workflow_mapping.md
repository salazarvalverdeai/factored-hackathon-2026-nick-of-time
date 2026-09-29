# Mapeo a workflows — reglas, cobertura y confiabilidad

> Documento autocontenido para el Project de claude.ai. Generado con `python -m eda.report mapping` desde
> `outputs/tables/03_*.csv` (módulo `python -m eda.workflows`). Reglas versionadas en
> `docs/eda/queries/03_workflow_mapping.csv` (versión **v1**). Todas las cifras son `[medido]` salvo que se
> indique. Mapeo hecho por Claude con criterio propio (decisión 11 del plan); pendiente de revisión de Freddy.

## 1. Por qué hace falta un mapeo y qué lo limita
Ningún campo del dataset dice "workflow". El reto propone 4 workflows de ejemplo (W1 cuentas/pagos, W2 tarjetas,
W3 disputas, W4 crédito/elegibilidad) y el EDA debe compararlos con la misma vara. Lo que limita el mapeo
(ver `data_quality.md`):
- `contact_reason` es idéntico a `reason_category`: **solo 6 motivos** para todos los contactos.
- `detected_intents` tiene **un solo valor** (`consulta_general`); `main_topics` copia `reason_category`.
- El producto de una interacción no se puede saber: `mentioned_products` es 99.35% huérfano.
- Complaints no se vincula a la interacción (`origin_interaction_id` 100% nulo) y su `affected_product_id` es de
  otro cliente en el 100% de los casos.
- El texto de los transcripts son **2 plantillas de consulta de saldo** (tarjeta de crédito / cuenta de ahorros) con
  frases de relleno, **independientes del motivo y de los productos del cliente** (§5).

Por eso el mapeo se hace **por fuente**, cada una con su propia regla y su propio denominador, y cada regla lleva una
confianza: **alta** (la semántica del campo corresponde sin ambigüedad), **media** (corresponde en la mayoría de los
casos, con un workflow alternativo plausible), **baja** (asignación por conveniencia, con varias alternativas).

## 2. Cobertura por fuente
Cobertura **estricta** = % asignado a W1–W4 con reglas de confianza alta o media. **Amplia** = incluye las de
confianza baja. Fuente: `03_coverage_summary.csv` (`queries/03_apply_mapping.sql` sobre `03_mapping_sources.sql`).

| Fuente | n | % W1 | % W2 | % W3 | % W4 | % OTRO | % AMBIGUO | % 4W estricta | % 4W amplia |
|---|---|---|---|---|---|---|---|---|---|
| call_center_interactions (contactos) | 686,296 | 35.0 | 0.0 | 17.1 | 8.0 | 18.0 | 22.0 | 35.0 | 60.0 |
| call_transcripts (texto de la llamada) | 171,321 | 49.9 | 50.1 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| complaints (casos) | 67,095 | 2.0 | 0.0 | 36.4 | 0.0 | 61.5 | 0.0 | 36.4 | 38.5 |
| transactions (eventos disparadores) | 4,425,008 | 54.5 | 34.6 | 1.1 | 7.9 | 2.0 | 0.0 | 6.7 | 98.0 |
| products (cartera, foto única) | 400,000 | 55.0 | 35.0 | 0.0 | 8.0 | 2.0 | 0.0 | 98.0 | 98.0 |
| digital_events (navegación) | 15,620,994 | 24.3 | 7.7 | 0.0 | 7.7 | 55.3 | 5.0 | 39.7 | 39.7 |

Lectura:
- **Contactos (interactions)**: solo W1 tiene una regla de confianza media (`Transaccional`, 35.0%).
  W3 (`Queja`) y W4 (`Comercial`) entran con confianza baja; **W2 no tiene ninguna regla a nivel de contacto**.
  22.0% queda AMBIGUO (`Producto`) y 18.0% OTRO (`Técnico`, `Retención`). Cobertura estricta
  de los 4 workflows: **35.0%**; amplia: 60.0%.
- **Transcripts**: 100% asignado (W1 / W2 ≈ 50/50), pero la asignación sale de una plantilla que no se relaciona con
  nada más (§5). No sirve para dimensionar.
- **Complaints**: W3 36.4% (cargos no reconocidos y cobros indebidos), W1 2.0% (baja),
  OTRO 61.5% (app, sucursal, servicio). **W2 y W4 no tienen complaints asignables.**
- **Transactions**: la cobertura estricta (6.7%) son los **eventos disparadores** de
  contacto: fraude y reversos (W3), declinaciones de tarjeta (W2), pagos rechazados o pendientes (W1). El resto es
  actividad normal (confianza baja). Las transacciones son consistentes con su producto (fase 1, C12).
- **Products** y **digital_events** describen la cartera y la navegación: útiles para contexto y para tools de un
  agente, no para contar contactos.

## 3. Poblaciones por workflow que usan las fases 4–6
Decisión tomada: cada métrica del scorecard se calcula sobre la población de su fuente, con su propio n. Las
poblaciones pueden solaparse (una interacción `Transaccional` con transcript de tarjeta cuenta en W1 y en W2).

| Workflow | Contactos (interactions) | Texto (transcripts) | Casos (complaints) | Eventos disparadores (transactions / products) |
|---|---|---|---|---|
| W1_cuentas_pagos | INT-01 `Transaccional` (media) | TRS-01 (alta) | CMP-04 (baja) | TRX-04, TRX-05 (media) |
| W2_tarjetas | — (sin regla) | TRS-02 (media) | — | TRX-03 declinación de tarjeta (alta); PRD-01 tarjeta bloqueada (alta) |
| W3_disputas | INT-02 `Queja` (baja) | — | CMP-01 (alta), CMP-02, CMP-03 (media) | TRX-01 fraude (alta); TRX-02 reverso (media) |
| W4_credito | INT-03 `Comercial` (baja) | — | — | PRD-03 cartera de préstamos (alta); TRX-08 (baja) |

## 4. Tabla de reglas (v1)
Orden: dentro de cada fuente gana la primera regla (por prioridad) que se cumple. n y % sobre el total de la fuente
(`03_coverage_by_rule.csv`).

| Regla | Fuente | Prio. | Condición | Workflow | Confianza | n | % | Justificación |
|---|---|---|---|---|---|---|---|---|
| INT-01 | interactions | 1 | `reason_category = 'Transaccional'` | W1_cuentas_pagos | media | 240,056 | 35.0 | Consultas sobre movimientos, pagos y transferencias: núcleo de W1. Media porque puede incluir movimientos de tarjeta (W2) o cargos a disputar (W3) y no hay campo que lo distinga |
| INT-02 | interactions | 2 | `reason_category = 'Queja'` | W3_disputas | baja | 117,021 | 17.1 | Una queja bancaria suele originar un reclamo o disputa. Baja: puede ser queja de servicio o de sucursal y complaints no se vincula con la interacción (origin_interaction_id 100% nulo) |
| INT-03 | interactions | 3 | `reason_category = 'Comercial'` | W4_credito | baja | 54,879 | 8.0 | Contactos comerciales = oferta y elegibilidad de productos; en banca minorista predominan tarjetas y préstamos. Baja: también incluye ahorro e inversión y no hay producto confiable por interacción |
| INT-04 | interactions | 4 | `reason_category = 'Técnico'` | OTRO | media | 102,899 | 15.0 | Soporte técnico (app/canales digitales) no es uno de los 4 workflows. Media: una falla técnica puede ser de tarjeta (W2) |
| INT-05 | interactions | 5 | `reason_category = 'Retención'` | OTRO | alta | 20,578 | 3.0 | Retención/cancelación no es uno de los 4 workflows |
| INT-06 | interactions | 6 | `reason_category = 'Producto'` | AMBIGUO | baja | 150,863 | 22.0 | Consulta de producto: puede ser cuenta (W1), tarjeta (W2) o crédito (W4). mentioned_products es 99.35% huérfano y no permite decidir |
| TRS-01 | transcripts | 1 | `customer_text LIKE '%cuenta de ahorros%'` | W1_cuentas_pagos | alta | 85,411 | 49.9 | Plantilla 'saldo actual en mi cuenta de ahorros': consulta de saldo de cuenta. Ojo: la plantilla es independiente de reason_category y de los productos del cliente |
| TRS-02 | transcripts | 2 | `customer_text LIKE '%tarjeta de crédito%'` | W2_tarjetas | media | 85,910 | 50.1 | Plantilla 'saldo de mi tarjeta de crédito' + respuesta con límite disponible: servicio de tarjeta. Media: una consulta de saldo también encaja en W1. Misma advertencia de independencia |
| TRS-03 | transcripts | 3 | `TRUE` | AMBIGUO | baja | 0 | 0.0 | Texto sin plantilla reconocida (no ocurre en v1) |
| CMP-01 | complaints | 1 | `category = 'Transactions' AND case_type = 'Claim'` | W3_disputas | alta | 3,335 | 5.0 | Reclamo formal por 'Cargo no reconocido': intake de disputa. Nota: case_type es independiente de category en los datos (la confianza refleja semántica no evidencia) |
| CMP-02 | complaints | 2 | `category = 'Transactions' AND case_type IN ('Complaint', 'Request')` | W3_disputas | media | 9,568 | 14.3 | Queja o solicitud por 'Cargo no reconocido': disputa aunque no esté tipificada como Claim |
| CMP-03 | complaints | 3 | `category = 'Fees' AND case_type IN ('Claim', 'Complaint')` | W3_disputas | media | 11,528 | 17.2 | Reclamo o queja por 'Cobro indebido': disputa de comisión/cargo |
| CMP-04 | complaints | 4 | `category = 'Fees' AND case_type = 'Request'` | W1_cuentas_pagos | baja | 1,367 | 2.0 | Solicitud sobre comisiones: consulta de cuenta más que disputa |
| CMP-05 | complaints | 5 | `category IN ('Technical', 'Branch', 'Service')` | OTRO | alta | 39,962 | 59.6 | 'Problema con app', 'Atención en sucursal' y 'Calidad de servicio' no son de los 4 workflows |
| CMP-06 | complaints | 6 | `case_type = 'Suggestion'` | OTRO | media | 1,335 | 2.0 | Sugerencias sobre transacciones o comisiones: no es intake de disputa |
| CMP-07 | complaints | 7 | `TRUE` | AMBIGUO | baja | 0 | 0.0 | Resto (no ocurre en v1) |
| TRX-01 | transactions | 1 | `is_fraud` | W3_disputas | alta | 4,316 | 0.1 | Transacción marcada como fraude: origina reclamo/disputa del cliente |
| TRX-02 | transactions | 2 | `transaction_status = 'Reversed'` | W3_disputas | media | 44,714 | 1.0 | Reverso: resultado típico de una disputa o contracargo. Media: también hay reversos operativos |
| TRX-03 | transactions | 3 | `transaction_status = 'Declined' AND product_type IN ('Tarjeta Crédito', 'Tarjeta Débito')` | W2_tarjetas | alta | 77,641 | 1.8 | Declinación de tarjeta con response_code ISO 8583: disparador clásico de soporte de tarjetas |
| TRX-04 | transactions | 4 | `transaction_status = 'Declined' AND product_type IN ('Cuenta Ahorro', 'Cuenta Corriente')` | W1_cuentas_pagos | media | 121,242 | 2.7 | Pago o transferencia rechazada desde cuenta: consulta de pagos |
| TRX-05 | transactions | 5 | `transaction_status = 'Pending' AND product_type IN ('Cuenta Ahorro', 'Cuenta Corriente')` | W1_cuentas_pagos | media | 48,599 | 1.1 | Pago o transferencia pendiente: consulta de pagos |
| TRX-06 | transactions | 6 | `product_type IN ('Tarjeta Crédito', 'Tarjeta Débito')` | W2_tarjetas | baja | 1,452,465 | 32.8 | Actividad normal de tarjeta: contexto de W2 no evento de contacto |
| TRX-07 | transactions | 7 | `product_type IN ('Cuenta Ahorro', 'Cuenta Corriente')` | W1_cuentas_pagos | baja | 2,240,623 | 50.6 | Actividad normal de cuenta: contexto de W1 no evento de contacto |
| TRX-08 | transactions | 8 | `product_type IN ('Préstamo Personal', 'Préstamo Hipotecario')` | W4_credito | baja | 348,631 | 7.9 | Pagos y ajustes de préstamos: servicio de crédito (no elegibilidad) |
| TRX-09 | transactions | 9 | `TRUE` | OTRO | media | 86,777 | 2.0 | Inversión y Seguro: fuera de los 4 workflows |
| PRD-01 | products | 1 | `product_type IN ('Tarjeta Crédito', 'Tarjeta Débito') AND product_status = 'Blocked'` | W2_tarjetas | alta | 7,044 | 1.8 | Tarjeta bloqueada: disparador de soporte de tarjetas (estado al corte: foto única) |
| PRD-02 | products | 2 | `product_type IN ('Tarjeta Crédito', 'Tarjeta Débito')` | W2_tarjetas | alta | 132,996 | 33.2 | Cartera de tarjetas |
| PRD-03 | products | 3 | `product_type IN ('Préstamo Personal', 'Préstamo Hipotecario')` | W4_credito | alta | 31,870 | 8.0 | Cartera de préstamos |
| PRD-04 | products | 4 | `product_type IN ('Cuenta Ahorro', 'Cuenta Corriente')` | W1_cuentas_pagos | alta | 220,182 | 55.0 | Cartera de cuentas |
| PRD-05 | products | 5 | `TRUE` | OTRO | alta | 7,908 | 2.0 | Inversión y Seguro |
| DEV-01 | digital_events | 1 | `page_url IN ('/payments', '/transfer', '/accounts', '/transactions')` | W1_cuentas_pagos | alta | 3,797,081 | 24.3 | Páginas de pagos, transferencias, cuentas y movimientos |
| DEV-02 | digital_events | 2 | `page_url = '/products/credit-card'` | W2_tarjetas | media | 1,198,674 | 7.7 | Página de tarjeta de crédito. Media: puede ser una solicitud de tarjeta (W4) |
| DEV-03 | digital_events | 3 | `page_url = '/products/loans'` | W4_credito | alta | 1,199,796 | 7.7 | Página de préstamos |
| DEV-04 | digital_events | 4 | `page_url IN ('/login', '/logout', '/home', '/help', '/products', '/products/savings')` | OTRO | media | 8,645,049 | 55.3 | Navegación general, autenticación, ayuda y ahorro |
| DEV-05 | digital_events | 5 | `TRUE` | AMBIGUO | baja | 780,394 | 5.0 | Evento sin page_url |

## 5. Confiabilidad: motivo vs texto y sesgo de cobertura
**Motivo vs plantilla del transcript** (reemplaza el acuerdo motivo vs `detected_intents`, que tiene un solo valor).
Fuente: `03_reason_vs_text_agreement.csv` (`queries/03_reason_vs_text.sql`).

| Workflow por motivo | Workflow por texto | n | % de transcripts |
|---|---|---|---|
| AMBIGUO | W1_cuentas_pagos | 18,973 | 11.1 |
| AMBIGUO | W2_tarjetas | 18,685 | 10.9 |
| OTRO | W1_cuentas_pagos | 15,347 | 9.0 |
| OTRO | W2_tarjetas | 15,524 | 9.1 |
| W1_cuentas_pagos | W1_cuentas_pagos | 29,850 | 17.4 |
| W1_cuentas_pagos | W2_tarjetas | 29,936 | 17.5 |
| W3_disputas | W1_cuentas_pagos | 14,476 | 8.4 |
| W3_disputas | W2_tarjetas | 14,722 | 8.6 |
| W4_credito | W1_cuentas_pagos | 6,765 | 3.9 |
| W4_credito | W2_tarjetas | 7,043 | 4.1 |

- Acuerdo bruto: 17.4%; **kappa de Cohen = 0.0003** (≈ 0: el acuerdo es el del azar).
- Motivo × plantilla: χ² = 10.19, p = 0.07,
  **V de Cramér = 0.00771**. La plantilla (saldo de tarjeta vs saldo de cuenta) se
  reparte ~50/50 en cada motivo, incluidos `Queja` y `Técnico`.
- La plantilla tampoco se relaciona con los productos del cliente: 48.8–48.9% de los clientes con cualquiera de las dos
  plantillas tiene tarjeta de crédito, igual que el total de clientes (48.8%) `[medido]`
  (consulta de validación en `queries/03_template_vs_ownership.sql`).
- Conclusión: **ni el motivo ni el texto son labels confiables de intención**, y no hay una segunda fuente que los
  valide. Un clasificador de intención sobre este texto aprendería una plantilla, no una intención.

**Sesgo de `has_transcript` y de encuestas por workflow** (decisión 3 del plan). Fuente:
`03_transcript_bias_by_workflow.csv` (`queries/03_transcript_bias.sql`).

| Regla | Workflow | n | % con transcript | % con encuesta |
|---|---|---|---|---|
| INT-01 | W1_cuentas_pagos | 240,056 | 24.9 | 31.0 |
| INT-02 | W3_disputas | 117,021 | 25.0 | 31.1 |
| INT-03 | W4_credito | 54,879 | 25.2 | 31.2 |
| INT-04 | OTRO | 102,899 | 25.0 | 30.9 |
| INT-05 | OTRO | 20,578 | 25.2 | 30.9 |
| INT-06 | AMBIGUO | 150,863 | 25.0 | 30.9 |

- χ² (transcript × regla) p = 0.839, V de Cramér = 0.00174: **sin sesgo**. Lo que salga de
  transcripts o encuestas es representativo del workflow en cuanto a cobertura (no en cuanto a contenido).

## 6. Qué quedó en OTRO y AMBIGUO
- **AMBIGUO en contactos** (22.0%): `Producto`. Podría repartirse entre W1, W2 y W4 si existiera el
  producto de la interacción; no existe.
- **OTRO en contactos** (18.0%): `Técnico` (soporte de app y canales, 15.0%) y `Retención` (3.0%).
  `Técnico` es el candidato más fuerte a un "quinto workflow" (soporte digital), fuera de los 4 del reto.
- **OTRO en complaints** (61.5%): `Problema con app`, `Atención en sucursal`, `Calidad de servicio` y
  sugerencias.
- **AMBIGUO en digital_events** (5.0%): eventos sin `page_url`.

## 7. Catálogo de plantillas de texto
El catálogo completo (deduplicado, con frecuencia y workflow, sin identificadores) está en
`outputs/tables/03_template_catalog.csv` y se reparte en la sección 8 de cada expediente. Plantillas distintas:
`call_transcripts.agent_text` = 42, `call_transcripts.customer_text` = 42, `complaints.description` = 5, `complaints.resolution` = 5, `satisfaction_surveys.open_comments` = 13. Sujeto a la pregunta 4 de Slack.

## 8. Cómo cambiar el mapeo
Editar `docs/eda/queries/03_workflow_mapping.csv` (subir `version`), correr `python -m eda.workflows` y
`python -m eda.report`. Las fases 4–6 usan las mismas reglas vía `eda.workflows.case_expr()`.
