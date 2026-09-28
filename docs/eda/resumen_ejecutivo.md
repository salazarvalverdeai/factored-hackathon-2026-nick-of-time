# Resumen ejecutivo — EDA LATAM Bank

> Una página para abrir en el Project de claude.ai junto con los expedientes (`docs/eda/workflows/W*.md`). Dataset
> sintético de Factored (MX, CO, AR; jun 2023 – jun 2026; 12 de 13 tablas analizadas). Cifras `[medido]` salvo
> indicación; cada una tiene su query en `docs/eda/queries/` y su detalle en `findings.md`. 26 sep 2026.

## Qué tiene el dataset
- **Volumen estable y joins sólidos**: 19,033 contactos/mes, 1,864 complaints/mes, 122,779 transacciones/mes, sin
  tendencia ni estacionalidad. interaction → transcript → survey y transaction → product son 100% consistentes.
- **Outcomes de contacto que dependen del motivo**: FCR de 43.6% (`Queja`) a 91.5% (`Transaccional`); duración p50 de
  3.4 a 9.0 min (`04_workflow_scorecard.csv`).
- **Señales deterministas para tools**: saldos y movimientos por cliente, estado de pagos, `response_code` ISO 8583 en
  declinaciones, `product_status`, tipo de cambio diario coherente con `amount_usd` (desvío p95 2%).
- **Una señal casi determinista de fraude**: `fraud_score` ≥ 50 → 100% de precisión y 48.8% de recall sobre `is_fraud`
  (`05_fraud_score_thresholds.csv`).
- **Problemas de calidad reales** que sirven de evidencia de data engineering: FK a productos de otro cliente (100% en
  complaints), fechas futuras (~4%), transacciones antes de la apertura del producto (18.7%), día operativo corrido,
  `México`/`Mexico` (`calidad_datos.md` §C).

## Qué no tiene
- **Motivo granular, intents o texto real**: 6 motivos; `detected_intents` = 1 valor; transcripts = 2 plantillas de
  consulta de saldo independientes del motivo (kappa 0.0003); complaints con 5 descripciones de plantilla.
- **Vínculos clave**: complaint → interacción (100% nulo), producto por interacción (99.35% huérfano).
- **Métricas de dolor informativas en casos**: `sla_breached` ≈ 20% en todo; escalamiento ≈ 10% en todo; encuestas
  truncadas (CSAT/CES 1–4, NPS 2–7, sin promotores).
- **Historia de dimensiones** (foto única), **portugués**, **políticas**, **identidad**, **costos del banco**, y los
  duplicados/llegadas tardías/evolución de schema que anuncia el diccionario.

## Dónde hay señal aprendible (fase 5; split temporal, baseline de mayoría, AUC con IC95)
| Label | Workflow | Resultado |
|---|---|---|
| No resuelto (1 − FCR) | W1 vs W3 | AUC 0.763 [0.760, 0.766], **100% explicado por el motivo** (el modelo es una tabla de 6 filas) |
| Requiere seguimiento | transversal | AUC 0.676 [0.674, 0.679], 100% explicado por el motivo |
| Fraude vía `fraud_score` | W3 | AUC 0.752 [0.722, 0.782], AP 0.52 vs prevalencia 0.0009; features + score 0.792 (sin mejora significativa) |
| Escalado, SLA, declinada, reversada, tarjeta bloqueada, mora | todos | **ruido** (AUC 0.497–0.508, IC incluye 0.5) |

## Ranking por el criterio alternativo (labels, viabilidad, señales deterministas)
El dolor de contacto discrimina solo por motivo y dos workflows no tienen contactos confiables, así que se rankea con el
criterio acordado (`findings.md` §C):
1. **W3 disputas**: única señal que define cuándo actuar (`fraud_score`), peor dolor (FCR 43.6%, NPS −85.3), casos
   propios (679/mes). Mapeo de contactos de confianza baja.
2. **W1 cuentas/pagos**: el más viable y mejor mapeado (35.0% de contactos, confianza media), señales deterministas
   ricas; sin dolor (FCR 91.5%) ni componente aprendido propio.
3. **W2 tarjetas**: buenas señales deterministas (2,156 declinaciones/mes con `response_code`), cero contactos
   atribuibles, labels = ruido.
4. **W4 crédito**: sin señal (mora AUC 0.497), mapeo de confianza baja, requisitos de política más duros.

## Ideas candidatas
1. **W3 — Intake de disputas con triage verificable en 3 zonas** (recomendada): `fraud_score` ≥ 50 → acción automática
   verificada; 30–50 → confirmar y derivar; < 30 o sin score → handoff estructurado. Números: 679 casos/mes;
   precisión 100% / recall 48.8% en ≥ 50; FCR de `Queja` 43.6% vs 76.6% del banco.
2. **W1 — Consultas de cuenta y pagos verificadas contra el ledger**: 6,661 contactos/mes; FCR 91.5%, AHT 3.7 min,
   cota automatizable 69.3%; 4,713 pagos rechazados o pendientes por mes.
3. **W2 — Diagnóstico determinista de declinaciones y bloqueos**: 2,156 declinaciones de tarjeta/mes con código ISO;
   7,044 tarjetas bloqueadas; componente aprendido solo con datos generados por el equipo.

Para las tres: el escalamiento no se puede aprender del dataset (AUC 0.501), así que la política de handoff va en
reglas, fuera del modelo. **Business case**: con costos LATAM (USD 10–20/h) el ahorro por contacto es marginal o
negativo (W1 base: −51k USD/año `[proyectado]`); solo con el costo asistido global de Gartner (USD 13.50/contacto) sale
positivo (+646k). El argumento fuerte es control de riesgo, 24/7 y consistencia, no costo (`06_business_case_inputs.csv`).

## Preguntas para Slack
1. ¿`contact_reason` = `reason_category` y `detected_intents` con un solo valor son intencionales?
2. ¿`origin_interaction_id` nulo y `affected_product_id` de otros clientes son intencionales (test de aislamiento)?
3. ¿Definición de `sla_breached`? ¿Escalas reales de CSAT, NPS y CES?
4. ¿Se permite enviar datos del dataset (sintético) a APIs de LLM externas? (condiciona el catálogo de plantillas)
5. ¿`fraud_score` es un input disponible en tiempo real o una variable de evaluación?
6. ¿`reason_category` se captura al inicio (IVR) o al cierre? (si es al cierre, la señal de FCR es leakage)
7. ¿Los duplicados, llegadas tardías y evolución de schema anunciados deben simularse o el dataset no es la versión final?
