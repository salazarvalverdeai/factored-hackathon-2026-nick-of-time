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
