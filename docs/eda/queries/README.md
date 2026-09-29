# Queries behind each figure

Convention: `NN_topic_description.sql`, where NN is the phase (00–06). Each `.sql` starts with a comment that says
which `findings.md` figure it supports and which `outputs/tables/` table it produces. They are run with `scripts/db.py`:

    python -c "from scripts.db import get_con; print(get_con().sql(open('docs/eda/queries/02_top_contact_reasons.sql').read()))"

`03_workflow_mapping.csv` (phase 3) is the value → workflow rule table, versioned here because it is an analysis
decision, not data.
