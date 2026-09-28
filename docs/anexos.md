# Anexos: stack, contratos, números, pendientes

## Stack y decisiones cerradas (lunes 28)

| Pregunta | Decisión | Por qué |
| --- | --- | --- |
| Dónde corre el grafo | LangGraph Platform (opción A): deploy desde `langgraph.json`, Studio, persistencia, `interrupt()` | El equipo lo conoce; datos y claves del dataset son públicos, sin restricción para servicios externos; se declara en el README |
| Tools del cliente | Servidor MCP (FastMCP) en la EC2 detrás de Caddy, API key o mTLS y allowlist; permisos por `customer_id` de sesión dentro de cada tool | Un servicio del banco detrás de un gateway |
| Tools del analista | Endpoints de la API (`POST /api/casos/{id}/accion`), ejecutadas por el humano desde la consola; el copiloto solo propone | Separación de actores; cada clic es un evento auditado |
| Modo de aprobación | Configurable por acción en `policies.yaml`: `auto`, `human_required`, `manual_check`; interruptor global "modo supervisado" en la consola, auditado | Automatización segura y control humano activable |
| Migración a B (todo en EC2) | Documentada, no ejecutada por tiempo; cambiar A → B es reemplazar el adaptador MCP por import directo | Ruta a operación |
| LLM | Amazon Bedrock en `us-east-2`, por rol IAM | Costo por token medible por caso |
| `fraud_score` | Tool `obtener_score(transaction_id)` con proveedor intercambiable: `dataset` (el del banco), `reglas`, `modelo`, `llm` (solo ilustra, fuerza zona humano); fuente y versión en auditoría | Consumimos el score del motor de fraude del banco; no construimos uno |
| Backend | FastAPI en contenedor en EC2, GHCR, `docker compose` (Caddy + api + web), GitHub Actions con auto-deploy | App Runner no lee GHCR; Caddy resuelve HTTPS |
| Frontend | Next.js + Tailwind + shadcn/ui + next-themes; `/chat` parte de `agent-chat-ui` | Dark mode y componentes listos |
| Voz | Opcional si sobra tiempo: ElevenLabs en `/chat` | Fuera del mínimo |
| Datos | Bronze → silver → gold con pandera; gold Parquet con manifest; DuckDB en el contenedor; versiones fijadas | 15 números reproducidos; sha estable |
| Estado y auditoría | DynamoDB (SQLite en dev): `case_events` append-only, `llm_calls`, `policy_denials`; estado del caso = último evento | Cada fila es un nodo del grafo de evidencia |
| Observabilidad | LangSmith en desarrollo + log de auditoría propio como fuente de verdad | El reto pide registros, no chain-of-thought |
| CI | `ci.yml` mínimo: tests, validación de schemas de eval, build | Sin CI los sellos quedan rojos sin que nadie lo vea |
| Fuera | AgentCore, Bedrock Agents, Lambda por tool, Neptune, Graph RAG, multi-agente, LangGraph Server autoalojado, modelo de fraude propio | No suman puntos |

## Contratos (en `contracts/` y `eval/`)

| Contrato | Qué fija | Lo que no se negocia |
| --- | --- | --- |
| `policies.yaml` | Deny por defecto; identidad (TTL 15 min, OTP para escribir); alcance por sesión; proveedor de score; zonas alta ≥ 50, media 30–49, humano < 30 o nulo; umbral de monto (1,000 y 5,000 USD, a calibrar); modo de aprobación por acción e interruptor global; ticket siempre; abono provisional nunca `auto`; handoff triggers; reloj por país con fuente; reintentos 2, timeout 800 ms; idempotencia; actores y sus tools | El LLM nunca lee ni edita este archivo; la zona se calcula solo sobre `obtener_score()` |
| `tools.py` (cliente) | `buscar_transaccion`, `obtener_score`, `calcular_plazo`, `bloquear_tarjeta`, `abrir_caso`, `estado_producto`, `estado_caso`; toda tool recibe `session_id` | `bloquear_tarjeta` → `estado_producto == Blocked` antes de informar |
| API del analista | `listar_casos`, `ver_caso`, `aprobar_abono`, `aprobar_bloqueo`, `desbloquear_tarjeta`, `pedir_datos_cliente`, `marcar_ambiguo`, `cerrar_caso`, `reabrir_caso`, `modo_supervisado` | Solo el humano las ejecuta; cada una es un evento con actor y motivo |
| `handoff.schema.json` | Solicitud, hechos verificados, acciones con resultado y `verificado`, evidencia, preguntas abiertas, propuesta del copiloto, plazo con fuente, `trace_id` | Nunca el transcript crudo |
| `eval_case.schema.json` | Id, idioma, tipo, origen team-generated, estado inicial, mensajes, esperado (decisión, zona, estado final) | Estado final, no texto |
| `gold_contract.md` | Tablas base (12 meses: 2025-06-01 a 2026-05-31), derivadas, fixtures, `gold_eval/` y `gold_analytics/`; reglas G1–G5 antes de publicar | `is_fraud` nunca en tablas de las tools; gold solo lectura |

## Números del pitch verificados
Los 15 números se reproducen con `python -m queries.run`; ver `docs/eda/README.md` (tabla número → query → CSV) y `04_diego.md` (explicación en palabras). Tres cambian de redacción: duración mediana en vez de AHT; recall 48.8% sobre fraudes con score (38.7% del total); 679 solo como promedio de 36.4%.

## Cambios del lunes en la tarde
- `policies.yaml`: `case_queue`, `notifications`, `guardrails` (15 con ID), `data_splits`; `bloquear_tarjeta` en zona alta → `manual_check`; `close: human_only`.
- `tools.py`: `calcular_plazo`, `notificar_cliente`, `AccionAnalistaIn/Out`, `Transaccion.split`.
- `eval_case.schema.json`: `conjunto`, `guardrail_ids`, `estado_cola`, `notificaciones`. `handoff.schema.json`: `estado_cola`, `notificaciones_enviadas`, `guardrails_disparados`.
- Repo `factored-hackathon-2026-contrareloj`: `docs/README.md`, `docs/equipo/*.md`, `docs/anexos.md`, `docs/stack.md`, `docs/conceptos.md`, `docs/diferenciales.md`, `docs/assets/*.svg`, `contracts/`, `eval/`.

## Pendientes
- [ ] Cuentas de GitHub de los cuatro; push del repo público (David) en cuanto Freddy comparta el nombre final.
- [ ] Confirmar en Slack la hora límite: lunes 5 de octubre, 5:00 pm.
- [ ] Modelos de Bedrock habilitados en `us-east-2`.
- [ ] Plan y región de LangGraph Platform verificados.
- [ ] Databricks lee el bucket S3 o se descarta.
- [ ] Matriz de conteos del set de evaluación (Freddy).
- [ ] `docs/decisiones.md` con estas decisiones fechadas.
- [ ] Umbrales de monto calibrados con el snapshot.
- [ ] Defaults del modo de aprobación por acción y por zona en `policies.yaml`.
- [ ] Fijar versiones en `requirements.txt` (DuckDB incluido).
- [ ] Decidir clasificador de injection (reglas + LR recomendado, o Llama Guard) y grounding de salida (comparación exacta recomendada, o LLM juez).
