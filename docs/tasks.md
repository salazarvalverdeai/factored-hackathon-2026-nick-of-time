# Tablero (mover a issues de GitHub el lunes)

## Lun 28 · contratos y repo (todos, 2 h)
- [ ] Repo público `factored-hackathon-2026-<equipo>` con `.gitignore` (`.env`, `data/`) desde el commit 1
- [ ] Revisar `problem.md`, `contracts/policies.yaml`, `contracts/tools.py`, `contracts/handoff.schema.json`, `eval/eval_case.schema.json` (30 min, todos)
- [ ] Preguntar en Slack #technical-help: ¿datos sintéticos a APIs externas? ¿fraud_score disponible en tiempo real? ¿hora límite del 5-oct?
- [ ] Datos 1: descarga del dataset con credenciales en `.env`; snapshot de customers/products/transactions/complaints/surveys
- [ ] Datos 2: congelar en `queries/` las queries del pitch (36.4%, FCR, AHT, NPS, 16 días, 120 fraudes, zonas del score)

## Mar 29 · esqueleto
- [ ] Datos 1: DuckDB + checks (dedupe, schema, FK cruzada, fechas futuras, México/Mexico) + `make setup`
- [ ] Full stack: FastAPI + tools según `contracts/tools.py` con filtro por sesión + identidad mock (OTP, TTL 15 min)
- [ ] Freddy: evaluador de `policies.yaml` (zonas, amount gate, reloj por país con días hábiles) + logger de trazas (OTel o JSONL con spans)
- [ ] Datos 2: primeros 60 casos ES del set (normal/ambiguo/humano) con respuesta esperada

## Mié 30 · caso normal end-to-end + Jev
- [ ] Full stack + Freddy: EV-0001 corre de punta a punta con verificación (Blocked + caso + plazo MX)
- [ ] Freddy: prueba Jev en 40 frases ES/PT vs reglas; si no supera a reglas en PT o falla el acceso → descartado hoy
- [ ] Datos 2: 60 casos PT + 40 de ataque (injection, sesión, tool caída, dato faltante)
- [ ] Datos 1: fixture de llegadas tardías etiquetado; linaje del snapshot

## Jue 1 · clasificador + UI cliente
- [ ] Freddy: reglas → embeddings + LR (calibrado) → [Jev]; split por plantilla; τ en validación
- [ ] Full stack: UI de chat ES/PT con panel de traza
- [ ] Datos 2: segunda persona etiqueta una muestra de 40 casos (acuerdo)
- [ ] Todos: los 3 casos obligatorios corren

## Vie 2 · vista del agente + explicabilidad
- [ ] Full stack: tarjeta de handoff según schema + botones (aprobar abono / pedir datos) + grafo de evidencia desde el log
- [ ] Freddy: harness completo (estado final, pass^4, latencia, costo en tokens) + casos de "no"
- [ ] Datos 1: casos missing_data y late_arrival en el harness

## Sáb 3 · eval y deploy
- [ ] Freddy: correr eval completo, análisis de errores, tabla por escenario × idioma × segmento con n
- [ ] Full stack: deploy público, reintentos y fallback, grabar demo
- [ ] Datos 2: tabla de resultados + separación medido/simulado/proyectado en slides

## Dom 4 · entrega
- [ ] Video 3 min (guion en `guion_slides_w3.md`), 4–6 slides, README con setup en un comando
- [ ] Datos 1: revisar historial de git por secretos (`git log -p | grep -i AKIA`)
- [ ] Lun 5 a primera hora: enviar repo + deploy + slides + video a hackathon.admin@factored.ai
