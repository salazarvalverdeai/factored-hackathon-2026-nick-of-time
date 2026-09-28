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
| GianMarco | URL del grafo en Platform; contratos de tools y de handoff; endpoint `POST /api/casos/{id}/accion` especificado | Mar 29 (contratos), Mié 30 (URL) |
| Diego | Matriz de conteos del set; lista de casos de ataque; formato de resultados del harness | Lun 28, Jue 1 |
| David | `gold_contract.md` con lo que leen las tools | Lun 28 |
| Todos | `docs/decisiones.md`; `docs/ml.md`; tabla de resultados | Diario; Sáb 3 |

## Tools por actor (lo defino yo, lo construye GianMarco)

| Actor | Tool | Quién la llama | Efecto |
| --- | --- | --- | --- |
| Cliente (agente vía MCP) | `buscar_transaccion`, `obtener_score`, `calcular_plazo` | El grafo, con `session_id` | Solo lectura sobre el cliente de la sesión |
| Cliente (agente vía MCP) | `bloquear_tarjeta`, `abrir_caso` | El grafo, si la política lo permite y el modo de aprobación lo autoriza | Escritura con post-condición e idempotencia |
| Cliente (agente vía MCP) | `estado_producto`, `estado_caso` | El grafo después de cada acción | Verificación; sin esto no se informa nada |
| Analista (consola vía API) | `listar_casos`, `ver_caso` (tarjeta, evidencia, traza) | La consola | Solo lectura |
| Analista (consola vía API) | `aprobar_abono`, `aprobar_bloqueo`, `desbloquear_tarjeta`, `pedir_datos_cliente`, `marcar_ambiguo`, `cerrar_caso`, `reabrir_caso` | El humano con un clic; el copiloto solo propone | Cada una es un evento en `case_events` con actor, motivo y `trace_id` |

El agente nunca llama a las tools del analista; la consola nunca llama a las del cliente.

## Modo de aprobación configurable

En `policies.yaml`, por acción: `auto` (ejecuta y verifica), `human_required` (propone y espera clic del analista), `manual_check` (ejecuta, pero el caso queda en revisión hasta un visto bueno). Defaults del demo: `abrir_caso` auto en las tres zonas; `bloquear_tarjeta` auto en zona alta, `human_required` en media; `abono_provisional` siempre `human_required`. Un interruptor global "modo supervisado" en la consola fuerza `human_required` en todo; cada cambio del interruptor queda en auditoría.

## Tareas

| Día | Tarea | Hecho cuando |
| --- | --- | --- |
| Lun 28 | Repo y nombre; cuentas de GitHub del equipo; Bedrock habilitado; plan y región de Platform; matriz de conteos del set; `docs/decisiones.md`; evaluador de `policies.yaml` con modo de aprobación | Tests por zona × país × modo pasan; `score=None` → humano |
| Mar 29 | Reloj regulatorio en días hábiles; servidor MCP con las tools del cliente sobre gold v1, permisos por sesión adentro, API key y allowlist | MX débito 48 h → abono +2 hábiles; Platform lista las tools; test de aislamiento por cliente |
| Mié 30 | Grafo LangGraph v0 (estado tipado, 7 nodos, `interrupt()`, checkpointer) en Platform; prueba de Jev (40 ES + 40 PT vs reglas) | EV-0001 llega a `Blocked` + caso + plazo MX; decisión Jev escrita |
| Jue 1 | Clasificador: reglas → embeddings + regresión logística calibrada → [Jev]; τ en validación; casos de ataque con Diego | Macro-F1 por idioma; el nodo `entender` se abstiene bajo τ |
| Vie 2 – Sáb 3 | Harness (estado final, pass^4, latencia, costo desde `llm_calls`, por idioma × tipo × segmento); calibración de zonas contra `is_fraud` con IC | `eval/resultados/*.csv` con n por celda; `docs/ml.md` |
| Diario desde Mié | Un caso end-to-end por día en la URL pública; jueves congela alcance | Corre o se recorta |

Viernes debe existir: los tres casos obligatorios corriendo contra la URL de Platform con verificación, handoff y modo supervisado activable.

## Dónde encuentro lo mío
`contracts/` (policies.yaml, tools.py, handoff.schema.json, gold_contract.md) · `apps/api/graph/`, `apps/api/policy/`, `apps/api/mcp/`, `apps/api/classifier/` · `eval/` (harness, casos, resultados) · `docs/decisiones.md`, `docs/ml.md`.
