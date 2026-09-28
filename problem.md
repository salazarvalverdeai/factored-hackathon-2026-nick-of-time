# problem.md — W3 · Intake de disputas con reloj regulatorio (Regulatory-clock dispute intake)

**Decidido el:** [fecha de la votación] · **No se reabre:** workflow, zonas y umbrales, formato de handoff, formato
de casos de eval, nombre del equipo.
**Etiquetas:** `[dato]` calculado sobre el dataset (query en `queries/`) · `[externo]` fuente con link ·
`[supuesto]` · `[simulado]` medido en nuestro harness · `[proyectado]`.

## 1. Problema
Un cliente ve un cargo que no reconoce o un cobro indebido y reclama. Es el **36.4% de los reclamos** `[dato]`
(679/mes en promedio sobre 1,864), el motivo con peor FCR (**43.6% vs 76.6%** `[dato]`), 63% con seguimiento,
duración mediana 7.2 vs 4.9 min, NPS −85.3, resolución p50 16 días `[dato]`, y el único con plazo legal por país
(MX: abono ≤ día hábil 2 en débito y dictamen ≤ 45 días; AR: 10 días hábiles; CO: 15 días; BR: 10 días hábiles)
`[externo]` ver `policies.yaml`.

## 2. Alcance
**Entra:** intake ES/PT · identidad mock (sesión + OTP con vencimiento) · identificación de la transacción del
propio cliente · ticket automático en las 3 zonas · triage por `fraud_score` (≥ 50 acción verificada; 30–49
confirmar; < 30 o nulo humano) · bloqueo con post-condición · reloj regulatorio · tarjeta de handoff · vista del
agente (copiloto que propone, humano decide) · trazas + log de auditoría · harness held-out ES/PT con ataques ·
deploy público · README reproducible.
**No entra (a propósito):** investigación del caso, contracargo con la red, abono automático, voz, WhatsApp real,
multi-agente, Graph RAG, fine-tuning.

## 2b. Despliegue y scoring (decidido lun 28)
- **Grafo en LangGraph Platform** (opción A) con tools como servidor MCP en la EC2; la opción B (todo en EC2)
  queda documentada como migración directa (mismo grafo, adaptador de tools distinto) y no se ejecuta por tiempo.
  Condición: confirmar en Slack que el texto sintético puede salir de AWS y declararlo en el README.
- **`fraud_score` como tool con proveedor intercambiable** (`dataset` al inicio; `reglas`, `modelo` o `llm` por
  configuración). La fuente y versión del score quedan en la auditoría y en la tarjeta de handoff.

## 3. Solución en una frase
El LLM entiende, las reglas (YAML) deciden, las tools tipadas actúan, la verificación confirma, las trazas
registran, el humano recibe evidencia.

## 4. Componente aprendido vs baseline
Clasificador de intención y slots ES/PT: reglas por palabras clave → embeddings + regresión logística → Jev
(tercer brazo, solo si pasa la prueba ES/PT del miércoles 30). Mismo held-out, split por plantilla. Secundario:
calibración de zonas contra `is_fraud`. Escalamiento por reglas (AUC 0.501 `[dato]`).

## 5. Cómo se mide
Estado final (no texto): ¿bloqueó?, ¿abrió caso?, ¿escaló cuando debía?, ¿negó cuando debía? Métricas del reto:
safe automated resolution, unsafe outcomes con denominador, escalation quality (perdidos e innecesarios),
p50/p95, costo por caso intentado y por resolución, por idioma y segmento, pass^4. Ver `eval/eval_case.schema.json`.

## 6. Riesgos aceptados
Texto real 0 (set del equipo, etiquetado) · PT 0% en datos · precisión 100% con score ≥ 50 es del generador
`[supuesto]` · 20.6% de fraudes sin score → humano · FK de complaints rota → disputa desde `transactions` ·
Jev 12 días de vida → fallback LR · ¿datos sintéticos a APIs externas? (preguntar en Slack antes del martes).

## 7. Reparto
| Persona | Dueño de |
|---|---|
| Freddy (AI/ML, líder, integrador) | `policies.yaml`, contratos, motor de reglas, clasificador vs baselines, Jev, harness |
| Full stack | orquestador, tools sobre el snapshot, identidad mock, UI cliente + agente, trazas, grafo, deploy |
| Datos 1 (engineering) | pipeline con contratos, snapshot DuckDB, checks, fixture de llegadas tardías, `make setup` |
| Datos 2 (analytics) | queries del pitch, plazos con fuente, business case, set ES/PT (redacción y etiquetado), reporte |

## 8. Calendario
Lun 28 contratos y repo · Mar 29 esqueleto · Mié 30 caso normal end-to-end + prueba Jev · Jue 1 clasificador,
set ES/PT, UI cliente · Vie 2 vista agente, trazas, grafo · Sáb 3 eval completo y deploy · Dom 4 video, slides,
README, secretos · Lun 5 entrega a primera hora.
