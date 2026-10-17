-- Run in Superset SQL Lab, database Lakehouse Trino.
SELECT count(*) AS bronze_lineitems, min(shipdate) AS first_shipdate,
       max(shipdate) AS last_shipdate
FROM iceberg.bronze.lineitem;

SELECT orderkey, linenumber, extendedprice, discount, shipdate
FROM iceberg.bronze.lineitem
ORDER BY orderkey, linenumber
LIMIT 10;

SELECT orderkey, revenue, orderdate, shippriority
FROM iceberg.gold.q3_shipping_priority
ORDER BY revenue DESC, orderdate, orderkey;
