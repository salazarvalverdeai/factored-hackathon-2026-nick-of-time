# factored-hackathon-2026-contrareloj

Factored AI & Data Hackathon 2026, equipo Contrarreloj. Dataset sintético LATAM Bank (MX, CO, AR; jun 2023 – jun 2026).

## Qué hay
| Carpeta | Contenido |
|---|---|
| `contracts/gold_contract.md` | Contrato de gold: 12 meses de transactions, `customer_id` resuelto por join, `is_fraud` solo en `gold_eval/`, tablas derivadas `customer_profile` y `transactions_enriched` |
| `data/pipeline/` | Pipeline bronze → silver → gold (DuckDB). Contratos de silver en `contracts.py` (pandera) |
| `data/fixtures/late_arrival/` | Fixture sintético de llegadas tardías y cambio de schema (IDs `FX-`) |
| `data/quality_report.md` | Reporte de calidad generado por el pipeline (no se edita a mano) |
| `data/gold/manifest.json` | Versión, fecha, filas y sha256 de cada tabla de `data/gold/` y `data/gold_eval/` (los Parquet no entran a git) |
| `docs/eda/` | EDA: índice en `docs/eda/README.md`, expedientes por workflow, calidad de datos, mapeo, notas del pipeline |
| `queries/pitch/` | Queries de verificación de los números del pitch y su salida (copia del repo del EDA) |
| `tests/` | pytest sin red: contratos, check de pertenencia al cliente y fixture de punta a punta |

## Cómo está organizado
La guía de construcción del equipo empieza en [`docs/README.md`](docs/README.md). Documentos, contratos y esquemas:

- [`docs/README.md`](docs/README.md) — índice del equipo y guía de construcción.\
  Qué construimos, conceptos compartidos, arquitectura, quién aporta qué, calendario, reglas y dependencias.
- [`docs/equipo/01_freddy.md`](docs/equipo/01_freddy.md) — Freddy: agente, políticas, MCP, ML, integración.\
  Qué recibe y entrega, tools por actor, modo de aprobación configurable y tareas.
- [`docs/equipo/02_gianmarco.md`](docs/equipo/02_gianmarco.md) — GianMarco: deploy, chat, consola, páginas.\
  EC2 con auto-deploy, `/chat`, consola del analista con sus tools por API y tareas.
- [`docs/equipo/03_david.md`](docs/equipo/03_david.md) — David: pipeline, calidad, presentación del repo.\
  Reglas del gold, manifest, fixtures, `make setup` y tareas.
- [`docs/equipo/04_diego.md`](docs/equipo/04_diego.md) — Diego: analytics, negocio, set de evaluación.\
  Los números explicados, qué es un buen caso de evaluación y tareas.
- [`docs/anexos.md`](docs/anexos.md) — anexos: stack, contratos, números, pendientes.\
  Decisiones de stack cerradas el lunes 28, contratos en `contracts/` y `eval/`, números del pitch verificados.
- [`docs/stack.md`](docs/stack.md) — stack cerrado y setup del full stack.\
  Decisiones y por qué, páginas de la app, estructura del repo, auto-deploy y criterios de aceptación.
- [`docs/conceptos.md`](docs/conceptos.md) — guía de conceptos de la idea W3.\
  One-pager, glosario, AS IS / TO BE, plazos legales, evaluación, business case y riesgos.
- [`problem.md`](problem.md) — definición del problema W3: intake de disputas con reloj regulatorio.\
  Alcance, despliegue, componente aprendido vs baseline, cómo se mide, riesgos, reparto y calendario.
- [`docs/tasks.md`](docs/tasks.md) — tablero de tareas por día (lun 28 a dom 4).\
  Se mueve a issues de GitHub.
- [`contracts/gold_contract.md`](contracts/gold_contract.md) — contrato de gold vigente (pipeline).\
  Lo aplica `data/pipeline/gold.py`; reglas G1–G5 verificadas en cada corrida y en `tests/`.
- [`contracts/gold_contract.propuesta.md`](contracts/gold_contract.propuesta.md) — propuesta de Freddy: qué lee el agente del gold y qué no.\
  Pendiente de conciliar con `gold_contract.md` (David).
- [`contracts/policies.yaml`](contracts/policies.yaml) — motor de políticas fuera del modelo (`default: deny`).\
  Identidad, alcance por cliente, zonas, umbrales y modo de aprobación; el LLM nunca lo lee ni lo edita.
- [`contracts/tools.py`](contracts/tools.py) — contratos tipados de las tools (pydantic).\
  Los permisos viven aquí: cada tool resuelve `customer_id` desde la sesión, nunca desde el texto.
- [`contracts/handoff.schema.json`](contracts/handoff.schema.json) — JSON Schema de la tarjeta de handoff.\
  Lo que recibe el humano: solicitud, hechos verificados, acciones, evidencia, preguntas abiertas y plazo.
- [`eval/eval_case.schema.json`](eval/eval_case.schema.json) — JSON Schema de un caso de evaluación held-out.\
  El harness compara estado final, no texto; IDs `EV-NNNN`, idioma, tipo de caso, país y segmento.
- [`eval/ejemplos.jsonl`](eval/ejemplos.jsonl) — casos de ejemplo que cumplen el esquema.\
  Referencia para armar el set ES/PT (`EV-0001` es el caso normal end-to-end).
- [`docs/assets/arquitectura.svg`](docs/assets/arquitectura.svg) — diagrama de arquitectura.\
  El LLM entiende, las reglas deciden, las tools actúan, la verificación confirma.
- [`docs/assets/arquitectura_despliegue_A_B.svg`](docs/assets/arquitectura_despliegue_A_B.svg) — despliegue opción A vs B.\
  Mismo grafo y tools; cambia dónde corre el grafo y cómo llama a las tools. Se usa en `docs/README.md`.
- [`docs/assets/flujo_3_zonas.svg`](docs/assets/flujo_3_zonas.svg) — flujo de un caso por las tres zonas.\
  Entender, identidad, recuperar, decidir por reglas, y los casos en que el sistema dice "no".
- [`docs/assets/grafo_evidencia.svg`](docs/assets/grafo_evidencia.svg) — grafo de evidencia para el revisor.\
  Cada nodo es una fila del log de ejecución (cliente, producto, transacción, score).
- [`docs/assets/pipeline_y_duenos.svg`](docs/assets/pipeline_y_duenos.svg) — pasos de un caso y qué aporta cada persona.\
  Se usa en `docs/README.md`.

## Cómo se reproduce
```bash
cp .env.example .env       # completar las credenciales S3 (diccionario de datos de Factored, pág. 2)
make setup                 # venv + dependencias + pipeline desde S3 + fixture + data/quality_report.md
make test                  # pytest, sin red
```
`make setup SOURCE=local` corre sobre un espejo local ya descargado en `data/<tabla>/` (sin red). Las credenciales
viven solo en `.env`, que no entra a git.
