# GianMarco · full stack: deploy, chat, consola, páginas

Entrego lo que se ve y lo que se despliega: EC2 con auto-deploy, el chat del cliente contra Platform, la consola del analista con sus tools por API, y las páginas que muestran el trabajo de los demás.

Flujo (recibo → construyo → entrego): contratos y URL del grafo (Freddy), spec de vistas y hola mundos (Diego), gold y contenido de `/datos` (David), cuenta AWS y cuentas de GitHub → EC2 + Caddy TLS + GHCR + auto-deploy, identidad mock, `case_events` y auditoría, `/chat` desde agent-chat-ui, consola con tools del analista, páginas `/datos` `/evaluacion` `/analytics` → EC2 lista para el MCP (Freddy), URL pública con los tres casos, consola con aprobar abono, `docker compose up` reproducible.

## Qué recibo y qué entrego

| Recibo de | Qué | Para |
| --- | --- | --- |
| Freddy | Contratos de tools y de handoff; URL del grafo en Platform; especificación de `POST /api/casos/{id}/accion` y de las tools del analista | Conectar `/chat`; construir la consola |
| Diego | Hola mundos de DuckDB y DynamoDB; especificación de vistas (campos, estados, botones); CSV para `/analytics` | Construir sin adivinar |
| David | Gold v1 y manifest; contenido de `/datos` | Tools sobre DuckDB; página de datos |

| Entrego a | Qué | Cuándo |
| --- | --- | --- |
| Freddy | EC2 con Caddy y dominio para desplegar el MCP; tablas `case_events`, `llm_calls`, `policy_denials`; endpoint de acciones del analista | Lun 28 (EC2), Mié 30 (tablas) |
| Todos | URL pública con auto-deploy; `/chat`; `/consola`; `/datos`, `/evaluacion`, `/analytics`, `/agente`; `docker compose up` reproducible | Mar 29, Jue 1, Vie 2, Dom 4 |

## Tareas

| Día | Tarea | Hecho cuando |
| --- | --- | --- |
| Lun 28 | Estructura del repo; EC2 + dominio + Caddy TLS; `ci.yml` mínimo; FastAPI hola mundo en GHCR | `https://dominio/api/health` con candado; CI verde en el primer PR |
| Mar 29 | `deploy.yml` (build → GHCR → ssh → `compose pull && up` → smoke); Next + shadcn + next-themes hola mundo | Push a `main` visible en menos de 10 min; dark por defecto; se ve bien a 390 px |
| Mié 30 | `case_events` append-only, `llm_calls`, `policy_denials` en DynamoDB (SQLite en dev); `POST /api/casos/{id}/accion` con las tools del analista y el interruptor de modo supervisado | Estado del caso = último evento; cada DENY y cada clic del analista es una fila |
| Jue 1 | `/chat` desde `agent-chat-ui` contra Platform: dark, toggle ES/PT, panel de traza | Los tres casos obligatorios se ven en la URL pública |
| Vie 2 | `/consola`: bandeja, tarjeta de handoff según schema, botones (aprobar abono, aprobar bloqueo, pedir datos, cerrar, reabrir), grafo de evidencia desde `case_events`; `/datos`, `/evaluacion`, `/analytics`, `/agente` con contenido de sus dueños | Aprobar abono cambia el estado y queda en auditoría |
| Sáb 3 – Dom 4 | Deploy final, reintentos y fallback, grabar demo, README de setup | `docker compose up` levanta todo con SQLite y gold local |
| Si sobra tiempo | Voz en `/chat` con ElevenLabs (texto a voz de la respuesta y, si alcanza, dictado); opcional | Un caso normal se escucha en español y portugués |

Condiciones del front: dark por defecto con toggle; responsive (chat a pantalla completa en móvil, consola de tres columnas que pasa a pestañas bajo 1024 px); colores por zona (alta verde, media ámbar, humano rojo; DENY en rojo con `policy_id`); IDs en monoespaciada; "aceptado" y "verificado ✓" se ven distintos; estados de carga, error, vacío, DENY y sesión vencida en cada vista. Referencias: inbox de Intercom (consola), Linear (densidad y dark), visor de trazas de Langfuse (panel de traza).

Viernes debe existir: chat público con los tres casos visibles y consola con bandeja, aprobar abono y modo supervisado.

## Dónde encuentro lo mío
`docker-compose.yml`, `Caddyfile`, `.github/workflows/` · `apps/api/` (FastAPI, `audit/`, `routes/casos.py`) · `apps/web/` (Next: `/chat`, `/consola`, páginas) · `contracts/handoff.schema.json` · `infra/`.
