# Fixture `late_arrival` (datos sintéticos de prueba)

> **FIXTURE: ninguna fila sale del dataset LATAM Bank.** Los IDs llevan el prefijo `FX-`, los nombres dicen
> `FIXTURE` y el pipeline marca la fuente como `fixture` en `manifest.json`. Se genera con
> `python -m data.fixtures.late_arrival.make_fixture` (determinista) y los CSV se versionan tal cual.

## Para qué existe
El diccionario del dataset anuncia llegadas tardías y evolución de schema, pero no están en los datos: el rezago
`process_date − fecha del evento` es 0 o −1 y hay una sola firma de header por tabla (`docs/eda/data_quality.md`
§B4, §B6). Este fixture tiene la misma forma que el bucket (particiones `year=/month=/day=`, BOM, CRLF) y sirve para
demostrar cómo el pipeline maneja una segunda entrega.

## Entregas
Cada entrega es una carpeta con claves estilo S3; `fixture.json` declara su fecha de entrega (la "fecha de carga" que
usa el check de fechas futuras). La entrega 2 se superpone a la 1: una clave repetida reemplaza al archivo anterior, como
una re-entrega que sobrescribe el objeto en S3.

| Entrega | Archivo | Qué prueba |
|---|---|---|
| `delivery_1` | `customers/customers.csv` | FX-CLI-004 con `last_updated` en 2027 (fecha futura) |
| `delivery_1` | `products/products.csv` | FX-PRD-002 abre después de FX-TRX-0002; FX-PRD-006 con `last_updated` futuro |
| `delivery_1` | `transactions/…/day=15/…` | `Mexico` (FX-TRX-0003), antes de la apertura (0002), `customer_id` que no es el dueño del producto (0005: gold lo resuelve al dueño), evento de 2025-05-31 fuera de la ventana de 12 meses (0015: queda en silver, no en gold) |
| `delivery_1` | `transactions/…/day=16/…` | duplicado exacto de FX-TRX-0008, `Mexico` (0007), producto inexistente (0009) |
| `delivery_1` | `complaints/…/day=16/…` | producto de otro cliente (FX-CMP-002), producto inexistente (003), sin `category` (004) |
| `delivery_2` | `customers/customers.csv` | re-entrega del snapshot: FX-CLI-002 cambia de segmento, alta de FX-CLI-006 |
| `delivery_2` | `transactions/…/day=16/…` | re-entrega de la partición: sin el duplicado y con FX-TRX-0010 que faltaba |
| `delivery_2` | `transactions/…/day=20/…` | **llegadas tardías** (eventos del 12, 13 y 14 con `process_date` del 20; corrección de 0008 del 16) y **cambio de schema**: `transaction_country` llega como `txn_country` y aparece `merchant_mcc` |

Las fechas caen en mayo de 2026, dentro de la ventana de `contracts/gold_contract.md`. Los conteos que debe producir
el pipeline en cada entrega (incluidas las tablas derivadas y `gold_eval/`) están en `fixture.json` → `expected`. Los verifican
`tests/test_fixture_late_arrival.py` y la sección 7 de `data/quality_report.md`.

## Cómo se corre
```bash
python -m data.pipeline fixture   # delivery_1 y luego delivery_1 + delivery_2 en data/_fixture_run/ (gitignored)
python -m data.pipeline report    # la sección 7 del reporte muestra qué cambió entre las dos
```
