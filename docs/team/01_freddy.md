# Freddy · agente, políticas, MCP, ML, integración

Entrego el núcleo: el grafo en Platform, las políticas, el servidor MCP con las tools del cliente, el clasificador y el harness. Soy el integrador: un caso end-to-end por día desde el miércoles.

Flujo (recibo → construyo → entrego): gold v1 y `demo_index` (David), set ES/PT y hola mundos (Diego), EC2 con Caddy y `case_events` (GianMarco), Bedrock y Platform habilitados → `policies.yaml` + evaluador + reloj, servidor MCP con tools del cliente, grafo LangGraph en Platform, clasificador ES/PT vs baselines, harness held-out con pass^4 → URL del grafo y contratos (GianMarco), matriz del set y ataques (Diego), `gold_contract` (David), tabla de resultados (todos).

## Qué recibo y qué entrego

| Recibo de | Qué | Para |
| --- | --- | --- |
| David | Gold v1 (customers, products, transactions 12 m) y derivadas; `demo_index.csv` | Tools sobre DuckDB; fixtures de eval |
| Diego | Hola mundos DuckDB y DynamoDB; set ES/PT; matriz de conteos aprobada | Harness; casos de ataque |
| GianMarco | EC2 con Caddy y dominio; `case_events`, `llm_calls`, `policy_denials`; `/chat` contra Platform | Desplegar el MCP; registrar decisiones y costo |

| Entrego a | Qué | Cuándo |
| --- | --- | --- |
| GianMarco | URL del grafo en Platform; contratos de tools y de handoff; endpoint `POST /api/cases/{id}/action` especificado | Mar 29 (contratos), Mié 30 (URL) |
| Diego | Matriz de conteos del set; lista de casos de ataque; formato de resultados del harness | Lun 28, Jue 1 |
| David | `gold_contract.md` con lo que leen las tools | Lun 28 |
| Todos | `docs/decisions.md`; `docs/ml.md`; tabla de resultados | Diario; Sáb 3 |

## Tools por actor (lo defino yo, lo construye GianMarco)

| Actor | Tool | Quién la llama | Efecto |
| --- | --- | --- | --- |
| Cliente (agente vía MCP) | `search_transaction`, `get_fraud_score`, `compute_deadline` | El grafo, con `session_id` | Solo lectura sobre el cliente de la sesión |
| Cliente (agente vía MCP) | `block_card`, `open_case` | El grafo, si la política lo permite y el modo de aprobación lo autoriza | Escritura con post-condición e idempotencia |
| Cliente (agente vía MCP) | `get_product_status`, `get_case_status` | El grafo después de cada acción | Verificación; sin esto no se informa nada |
| Analista (consola vía API) | `list_cases`, `get_case` (tarjeta, evidencia, traza) | La consola | Solo lectura |
| Analista (consola vía API) | `approve_credit`, `approve_block`, `unblock_card`, `request_customer_info`, `mark_ambiguous`, `close_case`, `reopen_case` | El humano con un clic; el copiloto solo propone | Cada una es un evento en `case_events` con actor, motivo y `trace_id` |

El agente nunca llama a las tools del analista; la consola nunca llama a las del cliente.

## Modo de aprobación configurable

En `policies.yaml`, por acción: `auto` (ejecuta y verifica), `human_required` (propone y espera clic del analista), `manual_check` (ejecuta, pero el caso queda en revisión hasta un visto bueno). Defaults del demo: `open_case` auto en las tres zonas; `block_card` auto en zona alta, `human_required` en media; `provisional_credit` siempre `human_required`. Un interruptor global "modo supervisado" en la consola fuerza `human_required` en todo; cada cambio del interruptor queda en auditoría.

## Tareas

| Día | Tarea | Hecho cuando |
| --- | --- | --- |
| Lun 28 | Repo y nombre; cuentas de GitHub del equipo; Bedrock habilitado; plan y región de Platform; matriz de conteos del set; `docs/decisions.md`; evaluador de `policies.yaml` con modo de aprobación | Tests por zona × país × modo pasan; `score=None` → humano |
| Mar 29 | Reloj regulatorio en días hábiles; servidor MCP con las tools del cliente sobre gold v1, permisos por sesión adentro, API key y allowlist | MX débito 48 h → abono +2 hábiles; Platform lista las tools; test de aislamiento por cliente |
| Mié 30 | Grafo LangGraph v0 (estado tipado, 7 nodos, `interrupt()`, checkpointer) en Platform; prueba de Jev (40 ES + 40 PT vs reglas) | EV-0001 llega a `Blocked` + caso + plazo MX; decisión Jev escrita |
| Jue 1 | Clasificador: reglas → embeddings + regresión logística calibrada → [Jev]; τ en validación; casos de ataque con Diego | Macro-F1 por idioma; el nodo `understand` se abstiene bajo τ |
| Vie 2 – Sáb 3 | Harness (estado final, pass^4, latencia, costo desde `llm_calls`, por idioma × tipo × segmento); calibración de zonas contra `is_fraud` con IC | `eval/results/*.csv` con n por celda; `docs/ml.md` |
| Diario desde Mié | Un caso end-to-end por día en la URL pública; jueves congela alcance | Corre o se recorta |

Viernes debe existir: los tres casos obligatorios corriendo contra la URL de Platform con verificación, handoff y modo supervisado activable.

## Dónde encuentro lo mío
`contracts/` (policies.yaml, tools.py, handoff.schema.json, gold_contract.md) · `apps/api/graph/`, `apps/api/policy/`, `apps/api/mcp/`, `apps/api/classifier/` · `eval/` (harness, casos, resultados) · `docs/decisions.md`, `docs/ml.md`.

## Cambios del lunes en la tarde
- Guardrails con ID en `contracts/policies.yaml` (`guardrails`); cada DENY cita su ID; cada guardrail tiene un caso en `eval/`. Yo escribo el clasificador de injection (reglas + LR) y el filtro de grounding de salida (comparación exacta contra resultados de tools).
- Particiones en gold: `split` por cliente y `period` por tiempo; el held-out se sella el jueves 1 con `eval/heldout.sha256`; se corre el sábado 4 veces y no se ajusta después.
- Dos matrices para Diego: set del clasificador (300–400 frases, 70/15/15) y held-out del agente (~180 casos solo con clientes 8–9).
- Métrica nueva: bloqueos del agente contra `is_fraud` real (solo `gold_eval`, solo el harness).
- Cierre siempre humano y `notify_customer`: la zona alta ejecuta y deja el caso en `verification`; el nodo escalar dispara la notificación por estado.
