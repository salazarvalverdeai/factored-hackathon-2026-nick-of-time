# Nick of Time — guía de construcción (detalle para el equipo)

28 de septiembre de 2026 · Freddy

## Qué construimos

No es un chat: es una plataforma de atención de disputas con cuatro piezas sobre un mismo backend, y el chat es solo la puerta de entrada. El LLM entiende, las reglas deciden, las tools actúan, la verificación confirma y el humano recibe evidencia.

| Pieza | Qué es | Quién la usa | Criterio del reto |
| --- | --- | --- | --- |
| Canal del cliente | Chat ES/PT que hace el intake completo sin humano en zona alta y media | Cliente | Casos normal y ambiguo; idiomas |
| Núcleo de decisión y acción | Grafo LangGraph + clasificador de intención + motor de políticas (YAML) + tools tipadas + verificación + reloj regulatorio | Backend | Puntos 2 y 3: acciones verificadas, permisos fuera del modelo |
| Consola del analista | Bandeja de casos escalados con tarjeta de handoff, grafo de evidencia, traza y botones (aprobar abono, pedir datos, cerrar) | Analista de disputas | Caso "requiere humano"; escalation quality |
| Evidencia y evaluación | Log de auditoría, trazas, harness held-out, pipeline con contratos | Jurado y nosotros | Puntos 4, 5 y 6 |

Siete páginas en la web: `/` portada, `/chat` cliente, `/console` analista, `/data` pipeline y calidad, `/evaluation` tabla de resultados, `/analytics` tablero, `/agent` grafo real y políticas. Las dos primeras van al video; las otras las abre el jurado después.

Fuera a propósito: investigación del caso, contracargo con la red, abono automático, voz, WhatsApp real, multi-agente, Graph RAG, fine-tuning. Resolvemos el contacto, no el reclamo: el reclamo lo resuelve el banco dentro del plazo que nosotros calculamos y mostramos.

| Alcance | Contenido |
| --- | --- |
| Entra (mínimo funcional) | Intake ES/PT; identidad mock con OTP; transacción del propio cliente; ticket automático en las tres zonas; triage por zona con bloqueo verificado; reloj regulatorio por país; **modo de aprobación configurable** (auto, con aprobación humana o con verificación manual; en zona alta el sistema actúa ya y el caso queda en verificación); **cierre siempre humano**, también de los casos automáticos; tarjeta de handoff; consola del analista con cola de cinco estados y sus tools; **notificación al cliente en cada estado** (log en el demo); **guardrails con ID** en entrada, sesión, tools, política, salida y operación, cada uno con su caso de prueba; trazas y auditoría; harness held-out sellado; deploy público; README reproducible |
| Entra si sobra tiempo | Notificación por Telegram (provisional); grafo de evidencia por caso; Jev como tercer brazo; `/analytics` embebido; voz en `/chat` con ElevenLabs |
| No entra | Investigación del caso, contracargo, abono automático, voz en tiempo real, WhatsApp real, multi-agente, Graph RAG, fine-tuning, modelo de fraude propio |

Dos actores, dos juegos de tools que nunca se cruzan: el cliente (a través del agente, vía MCP) puede buscar su transacción, obtener el score, calcular el plazo, bloquear su tarjeta y abrir su caso, siempre con verificación; el analista (desde la consola, vía API) lista y ve casos, aprueba abono o bloqueo, desbloquea, pide datos, marca ambiguo, cierra y reabre. El copiloto propone; solo el humano ejecuta las suyas.

## Conceptos que todos explican igual

Etiquetas de cada cifra: `[dato]` lo calculamos sobre el dataset del reto con query en el repo; `[externo]` fuente pública con link; `[supuesto]` estimación nuestra; `[simulado]` medido en nuestro harness, no en producción; `[proyectado]` extrapolación.

| Concepto | Definición que usamos | De dónde sale |
| --- | --- | --- |
| Disputa | Cargo no reconocido o cobro indebido sobre una transacción del cliente | `complaints.category` Transactions o Fees `[dato]` |
| Intake | Recibir el reclamo, verificar identidad, identificar la transacción exacta, decidir, actuar, verificar, abrir el caso con plazo y entregar al humano lo que él decide | Nuestro alcance |
| Resolución del contacto | El cliente termina con identidad verificada, transacción identificada, tarjeta protegida si había riesgo, número de caso, plazo y siguientes pasos, sin volver a llamar | Lo que mide el FCR (43.6% en quejas `[dato]`) y lo que reportamos como safe automated resolution |
| Resolución del reclamo | Abono y dictamen; la hace el banco en días dentro del plazo legal | Fuera de alcance; el sistema solo arranca el reloj |
| Zona | Franja del score que decide qué se automatiza: alta ≥ 50 (precisión 100%, recall 48.8% sobre fraudes con score, 38.7% del total), media 30–49 (precisión 79.6%), humano < 30 o sin score (20.6% de los fraudes) | `p08_fraud_score_thresholds.csv` `[dato]`; la precisión 100% es propiedad del generador sintético `[supuesto]` |
| Acción verificada | Después de actuar se relee el estado; solo se informa lo confirmado | Punto 2 del reto |
| Handoff | Tarjeta con solicitud, hechos verificados, acciones con resultado, evidencia (IDs), preguntas abiertas y plazo; nunca el chat crudo | Punto 3 del reto |
| Reloj regulatorio | Plazo legal por país y producto que corre desde el reclamo | CONDUSEF, BCRA, SFC, CMN 4.860 `[externo]` |
| Política fuera del modelo | Zonas, umbrales, permisos y plazos viven en `policies.yaml` y en las tools; el LLM no los lee ni los cambia | Punto 3 del reto |
| Held-out, baseline, pass^k | Casos que el sistema no vio; solución simple de comparación; cada caso k veces | Puntos 4 y 5 del reto |

Dos términos nuevos desde hoy: **modo de aprobación** es el ajuste por acción que decide si el sistema ejecuta solo (`auto`), propone y espera el clic del analista (`human_required`) o ejecuta y deja el caso en revisión (`manual_check`); **tools por actor** significa que el agente solo ve las del cliente y la consola solo las del analista, y cada llamada queda en auditoría con su actor.

## Arquitectura

![Arquitectura v2 mapeada al ciclo del reto](assets/architecture_v2_challenge_cycle.svg)

Opciones de despliegue A y B: `assets/deployment_options_A_B.svg`. Flujo del analista: `assets/analyst_flow.svg`.

El grafo y las tools se escriben una vez; A y B difieren solo en dónde corre el grafo y en cómo llama a las tools (MCP por red o import directo). GianMarco construye la EC2 primero porque es la base de ambas; Freddy levanta A encima cuando Platform tenga URL y Slack apruebe.

## Quién aporta qué en el proceso

Cada tarea tiene un "hecho cuando" observable. La franja de cada persona dice qué debe existir el viernes 2. Tacha aquí mismo lo que vayas cerrando.

![Flujo de un caso y qué aporta cada uno](assets/pipeline_and_owners.svg)

Arriba, los seis pasos que recorre un caso; abajo, la pieza que cada uno aporta por detrás para que ese paso exista. El paso 4 es el único donde decide una regla, nunca el modelo.

| Persona | Entrega por detrás | Dónde entra en el flujo | Detalle |
| --- | --- | --- | --- |
| Freddy | Grafo en Platform, `policies.yaml` con modo de aprobación, servidor MCP con las tools del cliente, clasificador ES/PT, harness | Entender, decidir, actuar, verificar, escalar; la evaluación | Freddy |
| GianMarco | EC2 con auto-deploy, `/chat`, consola con las tools del analista por API, `case_events` y auditoría, páginas | Canal del cliente, consola del analista, registro de cada acción | GianMarco |
| David | Gold v1 y v2 con contratos, manifest, fixtures de demo y de llegadas tardías, `/data` | Recuperar (lo que leen las tools) y la evidencia de data engineering | David |
| Diego | Queries del pitch, negocio y plazos, especificación de vistas, set de evaluación ES/PT, tablero | El problema en números, los casos que prueban el sistema, la tabla de resultados | Diego |

Repo: `factored-hackathon-2026-nick-of-time`. Detalle por persona en `docs/team/`; stack, contratos, números y pendientes en `docs/appendix.md`; diferenciales en `docs/differentiators.md`; contratos en `contracts/`; esquemas en `eval/`.

## Guardrails, por capa

Ninguno vive solo en el prompt: cada uno tiene un lugar en código, un ID que citan los DENY y un caso en el harness. Lista completa con implementación en `contracts/policies.yaml` (`guardrails`).

| ID | Capa | Qué protege | Caso que lo prueba |
| --- | --- | --- | --- |
| G-IN-01 | Entrada | Prompt injection directa e indirecta: texto del cliente y salidas de tools como datos delimitados; clasificador de injection → zona humano | injection |
| G-IN-02 | Entrada | Datos inventados por el cliente: monto, fecha y comercio solo sirven para buscar; score, producto y país salen del gold | injection |
| G-IN-03 | Entrada | Idioma y ambigüedad: ES/PT con umbral; baja confianza → pregunta, luego humano | ambiguo |
| G-IN-04 | Entrada | PII y fuera de alcance: PAN/CVV/contraseña se rechazan; temas fuera de disputas → abstención | out_of_scope |
| G-SES-01 / 02 | Sesión | OTP con TTL; `customer_id` solo desde la sesión; acceso a otro cliente → DENY | session_expired, unauthorized_access |
| G-TOOL-01 / 02 | Tools | Allowlist y esquemas estrictos; escrituras con modo de aprobación, idempotencia y post-condición; abono nunca auto | unauthorized_access, tool_failure |
| G-POL-01 | Política | Deny por defecto; toda denegación es una fila en `policy_denials` | todos |
| G-OUT-01 / 02 | Salida | Grounding: todo número, fecha, ID o estado existe en una tool o en la política; "bloqueada" solo con estado verificado | missing_data, tool_failure |
| G-OUT-03 / 04 | Salida | Sin datos ajenos ni secretos en la respuesta; sin promesas que la política no dio; abstención explícita | unauthorized_access, missing_data |
| G-OPS-01 / 02 | Operación | Tope de tokens antes de llamar, reintentos acotados, timeout; auditoría inmutable con actor y `trace_id` | tope, inspección |

## Datos de prueba: qué sale del dataset y qué ponemos nosotros

El dataset da la verdad del estado (clientes, productos, transacciones, scores, país) y las etiquetas de fraude; no da conversaciones ni resultados de disputas atados a una transacción. La partición se hace una sola vez en gold: `split` por cliente (`hash(customer_id) mod 10`: 0–6 entrenamiento, 7 desarrollo, 8–9 held-out) y `period` por tiempo (ajuste jun-2025 a feb-2026, medición mar–may-2026).

| Conjunto | De dónde sale | Para qué | Split y sello |
| --- | --- | --- | --- |
| Test del ML sobre `is_fraud` | 100% dataset (`gold_eval`) | Zonas del score y, si hace falta, el scoring de respaldo | Ajuste con clientes 0–6 × periodo de ajuste; medición en 8–9 × periodo de medición |
| Held-out del agente (~180 casos) | Estado real de clientes 8–9 + mensaje escrito por nosotros; el resultado esperado se deriva del registro | Safe resolution, unsafe outcomes, escalation quality, latencia, costo, pass^4; bloqueos del agente contra `is_fraud` real | Sellado el jueves 1 (`eval/heldout.sha256`); se corre el sábado 4 veces; nada se ajusta después |
| Casos de desarrollo (~60) | Clientes de la partición 7 | Construir y depurar | Sin sello |
| Set del clasificador de texto (300–400 frases) | Team-generated ES/PT con intención y slots | Componente aprendido vs baselines | 70/15/15 por autor o plantilla; nada del test aparece en el held-out ni en el prompt |

## Diferenciales frente a otros equipos

Con ~180 equipos y 10 días, la mayoría convergerá en un chat con RAG sobre políticas inventadas, casi siempre W1, con el LLM decidiendo, métricas de contención sobre una demo y sin held-out. Lo que nos separa, cada uno atado a un criterio del reto y con una prueba que se muestra:

| Diferencial | Criterio del reto | Cómo se demuestra |
| --- | --- | --- |
| Verificación visible: aceptado ≠ verificado; tool caída → acción no confirmada | Punto 2 | Caso `tool_failure` en el video |
| Política fuera del modelo, con cada DENY como fila y guardrails con ID | Puntos 3 y 5 | La inyección engaña al texto y no a la regla |
| Modo de aprobación configurable y cierre siempre humano | "AI should not be autonomous just because it can" | Interruptor supervisado en la consola |
| Evaluación por estado final, pass^4, n por celda, ES/PT y ataques, sobre held-out sellado | Puntos 4 y 5 | Tabla con fallas incluidas |
| Bloqueos del agente medidos contra `is_fraud` real del dataset | Unsafe outcomes | Métrica que no escribimos nosotros |
| Los 15 números reproducibles con `make setup` en 60 s y corregidos en público | Punto 1, Data Analytics | Índice número → query → CSV en `docs/eda/README.md` |
| Reloj regulatorio por país con fuente | Business reasoning | Día hábil 2 visible en el caso |
| Dos actores con tools separadas y notificación al cliente en cada estado | Escalation quality | Consola + panel del cliente |
| Etiquetas dato / externo / supuesto / simulado / proyectado en todo | Honestidad que pide el kickoff | Cada número del pitch y del README |

Dónde podríamos perder: si el caso end-to-end no corre el miércoles 30; si el clasificador ES/PT queda flojo y el componente aprendido parece decorado (el baseline de reglas va antes que el modelo); y si la demo se ve pobre frente a interfaces bonitas (`/chat` parte de `agent-chat-ui`).

## Calendario e hitos

Ver `hitos` en el deck de plan (lun 28 contratos · mar 29 gold v1 y MCP · mié 30 EV-0001 end-to-end · jue 1 chat y 3 casos · vie 2 funcional · sáb 3 eval y deploy · dom 4 paquete · lun 5 entrega 5:00 pm).

El miércoles 30 ordena la semana: si EV-0001 no corre de punta a punta, el jueves se congela a los tres casos obligatorios y se recorta lo demás. La entrega es el lunes 5 de octubre a las 5:00 pm (hora por confirmar en Slack); se envía a primera hora para no depender de la tarde.

## Reglas de trabajo y dependencias externas

Cinco reglas y una definición de "funcional".

1. Contratos primero: nadie codea contra algo que no esté en `contracts/`; cambiar uno es un PR revisado por Freddy.
2. Un caso end-to-end por día en la URL pública desde el miércoles, aunque sea feo.
3. El harness es de todos: David agrega datos faltantes y tardíos; GianMarco sesión vencida y tool caída; Freddy inyección y ambigüedad ES/PT; Diego por país y segmento.
4. El jueves se congela el alcance. Lo de "si sobra tiempo" se toca el sábado.
5. Secretos: `.env` en `.gitignore` desde el primer commit; David revisa el historial el domingo.

Funcional el viernes significa: caso normal en español con bloqueo verificado, caso abierto y plazo MX visible; caso ambiguo en portugués que pregunta con opciones y no actúa; caso humano con tarjeta de handoff en la consola, copiloto que propone y humano que aprueba con registro en auditoría; el sistema dice no (inyección → DENY con `policy_id`, sesión vencida → reautenticar, tool caída → escala con acción no confirmada); modo supervisado activable desde la consola; traza visible por paso; `/data` y `/analytics` con contenido real; deploy público que se levanta con `docker compose up`. Lista de recortes en orden: voz con ElevenLabs → grafo de evidencia → Jev → `/analytics` embebido → opción A si Platform falla. Los tres casos con verificación y handoff no se recortan nunca. Los datos son públicos y las claves del dataset también: no hay restricción para usar servicios externos, y se declara en el README.

| Dependencia | Si falla | Plan B | Dueño |
| --- | --- | --- | --- |
| Bedrock sin modelos el martes | No hay LLM | Orquestador con respuestas fijas hasta el miércoles; pedir habilitación hoy | Freddy |
| Databricks no lee el bucket | Pipeline atascado | DuckDB local sin discusión | David |
| Platform con plan o región que no sirve | Sin deploy del grafo | Opción B desde el miércoles: mismo grafo en FastAPI en la EC2 | Freddy y GianMarco |
| EC2 sin HTTPS a tiempo | El front no llama al backend | Caddy con dominio DuckDNS; mientras, todo local con compose | GianMarco |
| Jev no responde ES/PT | Sin tercer brazo | Se descarta el miércoles; LR queda como componente aprendido | Freddy |
| Freddy sobrecargado el miércoles | El grafo se atrasa | GianMarco toma el evaluador de políticas; Freddy se queda con grafo y harness | Todos |
