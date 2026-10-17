CREATE TABLE iceberg.gold.q3_shipping_priority
WITH (format = 'PARQUET', compression_codec = 'ZSTD', format_version = 2)
AS
SELECT orderkey, sum(net_revenue) AS revenue, orderdate, shippriority
FROM iceberg.silver.q3_lines
GROUP BY orderkey, orderdate, shippriority
ORDER BY revenue DESC, orderdate, orderkey
LIMIT 10;
