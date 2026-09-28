-- Respalda: calidad_datos.md §B3 (huérfanos en call_center_interactions.mentioned_products, lista separada por comas).
-- Produce: fila 'call_center_interactions.mentioned_products' de outputs/tables/01_fk_orphans.csv.
-- Denominador: IDs de producto mencionados (tras separar la lista), no interacciones.
WITH m AS (
    SELECT trim(unnest(string_split(mentioned_products, ','))) AS product_id
    FROM call_center_interactions
    WHERE mentioned_products IS NOT NULL
)
SELECT count(*)                                                        AS n_with_fk,
       (SELECT count(*) FROM call_center_interactions WHERE mentioned_products IS NULL) AS n_fk_null,
       count(*) FILTER (WHERE p.product_id IS NULL)                    AS n_orphans
FROM m
LEFT JOIN (SELECT DISTINCT product_id FROM products) p USING (product_id)
