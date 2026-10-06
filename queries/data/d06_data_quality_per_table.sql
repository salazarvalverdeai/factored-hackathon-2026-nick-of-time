-- Data quality per gold table: rows, the null rate of key columns and how many rows carry each qc_* flag. Backs the
-- profile table of /data (spec 12 AC-03) [data]. Runs on this repo's gold (views customers, products, transactions,
-- complaints): see run.py. Aggregate only: counts per column name, never values; personal columns are not profiled.
-- kind: rows = rows of the table; null = rows where the key column is null; flag = rows with qc_* = true (flags mark
-- rows, nothing is deleted: contracts/gold_contract.md). numerator/denominator are the counts behind pct.
SELECT 'customers' AS table_name, 'rows' AS kind, '*' AS name, count(*) AS numerator, count(*) AS denominator FROM customers
UNION ALL
SELECT 'customers', 'null', 'country', count(*) FILTER (WHERE country IS NULL), count(*) FROM customers
UNION ALL
SELECT 'customers', 'null', 'segment', count(*) FILTER (WHERE segment IS NULL), count(*) FROM customers
UNION ALL
SELECT 'customers', 'null', 'customer_status', count(*) FILTER (WHERE customer_status IS NULL), count(*) FROM customers
UNION ALL
SELECT 'customers', 'null', 'registration_date', count(*) FILTER (WHERE registration_date IS NULL), count(*) FROM customers
UNION ALL
SELECT 'customers', 'flag', 'qc_future_last_updated', count(*) FILTER (WHERE qc_future_last_updated), count(*) FROM customers
UNION ALL
SELECT 'customers', 'flag', 'qc_label_normalized', count(*) FILTER (WHERE qc_label_normalized), count(*) FROM customers
UNION ALL
SELECT 'products' AS table_name, 'rows' AS kind, '*' AS name, count(*) AS numerator, count(*) AS denominator FROM products
UNION ALL
SELECT 'products', 'null', 'customer_id', count(*) FILTER (WHERE customer_id IS NULL), count(*) FROM products
UNION ALL
SELECT 'products', 'null', 'product_type', count(*) FILTER (WHERE product_type IS NULL), count(*) FROM products
UNION ALL
SELECT 'products', 'null', 'product_status', count(*) FILTER (WHERE product_status IS NULL), count(*) FROM products
UNION ALL
SELECT 'products', 'null', 'opening_date', count(*) FILTER (WHERE opening_date IS NULL), count(*) FROM products
UNION ALL
SELECT 'products', 'null', 'credit_limit', count(*) FILTER (WHERE credit_limit IS NULL), count(*) FROM products
UNION ALL
SELECT 'products', 'flag', 'qc_customer_orphan', count(*) FILTER (WHERE qc_customer_orphan), count(*) FROM products
UNION ALL
SELECT 'products', 'flag', 'qc_future_last_updated', count(*) FILTER (WHERE qc_future_last_updated), count(*) FROM products
UNION ALL
SELECT 'transactions' AS table_name, 'rows' AS kind, '*' AS name, count(*) AS numerator, count(*) AS denominator FROM transactions
UNION ALL
SELECT 'transactions', 'null', 'customer_id', count(*) FILTER (WHERE customer_id IS NULL), count(*) FROM transactions
UNION ALL
SELECT 'transactions', 'null', 'product_id', count(*) FILTER (WHERE product_id IS NULL), count(*) FROM transactions
UNION ALL
SELECT 'transactions', 'null', 'amount', count(*) FILTER (WHERE amount IS NULL), count(*) FROM transactions
UNION ALL
SELECT 'transactions', 'null', 'transaction_status', count(*) FILTER (WHERE transaction_status IS NULL), count(*) FROM transactions
UNION ALL
SELECT 'transactions', 'null', 'merchant_category', count(*) FILTER (WHERE merchant_category IS NULL), count(*) FROM transactions
UNION ALL
SELECT 'transactions', 'null', 'fraud_score', count(*) FILTER (WHERE fraud_score IS NULL), count(*) FROM transactions
UNION ALL
SELECT 'transactions', 'flag', 'qc_customer_orphan', count(*) FILTER (WHERE qc_customer_orphan), count(*) FROM transactions
UNION ALL
SELECT 'transactions', 'flag', 'qc_product_orphan', count(*) FILTER (WHERE qc_product_orphan), count(*) FROM transactions
UNION ALL
SELECT 'transactions', 'flag', 'qc_product_other_customer', count(*) FILTER (WHERE qc_product_other_customer), count(*) FROM transactions
UNION ALL
SELECT 'transactions', 'flag', 'qc_before_product_open', count(*) FILTER (WHERE qc_before_product_open), count(*) FROM transactions
UNION ALL
SELECT 'transactions', 'flag', 'qc_future_date', count(*) FILTER (WHERE qc_future_date), count(*) FROM transactions
UNION ALL
SELECT 'transactions', 'flag', 'qc_late_arrival', count(*) FILTER (WHERE qc_late_arrival), count(*) FROM transactions
UNION ALL
SELECT 'transactions', 'flag', 'qc_label_normalized', count(*) FILTER (WHERE qc_label_normalized), count(*) FROM transactions
UNION ALL
SELECT 'complaints' AS table_name, 'rows' AS kind, '*' AS name, count(*) AS numerator, count(*) AS denominator FROM complaints
UNION ALL
SELECT 'complaints', 'null', 'customer_id', count(*) FILTER (WHERE customer_id IS NULL), count(*) FROM complaints
UNION ALL
SELECT 'complaints', 'null', 'category', count(*) FILTER (WHERE category IS NULL), count(*) FROM complaints
UNION ALL
SELECT 'complaints', 'null', 'case_type', count(*) FILTER (WHERE case_type IS NULL), count(*) FROM complaints
UNION ALL
SELECT 'complaints', 'null', 'claimed_amount', count(*) FILTER (WHERE claimed_amount IS NULL), count(*) FROM complaints
UNION ALL
SELECT 'complaints', 'null', 'affected_product_id', count(*) FILTER (WHERE affected_product_id IS NULL), count(*) FROM complaints
UNION ALL
SELECT 'complaints', 'null', 'resolution_date', count(*) FILTER (WHERE resolution_date IS NULL), count(*) FROM complaints
UNION ALL
SELECT 'complaints', 'flag', 'qc_customer_orphan', count(*) FILTER (WHERE qc_customer_orphan), count(*) FROM complaints
UNION ALL
SELECT 'complaints', 'flag', 'qc_affected_product_orphan', count(*) FILTER (WHERE qc_affected_product_orphan), count(*) FROM complaints
UNION ALL
SELECT 'complaints', 'flag', 'qc_affected_product_other_customer', count(*) FILTER (WHERE qc_affected_product_other_customer), count(*) FROM complaints
UNION ALL
SELECT 'complaints', 'flag', 'qc_future_date', count(*) FILTER (WHERE qc_future_date), count(*) FROM complaints
UNION ALL
SELECT 'complaints', 'flag', 'qc_late_arrival', count(*) FILTER (WHERE qc_late_arrival), count(*) FROM complaints
