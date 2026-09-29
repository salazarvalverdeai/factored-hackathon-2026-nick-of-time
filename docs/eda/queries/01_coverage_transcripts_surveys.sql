-- Respalda: data_quality.md §B8 (cobertura de transcripts y encuestas sobre interacciones) y la decisión 3 del
-- plan (sesgo de has_transcript; aquí por reason_category/canal/tipo; por workflow se mide en la fase 3).
-- Produce: outputs/tables/01_coverage.csv (vía eda/quality.py).
WITH t AS (SELECT interaction_id, count(*) AS n_tr FROM call_transcripts GROUP BY 1),
     s AS (SELECT interaction_id, count(*) AS n_sv FROM satisfaction_surveys WHERE interaction_id IS NOT NULL GROUP BY 1),
     j AS (
        SELECT i.reason_category, i.channel, i.interaction_type, i.has_transcript,
               t.interaction_id IS NOT NULL AS with_transcript_row,
               s.interaction_id IS NOT NULL AS with_survey
        FROM call_center_interactions i
        LEFT JOIN t USING (interaction_id)
        LEFT JOIN s USING (interaction_id)
     )
SELECT CASE WHEN grouping(reason_category) = 0 THEN 'reason_category'
            WHEN grouping(channel) = 0 THEN 'channel'
            WHEN grouping(interaction_type) = 0 THEN 'interaction_type'
            ELSE 'total' END                                         AS dimension,
       coalesce(reason_category, channel, interaction_type, 'total') AS value,
       count(*)                                                      AS n_interactions,
       round(100.0 * avg(has_transcript::INT), 2)                    AS pct_has_transcript_flag,
       round(100.0 * avg(with_transcript_row::INT), 2)               AS pct_with_transcript_row,
       round(100.0 * avg(with_survey::INT), 2)                       AS pct_with_survey
FROM j
GROUP BY GROUPING SETS ((), (reason_category), (channel), (interaction_type))
ORDER BY dimension, n_interactions DESC
