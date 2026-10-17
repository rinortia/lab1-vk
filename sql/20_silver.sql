CREATE TABLE iceberg.silver.q3_lines
WITH (format = 'PARQUET', compression_codec = 'ZSTD', format_version = 2)
AS
WITH clean_customer AS (
    SELECT custkey, upper(trim(mktsegment)) AS mktsegment
    FROM iceberg.bronze.customer
    WHERE custkey > 0 AND mktsegment IS NOT NULL AND trim(mktsegment) <> ''
), clean_orders AS (
    SELECT orderkey, custkey, orderdate, shippriority
    FROM iceberg.bronze.orders
    WHERE orderkey > 0 AND custkey > 0
      AND orderdate IS NOT NULL AND shippriority IS NOT NULL
), clean_lineitem AS (
    SELECT orderkey, linenumber, shipdate,
           CAST(extendedprice AS DECIMAL(15, 2)) AS extendedprice,
           CAST(discount AS DECIMAL(4, 2)) AS discount
    FROM iceberg.bronze.lineitem
    WHERE orderkey > 0 AND linenumber > 0 AND shipdate IS NOT NULL
      AND extendedprice >= 0 AND discount BETWEEN 0 AND 1
)
SELECT l.orderkey, l.linenumber, c.custkey, c.mktsegment,
       o.orderdate, l.shipdate, o.shippriority,
       l.extendedprice, l.discount,
       l.extendedprice * (DECIMAL '1.00' - l.discount) AS net_revenue
FROM clean_customer c
JOIN clean_orders o ON c.custkey = o.custkey
JOIN clean_lineitem l ON l.orderkey = o.orderkey
WHERE c.mktsegment = 'BUILDING'
  AND o.orderdate < DATE '1995-03-15'
  AND l.shipdate > DATE '1995-03-15';
