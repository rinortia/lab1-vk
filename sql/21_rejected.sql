CREATE TABLE iceberg.silver.rejected_rows
WITH (format = 'PARQUET', compression_codec = 'ZSTD', format_version = 2)
AS
SELECT 'customer' AS source_table, CAST(custkey AS VARCHAR) AS row_id,
       'invalid key or segment' AS reason
FROM iceberg.bronze.customer
WHERE custkey IS NULL OR custkey <= 0
   OR mktsegment IS NULL OR trim(mktsegment) = ''
UNION ALL
SELECT 'orders', CAST(orderkey AS VARCHAR), 'invalid key, date or priority'
FROM iceberg.bronze.orders
WHERE orderkey IS NULL OR orderkey <= 0 OR custkey IS NULL OR custkey <= 0
   OR orderdate IS NULL OR shippriority IS NULL
UNION ALL
SELECT 'lineitem', concat(CAST(orderkey AS VARCHAR), ':', CAST(linenumber AS VARCHAR)),
       'invalid key, date, price or discount'
FROM iceberg.bronze.lineitem
WHERE orderkey IS NULL OR orderkey <= 0 OR linenumber IS NULL OR linenumber <= 0
   OR shipdate IS NULL OR extendedprice IS NULL OR extendedprice < 0
   OR discount IS NULL OR discount < 0 OR discount > 1;
