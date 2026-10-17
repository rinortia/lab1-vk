-- Original Q3 arithmetic; source is tpch.sfN or iceberg.bench_... .
-- The extra tie breakers make the top 10 reproducible.
SELECT l.orderkey,
       sum(l.extendedprice * (1 - l.discount)) AS revenue,
       o.orderdate, o.shippriority
FROM {{source}}.customer c
JOIN {{source}}.orders o ON c.custkey = o.custkey
JOIN {{source}}.lineitem l ON l.orderkey = o.orderkey
WHERE c.mktsegment = 'BUILDING'
  AND o.orderdate < DATE '1995-03-15'
  AND l.shipdate > DATE '1995-03-15'
GROUP BY l.orderkey, o.orderdate, o.shippriority
ORDER BY revenue DESC, o.orderdate, l.orderkey
LIMIT 10;
