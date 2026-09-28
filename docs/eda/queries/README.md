# Queries que respaldan cada cifra

Convención: `NN_tema_descripcion.sql`, donde NN es la fase (00–06). Cada `.sql` empieza con un comentario que dice
qué cifra de `findings.md` respalda y qué tabla de `outputs/tables/` produce. Se ejecutan con `scripts/db.py`:

    python -c "from scripts.db import get_con; print(get_con().sql(open('docs/eda/queries/02_top_contact_reasons.sql').read()))"

`03_workflow_mapping.csv` (fase 3) es la tabla de reglas valor → workflow, versionada aquí porque es una decisión
de análisis, no un dato.
