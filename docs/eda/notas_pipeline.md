# Notas del pipeline y de la verificación de números del pitch

> Decisiones y lista de lo no verificado, copiadas tal cual del reporte de cierre del 28 sep 2026 (índice de
> `docs/eda/README.md`, verificación en `queries/pitch/`, pipeline en `data/pipeline/`, fixture en
> `data/fixtures/late_arrival/`, tests en `tests/`).

## Decisiones

Las cinco tareas están hechas en este repo; no encontré el repo nuevo en disco.

Cubre las 4 tablas de la idea W3, completas: customers, products, transactions y complaints.

**Decisiones que tomé y que puedes revertir:**
- Las queries del EDA siguen en `docs/eda/queries/`, porque los documentos las citan por esa ruta. En `queries/` solo están las de verificación.
- `.gitignore` ahora deja entrar `data/pipeline/`, `data/fixtures/`, el reporte y el manifest. Eso relaja la regla 4 de `CLAUDE.md` ("data/ no entra a git"), que no toqué; decide tú si la actualizas.
- No creé `eval/`: ninguna de las tareas lo pedía.
- Instalé `pandera[polars]` y `pytest` en el `.venv` y los agregué a `requirements.txt`.

## Lo que no pude verificar

- **Instalación desde un clon limpio.** Corrí sobre un `.venv` existente (Python 3.14) y con el espejo de S3 ya completo, así que nunca se ejercitó la descarga ni la creación del venv.
- **Integridad de `customers.csv` y `products.csv`.** Su ETag es multipart y no es un md5, así que solo comparo el tamaño.
- **Zona horaria de la fecha de carga.** Usé la hora de Lima, como `calidad_datos.md`. Si fuera UTC, las fechas futuras bajarían en 49 customers y 113 products (salió de una query que corrí aparte y no guardé).
- **Dominios de los contratos.** Salen de los valores que se observaron en el EDA, así que pasan por construcción sobre estos datos. Detectan cambios nuevos, pero no validan la regla de negocio.
- **Cómo llegarían los datos tardíos en la práctica.** El fixture asume que una re-entrega sobrescribe el objeto en S3 y que los renombres se declaran como alias. Factored no lo ha dicho (preguntas 6 y 7 de Slack).
- **Supuestos detrás de los números.** Que `Queja` equivalga a disputas es una regla de confianza baja, y no sé si `fraud_score` está disponible en tiempo real. Las queries reproducen los números, pero no validan esos supuestos.
- **"Sin red" en los tests.** El bloqueo cubre los sockets de Python, no la capa C++ de DuckDB. Los tests no usan httpfs e ICU viene enlazado estáticamente, pero no queda forzado.
- **Diff por fila.** Usa el `hash()` de 64 bits de DuckDB, no criptográfico. El sha256 del manifest sí es exacto.
- **Números fuera de la lista.** No revisé el benchmark, los costos, el 32.8% automatizable ni el ahorro: son supuestos o proyecciones.

## Migración a este repo (28 sep 2026)

Lo de arriba se copió tal cual desde el repo del EDA. Esta sección registra lo que se hizo al traer el pipeline aquí.

**Decisiones**
- El repo no existía (ni en disco ni en GitHub): se creó local en `factored-hackathon-2026-contrareloj`, sin remoto
  ni push.
- `contracts/gold_contract.md` no existía: se redactó desde los 4 requisitos del equipo (12 meses de transactions,
  `customer_id` resuelto por join, `is_fraud` solo en `gold_eval/`, `customer_profile` y `transactions_enriched`). Lo
  que no sale de esos 4 puntos está marcado **[propuesta]** en el contrato.
- Ventana de 12 meses: últimos meses completos, 2025-06-01 → 2026-05-31 (elegida por Freddy).
- Se copió, no se movió: el repo del EDA conserva `docs/eda`, `data/pipeline`, `data/fixtures`, `tests` y el Makefile.
- `contracts.py` quedó en `data/pipeline/`, donde lo importa el pipeline; `contracts/` tiene el contrato de gold.
- También se copió `queries/pitch/` (SQL + CSV, sin el runner) para que el índice de `docs/eda/` no quede con enlaces
  rotos. Aquí no se puede regenerar: gold solo tiene 4 tablas y 12 meses. Los enlaces a `docs/pitch/pitch_brief.md`
  quedaron como texto (archivo del repo del EDA).
- Bronze descarga solo las particiones de transactions desde 2025-05-31 (un día antes de la ventana, por el día
  operativo corrido) en adelante: 714 archivos no se descargan.
- El fixture se movió a mayo de 2026 para que caiga en la ventana, y se agregó un evento de 2025-05-31 (WIN-01).
- `.gitattributes` guarda los CSV del fixture byte a byte (BOM + CRLF); con `core.autocrlf=input` git los convertía.
- El reporte no compara con el EDA: `outputs/tables/` no está aquí y transactions cubre otro período. `make pitch` se
  quitó del Makefile.

**Corrida desde un clon limpio**

| Dato | Valor |
|---|---|
| Fecha | 2026-09-28, 20:02:10 → 20:03:10 UTC |
| Procedimiento | `git clone` del commit `4ba3547` a un directorio temporal, `.env` copiado a mano (no está en git), `PIP_NO_CACHE_DIR=1 make setup` |
| Python del venv nuevo | 3.13.11 (duckdb 1.5.6, polars 1.44.2, pandera 0.33.1, pyarrow 25.0.1) |
| **Tiempo total de `make setup`** | **60.27 s** de reloj (`/usr/bin/time -p`) |
| Del total, corrida del pipeline | 49.7 s (el resto: venv, dependencias sin caché, fixture y reporte) |
| Descarga desde S3 | 1,482 objetos, 416.5 MB; 714 omitidos fuera de la ventana |
| Resultado | exit 0; gold v1 con los mismos sha256 que `data/gold/manifest.json` del commit en las 7 tablas; reglas G1–G5 cumplen; `make test`: 6 passed |

Control cruzado: gold tiene 1,477,723 transacciones en la ventana y `gold_eval` 1,372 fraudes, los mismos conteos que
da el dataset completo en el repo del EDA para esa ventana.

**Lo que sigue sin verificar**
- El contrato real del equipo: si existe otro `gold_contract.md`, puede diferir de este borrador, sobre todo en lo
  marcado [propuesta].
- Otra máquina u otra red: el clon limpio corrió en la misma Mac y con la misma conexión a S3. Probado con Python 3.13
  (aquí) y 3.14 (repo del EDA); otras versiones no.
- Estabilidad del sha256 entre versiones de librerías: `requirements.txt` no fija versiones. El mismo contenido de
  `customers` dio otro sha256 con DuckDB 1.5.5 (repo del EDA) que con 1.5.6 (aquí), porque cambia el escritor de
  Parquet. Una instalación futura con otra versión subiría la versión de gold sin cambio de datos.
