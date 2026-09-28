# queries/

## `pitch/`: verificación de los números del pitch
Una query por número (o grupo de números) que usa el pitch, con su salida al lado:

| Query | CSV de salida | Números |
|---|---|---|
| `p01_w3_share_complaints.sql` | `p01_w3_share_complaints.csv` | 36.4% de complaints son W3; 679 casos/mes |
| `p02_fcr_queja_vs_banco.sql` | `p02_fcr_queja_vs_banco.csv` | FCR 43.6% vs 76.6% (con IC95 de Wilson) |
| `p03_seguimiento_queja.sql` | `p03_seguimiento_queja.csv` | 63% requiere seguimiento |
| `p04_duracion_queja_vs_banco.sql` | `p04_duracion_queja_vs_banco.csv` | "AHT 7.2 vs 4.9" (mediana y media, las dos) |
| `p05_nps_queja_vs_banco.sql` | `p05_nps_queja_vs_banco.csv` | NPS −85.3 vs −74.5 |
| `p06_resolucion_dias_w3.sql` | `p06_resolucion_dias_w3.csv` | 16 días de resolución p50 |
| `p07_fraudes_mes.sql` | `p07_fraudes_mes.csv` | 120 fraudes/mes |
| `p08_fraud_score_umbrales.sql` | `p08_fraud_score_umbrales.csv` | precisión y recall por umbral de `fraud_score` |

Copia del repo del EDA (`factored-2026-eda-freddy`, 28 sep 2026). Allá `python -m queries.run` ejecuta todas contra
las vistas del EDA (`scripts/db.py`, caché Parquet de `data/`), reescribe los CSV, arma `pitch_numbers.csv` (valor
citado vs recalculado) y regenera la tabla de `docs/eda/README.md`. Aquí no se pueden regenerar: el gold de este repo
solo tiene 4 tablas y 12 meses de transactions, y los números salen del dataset completo. Cada `.sql` dice en su encabezado qué query y qué tabla del EDA respaldaban el número
originalmente (`docs/eda/queries/` → `outputs/tables/`).

Las queries del EDA están en `docs/eda/queries/`, donde las referencian los documentos.
