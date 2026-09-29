-- Respalda: data_quality.md §B5 (amount_usd coherente con el tipo de cambio del día).
-- Produce: outputs/tables/01_fx_consistency.csv (vía eda/quality.py).
-- Desvío = |amount_usd / amount - exchange_rate| / exchange_rate, con la tasa currency->USD del mismo día.
WITH fx AS (
    SELECT date, source_currency, exchange_rate
    FROM daily_exchange_rates WHERE target_currency = 'USD'
    QUALIFY row_number() OVER (PARTITION BY date, source_currency ORDER BY exchange_rate) = 1
),
j AS (
    SELECT x.currency, x.amount, x.amount_usd, fx.exchange_rate,
           abs(x.amount_usd / x.amount - fx.exchange_rate) / fx.exchange_rate AS rel_dev
    FROM transactions x
    LEFT JOIN fx ON fx.date = x.transaction_date::DATE AND fx.source_currency = x.currency
    WHERE x.currency IN ('COP', 'ARS') AND x.amount_usd IS NOT NULL AND x.amount > 0
)
SELECT currency, count(*) AS n_with_usd, count(exchange_rate) AS n_with_rate,
       round(quantile_cont(rel_dev, 0.5), 4) AS rel_dev_p50, round(quantile_cont(rel_dev, 0.95), 4) AS rel_dev_p95,
       count(*) FILTER (WHERE rel_dev > 0.05) AS n_dev_gt_5pct
FROM j GROUP BY 1 ORDER BY 1
