# Stack cerrado y setup del full stack — W3 Contra Reloj

> Lunes 28-sep-2026. Decisiones para no volver a discutir. Etiqueta `[opinión]` donde es criterio mío.

---

## 1. Decisiones de stack (y por qué)

| Pregunta | Decisión | Por qué |
|---|---|---|
| ¿Amplify + EC2 con GHCR? | **Sí, con un matiz:** backend en **EC2** con `docker compose` y imágenes en **GHCR**; frontend en **Amplify** solo si el equipo quiere dos deploys. **Recomendación `[opinión]`: monolito de despliegue en EC2** (Caddy + API + web en un `compose`) y Amplify como opcional | App Runner no lee GHCR (solo ECR), así que EC2 es lo natural con GHCR. El riesgo de separar es HTTPS: Amplify sirve en `https://` y si el backend en EC2 está en `http://` el navegador bloquea las llamadas (mixed content). Con Caddy en EC2 y un dominio (el tuyo o un subdominio gratis tipo DuckDNS) el TLS es automático y el front puede vivir en el mismo Caddy |
| ¿LangGraph con Bedrock? | **Sí, ahora, no después.** Es el orquestador | Tú ya lo conoces; su `StateGraph` es literalmente la máquina de estados Entender → Identidad → Recuperar → Decidir → Actuar → Verificar → Escalar; `get_graph().draw_mermaid()` dibuja el grafo real del agente para la UI y las slides (eso es el "wow" honesto: es el código, no un dibujo); checkpoints por sesión; `ChatBedrock` de `langchain-aws` conecta sin salir de la cuenta. Un solo grafo, sin multi-agente |
| ¿Observabilidad? | **LangSmith para desarrollo + nuestro log de auditoría como fuente de verdad** | LangSmith se enciende con dos variables de entorno y muestra cada nodo, tool y tokens. Pero es SaaS fuera de AWS: los textos del demo (sintéticos) viajan allá; se declara. El grafo de evidencia y el punto 6 del reto salen de **nuestra** tabla de auditoría (DynamoDB o SQLite), no de LangSmith. Si Slack prohíbe SaaS externo, se apaga LangSmith y queda el log propio + OpenTelemetry a CloudWatch |
| ¿Dónde viven las tools? | **En el mismo contenedor del backend**, como funciones Python decoradas `@tool` que leen DuckDB y escriben DynamoDB | Lambda agrega un deploy más, cold starts y credenciales; no suma puntos. En la slide de ruta a operación se dice: "en producción cada tool sería un servicio del banco detrás de un gateway" |
| ¿Astro o Next? | **Next.js (App Router) + Tailwind + shadcn/ui + next-themes.** Decidido | Astro no ejecuta Next; ejecuta islas de React. Next solo es más simple para una app con dos vistas con estado y streaming |
| ¿Dónde corre el grafo? | **Opción A primaria: LangGraph Platform** (deploy desde `langgraph.json`, Studio, persistencia, `interrupt()` para el humano) con las tools como **servidor MCP en la EC2** (FastMCP detrás de Caddy, API key o mTLS, allowlist de IP). **Opción B (todo en EC2)** queda documentada como migración: el grafo no importa nada de plataforma y las tools son las mismas funciones; cambiar A → B es reemplazar el adaptador MCP por import directo. Por tiempo no se ejecuta B; se explica en el README y en la slide de ruta a operación | El equipo conoce la plataforma; menos infraestructura que mantener en 8 días. Condiciones: preguntar en Slack hoy si el texto sintético puede salir de AWS y declararlo en el README; `langgraph dev` en local para depurar; el harness corre contra la URL del deploy. Si Slack lo prohíbe, B pasa a primaria sin tocar el grafo |
| ¿Cómo se obtiene el `fraud_score`? | **Como una tool con proveedor intercambiable**: `obtener_score(transaction_id)` → `{score, fuente, version}`. Proveedores: `dataset` (lee la columna del gold para las transacciones preseteadas del demo; el de arranque), `reglas` (heurística simple: monto vs habitual, canal, hora, país), `modelo` (plan B entrenado contra `is_fraud`), `llm` (solo para ilustrar; nunca decide bloqueo). El proveedor activo se fija en `policies.yaml` y la fuente queda en la auditoría y en la tarjeta de handoff ("score 72 · fuente: dataset v1") | Refleja la realidad: el motor de fraude del banco es un servicio que el sistema consume. Si Slack dice que el score no existe en tiempo real, se cambia el proveedor a `modelo` sin tocar el grafo ni las políticas |
| ¿Lógica de estados en la web? | **No.** Toda transición de caso pasa por `POST /api/casos/{id}/accion`, validada contra `policies.yaml` y escrita en auditoría | Permisos fuera del cliente; cada transición con traza. La web solo tiene estado de interfaz |
| ¿Databricks para el pipeline? | **Permitido con tres condiciones**, si no, DuckDB local | (1) workspace sin bloqueo de costo que lea hoy el bucket S3 de `us-east-2`; (2) gold materializado como Parquet en nuestro bucket, que la API lee con DuckDB; (3) notebooks exportados a `.py` en el repo + script local de respaldo para que el jurado reproduzca sin Databricks |
| ¿Monolito front + back? | **Sí en despliegue, no en código.** Dos carpetas (`apps/web`, `apps/api`), tres contenedores (caddy, api, web) en un `compose` en la misma EC2 | Evalúan "backend, frontend y deploy" y "setup reproducible", no la separación de servicios. Un `docker compose up` que levanta todo es más defendible que cinco servicios |
| ¿AgentCore o Bedrock Agents? | **No para construir.** Se menciona en ruta a producción | Bedrock Agents define la orquestación en consola: difícil de evaluar con pass^4 y de mostrar "política fuera del modelo". AgentCore Policy (Cedar) es exactamente nuestro motor de políticas, pero está en preview y suma curva; nuestro `policies.yaml` + evaluador hace lo mismo y lo controlamos. La slide de ruta: "el evaluador YAML se reemplazaría por AgentCore Policy y las tools irían al Gateway" |
| ¿Dashboard de analytics? | **Sí, como página de la app**, no como producto aparte | El kickoff dice que no es obligatorio, pero hay un criterio de Data Analytics. Una página con Recharts que lee CSV precalculados del gold layer cuesta medio día y muestra el problema y los resultados |
| ¿Modelo en Bedrock? | El que tengan habilitado en `us-east-2`; uno bueno para entender y redactar, uno barato para clasificación zero-shot de respaldo | Pedir habilitación hoy: tarda horas |

---

## 2. Qué es la plataforma (páginas de la app)

| Ruta | Para quién | Qué muestra | Dueño |
|---|---|---|---|
| `/` | todos | Portada: qué es, arquitectura (SVG), links a las vistas, estado del deploy | Full stack |
| `/chat` | cliente | Chat ES/PT con toggle de idioma, panel lateral con la traza del caso en vivo | Full stack |
| `/consola` | analista | Bandeja de casos escalados; detalle con tarjeta de handoff, grafo de evidencia, traza, botones aprobar abono / pedir datos / cerrar | Full stack |
| `/datos` | jurado | Pipeline (bronze → silver → gold), reporte de calidad con conteos, manifest del snapshot, fixture de updates | Datos 1 (contenido), Full stack (página) |
| `/evaluacion` | jurado | Tabla de resultados held-out por escenario × idioma × segmento con n, pass^4, latencia, costo; análisis de errores | Freddy (contenido), Full stack (página) |
| `/analytics` | jurado | Dashboard: problema en números, zonas del score, plazos por país, business case con etiquetas | Datos 2 (contenido), Full stack (página) |
| `/agente` | jurado | El grafo real de LangGraph (`draw_mermaid`), `policies.yaml` renderizado, contratos de tools | Freddy (contenido), Full stack (página) |

No es un chat: son siete páginas sobre un backend. El chat y la consola son las que se demuestran en el video; las otras cuatro son las que el jurado abre después.

---

## 3. Estructura del repo

```
factored-hackathon-2026-contrareloj/
├── README.md                 # setup en un comando, arquitectura, qué es real y qué es mock
├── problem.md
├── docker-compose.yml        # caddy + api + web
├── Caddyfile                 # TLS automático, /api/* → api:8000, /* → web:3000
├── .github/workflows/
│   ├── ci.yml                # tests + validación de schemas + build
│   └── deploy.yml            # build → push GHCR → ssh EC2 → compose pull && up
├── apps/
│   ├── api/                  # FastAPI + LangGraph + tools + policies
│   │   ├── graph/            # nodos del StateGraph
│   │   ├── tools/            # buscar_transaccion, bloquear_tarjeta, abrir_caso, estado_*
│   │   ├── policy/           # evaluador de policies.yaml + reloj regulatorio
│   │   ├── audit/            # log de auditoría (DynamoDB / SQLite) → grafo de evidencia
│   │   └── classifier/       # reglas, embeddings+LR, jev (opcional)
│   └── web/                  # Next.js + shadcn (7 páginas)
├── contracts/                # policies.yaml, tools.py, handoff.schema.json
├── data/
│   ├── pipeline/             # bronze→silver→gold, checks, manifest, fixture
│   └── gold/                 # parquet versionado (o .gitignore + descarga desde S3)
├── eval/                     # eval_case.schema.json, casos .jsonl, harness, resultados
├── docs/eda/                 # expedientes, queries, CSV de salida
└── infra/                    # user-data de EC2, IAM mínimo, variables de entorno de ejemplo
```

---

## 4. Auto-deploy (el "hola mundo" más importante)

`deploy.yml` en cada push a `main`:
1. `docker build` de `apps/api` y `apps/web` → push a `ghcr.io/<org>/contrareloj-api:sha` y `-web:sha`.
2. `ssh` a la EC2 (clave en GitHub Secrets) → `docker compose pull && docker compose up -d`.
3. Smoke test: `curl https://<dominio>/api/health` y `/` devuelven 200; si no, el job falla y avisa.

EC2: `t3.medium` (DuckDB con 5M transacciones cabe en memoria si el gold layer es Parquet filtrado; si no, `t3.large`), rol IAM con lectura a S3 del dataset, `bedrock:InvokeModel`, DynamoDB y CloudWatch Logs. Puertos 80/443 abiertos, 22 solo desde la IP del equipo.

---

## 5. Tareas del full stack con criterio de aceptación (hoy y mañana)

Orden estricto: cada hola mundo se hace, se despliega y se ve en la URL pública antes de pasar al siguiente.

| # | Tarea | Criterio de aceptación (se cumple o no) | Estimado |
|---|---|---|---|
| 1 | Repo `factored-hackathon-2026-contrareloj` con estructura de la sección 3, `.gitignore` (`.env`, `data/gold`, `node_modules`), `README` con placeholders | El repo existe, es público, y `git log -p \| grep -i -E "AKIA\|secret"` no devuelve nada | 30 min |
| 2 | EC2 + dominio + Caddy | `https://<dominio>/` responde con TLS válido (candado) y `https://<dominio>/api/health` devuelve `{"status":"ok","version":"<sha>"}` | 1.5 h |
| 3 | `apps/api` FastAPI hola mundo en contenedor | `/api/health` sale de la imagen `ghcr.io/.../contrareloj-api`, no del host | 45 min |
| 4 | `apps/web` Next.js + shadcn + next-themes hola mundo | La portada carga en dark por defecto, el toggle cambia a light, y se ve bien en un móvil (DevTools 390px) | 1 h |
| 5 | `deploy.yml` completo | Un push a `main` que cambia el texto de la portada se ve en la URL en menos de 10 min sin tocar la EC2 | 1 h |
| 6 | Bedrock hola mundo desde el contenedor | `POST /api/llm/ping` devuelve una frase generada por el modelo usando el rol IAM (sin claves en el contenedor) | 45 min |
| 7 | LangGraph hola mundo | Un `StateGraph` con nodos `entender → decidir → responder` corre en `/api/chat`, y `/api/agente/grafo` devuelve el Mermaid de `get_graph()` que la página `/agente` renderiza | 1.5 h |
| 8 | DuckDB + S3 hola mundo | `/api/tools/ping` lee un Parquet del bucket (o del gold local) y devuelve `count(*)` de `transactions` | 45 min |
| 9 | DynamoDB (o SQLite en dev) hola mundo | `/api/audit/ping` escribe y lee una fila `{trace_id, step, tool, result, ts}`; `docker compose` levanta el mismo código con SQLite si no hay AWS | 45 min |
| 10 | LangSmith + log de auditoría | Una llamada a `/api/chat` aparece como traza en LangSmith **y** como filas en la tabla de auditoría con el mismo `trace_id` | 30 min |
| 11 | Identidad mock | `POST /api/session` con `customer_id` → OTP simulado (siempre `000000` en demo) → sesión con TTL 15 min; `/api/tools/*` sin sesión devuelve `401` y con sesión vencida `SESSION_EXPIRED` | 1 h |
| 12 | Tools según `contracts/tools.py` sobre el gold layer | `buscar_transaccion` con la sesión de C-48213 nunca devuelve transacciones de otro cliente (test); `bloquear_tarjeta` dos veces con la misma `idempotency_key` no duplica; `estado_producto` refleja el bloqueo | 3 h |
| 13 | Página `/chat` real | Envía un mensaje, recibe respuesta en streaming, el panel lateral lista los pasos del grafo con tiempos | 3 h |
| 14 | Página `/consola` | Lista casos con `zona = humano`; abre uno y renderiza `handoff.schema.json`; el botón "aprobar abono" cambia el estado del caso y queda en la auditoría | 4 h |
| 15 | Páginas `/datos`, `/evaluacion`, `/analytics`, `/agente` | Cada una renderiza el contenido que le entrega su dueño desde archivos en `data/gold`, `eval/resultados` y `docs/` (JSON/CSV), sin código de negocio en el front | 1 día (viernes) |

Tareas 1–5 hoy. 6–10 mañana martes en la mañana. 11–12 martes tarde. 13 miércoles (junto al caso end-to-end). 14 jueves. 15 viernes.

---

## 6. Condiciones iniciales del front (para no rehacer)

- Dark por defecto (`next-themes`, `class` strategy), toggle en el header, tokens de color en `globals.css`.
- Responsive: chat a pantalla completa en móvil; consola de tres columnas (bandeja · caso · evidencia) que pasa a pestañas en < 1024px.
- Colores semánticos fijos: zona alta `emerald`, media `amber`, humano `rose`; DENY en rojo con `policy_id`.
- IDs en monoespaciada; "aceptado" y "verificado ✓" son estados distintos y se ven distintos.
- Toggle ES/PT que cambia el idioma de la UI y del caso; textos de UI en un JSON por idioma.
- Estados obligatorios en cada vista: cargando, error, vacío, DENY, sesión vencida.
- Referencias visuales: inbox de Intercom (consola), Linear (densidad y dark), visor de trazas de Langfuse (panel de traza).

---

## 7. Tareas de los otros tres con criterio de aceptación

### Freddy (agente, políticas, ML, harness)
| # | Tarea | Criterio de aceptación | Cuándo |
|---|---|---|---|
| F1 | Evaluador de `policies.yaml` (`apps/api/policy`) | `evaluate(score, amount_usd, pais, producto, sesion)` devuelve `zona`, `acciones_permitidas`, `plazos` con fechas en días hábiles y `policy_ids`; tests: 5 zonas/umbrales × 4 países pasan; `score=None` → humano | Lun–Mar |
| F2 | Reloj regulatorio | Para MX débito con transacción de las últimas 48 h devuelve `fecha_abono = +2 días hábiles` y `fecha_dictamen = +45 días`; AR `+10 hábiles`; CO `+15`; BR `+10 hábiles`; feriados como lista en YAML (fixture, etiquetado) | Mar |
| F3 | Grafo LangGraph v0 | `StateGraph` con estado tipado (`sesion`, `idioma`, `intencion`, `slots`, `candidatas`, `zona`, `acciones`, `verificaciones`, `handoff`); nodos entender → identidad → recuperar → decidir → actuar → verificar → escalar/responder; `langgraph dev` lo abre en Studio; EV-0001 llega a `Blocked` + caso + plazo | Mar–Mié |
| F4 | Prueba de Jev | 40 frases ES + 40 PT etiquetadas; Jev vs reglas: si no supera a reglas en PT o falla el acceso, se cierra con una nota en `docs/decisiones.md` | Mié |
| F5 | Clasificador de intención | Reglas por palabras clave; embeddings + regresión logística calibrada (split por plantilla, τ en validación); tabla macro-F1 por idioma, ECE y cobertura al 95% de exactitud; nodo `entender` usa el mejor y se abstiene bajo τ | Jue |
| F6 | Harness | Corre `eval/*.jsonl`, compara estado final contra `esperado`, pass^4, latencia p50/p95, tokens y costo por caso, por idioma × tipo × segmento con n; salida en `eval/resultados/*.csv` que lee `/evaluacion` | Vie–Sáb |
| F7 | Calibración de zonas | Curva precisión/recall de `fraud_score` contra `is_fraud` en held-out temporal + por cliente con IC; features + score vs score solo; conclusión honesta en `docs/ml.md` | Sáb |
| F8 | Integración diaria | Desde el miércoles, un caso end-to-end por día en la URL pública; bloqueo de alcance el jueves si no corre | Diario |

### Datos A (pipeline, calidad, presentación del repo)
| # | Tarea | Criterio de aceptación | Cuándo |
|---|---|---|---|
| A1 | Decidir Databricks o DuckDB | Hoy: un notebook o script lee `transactions` del bucket S3 de `us-east-2`; si no, DuckDB local sin discusión | Lun |
| A2 | Bronze → silver con contratos | Contratos de schema (pandera o Pydantic) para customers, products, transactions, complaints, surveys; checks con conteos: duplicados, nulos, FK a producto de otro cliente, fechas futuras, transacción antes de apertura, `México`/`Mexico`; `data/quality_report.md` generado, no escrito a mano | Mar |
| A3 | Gold Parquet + manifest | `data/gold/*.parquet` (o en S3) con `manifest.json`: versión, fecha, filas por tabla, hash; la API lo lee con DuckDB; `make setup` lo reproduce desde cero en < 15 min | Mar–Mié |
| A4 | Fixture de actualizaciones | Carpeta `data/fixtures/late_arrival/` con particiones tardías y un cambio de schema, etiquetada; el pipeline la procesa y el reporte muestra qué cambió; casos `missing_data` y `late_arrival` en `eval/` | Jue |
| A5 | `docs/eda` ordenado | Expedientes W1–W4, `findings.md`, `calidad_datos.md`, `queries/` con su CSV de salida; un índice que diga qué archivo respalda cada número del pitch | Mié |
| A6 | Página `/datos` (contenido) | JSON/MD que el front renderiza: diagrama del pipeline, tabla de checks con conteos, manifest, fixture | Vie |
| A7 | README y reproducibilidad | `git clone` + `.env.example` + `docker compose up` levanta todo con SQLite y gold local; sección "qué es real, qué es mock, qué es sintético"; revisión de secretos en el historial | Dom |

### Datos B (analytics, negocio, set de evaluación)
| # | Tarea | Criterio de aceptación | Cuándo |
|---|---|---|---|
| B1 | Queries del pitch congeladas | `queries/` con SQL y CSV de salida para: 36.4% (reglas CMP-01/02/03 con confianza), FCR y seguimiento por motivo, AHT, NPS/CSAT, 16 días, 120 fraudes/mes, precisión/recall por umbral de score; cada número del deck apunta a un archivo | Lun–Mar |
| B2 | Plazos y business case | `docs/negocio.md`: tabla de plazos por país con link; fórmula de ahorro con supuestos etiquetados; outcomes de tiempo y calidad con línea base; separación medido / simulado / proyectado | Mar |
| B3 | Set de evaluación ES/PT | 200–300 casos en `eval/casos.jsonl` válidos contra `eval_case.schema.json`; cobertura mínima por celda idioma × tipo (normal, ambiguo, humano, injection, session_expired, unauthorized, tool_failure, missing_data) × país; Freddy define la matriz de conteos el lunes | Mar–Jue |
| B4 | Doble etiquetado | Una segunda persona etiqueta 40 casos al azar; acuerdo reportado (% y kappa); desacuerdos resueltos y documentados | Jue |
| B5 | Especificación de vistas | Una página por vista (chat, consola) con campos, estados y acciones, para que el full stack construya sin adivinar | Mar |
| B6 | Tablero `/analytics` | Power BI publicado en la web y embebido, o CSV + Recharts; lee solo `queries/*.csv`; muestra problema, zonas, plazos, business case con etiquetas | Jue–Vie |
| B7 | Tabla de resultados | Con la salida del harness: por escenario × idioma × segmento con n; texto para la slide de resultados y para el README | Sáb |
