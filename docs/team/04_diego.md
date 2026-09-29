# Diego · analytics, negocio, set de evaluación

Entrego lo que hace medible todo lo demás: el set de evaluación ES/PT, los números del problema y del negocio con su query, la especificación de las vistas y el tablero.

Flujo (recibo → construyo → entrego): matriz del set y ataques (Freddy), `demo_index.csv` y `gold_analytics` (David), salida del harness (Freddy), plazos por país con fuente → queries del pitch congeladas con CSV, `docs/business.md`, spec de vistas chat y consola, set ES/PT de 200–300 casos con doble etiquetado, tablero `/analytics` → hola mundos y spec (GianMarco), `eval/cases.jsonl` (Freddy), tabla de resultados con n, slides de problema y negocio.

## Qué recibo y qué entrego

| Recibo de | Qué | Para |
| --- | --- | --- |
| Freddy | Matriz de conteos del set por idioma × tipo × país; lista de casos de ataque; formato de resultados del harness | Escribir el set; la tabla de resultados |
| David | `demo_index.csv` (clientes y transacciones reales con zona esperada); `gold_analytics/` | Casos con fixtures reales; tablero |

| Entrego a | Qué | Cuándo |
| --- | --- | --- |
| GianMarco | Hola mundos de DuckDB y DynamoDB; especificación de vistas chat y consola; CSV para `/analytics` | Lun 28, Mar 29, Jue 1 |
| Freddy | `eval/cases.jsonl` (200–300 casos válidos contra el schema); acuerdo del doble etiquetado | Jue 1 |
| Todos | `queries/` con CSV; `docs/business.md`; tabla de resultados; texto de slides 1, 2, 9 y 10 | Mar 29, Sáb 3 |

## Los números, explicados

| Número | Qué significa | Cómo se calcula | Cómo se dice en el pitch |
| --- | --- | --- | --- |
| 36.4% de los reclamos son W3 | De cada 100 reclamos del banco, 36 son cargos no reconocidos o cobros indebidos | `complaints` con `category` Transactions (5.0% Claim, confianza alta; 14.3% Complaint/Request, media) o Fees (17.2%, media), sobre 66,960 reclamos en 35 meses | "36.4% de los reclamos"; 679/mes solo como promedio |
| FCR 43.6% vs 76.6% | De cada 10 clientes que contactan por una queja, menos de 5 quedan resueltos en la primera vez; en el resto del banco, casi 8 | `call_center_interactions.was_resolved` promedio por `reason_category`; IC95 [43.3, 43.9], n = 117,021 | "Casi 6 de cada 10 vuelven a contactar" |
| 63% requiere seguimiento | La queja deja una tarea pendiente en 63 de cada 100 contactos (34.8% en el banco) | `requires_followup` por motivo | "Trabajo que no termina en la llamada" |
| Duración mediana 7.2 vs 4.9 min | La mitad de los contactos de queja dura más de 7.2 min; en el banco, más de 4.9 | `duration_seconds`, mediana por motivo. No decir "AHT": el AHT medio del banco es 5.4 | "El contacto dura casi el doble" |
| NPS −85.3 vs −74.5 | Casi nadie recomendaría el banco después de reclamar; la escala del dataset es 2–7 y no tiene promotores, así que solo vale como comparación | `satisfaction_surveys` unidas por `interaction_id` | "El peor motivo del banco en satisfacción" |
| 16 días de resolución p50 | La mitad de los reclamos W3 tarda más de 16 días; igual que el banco, así que no es dolor propio | `complaints.resolution_days` | Solo contra el plazo legal (Argentina: 10 días hábiles) |
| 120 fraudes/mes | Transacciones con `is_fraud = 1` por mes (4,316 en total, 891 sin score) | `transactions` sobre 35 meses completos | "58 de ellos son detectables en zona alta" |
| Precisión 100%, recall 48.8% con score ≥ 50 | Todas las transacciones con score ≥ 50 fueron fraude; ese corte atrapa el 48.8% de los fraudes que tienen score (38.7% de todos) | Barrido de umbrales contra `is_fraud` | "Precisión histórica; propiedad del generador sintético" |

## Qué es un buen caso de evaluación

Una transacción real del gold (de `demo_index.csv`) más un mensaje escrito por nosotros en español o portugués, con la decisión esperada (bloquear y caso, confirmar, preguntar, handoff, deny, reautenticar, escalar con acción no confirmada) y el estado final esperado. El harness compara estado final, no texto. Los mensajes se etiquetan como team-generated; una segunda persona etiqueta 40 al azar y se reporta el acuerdo.

## Tareas

| Día | Tarea | Hecho cuando |
| --- | --- | --- |
| Lun 28 | Hola mundos de DuckDB (`count(*)` de un Parquet) y DynamoDB (escribir y leer una fila) con credenciales, entregados a GianMarco; queries del pitch congeladas con CSV | Los dos scripts corren desde el contenedor; cada cifra tiene archivo |
| Mar 29 | `docs/business.md`: plazos por país con link, ahorro con supuestos, outcomes de tiempo y calidad; especificación de vistas chat y consola (campos, estados, botones) | GianMarco construye sin adivinar |
| Mié 30 – Jue 1 | Set ES/PT de 200–300 casos desde `demo_index.csv` según la matriz de Freddy; casos de ataque con Freddy | Válidos contra el schema; cobertura por celda |
| Jue 1 | Doble etiquetado de 40 casos por otra persona; acuerdo reportado | % y kappa en `eval/README.md` |
| Vie 2 – Sáb 3 | `/analytics` (Power BI publicado y embebido, o Recharts sobre `queries/*.csv`); tabla de resultados con la salida del harness | Slide de resultados con números reales |

Viernes debe existir: set completo con doble etiquetado; tablero `/analytics`; texto de negocio listo.

## Dónde encuentro lo mío
`queries/pitch/` · `docs/business.md` · `docs/views/` (spec de chat y consola) · `eval/cases.jsonl`, `eval/README.md` · `apps/web/app/analytics/` (o el embed de Power BI) · `docs/eda/README.md` (índice número → archivo).

## Cambios del lunes en la tarde
- Dos conjuntos: (A) set del clasificador, 300–400 frases ES/PT con intención y slots, 70/15/15 por autor o plantilla; (B) held-out del agente, ~180 casos solo con clientes `heldout` (ES 110 / PT 70; normal 45, ambiguo 30, humano 30, injection 25, unauthorized 15, session_expired 10, tool_failure 15, missing_data 5, late_arrival 5; MX, CO, AR, BR × 4 segmentos). Los ~60 casos de desarrollo usan clientes `dev`.
- El resultado esperado se deriva del registro real; el mensaje es lo único team-generated. Cada caso lleva `set`, `guardrail_ids` y `queue_status` esperados.
- La especificación de la consola incluye la cola de cinco estados, el interruptor de modo supervisado y el panel de notificaciones del cliente.
