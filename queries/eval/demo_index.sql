-- Candidate transactions for the demo and the agent evaluation cases (spec 09 §7.2, AC-01) [data].
-- One row per candidate: an approved card transaction on a product the customer owns, with no qc flag raised, in the
-- 90 days before DEMO_TODAY (2026-06-01, ADR 0020). Reads data/gold/ only; the evaluation labels are never read (AC-08).
-- Run from the repo root after `make setup`: python -m eval.demo_index  (rewrites eval/demo_index.csv)
--
-- Split (§7.1): the first 8 hex digits of md5(customer_id), as an integer, mod 10 -> 7 dev, 8-9 heldout. Train
-- customers (0-6) are left out: no demo customer and no evaluation case uses them.
-- Zones and amount tiers copy contracts/policies.yaml (zones, amount_gate.by_country); tests/test_spec09_demo_index.py
-- recomputes both with the policy engine on every row of the CSV.
-- Sample: every high- and medium-zone candidate is kept (they are scarce). The human zone keeps 6 rows per
-- country x split x product x score band (null, below 30) x segment, in md5(seed || transaction_id) order, so a
-- re-run on the same gold gives the same file.
WITH gate(country, currency, usd_rate, low, high) AS (
    VALUES ('MX', 'MXN', 18.0, 18000, 90000),
           ('CO', 'COP', 4000, 4000000, 20000000),
           ('AR', 'ARS', 350, 350000, 1750000)
),
cards AS (                                   -- every card transaction: the neighbours counted by n_candidates_7d
    SELECT *,
           CASE customer_country WHEN 'México' THEN 'MX' WHEN 'Colombia' THEN 'CO' WHEN 'Argentina' THEN 'AR' END AS country,
           CASE product_type WHEN 'Tarjeta Débito' THEN 'debit' WHEN 'Tarjeta Crédito' THEN 'credit' END AS card
    FROM read_parquet('data/gold/transactions_enriched.parquet')
    WHERE product_type IN ('Tarjeta Débito', 'Tarjeta Crédito')
),
candidates AS (
    SELECT c.*,
           CASE ('0x' || substr(md5(c.customer_id), 1, 8))::BIGINT % 10
                WHEN 7 THEN 'dev' WHEN 8 THEN 'heldout' WHEN 9 THEN 'heldout' END AS split,
           CASE WHEN c.fraud_score >= 50 THEN 'high' WHEN c.fraud_score >= 30 THEN 'medium' ELSE 'human' END AS zone,
           c.amount * CASE WHEN c.currency = 'USD' THEN g.usd_rate WHEN c.currency = g.currency THEN 1 END AS amount_local,
           g.low, g.high
    FROM cards c
    JOIN gate g USING (country)
    WHERE c.transaction_status = 'Approved'
      AND c.transaction_date >= TIMESTAMP '2026-03-03 00:00:00'
      AND c.transaction_date < TIMESTAMP '2026-06-01 00:00:00'
      AND NOT (c.qc_customer_orphan OR c.qc_product_orphan OR c.qc_product_other_customer OR c.qc_before_product_open
               OR c.qc_future_date OR c.qc_late_arrival OR c.qc_label_normalized)
),
ranked AS (
    SELECT *,
           row_number() OVER (
               PARTITION BY country, split, card, zone, fraud_score IS NULL, customer_segment
               ORDER BY md5('demo-index-v1' || transaction_id)) AS pick
    FROM candidates
    WHERE split IS NOT NULL AND amount_local IS NOT NULL
),
kept AS (
    SELECT * FROM ranked WHERE zone <> 'human' OR pick <= 6
)
SELECT k.customer_id,
       k.country,
       k.customer_segment AS segment,
       k.split,
       k.product_id,
       k.card AS product_type,
       k.transaction_id,
       strftime(k.transaction_date, '%Y-%m-%d %H:%M:%S') AS transaction_date,
       round(k.amount, 2) AS amount,
       k.currency,
       k.merchant_name,
       k.fraud_score,
       k.zone,
       CASE WHEN k.amount_local <= k.low THEN 'low' WHEN k.amount_local <= k.high THEN 'mid' ELSE 'above_high' END AS amount_tier,
       (SELECT count(*) FROM cards n
        WHERE n.customer_id = k.customer_id
          AND n.transaction_date BETWEEN k.transaction_date - INTERVAL 7 DAY AND k.transaction_date + INTERVAL 7 DAY
       ) AS n_candidates_7d                  -- the customer's card transactions within 7 days either side, itself included
FROM kept k
ORDER BY k.country, k.split, k.zone, k.card, k.transaction_id;
